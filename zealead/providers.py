"""LLM providers behind one call: Anthropic, OpenAI Chat Completions, OpenAI Responses,
Ollama and Bedrock-compatible gateways.

The agent loop speaks the Anthropic Messages shape (system + messages of typed blocks,
tools with input_schema). Each provider converts that request to its own wire format
and converts the reply back into blocks with .type / .text / .id / .name / .input, a
stop_reason (end_turn | tool_use | max_tokens | refusal | pause_turn) and a usage object.

Retries happen in three layers here, innermost first (the pool breaker and the intent
rerun sit above this module):
  connect  no 200 yet: transport errors and 408/429/5xx
  empty    openai format only: a 200 that finished normally with no content at all
  stream   the stream broke after the 200 but before any output reached the caller
           (replies are buffered until complete, so a replay can't duplicate output)
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from types import SimpleNamespace as NS
from typing import Any, Awaitable, Callable
from urllib.parse import quote

import httpx

FORMATS = ("anthropic", "openai", "openai-responses", "ollama", "bedrock-gateway")
OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
THINKING_TYPES = ("", "disabled", "enabled", "adaptive")
EFFORTS = ("", "role", "low", "medium", "high", "xhigh", "max")
DEFAULT_MAX_TOKENS = 16000          # formats that require a cap (Anthropic, Bedrock)
DEFAULT_WINDOW_K = 200
RETRYABLE = {408, 429, 500, 502, 503, 504, 529}
TRANSIENT_STREAM = {0, 408, 429, 500, 502, 503, 504, 529}

# Built-in defaults per retry layer: attempts and the exponential backoff (base, cap) in seconds.
LAYERS = {
    "connect": {"attempts": 3, "base": 0.5, "cap": 8.0},
    "empty": {"attempts": 2, "base": 0.5, "cap": 8.0},
    "stream": {"attempts": 2, "base": 0.5, "cap": 4.0},
    "breaker": {"attempts": 3},
    "intent": {"attempts": 2, "fixed": 3.0},
}
PROFILE_LAYERS = ("connect", "empty", "stream")


class ProviderError(Exception):
    """A failed model call. status 0 = transport (no HTTP status); phase says which layer may retry it."""

    def __init__(self, status: int, message: str, phase: str = "connect", retry_after: float | None = None):
        super().__init__(f"HTTP {status}: {message}" if status else message)
        self.status = status
        self.message = message
        self.phase = phase              # connect | stream | empty | final
        self.retry_after = retry_after

    @property
    def kind(self) -> str:
        if self.status == 401:
            return "AuthenticationError"
        if self.status == 403:
            return "PermissionDeniedError"
        if self.status == 404:
            return "NotFoundError"
        if self.status == 429:
            return "RateLimitError"
        if self.status == 0:
            return "ConnectionError"
        return f"API error {self.status}"


# --------------------------------------------------------------------------- retry policy
def rule_attempts(rule: dict | None, layer: str) -> int:
    """attempts: 0/empty = built-in default, -1 = layer off, >0 = that count."""
    a = int((rule or {}).get("attempts") or 0)
    if a < 0:
        return 0
    return a or int(LAYERS[layer]["attempts"])


def rule_delay(rule: dict | None, layer: str, i: int) -> float:
    """Seconds before retry i (0-based): a fixed interval when set, else the layer's own backoff."""
    ms = int((rule or {}).get("interval_ms") or 0)
    if ms > 0:
        return ms / 1000
    d = LAYERS[layer]
    if "fixed" in d:
        return float(d["fixed"])
    return min(d["cap"], d["base"] * (2 ** i)) * (0.8 + random.random() * 0.4)


def normalize_rule(r: Any) -> dict:
    r = r if isinstance(r, dict) else {}
    try:
        a = int(r.get("attempts") or 0)
        ms = int(r.get("interval_ms") or 0)
    except (TypeError, ValueError):
        raise ValueError("attempts and interval_ms must be integers") from None
    if a < -1 or a > 20:
        raise ValueError("attempts must be between -1 and 20")
    if ms < 0 or ms > 3_600_000:
        raise ValueError("interval_ms must be between 0 and 3600000")
    return {"attempts": a, "interval_ms": ms}


