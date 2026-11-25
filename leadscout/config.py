"""Settings from the environment plus the campaign brief file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    db_path: str
    planner_model: str
    worker_model: str
    planner_effort: str
    worker_effort: str
    workers: int
    budget_tokens: int          # whole campaign (planner + workers); 0 = unlimited
    intent_max_turns: int       # one worker run
    planner_max_turns: int
    heartbeat_seconds: int
    stagnation_rounds: int      # planner rounds without a new lead before stopping
    noise_profile: str
    writer_model: str = "claude-opus-5-5"   # drafts the personalised message for each lead
    writer_effort: str = "low"
    auto_draft: int = 1                     # 1 = draft messages for every new lead while the task runs
    env: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        _load_dotenv()
        e = os.environ
        return cls(
            db_path=e.get("LEADSCOUT_DB", "leadscout.db"),
            planner_model=e.get("LEADSCOUT_PLANNER_MODEL", "claude-opus-5-5"),
            worker_model=e.get("LEADSCOUT_WORKER_MODEL", "claude-opus-5-5"),
            planner_effort=e.get("LEADSCOUT_PLANNER_EFFORT", "high"),
            worker_effort=e.get("LEADSCOUT_WORKER_EFFORT", "medium"),
            workers=_int("LEADSCOUT_WORKERS", 3),
            budget_tokens=_int("LEADSCOUT_BUDGET_TOKENS", 3_000_000),
            intent_max_turns=_int("LEADSCOUT_INTENT_MAX_TURNS", 25),
            planner_max_turns=_int("LEADSCOUT_PLANNER_MAX_TURNS", 12),
            heartbeat_seconds=_int("LEADSCOUT_HEARTBEAT_SECONDS", 90),
            stagnation_rounds=_int("LEADSCOUT_STAGNATION_ROUNDS", 10),
            noise_profile=e.get("LEADSCOUT_NOISE_PROFILE", "balanced"),
            writer_model=e.get("LEADSCOUT_WRITER_MODEL") or e.get("LEADSCOUT_WORKER_MODEL", "claude-opus-5-5"),
            writer_effort=e.get("LEADSCOUT_WRITER_EFFORT", "low"),
            auto_draft=1 if _int("LEADSCOUT_AUTO_DRAFT", 1) else 0,
            env=dict(e),
        )


    def with_overrides(self, overrides: dict[str, str]) -> "Settings":
        """Apply console-edited, non-secret settings on top of the environment."""
        import dataclasses
        s = dataclasses.replace(self, env=dict(self.env))
        for key, (attr, kind) in EDITABLE.items():
            if key in overrides and overrides[key] != "":
                try:
                    setattr(s, attr, kind(overrides[key]))
                except ValueError:
                    pass
        return s


# Settings the console may edit. API keys are deliberately absent: secrets stay
# in the environment / .env and are only reported as configured or missing.
EDITABLE: dict[str, tuple[str, type]] = {
    "planner_model": ("planner_model", str),
    "worker_model": ("worker_model", str),
    "planner_effort": ("planner_effort", str),
    "worker_effort": ("worker_effort", str),
    "workers": ("workers", int),
    "budget_tokens": ("budget_tokens", int),
    "intent_max_turns": ("intent_max_turns", int),
    "planner_max_turns": ("planner_max_turns", int),
    "heartbeat_seconds": ("heartbeat_seconds", int),
    "stagnation_rounds": ("stagnation_rounds", int),
    "noise_profile": ("noise_profile", str),
    "writer_model": ("writer_model", str),
    "writer_effort": ("writer_effort", str),
    "auto_draft": ("auto_draft", int),
}


def normalize_brief(data: dict) -> dict:
    missing = [k for k in ("product", "description", "ideal_customer") if not str(data.get(k) or "").strip()]
    if missing:
        raise ValueError(f"brief is missing required fields: {', '.join(missing)}")
    data = dict(data)
    data.setdefault("name", data["product"])
    if not data.get("name"):
        data["name"] = data["product"]
    data["recency_days"] = int(data.get("recency_days") or 30)
    data["target_leads"] = int(data.get("target_leads") or 30)
    for k in ("pain_points", "competitors", "keywords", "platforms", "exclude_platforms"):
        v = data.get(k) or []
        if isinstance(v, str):
            v = [x.strip() for x in v.replace("\n", ",").split(",") if x.strip()]
        data[k] = list(v)
    o = data.get("outreach")
    if o is not None and not isinstance(o, dict):
        raise ValueError("outreach must be a mapping with sender / tone / offer")
    if o:
        data["outreach"] = {k: str(o[k]).strip()[:300] for k in ("sender", "tone", "offer") if str(o.get(k) or "").strip()}
    return data


BRIEF_FIELDS = {
    "name": "Campaign name",
    "product": "Product name",
    "description": "What the product does, in a paragraph",
    "url": "Product URL",
    "ideal_customer": "Who buys it (role, company size, industry)",
    "pain_points": "Problems the product solves (list)",
    "competitors": "Competitor product names (list)",
    "keywords": "Seed phrases people use when they have the problem (list)",
    "platforms": "Allowed platforms (list); empty = every configured one",
    "exclude_platforms": "Platforms never to use (list)",
    "recency_days": "Only posts newer than this many days",
    "regions_languages": "Optional geographic or language focus",
    "objective": "Free-text goal, e.g. 'find 40 warm or hot leads, at least 10 hot'",
    "target_leads": "Fallback lead count when the objective names none",
    "notes": "Free-text rules (e.g. 'no students', 'B2B only', 'skip r/entrepreneur')",
    "outreach": "Optional: sender (who signs), tone, offer — used when drafting each lead's messages",
}


def load_brief(path: str) -> dict:
    data = yaml.safe_load(Path(path).read_text()) or {}
    try:
        return normalize_brief(data)
    except ValueError as e:
        raise SystemExit(str(e)) from None
