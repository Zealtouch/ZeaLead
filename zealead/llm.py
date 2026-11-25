"""Manual tool-use loop over any configured LLM.

One run = one planner round or one worker intent. The loop records usage per
call, stops when the campaign budget is spent, and gives the model a wrap-up
turn near its turn limit so collected results are written back instead of lost.

Every model call goes through the role's profile chain (llmpool.Router): the
provider layer retries connect / empty / stream failures on the same profile,
then the pool fails over to the next profile and the breaker records the result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import anthropic

from . import providers as P
from .llmpool import Health, Router, should_failover
from .store import TRANSCRIPT_TEXT_LIMIT, Store

log = logging.getLogger("zealead.llm")
RATE_LIMIT_WAITS = 10           # a lone profile that keeps answering 429: wait this many times, then give up

WRAPUP_NOTE = (
    "[Runtime notice] Your turn budget is almost spent. Start no new searches. Write back everything "
    "already found now (record_fact / report_lead, or add_intent / prove_goal for the planner), then reply "
    "with your one-paragraph summary."
)


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    handler: Callable[[dict], Awaitable[Any]]

    def param(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.schema}


@dataclass
class RunResult:
    text: str
    exhausted: bool          # hit the turn limit or the campaign budget
    error: str | None = None
    model_error: bool = False  # the model call itself failed (after retries and failover)


def _clip(s: str, n: int = TRANSCRIPT_TEXT_LIMIT) -> str:
    return s if len(s) <= n else s[:n] + f"\n… [{len(s) - n} more characters]"


def serialize_content(blocks) -> list[dict]:
    """Model reply blocks as plain JSON for the transcript (thinking kept only as its visible summary)."""
    out = []
    for b in blocks:
        t = getattr(b, "type", None)
        if t == "text":
            out.append({"type": "text", "text": _clip(b.text)})
        elif t == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        elif t == "thinking" and getattr(b, "thinking", ""):
            out.append({"type": "thinking", "text": _clip(b.thinking, 4000)})
    return out


class LLM:
    def __init__(self, store: Store, budget_tokens: int):
        self.client = anthropic.AsyncAnthropic(max_retries=0)
        self.store = store
        self.budget_tokens = budget_tokens
        self.router = Router(store)

    def budget_left(self, cid: int) -> bool:
        return not self.budget_tokens or self.store.tokens_spent(cid) < self.budget_tokens

    def retry_policy(self) -> dict:
        from .llmpool import retry_policy
        return retry_policy(self.store.get_settings())

    async def _create(self, **kw):
        """The environment profile's call (ANTHROPIC_API_KEY); test doubles override this."""
        return await P.create_with_fallbacks(self.client, os.environ.get("ZEALEAD_FALLBACKS", "default") != "off", **kw)

    async def _call(self, cid: int, role: str, run_id: int, req: P.Request, role_model: str,
                    role_effort: str) -> tuple[P.Reply, P.Profile]:
        """One model call through the role's chain: same-profile retries, then failover."""
        chain, meta = self.router.chain(role, role_model, P.estimate_tokens(req))
        health = Health(self.store, meta["settings"]) if meta["pool"] or any(p.id for p in chain) else None
        last: P.ProviderError | None = None
        for i, prof in enumerate(chain):
            r = P.Request(model=prof.model or role_model, system=req.system, messages=req.messages, tools=req.tools,
                          effort=prof.effort_for(role_effort), session_id=req.session_id)
            policy = P.merge_policy(meta["policy"], prof.retry)

            def on_retry(layer, n, e, prof=prof):
                self.store.log(cid, role, "text", f"LLM retry ({layer} #{n}) on {prof.name}: {e}"[:300])

            try:
                reply = await P.complete(prof, r, policy, create=self._create if prof.env_key else None, on_retry=on_retry)
            except P.ProviderError as e:
                last = e
                if health and prof.id:
                    health.failed(prof.id, e)
                if i + 1 < len(chain) and should_failover(e):
                    nxt = chain[i + 1]
                    self.store.log(cid, role, "text", f"LLM failover: {prof.name} → {nxt.name} ({e})"[:300])
                    continue
                raise
            if health and prof.id:
                health.passed(prof.id)
            return reply, prof
        raise last or P.ProviderError(0, "no model profile available", phase="final")

    async def run(self, *, cid: int, role: str, intent_id: int | None, model: str, effort: str,
                  system: str, user: str, tools: list[Tool], max_turns: int,
                  on_step: Callable[[str, str, str | None], None] | None = None,
                  title: str | None = None) -> RunResult:
        chain, _ = self.router.chain(role, model)
        run_id = self.store.start_run(cid, role, intent_id, chain[0].model or model, title)
        self.store.add_message(run_id, "user", [{"type": "text", "text": _clip(user)}])
        try:
            res = await self._loop(cid=cid, role=role, intent_id=intent_id, model=model, effort=effort, system=system,
                                   user=user, tools=tools, max_turns=max_turns, on_step=on_step, run_id=run_id)
        except BaseException as e:
            self.store.end_run(run_id, "stopped" if isinstance(e, asyncio.CancelledError) else "error", repr(e)[:500])
            raise
        self.store.end_run(run_id, "error" if res.error else ("exhausted" if res.exhausted else "done"), res.error)
        return res

    async def _loop(self, *, cid, role, intent_id, model, effort, system, user, tools, max_turns, on_step,
                    run_id) -> RunResult:
        by_name = {t.name: t for t in tools}
        messages: list[dict] = [{"role": "user", "content": user}]
        params = [t.param() for t in tools]
        wrapup_sent = False
        last_text = ""
        rate_waits = 0
        turn = 0
        while turn < max_turns + 2:
            if not self.budget_left(cid):
                return RunResult(last_text or "(campaign token budget spent)", True)
            t0 = time.monotonic()
            req = P.Request(model=model, system=system, messages=messages, tools=params,
                            session_id=f"ls-{role}-run{run_id}")
            try:
                resp, prof = await self._call(cid, role, run_id, req, model, effort)
            except P.ProviderError as e:
                if e.status == 429 and rate_waits < RATE_LIMIT_WAITS:
                    rate_waits += 1
                    await asyncio.sleep(30)
                    continue
                return RunResult(last_text, False, f"{e.kind}: {e.message}", model_error=True)

            mid = self.store.add_message(run_id, "assistant", serialize_content(resp.content))
            self.store.record_usage(cid, role, intent_id, resp.model or prof.model or model, resp.usage, run_id=run_id,
                                    stop_reason=resp.stop_reason, duration_ms=int((time.monotonic() - t0) * 1000),
                                    message_id=mid)
            texts = [b.text for b in resp.content if b.type == "text"]
            if texts:
                last_text = "\n".join(texts).strip()
                if on_step and last_text:
                    on_step("text", last_text[:300], last_text)

            if resp.stop_reason == "refusal":
                return RunResult(last_text, False, "model declined this request")
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "pause_turn":
                turn += 1
                continue
            uses = [b for b in resp.content if b.type == "tool_use"]
            if not uses:
                return RunResult(last_text, False)

            async def run_one(b):
                tool = by_name.get(b.name)
                if on_step:
                    on_step("tool_use", f"{b.name} {json.dumps(b.input)[:200]}", None)
                args = dict(b.input or {})
                t1 = time.monotonic()
                if not tool:
                    content, is_err = f"unknown tool {b.name}", True
                elif "_invalid_json" in args:
                    content, is_err = "tool arguments were not valid JSON; call the tool again with a JSON object", True
                else:
                    try:
                        out = await tool.handler(args)
                        content = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)
                        is_err = isinstance(out, dict) and "error" in out and len(out) <= 2
                    except Exception as e:  # tool failures go back to the model, not up the stack
                        content, is_err = f"{type(e).__name__}: {e}", True
                self.store.add_tool_call(cid, run_id, intent_id, role, b.name, args, content, is_err,
                                         int((time.monotonic() - t1) * 1000))
                return {"type": "tool_result", "tool_use_id": b.id, "content": content, "is_error": is_err}

            results: list[dict] = list(await asyncio.gather(*(run_one(b) for b in uses)))
            self.store.add_message(run_id, "tool", [
                {"type": "tool_result", "tool_use_id": r["tool_use_id"], "content": _clip(r["content"]),
                 "is_error": r["is_error"]} for r in results])
            if turn >= max_turns - 2 and not wrapup_sent:
                results.append({"type": "text", "text": WRAPUP_NOTE})
                wrapup_sent = True
            messages.append({"role": "user", "content": results})
            if turn >= max_turns + 1:
                break
            turn += 1
        return RunResult(last_text, True)