def normalize_policy(p: Any, layers=tuple(LAYERS)) -> dict:
    p = p if isinstance(p, dict) else {}
    return {k: normalize_rule(p.get(k)) for k in layers}


def merge_policy(global_policy: dict, override: dict) -> dict:
    """A profile's non-zero rules win over the global ones, field by field."""
    out = {}
    for k in LAYERS:
        g, o = global_policy.get(k) or {}, override.get(k) or {}
        out[k] = {"attempts": o.get("attempts") or g.get("attempts") or 0,
                  "interval_ms": o.get("interval_ms") or g.get("interval_ms") or 0}
    return out


# --------------------------------------------------------------------------- profile
@dataclass
class Profile:
    id: int
    name: str
    format: str
    model: str
    base_url: str = ""
    proxy: str = ""
    api_key: str = ""
    custom_headers: dict = field(default_factory=dict)
    rate_per_second: int = 0
    rate_per_minute: int = 0
    context_window_k: int = 0
    thinking_type: str = ""
    reasoning_effort: str = "role"
    priority: int = 0
    pool_exclude: bool = False
    streaming: bool = True
    max_tokens: int = 0
    max_tokens_field: str = ""
    session_header_key: str = ""
    user_agent: str = ""
    retry: dict = field(default_factory=dict)
    is_default: bool = False
    env_key: bool = False           # the implicit profile built from ANTHROPIC_API_KEY

    @property
    def usable(self) -> bool:
        return bool(self.api_key) or self.format == "ollama" or self.env_key

    @property
    def window_tokens(self) -> int:
        return (self.context_window_k or DEFAULT_WINDOW_K) * 1000

    def effort_for(self, role_effort: str) -> str:
        return role_effort if self.reasoning_effort == "role" else self.reasoning_effort

    def base(self) -> str:
        b = self.base_url.strip().rstrip("/")
        if b:
            return b
        if self.format == "ollama":
            return OLLAMA_DEFAULT_BASE_URL
        if self.format in ("openai", "openai-responses"):
            return OPENAI_DEFAULT_BASE_URL
        return ""


def parse_headers(text: str) -> dict:
    """'Name: Value' per line → dict. Rejects malformed lines and header injection."""
    out = {}
    for n, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"custom header line {n} is not 'Name: Value'")
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if not k or any(c in k for c in " \t\r\n:") or "\r" in v or "\n" in v:
            raise ValueError(f"custom header line {n} has an invalid name or value")
        if k.lower() in ("authorization", "host", "content-length", "content-type"):
            raise ValueError(f"custom header {k} is set by ZeaLead and can't be overridden")
        out[k] = v
    return out


@dataclass
class Request:
    model: str
    system: str
    messages: list
    tools: list                     # Anthropic tool params: name / description / input_schema
    effort: str = ""                # resolved effort ('' = don't send)
    session_id: str = ""


@dataclass
class Reply:
    content: list
    stop_reason: str
    usage: Any
    model: str


def _usage(i=0, o=0, cr=0, cw=0):
    return NS(input_tokens=i, output_tokens=o, cache_read_input_tokens=cr, cache_creation_input_tokens=cw)


def _g(b, key, default=None):
    return b.get(key, default) if isinstance(b, dict) else getattr(b, key, default)


def estimate_tokens(req: Request) -> int:
    n = len(req.system) + len(json.dumps(req.tools, default=str))
    for m in req.messages:
        c = m["content"]
        n += len(c) if isinstance(c, str) else len(json.dumps([_block_dict(b) for b in c], default=str))
    return n // 4


def _block_dict(b) -> dict:
    if isinstance(b, dict):
        return b
    if hasattr(b, "model_dump"):
        return b.model_dump(exclude_none=True)
    return {k: v for k, v in vars(b).items() if v is not None}


