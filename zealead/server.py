"""Console backend: JSON API plus the static Next.js UI, with campaigns running in-process.

Security model (self-hosted, like ZeaLead):
- User accounts. On first start the console asks for an admin account (/setup);
  after that every /api route except health, auth status and login needs a
  signed session token. Passwords are scrypt-hashed; the signing key lives in
  the keys directory, apart from the data.
- Binds to 127.0.0.1 by default. In Docker the published port is bound to
  127.0.0.1 unless ZEALEAD_BIND_ADDR says otherwise.
- API keys are never accepted or returned by the API; they live in .env.
- Collected posts are attacker-written text. The UI renders them as React text
  (escaped), never as HTML, and the CSP forbids loading code from elsewhere.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import io
import logging
import os
import platform as py_platform
import sys
from pathlib import Path
from typing import Any

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import auth as A
from .agents import DECOMPOSER_SYSTEM, PLANNER_SYSTEM, WORKER_SYSTEM
from .boundary import Envelope
from .config import EDITABLE, Settings, normalize_brief
from .connectors import ALL as ALL_CONNECTORS
from .connectors.base import Ctx
from .engine import Engine
from .llm import LLM
from .outreach import WRITER_SYSTEM, draft_for_lead, draft_pending
from .report import render_html
from .store import Store
from .tools import goal_progress, planner_tools, worker_tools

log = logging.getLogger("zealead.server")
WEBUI_DIR = Path(os.environ.get("ZEALEAD_WEBUI_DIR") or Path(__file__).parent / "webui")
LEAD_STATUSES = {"new", "contacted", "replied", "won", "dismissed"}
LEVELS = {"hot", "warm", "cold"}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


class Runner:
    """Campaigns this process is running."""

    def __init__(self, store: Store, settings: Settings):
        self.store = store
        self.settings = settings
        self.engines: dict[int, Engine] = {}
        self.tasks: dict[int, asyncio.Task] = {}
        self.drafting: dict[int, asyncio.Task] = {}
        self.llm_factory = LLM          # tests swap in a scripted model

    def _writer(self) -> tuple[LLM, Settings]:
        eff = self.settings.with_overrides(self.store.get_settings())
        # Drafting on request is an explicit operator action, so it isn't held to the task's token budget.
        return self.llm_factory(self.store, 0), eff

    async def draft_one(self, nid: int, instruction: str | None) -> dict:
        llm, eff = self._writer()
        return await draft_for_lead(llm, self.store, nid, eff.writer_model, eff.writer_effort, instruction)

    def is_drafting(self, cid: int) -> bool:
        t = self.drafting.get(cid)
        return bool(t and not t.done())

    def draft_all(self, cid: int) -> int:
        if self.is_drafting(cid):
            raise HTTPException(409, "messages are already being drafted for this task")
        pending = len(self.store.undrafted_leads(cid, 500))
        if pending:
            llm, eff = self._writer()

            async def go():
                try:
                    await draft_pending(llm, self.store, cid, eff.writer_model, eff.writer_effort, limit=500)
                except Exception:
                    log.exception("drafting messages for task %s failed", cid)

            self.drafting[cid] = asyncio.create_task(go())
        return pending

    def is_running_here(self, cid: int) -> bool:
        t = self.tasks.get(cid)
        return bool(t and not t.done())

    def start(self, cid: int) -> None:
        if self.is_running_here(cid):
            raise HTTPException(409, "task is already running")
        other = self.store.runner_alive(cid)
        if other:
            raise HTTPException(409, f"task is running in another process ({other})")
        settings = self.settings.with_overrides(self.store.get_settings())
        eng = Engine(settings, self.store)
        self.engines[cid] = eng

        async def go():
            try:
                await eng.run(cid, runner=f"console:{os.getpid()}")
            except Exception as e:  # surface failures in the activity feed instead of losing them
                log.exception("campaign %s failed", cid)
                self.store.set_campaign_status(cid, "failed", str(e))
                self.store.log(cid, "system", "error", f"task failed: {e}")

        self.tasks[cid] = asyncio.create_task(go())

    def pause(self, cid: int) -> None:
        eng = self.engines.get(cid)
        if not eng or not self.is_running_here(cid):
            raise HTTPException(409, "task is not running in this console")
        eng.stop(cid)

    async def shutdown(self) -> None:
        for t in self.drafting.values():
            t.cancel()
        for cid, eng in list(self.engines.items()):
            if self.is_running_here(cid):
                eng.stop(cid, "console shut down")
        for t in self.tasks.values():
            if not t.done():
                try:
                    await asyncio.wait_for(t, timeout=15)
                except (asyncio.TimeoutError, Exception):
                    t.cancel()


def _int_or_none(v: Any) -> int | None:
    if v in (None, "", "all"):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        raise HTTPException(400, f"not a number: {v}") from None


def _csv_safe(v: Any) -> Any:
    # Neutralise spreadsheet formula injection from attacker-written text.
    return "'" + v if isinstance(v, str) and v[:1] in "=+-@\t\r" else v


LEAD_CSV_COLS = ["node_id", "campaign_name", "intent_level", "fit_score", "status", "platform", "author", "author_url",
                 "url", "pain", "quote", "reason", "suggested_reply", "dm_message", "message_angle", "posted_at", "created_at"]


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or Settings.load()
    store = store or Store(settings.db_path)
    key = A.load_signing_key(settings.db_path)
    runner = Runner(store, settings)
    limiter = A.LoginLimiter()

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await runner.shutdown()

    app = FastAPI(title="ZeaLead", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.state.store, app.state.runner = store, runner

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    # ------------------------------------------------------------ auth helpers
    def current_user(request: Request) -> dict:
        h = request.headers.get("authorization", "")
        token = h[7:] if h.lower().startswith("bearer ") else ""
        data = A.decode_token(key, token) if token else None
        user = store.user(int(data["uid"])) if data and str(data.get("uid", "")).isdigit() else None
        if not user or A.password_fingerprint(user["password_hash"]) != data.get("pwf"):
            raise HTTPException(401, "sign in required")
        return user

    def admin_user(user: dict = Depends(current_user)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(403, "admin only")
        return user

    def public_user(u: dict) -> dict:
        return {k: u.get(k) for k in ("id", "username", "role", "created_at", "last_login_at")}

    U = [Depends(current_user)]
    ADMIN = [Depends(admin_user)]

    def camp_or_404(cid: int) -> dict:
        c = store.campaign(cid)
        if not c:
            raise HTTPException(404, "no such task")
        return c

    def company_or_400(company_id: Any) -> int | None:
        company_id = _int_or_none(company_id)
        if company_id is not None and not store.company(company_id):
            raise HTTPException(400, "no such company")
        return company_id

    def busy(cid: int) -> bool:
        return runner.is_running_here(cid) or bool(store.runner_alive(cid))

    # ------------------------------------------------------------ meta / auth
    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    @app.get("/api/auth/status")
    def auth_status():
        return {"setup_required": store.user_count() == 0, "version": __version__}

    def _login_response(user: dict) -> dict:
        store.touch_login(user["id"])
        return {"token": A.issue_token(key, user), "user": public_user(user)}

    @app.post("/api/auth/setup")
    def setup(body: dict[str, Any]):
        if store.user_count() > 0:
            raise HTTPException(409, "setup is already done; sign in instead")
        username, password = str(body.get("username") or "").strip(), str(body.get("password") or "")
        if not A.valid_username(username):
            raise HTTPException(400, "username: 1–64 letters, digits or . _ - @")
        if problem := A.password_problem(password):
            raise HTTPException(400, problem)
        uid = store.create_user(username, A.hash_password(password), "admin")
        return _login_response(store.user(uid))

    @app.post("/api/auth/login")
    def login(body: dict[str, Any], request: Request):
        addr = request.client.host if request.client else "?"
        if limiter.blocked(addr):
            raise HTTPException(429, "too many failed sign-ins; wait a few minutes")
        user = store.user_by_name(str(body.get("username") or "").strip())
        if not A.check_login(str(body.get("password") or ""), user["password_hash"] if user else None):
            limiter.fail(addr)
            raise HTTPException(401, "wrong username or password")
        limiter.reset(addr)
        return _login_response(user)

    @app.get("/api/auth/me")
    def me(user: dict = Depends(current_user)):
        return public_user(user)

    @app.post("/api/auth/password")
    def change_password(body: dict[str, Any], user: dict = Depends(current_user)):
        if not A.verify_password(str(body.get("current") or ""), user["password_hash"]):
            raise HTTPException(400, "current password is wrong")
        new = str(body.get("new") or "")
        if problem := A.password_problem(new):
            raise HTTPException(400, problem)
        store.set_user_password(user["id"], A.hash_password(new))
        return _login_response(store.user(user["id"]))

    # ------------------------------------------------------------ users (admin)
    @app.get("/api/users", dependencies=ADMIN)
    def list_users():
        return [public_user(u) for u in store.users()]

    @app.post("/api/users", dependencies=ADMIN)
    def create_user(body: dict[str, Any]):
        username, password = str(body.get("username") or "").strip(), str(body.get("password") or "")
        role = body.get("role") or "member"
        if not A.valid_username(username):
            raise HTTPException(400, "username: 1–64 letters, digits or . _ - @")
        if role not in ("admin", "member"):
            raise HTTPException(400, "role must be admin or member")
        if problem := A.password_problem(password):
            raise HTTPException(400, problem)
        if store.user_by_name(username):
            raise HTTPException(409, "that username is taken")
        return {"id": store.create_user(username, A.hash_password(password), role)}

    @app.patch("/api/users/{uid}")
    def update_user(uid: int, body: dict[str, Any], me_: dict = Depends(admin_user)):
        u = store.user(uid)
        if not u:
            raise HTTPException(404, "no such user")
        if "role" in body:
            if body["role"] not in ("admin", "member"):
                raise HTTPException(400, "role must be admin or member")
            if u["role"] == "admin" and body["role"] != "admin" and store.admin_count() <= 1:
                raise HTTPException(400, "keep at least one admin")
            store.set_user_role(uid, body["role"])
        if body.get("password"):
            if problem := A.password_problem(str(body["password"])):
                raise HTTPException(400, problem)
            store.set_user_password(uid, A.hash_password(str(body["password"])))
        return {"ok": True}

    @app.delete("/api/users/{uid}")
    def delete_user(uid: int, me_: dict = Depends(admin_user)):
        u = store.user(uid)
        if not u:
            raise HTTPException(404, "no such user")
        if uid == me_["id"]:
            raise HTTPException(400, "you can't delete your own account")
        if u["role"] == "admin" and store.admin_count() <= 1:
            raise HTTPException(400, "keep at least one admin")
        store.delete_user(uid)
        return {"ok": True}

    # ------------------------------------------------------------ companies
    def _company_body(body: dict[str, Any]) -> tuple[str, str | None, str | None]:
        name = str(body.get("name") or "").strip()
        if not name or len(name) > 120:
            raise HTTPException(400, "company name is required (max 120 characters)")
        website = str(body.get("website") or "").strip() or None
        if website and not website.startswith(("http://", "https://")):
            website = "https://" + website
        description = str(body.get("description") or "").strip()[:4000] or None
        return name, website, description

    @app.get("/api/companies", dependencies=U)
    def companies():
        return store.companies()

    @app.post("/api/companies", dependencies=U)
    def create_company(body: dict[str, Any]):
        name, website, description = _company_body(body)
        if any(c["name"].lower() == name.lower() for c in store.companies()):
            raise HTTPException(409, "a company with that name exists")
        return {"id": store.create_company(name, website, description)}

    @app.put("/api/companies/{company_id}", dependencies=U)
    def update_company(company_id: int, body: dict[str, Any]):
        if not store.company(company_id):
            raise HTTPException(404, "no such company")
        name, website, description = _company_body(body)
        if any(c["name"].lower() == name.lower() and c["id"] != company_id for c in store.companies()):
            raise HTTPException(409, "a company with that name exists")
        store.update_company(company_id, name, website, description)
        return {"ok": True}

    @app.delete("/api/companies/{company_id}", dependencies=U)
    def delete_company(company_id: int):
        if not store.company(company_id):
            raise HTTPException(404, "no such company")
        store.delete_company(company_id)
        return {"ok": True}

    # ------------------------------------------------------------ dashboard
    @app.get("/api/badges", dependencies=U)
    def badges():
        """Sidebar counters: tasks running now, hot leads nobody has acted on yet."""
        running = sum(1 for c in store.campaigns() if busy(c["id"]))
        new_hot = store.all_leads(level="hot", status="new", limit=1)["total"]
        return {"running": running, "new_hot": new_hot}

    @app.get("/api/dashboard", dependencies=U)
    def dashboard(company: str | None = None):
        out = store.dashboard(_int_or_none(company))
        running = [c for c in store.campaigns(_int_or_none(company)) if busy(c["id"])]
        out["running"] = [{"id": c["id"], "name": c["name"]} for c in running]
        return out

    # ------------------------------------------------------------ tasks (campaigns)
    def summary(c: dict) -> dict:
        cid = c["id"]
        goals = []
        for g in store.nodes(cid, "goal"):
            have, target, mi = goal_progress(store, cid, g.payload)
            goals.append({"id": g.id, "text": g.payload.get("text"), "state": g.state, "have": have, "target": target,
                          "min_intent": mi})
        status = c["status"]
        if status == "running" and not busy(cid):
            status = "paused"  # a crashed or killed runner left the flag behind
        company = store.company(c["company_id"]) if c.get("company_id") else None
        brief = c.get("brief") if isinstance(c.get("brief"), dict) else {}
        return {
            "id": cid, "name": c["name"], "status": status, "end_reason": c.get("end_reason"),
            "created_at": c.get("created_at"), "updated_at": c.get("updated_at"),
            "running_here": runner.is_running_here(cid), "runner": store.runner_alive(cid),
            "company_id": c.get("company_id"), "company_name": company["name"] if company else None,
            "product": brief.get("product"), "goals": goals, "leads": store.lead_counts(cid),
            "intents": {k: store.count_intents(cid, [k]) for k in ("open", "running", "done", "exhausted", "blocked")},
            "tokens": store.tokens_spent(cid),
        }

    @app.get("/api/campaigns", dependencies=U)
    def list_campaigns(company: str | None = None):
        return [summary(store.campaign(c["id"])) for c in store.campaigns(_int_or_none(company))]

    @app.post("/api/campaigns", dependencies=U)
    def create_campaign(body: dict[str, Any]):
        try:
            brief = yaml.safe_load(body["brief_yaml"]) if body.get("brief_yaml") else body.get("brief") or {}
            if not isinstance(brief, dict):
                raise ValueError("brief must be a mapping")
            brief = normalize_brief(brief)
        except (ValueError, yaml.YAMLError) as e:
            raise HTTPException(400, str(e)) from None
        cid = store.create_campaign(brief["name"], brief, company_or_400(body.get("company_id")))
        if body.get("start"):
            runner.start(cid)
        return {"id": cid}

    @app.get("/api/campaigns/{cid}", dependencies=U)
    def get_campaign(cid: int):
        c = camp_or_404(cid)
        out = summary(c)
        out["brief"] = c["brief"]
        out["constraints"] = store.constraints(cid)
        out["todos"] = store.get_todos(cid)
        out["usage"] = store.usage_summary(cid)
        out["coverage"] = store.community_coverage(cid)
        out["hints"] = [{"id": h.id, "text": h.summary, "state": h.state, "created_at": h.created_at}
                        for h in store.nodes(cid, "hint")]
        yields: dict[str, dict] = {}
        for i in store.intent_rows(cid):
            if i["state"] in ("done", "exhausted", "blocked"):
                r = yields.setdefault(i["platform"] or "?", {"intents": 0, "leads": 0})
                r["intents"] += 1
                r["leads"] += i["leads"]
        out["platform_yield"] = yields
        return out

    @app.put("/api/campaigns/{cid}/brief", dependencies=U)
    def update_brief(cid: int, body: dict[str, Any]):
        camp_or_404(cid)
        if busy(cid):
            raise HTTPException(409, "pause the task before editing its brief")
        try:
            brief = yaml.safe_load(body["brief_yaml"]) if body.get("brief_yaml") else body.get("brief") or {}
            if not isinstance(brief, dict):
                raise ValueError("brief must be a mapping")
            brief = normalize_brief(brief)
        except (ValueError, yaml.YAMLError) as e:
            raise HTTPException(400, str(e)) from None
        store.update_brief(cid, brief, brief["name"])
        return {"ok": True}

    @app.put("/api/campaigns/{cid}/company", dependencies=U)
    def set_company(cid: int, body: dict[str, Any]):
        camp_or_404(cid)
        store.set_campaign_company(cid, company_or_400(body.get("company_id")))
        return {"ok": True}

    @app.post("/api/campaigns/{cid}/start", dependencies=U)
    def start(cid: int):
        camp_or_404(cid)
        runner.start(cid)
        return {"ok": True}

    @app.post("/api/campaigns/{cid}/pause", dependencies=U)
    def pause(cid: int):
        camp_or_404(cid)
        runner.pause(cid)
        return {"ok": True}

    @app.delete("/api/campaigns/{cid}", dependencies=U)
    def delete(cid: int):
        camp_or_404(cid)
        if busy(cid):
            raise HTTPException(409, "pause the task before deleting it")
        store.delete_campaign(cid)
        return {"ok": True}

    @app.post("/api/campaigns/{cid}/hints")
    def add_hint(cid: int, body: dict[str, Any], user: dict = Depends(current_user)):
        camp_or_404(cid)
        text = str(body.get("text") or "").strip()
        if not text:
            raise HTTPException(400, "empty hint")
        nid = store.add_node(cid, "hint", {"summary": text[:1000], "text": text[:1000], "by": user["username"]},
                             "active", origin="human")
        store.log(cid, "operator", "hint", f"{user['username']}: {text[:300]}", text)
        eng = runner.engines.get(cid)
        if eng and runner.is_running_here(cid):
            eng.notify()
        return {"id": nid}

    @app.get("/api/campaigns/{cid}/intents", dependencies=U)
    def intents(cid: int):
        camp_or_404(cid)
        return store.intent_rows(cid)

    @app.get("/api/campaigns/{cid}/sessions", dependencies=U)
    def sessions(cid: int):
        camp_or_404(cid)
        return {"runs": store.runs(cid), "usage": store.usage_summary(cid), "running": busy(cid)}

    @app.get("/api/runs/{rid}/messages", dependencies=U)
    def run_messages(rid: int, after: int = 0):
        r = store.run(rid)
        if not r:
            raise HTTPException(404, "no such session")
        return {"run": r, "messages": store.run_messages(rid, after=after)}

    @app.get("/api/campaigns/{cid}/activity", dependencies=U)
    def activity(cid: int, after: int = 0, intent: int | None = None, limit: int = 200):
        camp_or_404(cid)
        return store.activity(cid, after=after, intent_id=intent, limit=min(limit, 1000))

    @app.get("/api/activity/{aid}", dependencies=U)
    def activity_detail(aid: int):
        a = store.activity_detail(aid)
        if not a:
            raise HTTPException(404, "no such activity")
        return a

    @app.get("/api/campaigns/{cid}/graph", dependencies=U)
    def graph(cid: int):
        camp_or_404(cid)
        return store.graph(cid)

    @app.get("/api/campaigns/{cid}/communities", dependencies=U)
    def communities(cid: int):
        camp_or_404(cid)
        return store.community_rows(cid)

    @app.get("/api/campaigns/{cid}/report.html", dependencies=U)
    def report(cid: int):
        camp_or_404(cid)
        return HTMLResponse(render_html(store, cid), headers={
            "Content-Disposition": f'attachment; filename="zealead-task-{cid}-report.html"'})

    @app.get("/api/nodes/{nid}", dependencies=U)
    def node(nid: int):
        n = store.get_node(nid)
        if not n:
            raise HTTPException(404, "no such node")
        anchored = store.anchored_sources(n.id)
        out = {"id": n.id, "campaign_id": n.campaign_id, "kind": n.kind, "state": n.state, "payload": n.payload,
               "origin": n.origin, "owner": n.owner, "created_at": n.created_at, "updated_at": n.updated_at,
               "parents": [{"id": p, "kind": (x.kind if (x := store.get_node(p)) else "?"), "summary": x.summary if x else ""}
                           for p in store.parents(n.id) + store.producers(n.id)],
               "yields": [{"id": y, "kind": (x.kind if (x := store.get_node(y)) else "?"), "summary": x.summary if x else ""}
                          for y in store.yields(n.id)],
               "sources": store.list_sources(ids=anchored) if anchored else []}
        if n.kind == "intent":
            out["worker_output"] = store.worker_output(n.id)
            out["runs"] = [r for r in store.runs(n.campaign_id) if r["intent_id"] == n.id]
        if n.kind == "lead":
            out["lead"] = store.lead(n.id)
            out["evidence"] = store.lead_evidence_rows(n.id)
        return out

    # ------------------------------------------------------------ leads (cross-task)
    def _lead_filters(company, campaign, level, status, platform):
        if level and level not in LEVELS:
            raise HTTPException(400, "level must be hot, warm or cold")
        if status and status not in LEAD_STATUSES:
            raise HTTPException(400, f"status must be one of {sorted(LEAD_STATUSES)}")
        return dict(company_id=_int_or_none(company), cid=_int_or_none(campaign), level=level or None,
                    status=status or None, platform=platform or None)

    @app.get("/api/leads", dependencies=U)
    def all_leads(company: str | None = None, campaign: str | None = None, level: str | None = None,
                  status: str | None = None, platform: str | None = None, q: str | None = None, sort: str = "level",
                  offset: int = 0, limit: int = 50):
        f = _lead_filters(company, campaign, level, status, platform)
        return store.all_leads(**f, q=q or None, sort=sort, offset=max(0, offset), limit=min(max(1, limit), 500))

    @app.get("/api/leads/stats", dependencies=U)
    def lead_stats(company: str | None = None, campaign: str | None = None):
        return store.lead_stats(_int_or_none(company), _int_or_none(campaign))

    @app.get("/api/leads.csv", dependencies=U)
    def leads_csv(company: str | None = None, campaign: str | None = None, level: str | None = None,
                  status: str | None = None, platform: str | None = None, q: str | None = None):
        f = _lead_filters(company, campaign, level, status, platform)
        rows = store.all_leads(**f, q=q or None, sort="level", limit=100000)["items"]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=LEAD_CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _csv_safe(v) for k, v in r.items()})
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="zealead-leads.csv"'})

    @app.get("/api/leads/{nid}", dependencies=U)
    def get_lead(nid: int):
        lead = store.lead(nid)
        if not lead:
            raise HTTPException(404, "no such lead")
        c = store.campaign(lead["campaign_id"])
        lead["campaign_name"] = c["name"] if c else None
        lead["evidence"] = store.lead_evidence_rows(nid)
        n = store.get_node(nid)
        lead["payload"] = n.payload if n else {}
        lead["producers"] = store.producers(nid)
        return lead

    @app.patch("/api/leads/{nid}", dependencies=U)
    def patch_lead(nid: int, body: dict[str, Any]):
        if not store.lead(nid):
            raise HTTPException(404, "no such lead")
        edits = {k: body[k] for k in ("suggested_reply", "dm_message") if k in body}
        if "status" not in body and not edits:
            raise HTTPException(400, "nothing to change: send status, suggested_reply or dm_message")
        if "status" in body:
            if body["status"] not in LEAD_STATUSES:
                raise HTTPException(400, f"status must be one of {sorted(LEAD_STATUSES)}")
            store.set_lead_status(nid, body["status"])
        for k, v in edits.items():
            if v is not None and (not isinstance(v, str) or len(v) > 4000):
                raise HTTPException(400, f"{k} must be text under 4000 characters")
        if edits:
            store.edit_draft(nid, reply=edits.get("suggested_reply"), dm=edits.get("dm_message"))
        return {"ok": True}

    @app.post("/api/leads/{nid}/draft", dependencies=U)
    async def draft_lead(nid: int, body: dict[str, Any] | None = None):
        if not store.lead(nid):
            raise HTTPException(404, "no such lead")
        instruction = (body or {}).get("instruction")
        if instruction is not None and (not isinstance(instruction, str) or len(instruction) > 500):
            raise HTTPException(400, "instruction must be text under 500 characters")
        r = await runner.draft_one(nid, instruction or None)
        if not r["ok"]:
            raise HTTPException(502, f"no messages drafted: {r['error']}")
        return get_lead(nid)

    @app.post("/api/campaigns/{cid}/draft-messages", dependencies=U)
    def draft_campaign(cid: int):
        camp_or_404(cid)
        if runner.is_running_here(cid) and effective().auto_draft:
            raise HTTPException(409, "the running task is already drafting messages for new leads")
        return {"queued": runner.draft_all(cid)}

    @app.get("/api/campaigns/{cid}/leads.csv", dependencies=U)
    def campaign_leads_csv(cid: int):
        camp_or_404(cid)
        return leads_csv(campaign=str(cid))

    # ------------------------------------------------------------ communities, records, logs
    @app.get("/api/communities", dependencies=U)
    def all_communities(company: str | None = None, platform: str | None = None, q: str | None = None,
                        offset: int = 0, limit: int = 50):
        return store.all_communities(_int_or_none(company), platform or None, q or None, max(0, offset),
                                     min(max(1, limit), 500))

    @app.get("/api/tool-calls", dependencies=U)
    def tool_calls(company: str | None = None, campaign: str | None = None, tool: str | None = None,
                   errors: bool = False, run: str | None = None, offset: int = 0, limit: int = 50):
        return store.tool_call_list(_int_or_none(company), _int_or_none(campaign), tool or None, errors,
                                    _int_or_none(run), max(0, offset), min(max(1, limit), 500))

    @app.get("/api/tool-calls/{tid}", dependencies=U)
    def tool_call(tid: int):
        t = store.tool_call(tid)
        if not t:
            raise HTTPException(404, "no such tool call")
        return t

    @app.get("/api/llm-calls", dependencies=U)
    def llm_calls(company: str | None = None, campaign: str | None = None, role: str | None = None,
                  model: str | None = None, offset: int = 0, limit: int = 50):
        return store.llm_call_list(_int_or_none(company), _int_or_none(campaign), role or None, model or None,
                                   max(0, offset), min(max(1, limit), 500))

    @app.get("/api/llm-calls/{uid}", dependencies=U)
    def llm_call(uid: int):
        c = store.llm_call(uid)
        if not c:
            raise HTTPException(404, "no such model call")
        return c

    @app.get("/api/logs", dependencies=U)
    def logs(company: str | None = None, campaign: str | None = None, role: str | None = None,
             kind: str | None = None, q: str | None = None, offset: int = 0, limit: int = 100):
        return store.logs(_int_or_none(company), _int_or_none(campaign), role or None, kind or None, q or None,
                          max(0, offset), min(max(1, limit), 500))

    # ------------------------------------------------------------ system
    def effective() -> Settings:
        return settings.with_overrides(store.get_settings())

    @app.get("/api/settings", dependencies=U)
    def get_settings():
        eff = effective()
        llm_ok = bool(settings.env.get("ANTHROPIC_API_KEY") or settings.env.get("ANTHROPIC_AUTH_TOKEN"))
        return {"values": {k: getattr(eff, attr) for k, (attr, _) in EDITABLE.items()},
                "overrides": store.get_settings(), "anthropic_configured": llm_ok,
                "fallbacks": os.environ.get("ZEALEAD_FALLBACKS", "default") != "off"}

    @app.put("/api/settings", dependencies=ADMIN)
    def put_settings(body: dict[str, Any]):
        bad = [k for k in body if k not in EDITABLE]
        if bad:
            raise HTTPException(400, f"not editable here: {', '.join(bad)} (API keys belong in .env)")
        for k, v in body.items():
            kind = EDITABLE[k][1]
            if v not in (None, ""):
                try:
                    kind(v)
                except ValueError:
                    raise HTTPException(400, f"{k} must be {kind.__name__}") from None
            store.set_setting(k, None if v in (None, "") else str(v))
        return {"ok": True, "note": "applies to tasks started from now on"}

    @app.get("/api/system/platforms", dependencies=U)
    def platforms():
        out = []
        for cls in ALL_CONNECTORS:
            c = cls(settings.env)
            ok, why = c.enabled()
            out.append({"platform": c.platform, "label": c.label, "enabled": ok, "missing": "" if ok else why,
                        "doc": (cls.__doc__ or sys.modules[cls.__module__].__doc__ or "").strip().split("\n")[0],
                        "tools": [{"name": t.name, "description": t.description, "schema": t.schema}
                                  for t in c.tools()]})
        return out

    @app.get("/api/system/agents", dependencies=U)
    def agents():
        eff = effective()
        env = Envelope()
        ptools = planner_tools(store, 0, env, {"dispatched": 0})
        wtools = worker_tools(Ctx(store, None, 0, None, 30, {}), env, {})

        def tl(ts):
            return [{"name": t.name, "description": t.description} for t in ts]

        return [
            {"role": "decomposer", "title": "Goal decomposer", "model": eff.planner_model, "effort": "medium",
             "max_turns": 4, "description": "Turns a brief into countable lead goals and operator constraints.",
             "system": DECOMPOSER_SYSTEM, "tools": [{"name": "set_goals", "description": "Record the lead goals."},
                                                    {"name": "set_constraints",
                                                     "description": "Record allow/deny constraints."}]},
            {"role": "planner", "title": "Planner", "model": eff.planner_model, "effort": eff.planner_effort,
             "max_turns": eff.planner_max_turns,
             "description": "Wakes on every graph change, judges goals and dispatches up to 4 search intents per round.",
             "system": PLANNER_SYSTEM, "tools": tl(ptools)},
            {"role": "worker", "title": "Worker", "model": eff.worker_model, "effort": eff.worker_effort,
             "max_turns": eff.intent_max_turns, "count": eff.workers,
             "description": "Claims one intent, searches the platforms, reports verified leads and facts, then stops.",
             "system": WORKER_SYSTEM, "tools": tl(wtools) + [{"name": "(platform tools)",
                                                              "description": "Every enabled platform's search tools."}]},
            {"role": "writer", "title": "Message writer", "model": eff.writer_model, "effort": eff.writer_effort,
             "max_turns": 4,
             "description": ("Drafts a personalised public reply and direct message for each lead from that person's "
                             "own post" + (" as leads are found." if eff.auto_draft else " when you ask (auto-draft is off).")),
             "system": WRITER_SYSTEM, "tools": [{"name": "save_messages", "description": (
                 "Save both drafts. Code checks length, that the product is named, that the only link is the "
                 "product URL, and that the messages aren't near-copies of another lead's.")}]},
        ]

    @app.get("/api/system/info", dependencies=U)
    def info():
        return {"version": __version__, "python": py_platform.python_version(), "db_path": settings.db_path,
                "keys_dir": str(A.keys_dir(settings.db_path)), "companies": len(store.companies()),
                "tasks": len(store.campaigns()), "users": store.user_count(), "webui": WEBUI_DIR.exists()}

    @app.get("/api/brief-template", dependencies=U)
    def brief_template():
        return {"yaml": (Path(__file__).parent / "brief_template.yaml").read_text()}

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_404(path: str):
        raise HTTPException(404, "no such endpoint")

    # ------------------------------------------------------------ UI (Next.js static export)
    if (WEBUI_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=WEBUI_DIR, html=True), name="ui")
    else:
        @app.get("/")
        def no_ui():
            return HTMLResponse(
                "<!doctype html><title>ZeaLead</title><body style='font-family:system-ui;padding:3rem'>"
                "<h1>ZeaLead API is running</h1><p>The console UI isn't built into this install. "
                "Run it with Docker (<code>./start.sh</code>), or build it: "
                "<code>cd web &amp;&amp; npm ci &amp;&amp; npm run build:static</code>, "
                "then copy <code>web/out</code> to <code>zealead/webui</code>.</p>")

    return app


def serve(host: str = "127.0.0.1", port: int = 8790) -> None:
    import uvicorn
    settings = Settings.load()
    store = Store(settings.db_path)
    app = create_app(settings, store)
    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print("\n  ZeaLead console")
    print(f"  ▸ open     http://{shown}:{port}")
    if store.user_count() == 0:
        print("  ▸ first run: open the console to create the admin account")
    print(f"  ▸ database {settings.db_path}\n", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning", proxy_headers=False)
