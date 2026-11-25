"""Model profiles, the failover pool and its breaker.

Each agent role resolves to a chain of profiles for every model call:
  - pinned role (System → LLM → Roles): that profile only, unless "also fall back when a
    pinned profile fails" is on;
  - otherwise the active profile, followed — when the pool is enabled — by every other
    usable profile not excluded from the pool, highest priority first, with equal
    priorities taking turns at the front.
Profiles in a breaker cooldown, or whose context window can't hold the request, are
skipped. With no profiles at all, the implicit environment profile (ANTHROPIC_API_KEY and
the per-role model names) is used, which is how ZeaLead behaved before profiles.

Breaker: transient failures (429, 5xx, transport) trip a profile after N in a row;
deterministic ones (401, 402, 403, 404) trip it at once. Cooldown 1 min → 5 min → 30 min
(or a fixed interval). State lives in the database, so it survives restarts and is shared
by the console and the CLI.
"""

from __future__ import annotations

import itertools
import json
import time

from .providers import LAYERS, Profile, ProviderError, normalize_policy, parse_headers, rule_attempts
from .secretbox import SecretBox
from .store import Store

BACKOFF = (60, 300, 1800)
ROLE_PIN = {"decomposer": "planner_profile", "planner": "planner_profile", "worker": "worker_profile",
            "writer": "writer_profile"}
_rr = itertools.count()
_boxes: dict[str, SecretBox] = {}


def box_for(store: Store) -> SecretBox:
    b = _boxes.get(store.path)
    if b is None:
        b = _boxes[store.path] = SecretBox.for_db(store.path)
    return b


def flag(settings: dict, key: str) -> bool:
    return str(settings.get(key) or "0").strip().lower() in ("1", "true", "on", "yes")


def retry_policy(settings: dict) -> dict:
    try:
        return normalize_policy(json.loads(settings.get("llm_retry") or "{}"))
    except (ValueError, TypeError):
        return normalize_policy({})


def profile_from_row(row: dict, box: SecretBox) -> Profile:
    try:
        key = box.open(row["api_key"])
    except Exception:
        key = ""                    # undecryptable (keys dir replaced): treated as no key
    try:
        headers = parse_headers(box.open(row["custom_headers"])) if row["custom_headers"] else {}
    except Exception:
        headers = {}
    try:
        retry = json.loads(row.get("retry") or "{}")
    except ValueError:
        retry = {}
    return Profile(
        id=row["id"], name=row["name"], format=row["format"], model=row["model"], base_url=row["base_url"],
        proxy=row["proxy"], api_key=key, custom_headers=headers, rate_per_second=row["rate_per_second"],
        rate_per_minute=row["rate_per_minute"], context_window_k=row["context_window_k"],
        thinking_type=row["thinking_type"], reasoning_effort=row["reasoning_effort"], priority=row["priority"],
        pool_exclude=bool(row["pool_exclude"]), streaming=bool(row["streaming"]), max_tokens=row["max_tokens"],
        max_tokens_field=row["max_tokens_field"], session_header_key=row["session_header_key"],
        user_agent=row["user_agent"], retry=retry, is_default=bool(row["is_default"]),
    )


def env_profile(model: str) -> Profile:
    return Profile(id=0, name="Environment (ANTHROPIC_API_KEY)", format="anthropic", model=model,
                   thinking_type="adaptive", reasoning_effort="role", streaming=False, is_default=True, env_key=True)


# --------------------------------------------------------------------------- breaker
class Health:
    def __init__(self, store: Store, settings: dict):
        self.store = store
        rule = retry_policy(settings).get("breaker") or {}
        self.soft_trip = rule_attempts(rule, "breaker")           # 0 = transient failures never trip
        self.cooldown = (rule.get("interval_ms") or 0) / 1000

    def _cool(self, trips: int) -> float:
        return self.cooldown if self.cooldown > 0 else BACKOFF[min(trips, len(BACKOFF)) - 1]

    def snapshot(self) -> dict[int, dict]:
        return self.store.llm_health()

    def is_open(self, pid: int, snap: dict | None = None) -> bool:
        h = (snap if snap is not None else self.snapshot()).get(pid)
        return bool(h and h["open_until"] > time.time())

    def passed(self, pid: int) -> None:
        h = self.snapshot().get(pid)
        if h and (h["fails"] or h["open_until"] > 0):
            self.store.clear_llm_health(pid)

    def failed(self, pid: int, err: ProviderError) -> bool:
        """Record a failed call after the inner retries; returns True when it tripped the breaker."""
        if not counts_against(err):
            return False
        h = self.snapshot().get(pid) or {"fails": 0, "trips": 0, "open_until": 0}
        fails = h["fails"] + 1
        trips = h["trips"]
        open_until = h["open_until"]
        tripped = is_hard(err) or (self.soft_trip > 0 and fails >= self.soft_trip)
        if tripped:
            trips += 1
            open_until = time.time() + self._cool(trips)
        self.store.put_llm_health(pid, fails, trips, open_until, str(err))
        return tripped