# --------------------------------------------------------------------------- rate limits
class RateLimiter:
    """Per-profile request-rate caps shared by every agent in this process."""

    def __init__(self):
        self._hist: dict[int, deque] = defaultdict(deque)
        self._locks: dict[tuple, asyncio.Lock] = {}

    async def acquire(self, pid: int, rps: int, rpm: int) -> None:
        if rps <= 0 and rpm <= 0:
            return
        key = (pid, id(asyncio.get_running_loop()))
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            while True:
                now = time.monotonic()
                dq = self._hist[pid]
                while dq and now - dq[0] >= 60:
                    dq.popleft()
                wait = 0.0
                if rpm > 0 and len(dq) >= rpm:
                    wait = 60 - (now - dq[0])
                if rps > 0:
                    recent = [t for t in dq if now - t < 1]
                    if len(recent) >= rps:
                        wait = max(wait, 1 - (now - recent[0]))
                if wait <= 0:
                    dq.append(now)
                    return
                await asyncio.sleep(wait)


LIMITER = RateLimiter()


# --------------------------------------------------------------------------- HTTP helpers
_clients: dict[tuple, httpx.AsyncClient] = {}


def http_client(proxy: str) -> httpx.AsyncClient:
    key = (proxy, id(asyncio.get_running_loop()))
    c = _clients.get(key)
    if c is None or c.is_closed:
        c = httpx.AsyncClient(proxy=proxy or None, timeout=httpx.Timeout(600, connect=20), follow_redirects=False)
        _clients[key] = c
    return c


def _headers(p: Profile, req: Request | None, auth: str = "bearer") -> dict:
    h = {"Content-Type": "application/json"}
    if p.api_key:
        h["Authorization"] = f"Bearer {p.api_key}"
    if p.user_agent:
        h["User-Agent"] = p.user_agent
    if p.session_header_key and req and req.session_id:
        h[p.session_header_key] = req.session_id
    if p.format == "bedrock-gateway":
        h.update(p.custom_headers)
    return h


def _err_message(r: httpx.Response) -> str:
    try:
        j = r.json()
        e = j.get("error", j)
        if isinstance(e, dict):
            return str(e.get("message") or e.get("type") or json.dumps(e))[:500]
        return str(e)[:500]
    except Exception:
        return r.text[:500] or r.reason_phrase


def _retry_after(r: httpx.Response) -> float | None:
    v = r.headers.get("retry-after")
    try:
        return min(60.0, float(v)) if v else None
    except ValueError:
        return None


async def _post_json(p: Profile, url: str, body: dict, req: Request | None) -> dict:
    try:
        r = await http_client(p.proxy).post(url, json=body, headers=_headers(p, req))
    except httpx.HTTPError as e:
        raise ProviderError(0, f"{type(e).__name__}: {e}") from None
    if r.status_code >= 400:
        raise ProviderError(r.status_code, _err_message(r), retry_after=_retry_after(r))
    try:
        return r.json()
    except ValueError:
        raise ProviderError(r.status_code, "response is not JSON", phase="stream") from None


async def _post_sse(p: Profile, url: str, body: dict, req: Request, on_event: Callable[[dict], None]) -> None:
    """POST with stream=true; feed each JSON data line to on_event. Errors after the 200 are stream-phase."""
    try:
        async with http_client(p.proxy).stream("POST", url, json=body, headers=_headers(p, req)) as r:
            if r.status_code >= 400:
                await r.aread()
                raise ProviderError(r.status_code, _err_message(r), retry_after=_retry_after(r))
            try:
                event = ""
                async for line in r.aiter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        obj = json.loads(data)
                    except ValueError:
                        continue
                    if isinstance(obj, dict) and event and "type" not in obj:
                        obj["type"] = event
                    on_event(obj)
            except httpx.HTTPError as e:
                raise ProviderError(0, f"stream broke: {type(e).__name__}: {e}", phase="stream") from None
    except httpx.HTTPError as e:
        raise ProviderError(0, f"{type(e).__name__}: {e}") from None


