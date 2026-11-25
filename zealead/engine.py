"""Event-driven engine: planner loop + N worker loops over the shared graph.

  graph change ──debounce──▶ planner round ──add_intent──▶ frontier
        ▲                                                   │ claim
        └──── write-back (facts / leads) ◀── worker ◀───────┘

Stops when every goal is proven, the token budget is spent, the frontier stays
empty while the planner dispatches nothing (stall), or too many rounds pass
without a new lead (stagnation).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from .agents import decompose, plan_round, run_worker
from .config import Settings
from .connectors import available
from .connectors.base import Ctx
from .connectors.web import DOMAIN_PLATFORM
from .governor import Governor
from .llm import LLM
from .outreach import draft_for_lead, draft_pending
from .store import Store

log = logging.getLogger("zealead")
DEBOUNCE = 0.8


class Engine:
    def __init__(self, settings: Settings, store: Store):
        self.s = settings
        self.store = store
        self.llm = LLM(store, settings.budget_tokens)
        self.gov = Governor(settings.noise_profile)
        self._wake = asyncio.Event()
        self._work = asyncio.Event()
        self._done = asyncio.Event()
        self._triggers: list[dict] = []
        self.end_reason = ""

    def notify(self, trigger: dict | None = None) -> None:
        if trigger:
            self._triggers.append(trigger)
        self._wake.set()

    def _finish(self, cid: int, status: str, reason: str) -> None:
        if not self._done.is_set():
            self.end_reason = reason
            self.store.set_campaign_status(cid, status, reason)
            self.store.log(cid, "system", "text", f"campaign {status}: {reason}")
            log.info("campaign %s %s: %s", cid, status, reason)
            self._done.set()
            self._work.set()

    def stop(self, cid: int, reason: str = "paused by operator") -> None:
        """Pause from outside (console or signal). Running intents return to the frontier."""
        self._finish(cid, "paused", reason)

    async def _heartbeat(self, cid: int, runner: str) -> None:
        while not self._done.is_set():
            self.store.heartbeat(cid, runner)
            await asyncio.sleep(10)

    # ------------------------------------------------------------------ run
    async def run(self, cid: int, runner: str = "cli") -> str:
        camp = self.store.campaign(cid)
        brief = camp["brief"]
        connectors, off = available(self.s.env, brief)
        self.connectors = connectors
        self.platforms_on = [c.platform for c in connectors]
        self.platforms_off = off
        if not connectors:
            raise RuntimeError("No platform connectors are enabled. Add platform keys to .env (see .env.example).")
        other = self.store.runner_alive(cid)
        if other:
            raise RuntimeError(f"campaign #{cid} is already running in another process ({other})")
        self.store.heartbeat(cid, runner)

        known = set(DOMAIN_PLATFORM.values())
        allow = {p.lower() for p in brief.get("platforms") or []}
        blocked = {p.lower() for p in brief.get("exclude_platforms") or []}
        if allow:
            blocked |= known - allow
        self.blocked = blocked

        self.store.set_campaign_status(cid, "running")
        self.store.reset_running(cid)
        self.store.close_open_runs(cid)
        if not self.store.nodes(cid, "goal"):
            log.info("decomposing goals")
            await decompose(self.llm, self.store, cid, brief, self.s.planner_model)
        for g in self.store.nodes(cid, "goal"):
            log.info("goal #%s: %s (target %s %s+)", g.id, g.payload.get("text"), g.payload.get("target_count"),
                     g.payload.get("min_intent"))

        beat = asyncio.create_task(self._heartbeat(cid, runner))
        tasks = [asyncio.create_task(self._planner_loop(cid, brief)), beat]
        tasks += [asyncio.create_task(self._worker_loop(cid, brief, f"worker-{i + 1}")) for i in range(self.s.workers)]
        if self.s.auto_draft:
            tasks.append(asyncio.create_task(self._writer_loop(cid)))
        self.notify()
        try:
            await self._done.wait()
            # A task that finished on its own drafts messages for any lead still waiting, so every
            # lead in the final list has them. Pauses and failures skip this to stop promptly.
            if self.s.auto_draft and self.store.campaign(cid)["status"] in ("done", "stopped"):
                for t in tasks:
                    if t is not beat:
                        t.cancel()
                self.store.heartbeat(cid, runner)
                n = await draft_pending(self.llm, self.store, cid, self.s.writer_model, self.s.writer_effort)
                if n:
                    log.info("drafted messages for %d remaining lead(s)", n)
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
            self.store.reset_running(cid)
            self.store.close_open_runs(cid)
            self.store.heartbeat(cid, None)
            if self.store.campaign(cid)["status"] == "running":
                self.store.set_campaign_status(cid, "paused", "runner stopped")
            await self.gov.aclose()
        return self.end_reason

    # ------------------------------------------------------------ planner
    async def _planner_loop(self, cid: int, brief: dict) -> None:
        stall_rounds = 0
        rounds_without_lead = 0
        last_lead_total = -1
        while not self._done.is_set():
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.s.heartbeat_seconds)
                src = "edge"
            except asyncio.TimeoutError:
                src = "heartbeat"
            await asyncio.sleep(DEBOUNCE)            # coalesce a burst of changes into one round
            self._wake.clear()
            if self._done.is_set():
                return

            if not self.store.nodes(cid, "goal", ["open"]):
                self._finish(cid, "done", "all goals met")
                return
            if not self.llm.budget_left(cid):
                self._finish(cid, "stopped", "token budget spent")
                return

            # Operator hints written from another process (`zealead hint`).
            for h in self.store.nodes(cid, "hint", ["active"]):
                self._triggers.append({"kind": "hint", "text": h.summary})
                self.store.set_state(h.id, "consumed")

            triggers, self._triggers = self._triggers, []
            running = self.store.count_intents(cid, ["running"])
            open_ = self.store.count_intents(cid, ["open"])
            if src == "heartbeat" and not triggers and (running or open_):
                continue                              # work in flight, nothing new to decide

            log.info("planner round (trigger=%s, open=%d, running=%d)", src, open_, running)
            self.store.log(cid, "planner", "round", f"planning round ({src})")
            res = await plan_round(self.llm, self.store, cid, brief, self.s.planner_model, self.s.planner_effort,
                                   self.s.planner_max_turns, self.platforms_on, self.platforms_off, triggers)
            err = res.get("error") or ""
            if err.startswith(("AuthenticationError", "PermissionDeniedError", "NotFoundError")):
                self._finish(cid, "failed", f"LLM configuration error: {err}")
                return
            if res["dispatched"]:
                log.info("planner dispatched %d intent(s)", res["dispatched"])
                self._work.set()

            if not self.store.nodes(cid, "goal", ["open"]):
                self._finish(cid, "done", "all goals met")
                return

            idle = not self.store.count_intents(cid, ["open", "running"])
            stall_rounds = stall_rounds + 1 if idle else 0
            if stall_rounds >= 3:
                self._finish(cid, "stopped", "stalled: planner found no new direction three rounds in a row")
                return
            if idle:
                self.notify()                         # hard floor: re-plan immediately rather than wait a heartbeat

            lc = self.store.lead_counts(cid)
            total = lc["hot"] + lc["warm"] + lc["cold"]
            rounds_without_lead = 0 if total > last_lead_total else rounds_without_lead + 1
            last_lead_total = max(last_lead_total, total)
            if rounds_without_lead >= self.s.stagnation_rounds:
                self._finish(cid, "stopped", f"stagnation: {rounds_without_lead} planning rounds without a new lead")
                return

    # -------------------------------------------------------------- writer
    async def _writer_loop(self, cid: int) -> None:
        """Draft a personalised reply and DM for each new lead while the task runs."""
        tried: set[int] = set()
        while not self._done.is_set():
            pending = [lid for lid in self.store.undrafted_leads(cid, 20) if lid not in tried]
            if not pending or not self.llm.budget_left(cid):
                await asyncio.sleep(3)
                continue
            lid = pending[0]
            tried.add(lid)
            try:
                r = await draft_for_lead(self.llm, self.store, lid, self.s.writer_model, self.s.writer_effort)
            except asyncio.CancelledError:
                raise
            except Exception:  # drafting must never take the task down
                log.exception("drafting messages for lead #%d failed", lid)
                continue
            if not r["ok"]:
                log.info("no messages for lead #%d: %s", lid, r["error"])

    # ------------------------------------------------------------- workers
    async def _worker_loop(self, cid: int, brief: dict, name: str) -> None:
        while not self._done.is_set():
            if not self.llm.budget_left(cid):
                self.notify()
                return
            intent = self.store.claim_next_intent(cid, name)
            if not intent:
                self._work.clear()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._work.wait(), timeout=5)
                continue
            log.info("%s ▶ intent #%d: %s", name, intent.id, intent.summary[:110])
            env = dict(self.s.env)
            env["_BLOCKED_PLATFORMS"] = self.blocked
            ctx = Ctx(self.store, self.gov, cid, intent.id, int(brief.get("recency_days", 30)), env)
            try:
                state, stats, output = await run_worker(self.llm, ctx, intent, brief, self.connectors,
                                                        self.s.worker_model, self.s.worker_effort, self.s.intent_max_turns)
            except asyncio.CancelledError:
                self.store.set_state(intent.id, "open")
                raise
            except Exception as e:  # keep the loop alive; the planner sees the blocked intent
                log.exception("%s failed on intent #%d", name, intent.id)
                state, stats, output = "blocked", {"leads": 0, "facts": 0}, f"worker crashed: {e}"
                self.store.log(cid, "worker", "result", output, output, intent_id=intent.id)
            self.store.set_state(intent.id, state)
            log.info("%s ✔ intent #%d %s: leads=%d facts=%d", name, intent.id, state, stats["leads"], stats["facts"])
            self.notify({"kind": "done", "intent_id": intent.id, "state": state, "output": output, **stats})