def is_hard(err: ProviderError) -> bool:
    return err.status in (401, 402, 403, 404)


def counts_against(err: ProviderError) -> bool:
    """400-class request errors fail the same on every profile; they say nothing about this one."""
    return err.status == 0 or err.status in (401, 402, 403, 404, 408, 429) or err.status >= 500


def should_failover(err: ProviderError) -> bool:
    return counts_against(err)


# --------------------------------------------------------------------------- router
class Router:
    """Builds the profile chain for one call from the current database state."""

    def __init__(self, store: Store):
        self.store = store

    def settings(self) -> dict:
        return self.store.get_settings()

    def profiles(self) -> list[Profile]:
        box = box_for(self.store)
        return [profile_from_row(r, box) for r in self.store.llm_profiles()]

    def active(self, profiles: list[Profile]) -> Profile | None:
        return next((p for p in profiles if p.is_default), profiles[0] if profiles else None)

    def chain(self, role: str, role_model: str, est_tokens: int = 0) -> tuple[list[Profile], dict]:
        s = self.settings()
        profiles = self.profiles()
        meta = {"pool": flag(s, "llm_pool_enabled"), "policy": retry_policy(s), "settings": s}
        if not profiles:
            return [env_profile(role_model)], meta
        pin_id = (s.get(ROLE_PIN.get(role, "")) or "").strip()
        pinned = next((p for p in profiles if pin_id and str(p.id) == pin_id), None)
        head = pinned or self.active(profiles)
        if not meta["pool"] or (pinned and not flag(s, "llm_pool_bind_fallback")):
            return [head], meta
        return order(head, profiles, Health(self.store, s).snapshot(), est_tokens, next(_rr)), meta

    def pool_status(self) -> dict:
        s = self.settings()
        profiles = self.profiles()
        snap = self.store.llm_health()
        active = self.active(profiles)
        now = time.time()
        soft = rule_attempts(retry_policy(s).get("breaker"), "breaker")
        rest = sorted((p for p in profiles if not active or p.id != active.id), key=lambda p: (-p.priority, p.id))
        out = []
        for p in ([active] if active else []) + rest:
            h = snap.get(p.id) or {}
            open_until = h.get("open_until", 0)
            state = "tripped" if open_until > now else ("degraded" if h.get("fails") else "ok")
            out.append({"profile_id": str(p.id), "name": p.name, "model": p.model, "format": p.format,
                        "active": bool(active and p.id == active.id), "excluded": p.pool_exclude or not p.usable,
                        "usable": p.usable, "priority": p.priority, "state": state, "fails": h.get("fails", 0),
                        "trips": h.get("trips", 0), "cooldown_secs": max(0, int(open_until - now)),
                        "last_error": h.get("last_error", "")})
        return {"enabled": flag(s, "llm_pool_enabled"), "bind_fallback": flag(s, "llm_pool_bind_fallback"),
                "soft_trip": soft, "chain": out}


def order(head: Profile, profiles: list[Profile], snap: dict, est_tokens: int, rr: int) -> list[Profile]:
    now = time.time()

    def ok(p: Profile) -> bool:
        h = snap.get(p.id)
        if h and h["open_until"] > now:
            return False
        return not (est_tokens and est_tokens > p.window_tokens)

    rest = [p for p in profiles if p.id != head.id and not p.pool_exclude and p.usable]
    rest.sort(key=lambda p: (-p.priority, p.id))
    # rotate each equal-priority group so duplicate keys share the load
    rotated: list[Profile] = []
    for _, grp in itertools.groupby(rest, key=lambda p: p.priority):
        g = list(grp)
        k = rr % len(g)
        rotated += g[k:] + g[:k]
    chain = [p for p in [head] + rotated if ok(p)]
    return chain or [head]


__all__ = ["Router", "Health", "order", "should_failover", "is_hard", "env_profile", "profile_from_row", "box_for",
           "retry_policy", "flag", "LAYERS"]
