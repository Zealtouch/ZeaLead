"""Console API: accounts, companies, tasks, leads, records, settings, security headers."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from leadscout import auth as A
from leadscout.config import Settings
from leadscout.demo import seed
from leadscout.server import create_app
from leadscout.store import Store

PW = "correct horse battery"


@pytest.fixture
def anon(tmp_path, monkeypatch):
    monkeypatch.setenv("LEADSCOUT_KEYS_DIR", str(tmp_path / "keys"))
    s = Settings.load()
    s.db_path = str(tmp_path / "s.db")
    st = Store(s.db_path)
    with TestClient(create_app(s, st)) as c:
        c.store = st
        yield c


@pytest.fixture
def client(anon):
    r = anon.post("/api/auth/setup", json={"username": "admin", "password": PW})
    assert r.status_code == 200
    anon.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return anon


def test_setup_once_then_login(anon):
    assert anon.get("/api/auth/status").json()["setup_required"] is True
    assert anon.get("/api/campaigns").status_code == 401
    assert anon.post("/api/auth/setup", json={"username": "admin", "password": "short"}).status_code == 400
    assert anon.post("/api/auth/setup", json={"username": "admin", "password": PW}).status_code == 200
    assert anon.get("/api/auth/status").json()["setup_required"] is False
    # setup can't be used a second time to create another admin
    assert anon.post("/api/auth/setup", json={"username": "evil", "password": PW}).status_code == 409
    assert anon.post("/api/auth/login", json={"username": "admin", "password": "wrong password!"}).status_code == 401
    assert anon.post("/api/auth/login", json={"username": "nobody", "password": PW}).status_code == 401
    tok = anon.post("/api/auth/login", json={"username": "ADMIN", "password": PW}).json()["token"]
    me = anon.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["username"] == "admin" and me["role"] == "admin" and "password_hash" not in me


def test_tokens_are_checked(client):
    assert client.get("/api/campaigns").json() == []
    bad = {"Authorization": "Bearer abc.def.ghi"}
    assert client.get("/api/campaigns", headers=bad).status_code == 401
    # a token signed with another key is refused
    forged = A.issue_token(b"x" * 32, client.store.user_by_name("admin"))
    assert client.get("/api/campaigns", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    # an expired token is refused
    old = A.issue_token(A.load_signing_key(client.store.path), client.store.user_by_name("admin"), ttl=-10)
    assert client.get("/api/campaigns", headers={"Authorization": f"Bearer {old}"}).status_code == 401


def test_password_change_signs_out_old_sessions(client):
    old = dict(client.headers)
    r = client.post("/api/auth/password", json={"current": PW, "new": "another long password"})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    assert client.get("/api/auth/me").status_code == 200


def test_login_rate_limit(anon):
    anon.post("/api/auth/setup", json={"username": "admin", "password": PW})
    for _ in range(10):
        anon.post("/api/auth/login", json={"username": "admin", "password": "nope nope nope"})
    assert anon.post("/api/auth/login", json={"username": "admin", "password": PW}).status_code == 429


def test_users_admin_only(client):
    assert client.post("/api/users", json={"username": "bo", "password": PW}).status_code == 200
    tok = client.post("/api/auth/login", json={"username": "bo", "password": PW}).json()["token"]
    member = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/users", headers=member).status_code == 403
    assert client.put("/api/settings", headers=member, json={"workers": "2"}).status_code == 403
    assert client.get("/api/campaigns", headers=member).status_code == 200
    me = client.get("/api/auth/me").json()
    assert client.delete(f"/api/users/{me['id']}").status_code == 400            # not yourself
    assert client.patch(f"/api/users/{me['id']}", json={"role": "member"}).status_code == 400  # last admin


def test_security_headers(client):
    r = client.get("/api/health")
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    assert client.get("/api/does-not-exist").status_code == 404


def test_companies_scope_tasks(client):
    acme = client.post("/api/companies", json={"name": "Acme", "website": "acme.test"}).json()["id"]
    assert client.post("/api/companies", json={"name": "acme"}).status_code == 409
    brief = "product: P\ndescription: d\nideal_customer: i"
    a = client.post("/api/campaigns", json={"brief_yaml": brief, "company_id": acme}).json()["id"]
    client.post("/api/campaigns", json={"brief_yaml": brief})
    assert [c["id"] for c in client.get(f"/api/campaigns?company={acme}").json()] == [a]
    assert len(client.get("/api/campaigns").json()) == 2
    assert client.get("/api/companies").json()[0]["website"] == "https://acme.test"
    assert client.post("/api/campaigns", json={"brief_yaml": brief, "company_id": 999}).status_code == 400
    assert client.delete(f"/api/companies/{acme}").status_code == 200
    assert client.get(f"/api/campaigns/{a}").json()["company_id"] is None


def test_create_campaign_validation(client):
    r = client.post("/api/campaigns", json={"brief": {"product": "X"}})
    assert r.status_code == 400 and "missing" in r.json()["error"]
    r = client.post("/api/campaigns", json={"brief_yaml": "product: P\ndescription: d\nideal_customer: i\ncompetitors: a, b"})
    cid = r.json()["id"]
    c = client.get(f"/api/campaigns/{cid}").json()
    assert c["brief"]["competitors"] == ["a", "b"] and c["status"] == "created"


def test_demo_views(client):
    cid = seed(client.store)
    c = client.get(f"/api/campaigns/{cid}").json()
    assert c["leads"]["hot"] >= 3 and c["goals"][0]["target"] == 12 and c["company_name"]
    g = client.get(f"/api/campaigns/{cid}/graph").json()
    assert {n["kind"] for n in g["nodes"]} == {"goal", "intent", "fact", "lead"}
    assert client.get(f"/api/campaigns/{cid}/communities").json()
    sessions = client.get(f"/api/campaigns/{cid}/sessions").json()["runs"]
    assert {r["role"] for r in sessions} == {"decomposer", "planner", "worker"}
    one = client.get(f"/api/runs/{sessions[-1]['id']}/messages").json()
    assert one["messages"][0]["role"] == "user"
    # the single-session header shows the same token and tool sums as the session list
    for k in ("input_tokens", "output_tokens", "cache_read", "tool_calls"):
        assert one["run"][k] == sessions[-1][k]
    d = client.get("/api/dashboard").json()
    assert d["leads"]["total"] == 9 and len(d["series"]) == 14
    leads = client.get("/api/leads?level=hot").json()
    assert leads["total"] >= 3 and all(x["intent_level"] == "hot" for x in leads["items"])
    lead = client.get(f"/api/leads/{leads['items'][0]['node_id']}").json()
    assert lead["evidence"] and lead["campaign_name"]
    assert client.get("/api/communities").json()["total"] >= 2
    tc = client.get("/api/tool-calls?errors=true").json()
    assert tc["total"] == 1 and client.get(f"/api/tool-calls/{tc['items'][0]['id']}").json()["is_error"] == 1
    lc = client.get("/api/llm-calls").json()
    assert lc["total"] > 0 and client.get(f"/api/llm-calls/{lc['items'][0]['id']}").json()["message"]
    assert client.get("/api/logs").json()["total"] > 0
    assert client.get(f"/api/campaigns/{cid}/report.html").status_code == 200


def test_system_pages(client):
    plats = client.get("/api/system/platforms").json()
    assert any(p["platform"] == "hackernews" and p["enabled"] and p["tools"] for p in plats)
    agents = client.get("/api/system/agents").json()
    assert [a["role"] for a in agents] == ["decomposer", "planner", "worker", "writer"]
    assert any(t["name"] == "add_intent" for t in agents[1]["tools"])
    assert client.get("/api/system/info").json()["users"] == 1


def test_lead_status_and_csv_injection(client):
    cid = seed(client.store)
    lead = client.get(f"/api/leads?campaign={cid}").json()["items"][0]
    assert client.patch(f"/api/leads/{lead['node_id']}", json={"status": "bogus"}).status_code == 400
    assert client.patch(f"/api/leads/{lead['node_id']}", json={"status": "won"}).status_code == 200
    won = client.get("/api/leads?status=won").json()["items"]
    assert [x["node_id"] for x in won] == [lead["node_id"]]
    # the operator can edit a drafted message; the other one is kept
    nid = lead["node_id"]
    before = client.get(f"/api/leads/{nid}").json()
    assert client.patch(f"/api/leads/{nid}", json={"dm_message": "Hi, edited by hand"}).status_code == 200
    after = client.get(f"/api/leads/{nid}").json()
    assert after["dm_message"] == "Hi, edited by hand" and after["message_edited"] == 1
    assert after["suggested_reply"] == before["suggested_reply"]
    assert client.patch(f"/api/leads/{nid}", json={}).status_code == 400
    # attacker-written quote starting with '=' must not become a spreadsheet formula
    client.store._x("UPDATE leads SET quote='=HYPERLINK(\"http://evil\")' WHERE node_id=?", (lead["node_id"],))
    assert "'=HYPERLINK" in client.get(f"/api/campaigns/{cid}/leads.csv").text
    assert "'=HYPERLINK" in client.get("/api/leads.csv").text


def test_settings_refuse_secrets(client):
    assert client.put("/api/settings", json={"ANTHROPIC_API_KEY": "sk-x"}).status_code == 400
    assert client.put("/api/settings", json={"workers": "abc"}).status_code == 400
    assert client.put("/api/settings", json={"workers": "5", "planner_effort": "xhigh"}).status_code == 200
    s = client.get("/api/settings").json()
    assert s["values"]["workers"] == 5 and s["values"]["planner_effort"] == "xhigh"
    assert "sk-" not in str(s)


def test_hint_and_delete(client):
    cid = seed(client.store)
    assert client.post(f"/api/campaigns/{cid}/hints", json={"text": "focus on agencies"}).status_code == 200
    c = client.get(f"/api/campaigns/{cid}").json()
    assert c["hints"][0]["text"] == "focus on agencies"
    assert client.post(f"/api/campaigns/{cid}/pause").status_code == 409
    assert client.delete(f"/api/campaigns/{cid}").status_code == 200
    assert client.get(f"/api/campaigns/{cid}").status_code == 404
