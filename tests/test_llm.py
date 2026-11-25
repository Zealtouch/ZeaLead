"""Model profiles: provider wire formats, retry layers, the failover pool and the LLM API. No network."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace as NS

import httpx
import pytest
from fastapi.testclient import TestClient

from zealead import llmpool
from zealead import providers as P
from zealead.config import Settings
from zealead.llm import LLM, Tool
from zealead.server import create_app
from zealead.store import Store

PW = "correct horse battery"


def _req(**kw):
    msgs = [
        {"role": "user", "content": "find leads"},
        {"role": "assistant", "content": [NS(type="text", text="searching"),
                                          NS(type="tool_use", id="t1", name="search", input={"q": "x"})]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "3 hits", "is_error": False}]},
    ]
    return P.Request(model="m", system="sys", messages=msgs,
                     tools=[{"name": "search", "description": "d", "input_schema": {"type": "object"}}], **kw)


def _mock(monkeypatch, handler):
    seen = []

    def wrapped(request: httpx.Request):
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    monkeypatch.setattr(P, "http_client", lambda proxy: client)
    monkeypatch.setattr(P, "rule_delay", lambda rule, layer, i: 0)
    return seen


def test_openai_chat_round_trip(monkeypatch):
    def handler(r):
        body = json.loads(r.content)
        assert body["messages"][0] == {"role": "system", "content": "sys"}
        assert body["messages"][2]["tool_calls"][0]["function"]["name"] == "search"
        assert body["messages"][3] == {"role": "tool", "tool_call_id": "t1", "content": "3 hits"}
        assert body["tools"][0]["function"]["parameters"] == {"type": "object"}
        assert body["max_completion_tokens"] == 500 and body["reasoning_effort"] == "high"
        return httpx.Response(200, json={"model": "gpt-x", "choices": [{"finish_reason": "tool_calls", "message": {
            "content": None, "tool_calls": [{"id": "c9", "function": {"name": "report", "arguments": '{"a": 1}'}}]}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 7, "prompt_tokens_details": {"cached_tokens": 40}}})

    seen = _mock(monkeypatch, handler)
    prof = P.Profile(1, "o", "openai", "gpt-x", api_key="sk-test", streaming=False, max_tokens=500,
                     max_tokens_field="max_completion_tokens", session_header_key="x-session-id", user_agent="ua/1")
    r = asyncio.run(P.complete(prof, _req(effort="high", session_id="s-1"), {}))
    assert r.stop_reason == "tool_use" and r.content[0].input == {"a": 1}
    assert (r.usage.input_tokens, r.usage.cache_read_input_tokens, r.usage.output_tokens) == (60, 40, 7)
    h = seen[0].headers
    assert h["authorization"] == "Bearer sk-test" and h["x-session-id"] == "s-1" and h["user-agent"] == "ua/1"
    assert str(seen[0].url) == "https://api.openai.com/v1/chat/completions"


def test_openai_stream_and_empty_retry(monkeypatch):
    calls = {"n": 0}

    def handler(r):
        calls["n"] += 1
        if calls["n"] == 1:   # a 200 with nothing in it → empty-response retry
            return httpx.Response(200, text='data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n')
        chunks = [{"choices": [{"delta": {"reasoning_content": "think "}}]},
                  {"choices": [{"delta": {"content": "Hel"}}]},
                  {"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]},
                  {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}]
        return httpx.Response(200, text="".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n")

    _mock(monkeypatch, handler)
    prof = P.Profile(2, "llama", "ollama", "llama3.2")
    assert prof.usable                                     # Ollama runs keyless
    r = asyncio.run(P.complete(prof, _req(), {}))
    assert calls["n"] == 2
    assert [b.type for b in r.content] == ["thinking", "text"] and r.content[1].text == "Hello"
    # with the empty layer off, the empty reply surfaces as an error
    calls["n"] = 0
    with pytest.raises(P.ProviderError) as e:
        asyncio.run(P.complete(prof, _req(), {"empty": {"attempts": -1}}))
    assert e.value.phase == "empty"


def test_connect_retry_then_give_up(monkeypatch):
    calls = {"n": 0}

    def handler(r):
        calls["n"] += 1
        return httpx.Response(503, json={"error": {"message": "overloaded"}})

    _mock(monkeypatch, handler)
    prof = P.Profile(3, "o", "openai", "m", api_key="k", streaming=False)
    with pytest.raises(P.ProviderError) as e:
        asyncio.run(P.complete(prof, _req(), {"connect": {"attempts": 2}}))
    assert e.value.status == 503 and calls["n"] == 3
    # 400 is a deterministic rejection: never retried
    calls["n"] = 0
    _mock(monkeypatch, lambda r: (calls.__setitem__("n", calls["n"] + 1), httpx.Response(400, json={"error": "bad"}))[1])
    with pytest.raises(P.ProviderError):
        asyncio.run(P.complete(prof, _req(), {}))
    assert calls["n"] == 1


def test_responses_api(monkeypatch):
    def handler(r):
        body = json.loads(r.content)
        assert body["instructions"] == "sys" and body["store"] is False
        kinds = [i.get("type", i.get("role")) for i in body["input"]]
        assert kinds == ["user", "assistant", "function_call", "function_call_output"]
        events = [{"type": "response.output_text.delta", "delta": "x"},
                  {"type": "response.completed", "response": {"status": "completed", "model": "o4", "output": [
                      {"type": "reasoning", "summary": [{"text": "plan"}]},
                      {"type": "function_call", "call_id": "f1", "name": "report", "arguments": "{}"}],
                      "usage": {"input_tokens": 9, "output_tokens": 3}}}]
        return httpx.Response(200, text="".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events))

    _mock(monkeypatch, handler)
    r = asyncio.run(P.complete(P.Profile(4, "r", "openai-responses", "o4", api_key="k"), _req(effort="low"), {}))
    assert r.stop_reason == "tool_use" and r.content[-1].id == "f1" and r.model == "o4"


def test_bedrock_gateway(monkeypatch):
    def handler(r):
        assert r.url.raw_path == b"/bedrock/model/anthropic.claude-x%3A0/invoke"
        assert r.headers["x-route"] == "demo" and r.headers["authorization"] == "Bearer tok"
        body = json.loads(r.content)
        assert body["anthropic_version"] == "bedrock-2023-05-31" and "model" not in body
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
                                         "usage": {"input_tokens": 3, "output_tokens": 1}})

    _mock(monkeypatch, handler)
    prof = P.Profile(5, "b", "bedrock-gateway", "anthropic.claude-x:0", base_url="https://gw.example/bedrock",
                     api_key="tok", custom_headers={"X-Route": "demo"})
    req = _req()
    req.model = prof.model
    r = asyncio.run(P.complete(prof, req, {}))
    assert r.content[0].text == "ok"


def test_header_parsing_rejects_injection():
    assert P.parse_headers("X-A: 1\n\nX-B: two words") == {"X-A": "1", "X-B": "two words"}
    for bad in ("no colon", "Authorization: x", "Bad Name: v"):
        with pytest.raises(ValueError):
            P.parse_headers(bad)


# ----------------------------------------------------------------------------- pool
def _profile_row(store, name, fmt="openai", priority=0, default=False, key="sk-1234567890", **kw):
    box = llmpool.box_for(store)
    fields = {"name": name, "format": fmt, "model": f"{name}-model", "api_key": box.seal(key) if key else "",
              "api_key_hint": "x", "priority": priority, "streaming": 0, **kw}
    pid = store.save_llm_profile(None, fields)
    if default:
        store.activate_llm_profile(pid)
    return pid


def test_pool_failover_and_breaker(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEALEAD_KEYS_DIR", str(tmp_path / "keys"))
    st = Store(str(tmp_path / "p.db"))
    a = _profile_row(st, "primary", default=True)
    b = _profile_row(st, "backup", priority=5)
    _profile_row(st, "excluded", priority=9, pool_exclude=1)
    _profile_row(st, "nokey", priority=9, key="")
    cid = st.create_campaign("t", {"product": "p"})
    used = []

    async def fake_dispatch(p, req, create=None):
        used.append(p.name)
        if p.name == "primary":
            raise P.ProviderError(402, "insufficient balance")
        return P.Reply([NS(type="text", text=f"hi from {p.model}")], "end_turn", P._usage(1, 1), p.model)

    monkeypatch.setattr(P, "dispatch", fake_dispatch)

    async def go():
        return await LLM(st, 0).run(cid=cid, role="worker", intent_id=None, model="env-model", effort="low",
                                    system="s", user="u", tools=[], max_turns=3)

    # pool off: the active profile only, and its failure is the run's failure
    res = asyncio.run(go())
    assert res.model_error and "402" in res.error and used == ["primary"]
    st.clear_llm_health()

    st.set_setting("llm_pool_enabled", "1")
    used.clear()
    res = asyncio.run(go())
    assert res.error is None and res.text == "hi from backup-model" and used == ["primary", "backup"]
    status = llmpool.Router(st).pool_status()
    by = {c["name"]: c for c in status["chain"]}
    assert by["primary"]["state"] == "tripped" and by["primary"]["cooldown_secs"] > 0   # 402 trips at once
    assert by["excluded"]["excluded"] and by["nokey"]["excluded"]
    # tripped profiles are skipped until recovered
    used.clear()
    asyncio.run(go())
    assert used == ["backup"]
    st.clear_llm_health(a)

    # a role pinned to a profile uses only that one unless bind-fallback is on
    st.set_setting("worker_profile", str(a))
    used.clear()
    assert asyncio.run(go()).model_error and used == ["primary"]
    st.set_setting("llm_pool_bind_fallback", "1")
    st.clear_llm_health()
    used.clear()
    assert asyncio.run(go()).error is None and used == ["primary", "backup"]
    assert b in (r["id"] for r in st.llm_profiles())


def test_breaker_soft_trip_and_priority_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEALEAD_KEYS_DIR", str(tmp_path / "keys"))
    st = Store(str(tmp_path / "h.db"))
    a = _profile_row(st, "a", default=True)
    h = llmpool.Health(st, {})
    for _ in range(2):
        assert not h.failed(a, P.ProviderError(503, "busy"))
    assert h.failed(a, P.ProviderError(503, "busy"))            # 3rd transient failure trips
    assert not h.failed(a, P.ProviderError(400, "bad request"))  # request errors never count
    h.passed(a)
    assert llmpool.Router(st).pool_status()["chain"][0]["state"] == "ok"
    # equal priorities take turns behind the head
    profs = [P.Profile(i, f"p{i}", "openai", "m", api_key="k", priority=1) for i in (1, 2, 3)]
    head = P.Profile(9, "head", "openai", "m", api_key="k")
    firsts = {llmpool.order(head, profs + [head], {}, 0, rr)[1].id for rr in range(3)}
    assert firsts == {1, 2, 3}
    # a profile whose window can't fit the request is skipped
    small = P.Profile(4, "small", "openai", "m", api_key="k", priority=5, context_window_k=8)
    assert small not in llmpool.order(head, [small, head], {}, 50_000, 0)


def test_intent_rerun_on_model_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEALEAD_KEYS_DIR", str(tmp_path / "keys"))
    st = Store(str(tmp_path / "r.db"))
    _profile_row(st, "only", default=True)
    st.set_setting("llm_retry", json.dumps({"intent": {"attempts": 1, "interval_ms": 1}}))
    calls = {"n": 0}

    async def flaky(p, req, create=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise P.ProviderError(0, "connection reset", phase="final")
        return P.Reply([NS(type="text", text="done")], "end_turn", P._usage(), p.model)

    monkeypatch.setattr(P, "dispatch", flaky)
    from zealead.agents import run_worker
    from zealead.connectors.base import Ctx
    from zealead.store import Node
    cid = st.create_campaign("t", {"product": "p"})
    iid = st.add_node(cid, "intent", {"summary": "look", "platform": "reddit"}, "running")
    intent = st.get_node(iid)
    assert isinstance(intent, Node)
    state, _, out = asyncio.run(run_worker(LLM(st, 0), Ctx(st, None, cid, iid, 30, {}), intent, {"product": "p"}, [],
                                           "m", "low", 4))
    assert state == "done" and out == "done" and calls["n"] == 2
    assert [r["title"] for r in st.runs(cid)][-1].endswith("(rerun 1)")


def test_tool_with_invalid_json_args_goes_back_to_model(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEALEAD_KEYS_DIR", str(tmp_path / "keys"))
    st = Store(str(tmp_path / "j.db"))
    _profile_row(st, "only", default=True)
    step = {"n": 0}

    async def model(p, req, create=None):
        step["n"] += 1
        if step["n"] == 1:
            return P.Reply([NS(type="tool_use", id="t", name="save", input={"_invalid_json": "{oops"})], "tool_use",
                           P._usage(), "m")
        assert "not valid JSON" in req.messages[-1]["content"][0]["content"]
        return P.Reply([NS(type="text", text="fixed")], "end_turn", P._usage(), "m")

    monkeypatch.setattr(P, "dispatch", model)
    ran = []

    async def save(args):
        ran.append(args)
        return {"ok": True}

    cid = st.create_campaign("t", {"product": "p"})
    res = asyncio.run(LLM(st, 0).run(cid=cid, role="writer", intent_id=None, model="m", effort="low", system="s",
                                     user="u", tools=[Tool("save", "d", {"type": "object"}, save)], max_turns=4))
    assert res.text == "fixed" and ran == []


# ----------------------------------------------------------------------------- API
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEALEAD_KEYS_DIR", str(tmp_path / "keys"))
    s = Settings.load()
    s.db_path = str(tmp_path / "api.db")
    st = Store(s.db_path)
    with TestClient(create_app(s, st)) as c:
        r = c.post("/api/auth/setup", json={"username": "admin", "password": PW})
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        c.store = st
        yield c


def test_profiles_api_keeps_keys_write_only(client):
    body = {"name": "OpenAI prod", "format": "openai", "model": "gpt-x", "api_key": "sk-secret-value-1234",
            "proxy": "socks5://u:hunter2@127.0.0.1:1080", "retry": {"connect": {"attempts": 5, "interval_ms": 0}}}
    pid = client.post("/api/llm/profiles", json=body).json()["id"]
    [p] = client.get("/api/llm/profiles").json()
    assert p["is_default"] and p["api_key_hint"] == "sk-…1234" and "secret" not in json.dumps(p)
    assert p["proxy"] == "socks5://u:****@127.0.0.1:1080" and p["retry"]["connect"]["attempts"] == 5
    row = client.store.llm_profile(int(pid))
    assert row["api_key"].startswith("v1:") and "sk-secret" not in row["api_key"]
    assert "hunter2" in row["proxy"]

    # saving the masked proxy back keeps the stored one; empty key keeps the stored key
    upd = {**body, "id": pid, "api_key": "", "proxy": p["proxy"], "priority": 3}
    assert client.post("/api/llm/profiles", json=upd).status_code == 200
    row = client.store.llm_profile(int(pid))
    assert "hunter2" in row["proxy"] and row["priority"] == 3 and row["api_key_hint"] == "sk-…1234"
    # moving the endpoint requires re-entering the key
    r = client.post("/api/llm/profiles", json={**upd, "base_url": "https://evil.example/v1"})
    assert r.status_code == 400 and "re-enter" in r.json()["error"]

    # validation
    assert client.post("/api/llm/profiles", json={**body, "format": "nope"}).status_code == 400
    assert client.post("/api/llm/profiles", json={**body, "base_url": "file:///etc"}).status_code == 400
    assert client.post("/api/llm/profiles", json={"name": "gw", "format": "bedrock-gateway", "model": "m",
                                                  "base_url": "https://gw.example"}).status_code == 400

    # second profile; the active one can't be deleted while others exist
    pid2 = client.post("/api/llm/profiles", json={"name": "Local", "format": "ollama", "model": "llama3.2"}).json()["id"]
    assert client.delete(f"/api/llm/profiles/{pid}").status_code == 409
    assert client.put("/api/settings", json={"writer_profile": pid2}).status_code == 200
    assert client.put("/api/settings", json={"writer_profile": "999"}).status_code == 400
    assert client.post(f"/api/llm/profiles/{pid2}/activate").status_code == 200
    assert client.delete(f"/api/llm/profiles/{pid}").status_code == 200
    assert client.get("/api/settings").json()["values"]["writer_profile"] == pid2
    agents = {a["role"]: a for a in client.get("/api/system/agents").json()}
    assert agents["writer"]["profile"] == "Local" and agents["worker"]["model"] == "llama3.2"


def test_pool_and_retry_api(client):
    a = client.post("/api/llm/profiles", json={"name": "A", "format": "openai", "model": "m", "api_key": "k-1"}).json()["id"]
    client.post("/api/llm/profiles", json={"name": "B", "format": "openai", "model": "m", "api_key": "k-2", "priority": 2})
    assert client.put("/api/settings", json={"llm_pool_enabled": True}).status_code == 200
    pool = client.get("/api/llm/pool").json()
    assert pool["enabled"] and [m["name"] for m in pool["chain"]] == ["A", "B"]
    client.store.put_llm_health(int(a), 1, 1, 9e12, "HTTP 402: no balance")
    assert client.get("/api/llm/pool").json()["chain"][0]["state"] == "tripped"
    assert client.post("/api/llm/pool/reset", json={"id": a}).status_code == 200
    assert client.get("/api/llm/pool").json()["chain"][0]["state"] == "ok"

    pol = client.put("/api/llm/retry", json={"connect": {"attempts": -1}, "intent": {"attempts": 4, "interval_ms": 500}})
    assert pol.status_code == 200 and client.get("/api/llm/retry").json()["intent"] == {"attempts": 4, "interval_ms": 500}
    assert client.put("/api/llm/retry", json={"connect": {"attempts": 99}}).status_code == 400


def test_test_and_models_endpoints(client, monkeypatch):
    async def fake_test(p, role_effort="low"):
        return {"ok": True, "latency_ms": 1, "model": p.model, "reply": f"key={p.api_key}"}

    async def fake_models(p):
        return ["a", "b"]

    monkeypatch.setattr(P, "test_connection", fake_test)
    monkeypatch.setattr(P, "list_models", fake_models)
    pid = client.post("/api/llm/profiles", json={"name": "A", "format": "openai", "model": "m", "api_key": "stored-k"}).json()["id"]
    # an empty key field tests with the stored key
    r = client.post("/api/llm/test", json={"format": "openai", "model": "m", "profile_id": pid}).json()
    assert r["ok"] and r["reply"] == "key=stored-k"
    # but never sends it to a different host
    r = client.post("/api/llm/test", json={"format": "openai", "model": "m", "profile_id": pid,
                                           "base_url": "https://elsewhere.example/v1"}).json()
    assert not r["ok"] and "re-enter" in r["error"]
    assert client.post("/api/llm/models", json={"format": "ollama"}).json() == {"ok": True, "models": ["a", "b"]}
    assert not client.post("/api/llm/test", json={"format": "openai", "model": "m"}).json()["ok"]   # no key
