"""Manual tool-use loop over the Claude Messages API.

One run = one planner round or one worker intent. The loop records usage per
call, stops when the campaign budget is spent, and gives the model a wrap-up
turn near its turn limit so collected results are written back instead of lost.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import anthropic

from .store import TRANSCRIPT_TEXT_LIMIT, Store

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
        self.client = anthropic.AsyncAnthropic(max_retries=4)
        self.store = store
        self.budget_tokens = budget_tokens
        self.use_fallbacks = os.environ.get("LEADSCOUT_FALLBACKS", "default") != "off"

    def budget_left(self, cid: int) -> bool:
        return not self.budget_tokens or self.store.tokens_spent(cid) < self.budget_tokens

    async def _create(self, **kw):
        if self.use_fallbacks:
            kw["betas"] = ["server-side-fallback-2026-07-01"]
            try:
                return await self.client.beta.messages.create(fallbacks="default", **kw)
            except TypeError as e:
                if "fallbacks" not in str(e):
                    raise
                # Older SDK without the typed parameter: same request body, passed through.
                return await self.client.beta.messages.create(extra_body={"fallbacks": "default"}, **kw)
        return await self.client.messages.create(**kw)

    async def run(self, *, cid: int, role: str, intent_id: int | None, model: str, effort: str,
                  system: str, user: str, tools: list[Tool], max_turns: int,
                  on_step: Callable[[str, str, str | None], None] | None = None,
                  title: str | None = None) -> RunResult:
        run_id = self.store.start_run(cid, role, intent_id, model, title)
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
        for turn in range(max_turns + 2):
            if not self.budget_left(cid):
                return RunResult(last_text or "(campaign token budget spent)", True)
            t0 = time.monotonic()
            try:
                resp = await self._create(
                    model=model, max_tokens=16000,
                    system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                    messages=messages, tools=params,
                    thinking={"type": "adaptive"}, output_config={"effort": effort},
                )
            except anthropic.RateLimitError:
                await asyncio.sleep(30)
                continue
            except (anthropic.BadRequestError, anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                    anthropic.NotFoundError) as e:
                return RunResult(last_text, False, f"{type(e).__name__}: {e.message}")
            except anthropic.APIStatusError as e:
                return RunResult(last_text, False, f"API error {e.status_code}: {e.message}")
            except anthropic.APIConnectionError as e:
                return RunResult(last_text, False, f"connection error: {e}")
            except TypeError as e:
                if "authentication method" not in str(e):
                    raise
                return RunResult(last_text, False, "AuthenticationError: no Anthropic credentials; set "
                                                   "ANTHROPIC_API_KEY in .env (or run `ant auth login`) and restart")

            mid = self.store.add_message(run_id, "assistant", serialize_content(resp.content))
            self.store.record_usage(cid, role, intent_id, getattr(resp, "model", None) or model, resp.usage, run_id=run_id,
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
        return RunResult(last_text, True)