def _stream_error(obj: dict) -> ProviderError:
    e = obj.get("error") or obj
    msg = str(e.get("message") or e) if isinstance(e, dict) else str(e)
    code = e.get("code") if isinstance(e, dict) else None
    status = code if isinstance(code, int) else (429 if "rate" in msg.lower() else 500 if "overload" in msg.lower() else 0)
    return ProviderError(status, msg[:500], phase="stream")


# --------------------------------------------------------------------------- Anthropic
def anthropic_kwargs(p: Profile, req: Request) -> dict:
    msgs = []
    for m in req.messages:
        c = m["content"]
        if isinstance(c, list):
            c = [d for d in (_block_dict(b) for b in c)
                 if not (d.get("type") in ("thinking", "redacted_thinking") and not d.get("signature") and not d.get("data"))]
        msgs.append({"role": m["role"], "content": c})
    max_tokens = p.max_tokens or DEFAULT_MAX_TOKENS
    kw: dict[str, Any] = {
        "model": req.model, "max_tokens": max_tokens, "messages": msgs,
        "system": [{"type": "text", "text": req.system, "cache_control": {"type": "ephemeral"}}],
    }
    if req.tools:
        kw["tools"] = req.tools
    if p.thinking_type == "adaptive":
        kw["thinking"] = {"type": "adaptive"}
    elif p.thinking_type == "enabled":
        kw["thinking"] = {"type": "enabled", "budget_tokens": max(1024, max_tokens // 2)}
    elif p.thinking_type == "disabled":
        kw["thinking"] = {"type": "disabled"}
    if req.effort:
        kw["output_config"] = {"effort": req.effort}
    return kw


def _anthropic_error(e: Exception, streaming_started: bool) -> ProviderError:
    import anthropic
    phase = "stream" if streaming_started else "connect"
    if isinstance(e, anthropic.APIStatusError):
        ra = None
        try:
            ra = _retry_after(e.response)
        except Exception:
            pass
        return ProviderError(e.status_code, str(getattr(e, "message", e))[:500], phase=phase, retry_after=ra)
    if isinstance(e, anthropic.APIConnectionError):
        return ProviderError(0, f"connection error: {e}", phase=phase)
    if isinstance(e, anthropic.APIError):
        msg = str(getattr(e, "message", e))
        status = 529 if "overloaded" in msg.lower() else 0
        return ProviderError(status, msg[:500], phase="stream")
    if isinstance(e, TypeError) and "authentication method" in str(e):
        return ProviderError(401, "no Anthropic credentials; set ANTHROPIC_API_KEY in .env (or run `ant auth login`) "
                                  "and restart, or add a model profile in System → LLM", phase="final")
    raise e


class AnthropicCaller:
    """Anthropic Messages API through the official SDK, one cached client per profile configuration."""

    _cache: dict[tuple, Any] = {}

    @classmethod
    def client(cls, p: Profile):
        import anthropic
        key = (p.id, p.api_key, p.base_url, p.proxy, p.user_agent, id(asyncio.get_running_loop()))
        c = cls._cache.get(key)
        if c is None:
            kw: dict[str, Any] = {"max_retries": 0}
            if p.api_key:
                kw["api_key"] = p.api_key
            if p.base_url.strip():
                kw["base_url"] = p.base_url.strip().rstrip("/")
            if p.proxy:
                kw["http_client"] = anthropic.DefaultAsyncHttpxClient(proxy=p.proxy)
            if p.user_agent:
                kw["default_headers"] = {"User-Agent": p.user_agent}
            c = anthropic.AsyncAnthropic(**kw)
            cls._cache[key] = c
        return c

    @staticmethod
    def official(p: Profile) -> bool:
        return not p.base_url.strip() and os.environ.get("ZEALEAD_FALLBACKS", "default") != "off"

    @classmethod
    async def call(cls, p: Profile, req: Request, create: Callable[..., Awaitable[Any]] | None = None) -> Reply:
        kw = anthropic_kwargs(p, req)
        if p.session_header_key and req.session_id:
            kw["extra_headers"] = {p.session_header_key: req.session_id}
        started = False
        try:
            if create is not None:                      # the environment profile (and test doubles)
                resp = await create(**kw)
            elif p.streaming:
                client = cls.client(p)
                if cls.official(p):
                    kw["betas"] = ["server-side-fallback-2026-07-01"]
                    kw["extra_body"] = {"fallbacks": "default"}
                    mgr = client.beta.messages.stream(**kw)
                else:
                    mgr = client.messages.stream(**kw)
                async with mgr as s:
                    started = True
                    resp = await s.get_final_message()
            else:
                client = cls.client(p)
                resp = await create_with_fallbacks(client, cls.official(p), **kw)
        except ProviderError:
            raise
        except Exception as e:
            raise _anthropic_error(e, started) from None
        return Reply(list(resp.content), resp.stop_reason or "end_turn", resp.usage,
                     getattr(resp, "model", None) or req.model)


async def create_with_fallbacks(client, use_fallbacks: bool, **kw):
    """messages.create, with server-side fallback models when talking to the official API."""
    if use_fallbacks:
        kw["betas"] = ["server-side-fallback-2026-07-01"]
        try:
            return await client.beta.messages.create(fallbacks="default", **kw)
        except TypeError as e:
            if "fallbacks" not in str(e):
                raise
            return await client.beta.messages.create(extra_body={"fallbacks": "default"}, **kw)
    return await client.messages.create(**kw)


# --------------------------------------------------------------------------- Bedrock gateway
def _blocks_from_anthropic_json(content: list) -> list:
    out = []
    for b in content or []:
        t = b.get("type")
        if t == "text":
            out.append(NS(type="text", text=b.get("text", "")))
        elif t == "tool_use":
            out.append(NS(type="tool_use", id=b.get("id"), name=b.get("name"), input=b.get("input") or {}))
        elif t == "thinking":
            out.append(NS(type="thinking", thinking=b.get("thinking", ""), signature=b.get("signature", "")))
    return out


async def bedrock_call(p: Profile, req: Request) -> Reply:
    """A gateway exposing Bedrock InvokeModel with bearer auth. Always non-streaming (InvokeModel)."""
    kw = anthropic_kwargs(p, req)
    kw.pop("model")
    body = {"anthropic_version": "bedrock-2023-05-31", **kw}
    url = f"{p.base()}/model/{quote(req.model, safe='')}/invoke"
    j = await _post_json(p, url, body, req)
    u = j.get("usage") or {}
    return Reply(_blocks_from_anthropic_json(j.get("content")), j.get("stop_reason") or "end_turn",
                 _usage(u.get("input_tokens", 0), u.get("output_tokens", 0), u.get("cache_read_input_tokens", 0),
                        u.get("cache_creation_input_tokens", 0)), j.get("model") or req.model)


# --------------------------------------------------------------------------- OpenAI Chat Completions / Ollama
def _tool_result_text(b) -> str:
    c = _g(b, "content", "")
    if isinstance(c, list):
        c = "\n".join(str(_g(x, "text", "")) for x in c)
    return ("[tool error] " if _g(b, "is_error") else "") + str(c)


def openai_messages(req: Request) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": req.system}]
    for m in req.messages:
        c = m["content"]
        if isinstance(c, str):
            out.append({"role": m["role"], "content": c})
            continue
        if m["role"] == "assistant":
            text = "\n".join(_g(b, "text", "") for b in c if _g(b, "type") == "text").strip()
            calls = [{"id": _g(b, "id"), "type": "function",
                      "function": {"name": _g(b, "name"), "arguments": json.dumps(_g(b, "input") or {})}}
                     for b in c if _g(b, "type") == "tool_use"]
            msg: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        texts = []
        for b in c:
            if _g(b, "type") == "tool_result":
                out.append({"role": "tool", "tool_call_id": _g(b, "tool_use_id"), "content": _tool_result_text(b)})
            elif _g(b, "type") == "text":
                texts.append(_g(b, "text", ""))
        if texts:
            out.append({"role": "user", "content": "\n\n".join(texts)})
    return out


def openai_tools(req: Request) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                              "parameters": t.get("input_schema") or {"type": "object"}}}
            for t in req.tools]


FINISH = {"stop": "end_turn", "tool_calls": "tool_use", "function_call": "tool_use", "length": "max_tokens",
          "content_filter": "refusal", None: "end_turn"}


def _parse_args(raw: str) -> dict:
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {"value": v}
    except ValueError:
        return {"_invalid_json": raw[:2000]}


def _openai_reply(msg: dict, finish: str | None, usage: dict, model: str) -> Reply:
    blocks: list = []
    reasoning = msg.get("reasoning_content") or msg.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        blocks.append(NS(type="thinking", thinking=reasoning))
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
    if content and content.strip():
        blocks.append(NS(type="text", text=content))
    for i, tc in enumerate(msg.get("tool_calls") or []):
        fn = tc.get("function") or {}
        blocks.append(NS(type="tool_use", id=tc.get("id") or f"call_{i}", name=fn.get("name", ""),
                         input=_parse_args(fn.get("arguments", ""))))
    stop = FINISH.get(finish, "end_turn")
    if any(b.type == "tool_use" for b in blocks):
        stop = "tool_use"
    if not any(b.type in ("text", "tool_use") for b in blocks) and stop == "end_turn":
        raise ProviderError(200, "empty response (no text and no tool calls)", phase="empty")
    u = usage or {}
    cached = int(((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
    prompt = int(u.get("prompt_tokens") or 0)
    return Reply(blocks, stop, _usage(max(0, prompt - cached), int(u.get("completion_tokens") or 0), cached), model)


def openai_body(p: Profile, req: Request, stream: bool) -> dict:
    body: dict[str, Any] = {"model": req.model, "messages": openai_messages(req)}
    if req.tools:
        body["tools"] = openai_tools(req)
    if p.max_tokens > 0:
        field_name = p.max_tokens_field if (p.format == "openai" and p.max_tokens_field) else "max_tokens"
        body[field_name] = p.max_tokens
    if req.effort:
        body["reasoning_effort"] = req.effort
    if p.thinking_type:
        body["thinking"] = {"type": "enabled" if p.thinking_type == "adaptive" else p.thinking_type}
    if stream:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    return body


async def openai_call(p: Profile, req: Request) -> Reply:
    url = f"{p.base()}/chat/completions"
    if not p.streaming:
        j = await _post_json(p, url, openai_body(p, req, False), req)
        ch = (j.get("choices") or [{}])[0]
        return _openai_reply(ch.get("message") or {}, ch.get("finish_reason"), j.get("usage") or {}, j.get("model") or req.model)

    acc: dict[str, Any] = {"content": "", "reasoning": "", "calls": {}, "finish": None, "usage": {}, "model": req.model}

    def on(obj: dict):
        if obj.get("error"):
            raise _stream_error(obj)
        if obj.get("usage"):
            acc["usage"] = obj["usage"]
        if obj.get("model"):
            acc["model"] = obj["model"]
        for ch in obj.get("choices") or []:
            d = ch.get("delta") or {}
            if d.get("content"):
                acc["content"] += d["content"]
            r = d.get("reasoning_content") or d.get("reasoning")
            if isinstance(r, str):
                acc["reasoning"] += r
            for tc in d.get("tool_calls") or []:
                slot = acc["calls"].setdefault(tc.get("index", 0), {"id": None, "name": "", "args": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                slot["name"] += fn.get("name") or ""
                slot["args"] += fn.get("arguments") or ""
            if ch.get("finish_reason"):
                acc["finish"] = ch["finish_reason"]

    await _post_sse(p, url, openai_body(p, req, True), req, on)
    msg = {"content": acc["content"], "reasoning_content": acc["reasoning"],
           "tool_calls": [{"id": s["id"], "function": {"name": s["name"], "arguments": s["args"]}}
                          for _, s in sorted(acc["calls"].items())]}
    return _openai_reply(msg, acc["finish"], acc["usage"], acc["model"])


# --------------------------------------------------------------------------- OpenAI Responses API
def responses_input(req: Request) -> list[dict]:
    out: list[dict] = []
    for m in req.messages:
        c = m["content"]
        if isinstance(c, str):
            out.append({"role": m["role"], "content": c})
            continue
        for b in c:
            t = _g(b, "type")
            if t == "text":
                out.append({"role": m["role"], "content": _g(b, "text", "")})
            elif t == "tool_use":
                out.append({"type": "function_call", "call_id": _g(b, "id"), "name": _g(b, "name"),
                            "arguments": json.dumps(_g(b, "input") or {})})
            elif t == "tool_result":
                out.append({"type": "function_call_output", "call_id": _g(b, "tool_use_id"), "output": _tool_result_text(b)})
    return out


def responses_body(p: Profile, req: Request, stream: bool) -> dict:
    body: dict[str, Any] = {"model": req.model, "instructions": req.system, "input": responses_input(req), "store": False}
    if req.tools:
        body["tools"] = [{"type": "function", "name": t["name"], "description": t.get("description", ""),
                          "parameters": t.get("input_schema") or {"type": "object"}} for t in req.tools]
    if p.max_tokens > 0:
        body["max_output_tokens"] = p.max_tokens
    if req.effort:
        body["reasoning"] = {"effort": req.effort, "summary": "auto"}
    if stream:
        body["stream"] = True
    return body


def _responses_reply(j: dict, model: str) -> Reply:
    blocks: list = []
    for item in j.get("output") or []:
        t = item.get("type")
        if t == "reasoning":
            text = "\n".join(s.get("text", "") for s in item.get("summary") or [] if isinstance(s, dict)).strip()
            if text:
                blocks.append(NS(type="thinking", thinking=text))
        elif t == "message":
            for c in item.get("content") or []:
                if c.get("type") == "output_text" and c.get("text", "").strip():
                    blocks.append(NS(type="text", text=c["text"]))
                elif c.get("type") == "refusal":
                    return Reply([NS(type="text", text=c.get("refusal", ""))], "refusal", _usage(), model)
        elif t == "function_call":
            blocks.append(NS(type="tool_use", id=item.get("call_id") or item.get("id"), name=item.get("name", ""),
                             input=_parse_args(item.get("arguments", ""))))
    if j.get("status") == "failed":
        e = j.get("error") or {}
        raise ProviderError(500, str(e.get("message") or "response failed"), phase="stream")
    stop = "end_turn"
    if any(b.type == "tool_use" for b in blocks):
        stop = "tool_use"
    elif j.get("status") == "incomplete":
        reason = (j.get("incomplete_details") or {}).get("reason")
        stop = "refusal" if reason == "content_filter" else "max_tokens"
    if not any(b.type in ("text", "tool_use") for b in blocks) and stop == "end_turn":
        raise ProviderError(200, "empty response (no text and no tool calls)", phase="empty")
    u = j.get("usage") or {}
    cached = int(((u.get("input_tokens_details") or {}).get("cached_tokens")) or 0)
    return Reply(blocks, stop, _usage(max(0, int(u.get("input_tokens") or 0) - cached), int(u.get("output_tokens") or 0), cached),
                 j.get("model") or model)


async def responses_call(p: Profile, req: Request) -> Reply:
    url = f"{p.base()}/responses"
    if not p.streaming:
        return _responses_reply(await _post_json(p, url, responses_body(p, req, False), req), req.model)
    final: dict = {}

    def on(obj: dict):
        t = obj.get("type", "")
        if t in ("error", "response.failed") and not obj.get("response"):
            raise _stream_error(obj)
        if t in ("response.completed", "response.incomplete", "response.failed"):
            final.update(obj.get("response") or {})

    await _post_sse(p, url, responses_body(p, req, True), req, on)
    if not final:
        raise ProviderError(0, "stream ended without a completed response", phase="stream")
    return _responses_reply(final, req.model)


# --------------------------------------------------------------------------- one call with retries
async def dispatch(p: Profile, req: Request, create=None) -> Reply:
    if p.format == "anthropic":
        return await AnthropicCaller.call(p, req, create)
    if p.format in ("openai", "ollama"):
        return await openai_call(p, req)
    if p.format == "openai-responses":
        return await responses_call(p, req)
    if p.format == "bedrock-gateway":
        return await bedrock_call(p, req)
    raise ProviderError(400, f"unknown format {p.format!r}", phase="final")


async def complete(p: Profile, req: Request, policy: dict, create=None,
                   on_retry: Callable[[str, int, ProviderError], None] | None = None) -> Reply:
    """One model call on one profile, through the connect / empty / stream retry layers."""
    used = {"connect": 0, "empty": 0, "stream": 0}
    while True:
        await LIMITER.acquire(p.id, p.rate_per_second, p.rate_per_minute)
        try:
            return await dispatch(p, req, create)
        except ProviderError as e:
            layer = None
            if e.phase == "connect" and (e.status == 0 or e.status in RETRYABLE):
                layer = "connect"
            elif e.phase == "empty":
                layer = "empty"
            elif e.phase == "stream" and e.status in TRANSIENT_STREAM:
                layer = "stream"
            if layer is None or used[layer] >= rule_attempts(policy.get(layer), layer):
                raise
            delay = rule_delay(policy.get(layer), layer, used[layer])
            if e.retry_after:
                delay = max(delay, e.retry_after)
            used[layer] += 1
            if on_retry:
                on_retry(layer, used[layer], e)
            await asyncio.sleep(delay)


# --------------------------------------------------------------------------- model list / connection test
async def list_models(p: Profile) -> list[str]:
    if p.format == "bedrock-gateway":
        raise ProviderError(400, "the Bedrock gateway format has no model list; enter the model ID manually", phase="final")
    if p.format == "anthropic":
        try:
            page = await AnthropicCaller.client(p).models.list(limit=1000)
            return sorted({m.id for m in page.data})
        except Exception as e:
            raise _anthropic_error(e, False) from None
    try:
        r = await http_client(p.proxy).get(f"{p.base()}/models", headers=_headers(p, None))
    except httpx.HTTPError as e:
        raise ProviderError(0, f"{type(e).__name__}: {e}") from None
    if r.status_code >= 400:
        raise ProviderError(r.status_code, _err_message(r))
    j = r.json()
    items = j.get("data") if isinstance(j, dict) else j
    if items is None and isinstance(j, dict):
        items = j.get("models")                 # Ollama's native /api/tags shape
    return sorted({str(m.get("id") or m.get("name")) for m in items or [] if isinstance(m, dict)})


async def test_connection(p: Profile, role_effort: str = "low") -> dict:
    req = Request(model=p.model, system="You are a connectivity check.",
                  messages=[{"role": "user", "content": "Reply with the single word: ok"}], tools=[],
                  effort=p.effort_for(role_effort), session_id="zealead-connection-test")
    t0 = time.monotonic()
    try:
        r = await complete(p, req, {"connect": {"attempts": -1}, "empty": {"attempts": -1}, "stream": {"attempts": -1}})
    except ProviderError as e:
        return {"ok": False, "error": str(e), "latency_ms": int((time.monotonic() - t0) * 1000)}
    text = " ".join(getattr(b, "text", "") for b in r.content if getattr(b, "type", "") == "text").strip()
    return {"ok": True, "latency_ms": int((time.monotonic() - t0) * 1000), "model": r.model, "reply": text[:200],
            "stop_reason": r.stop_reason}
