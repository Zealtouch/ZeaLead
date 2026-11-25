"""Command line interface."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone

from . import __version__
from .config import Settings, load_brief
from .connectors import available
from .engine import Engine
from .report import render_html
from .store import Store


def _fmt_ts(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else ""


def cmd_platforms(a, s: Settings, st: Store):
    brief = load_brief(a.brief)
    on, off = available(s.env, brief)
    print("Enabled:")
    for c in on:
        print(f"  ✔ {c.label}")
    print("Not enabled:")
    for why in off:
        print(f"  ✘ {why}")


def _company_id(st: Store, name: str | None) -> int | None:
    if not name:
        return None
    for c in st.companies():
        if c["name"].lower() == name.lower():
            return c["id"]
    return st.create_company(name)


def cmd_run(a, s: Settings, st: Store):
    brief = load_brief(a.brief)
    cid = st.create_campaign(brief["name"], brief, _company_id(st, a.company))
    print(f"campaign #{cid} created: {brief['name']}")
    _run(cid, s, st)


def cmd_resume(a, s: Settings, st: Store):
    if not st.campaign(a.campaign):
        sys.exit("no such campaign")
    _run(a.campaign, s, st)


def _run(cid: int, s: Settings, st: Store):
    eng = Engine(s.with_overrides(st.get_settings()), st)
    try:
        reason = asyncio.run(eng.run(cid))
    except RuntimeError as e:
        sys.exit(str(e))
    except KeyboardInterrupt:
        st.set_campaign_status(cid, "paused", "interrupted by operator")
        print(f"\npaused. Resume with: leadscout resume {cid}")
        return
    print(f"\ncampaign #{cid} finished: {reason}")
    cmd_status(argparse.Namespace(campaign=cid), s, st)


def cmd_status(a, s: Settings, st: Store):
    c = st.campaign(a.campaign)
    if not c:
        sys.exit("no such campaign")
    from .tools import goal_progress
    print(f"#{c['id']} {c['name']} — {c['status']}" + (f" ({c['end_reason']})" if c["end_reason"] else ""))
    for g in st.nodes(c["id"], "goal"):
        have, target, mi = goal_progress(st, c["id"], g.payload)
        print(f"  goal #{g.id} [{g.state}] {have}/{target} {mi}+ — {g.payload.get('text')}")
    counts = {k: st.count_intents(c["id"], [k]) for k in ("open", "running", "done", "exhausted", "blocked")}
    print(f"  intents: {counts}")
    lc = st.lead_counts(c["id"])
    print(f"  leads: hot={lc['hot']} warm={lc['warm']} cold={lc['cold']}  by platform: {json.dumps(lc['by_platform'])}")
    u = st.usage_summary(c["id"])
    print(f"  LLM: {u['calls']} calls, input {u['i']:,}, output {u['o']:,}, cache read {u['cr']:,}, cache write {u['cw']:,}")


def cmd_leads(a, s: Settings, st: Store):
    rows = st.leads(a.campaign, min_intent=a.min, platform=a.platform)
    if a.csv:
        cols = ["node_id", "intent_level", "fit_score", "platform", "author", "author_url", "url", "posted",
                "pain", "quote", "reason", "suggested_reply", "dm_message", "status"]
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                r = dict(r)
                r["posted"] = _fmt_ts(r.get("posted_at"))
                w.writerow({k: r.get(k) for k in cols})
        print(f"wrote {len(rows)} leads to {a.csv}")
        return
    for r in rows:
        print(f"#{r['node_id']:<5} {r['intent_level']:<4} fit={r['fit_score']:<3} {r['platform']:<12} "
              f"{(r['author'] or '?'):<22} {r['pain'] or ''}")
        print(f"       {r['url']}")
        print(f"       \"{(r['quote'] or '')[:160]}\"")
        if a.messages:
            for label, k in (("reply", "suggested_reply"), ("DM", "dm_message")):
                if r.get(k):
                    print(f"       {label}: " + r[k].replace("\n", "\n              "))
            if r.get("message_note"):
                print(f"       (skipped: {r['message_note']})")


def cmd_draft(a, s: Settings, st: Store):
    from .llm import LLM
    from .outreach import draft_for_lead, draft_pending
    s = s.with_overrides(st.get_settings())
    llm = LLM(st, 0)
    if a.lead:
        r = asyncio.run(draft_for_lead(llm, st, a.lead, s.writer_model, s.writer_effort, a.instruction))
        if not r["ok"]:
            sys.exit(f"no messages drafted: {r['error']}")
        lead = st.lead(a.lead)
        print(f"reply:\n{lead['suggested_reply'] or '(skipped)'}\n\nDM:\n{lead['dm_message'] or '(skipped)'}")
        return
    if a.campaign is None:
        sys.exit("give a campaign id, or --lead N")
    n = asyncio.run(draft_pending(llm, st, a.campaign, s.writer_model, s.writer_effort, limit=500))
    print(f"drafted messages for {n} lead(s); see them with: leadscout leads {a.campaign} --messages")


def cmd_report(a, s: Settings, st: Store):
    html = render_html(st, a.campaign)
    with open(a.out, "w") as f:
        f.write(html)
    print(f"wrote {a.out}")


def cmd_hint(a, s: Settings, st: Store):
    st.add_node(a.campaign, "hint", {"summary": a.text, "text": a.text}, "active", origin="human")
    print("hint queued; a running campaign picks it up at the next planner round (or on resume)")


def cmd_mark(a, s: Settings, st: Store):
    st.set_lead_status(a.lead, a.status)
    print(f"lead #{a.lead} → {a.status}")


def cmd_graph(a, s: Settings, st: Store):
    cid = a.campaign
    for g in st.nodes(cid, "goal"):
        print(f"goal #{g.id} [{g.state}] {g.payload.get('text')}")
    for n in st.nodes(cid, "intent"):
        print(f"  intent #{n.id} [{n.state}] ({n.payload.get('platform')}) parents={st.parents(n.id)}")
        print(f"     {n.summary}")
        for y in st.yields(n.id):
            x = st.get_node(y)
            if x:
                print(f"     └─ {x.kind} #{x.id}: {x.summary[:140]}")


def cmd_serve(a, s: Settings, st: Store):
    from .server import serve
    serve(a.host, a.port)


def cmd_demo(a, s: Settings, st: Store):
    from .demo import seed
    cid = seed(st)
    print(f"sample campaign #{cid} created (fictional data). Run `leadscout serve` and open it in the console.")


def _ask_password() -> str:
    import getpass

    from .auth import password_problem
    while True:
        pw = getpass.getpass("new password: ")
        if problem := password_problem(pw):
            print(problem)
            continue
        if getpass.getpass("repeat: ") != pw:
            print("passwords don't match")
            continue
        return pw


def cmd_user(a, s: Settings, st: Store):
    from .auth import hash_password, valid_username
    if a.action == "list":
        for u in st.users():
            print(f"#{u['id']} {u['username']} ({u['role']})")
        return
    if not a.username:
        sys.exit("username required")
    u = st.user_by_name(a.username)
    if a.action == "add":
        if u:
            sys.exit("that username exists")
        if not valid_username(a.username):
            sys.exit("username: 1–64 letters, digits or . _ - @")
        st.create_user(a.username, hash_password(_ask_password()), "admin" if a.admin else "member")
        print(f"user {a.username} created")
    elif a.action == "reset-password":
        if not u:
            sys.exit("no such user")
        st.set_user_password(u["id"], hash_password(_ask_password()))
        print(f"password changed for {a.username}; their existing sessions are signed out")


def cmd_list(a, s: Settings, st: Store):
    for c in st.campaigns():
        print(f"#{c['id']} {c['name']} — {c['status']} {c['end_reason'] or ''}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="leadscout", description="Autonomous multi-platform lead finder")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("serve", help="start the web console")
    sp.add_argument("--host", default=os.environ.get("LEADSCOUT_BIND_ADDR", "127.0.0.1"))
    sp.add_argument("--port", type=int, default=int(os.environ.get("LEADSCOUT_PORT", "8790")))
    sp.set_defaults(fn=cmd_serve)
    sp = sub.add_parser("demo", help="add a sample campaign with fictional data, to try the console")
    sp.set_defaults(fn=cmd_demo)
    sp = sub.add_parser("platforms", help="show which platform connectors are enabled")
    sp.add_argument("brief")
    sp.set_defaults(fn=cmd_platforms)
    sp = sub.add_parser("run", help="create a campaign from a brief and run it")
    sp.add_argument("brief")
    sp.add_argument("--company", help="company the campaign belongs to (created if new)")
    sp.set_defaults(fn=cmd_run)
    sp = sub.add_parser("resume", help="continue a paused or stopped campaign")
    sp.add_argument("campaign", type=int)
    sp.set_defaults(fn=cmd_resume)
    sp = sub.add_parser("list", help="list campaigns")
    sp.set_defaults(fn=cmd_list)
    sp = sub.add_parser("status")
    sp.add_argument("campaign", type=int)
    sp.set_defaults(fn=cmd_status)
    sp = sub.add_parser("leads", help="print or export leads")
    sp.add_argument("campaign", type=int)
    sp.add_argument("--min", default="cold", choices=["cold", "warm", "hot"])
    sp.add_argument("--platform")
    sp.add_argument("--csv")
    sp.add_argument("--messages", action="store_true", help="also print each lead's drafted reply and DM")
    sp.set_defaults(fn=cmd_leads)
    sp = sub.add_parser("draft", help="draft personalised messages for leads that have none (or one lead)")
    sp.add_argument("campaign", type=int, nargs="?")
    sp.add_argument("--lead", type=int, help="draft or rewrite the messages for this one lead")
    sp.add_argument("--instruction", help="with --lead: e.g. 'shorter, mention the free trial'")
    sp.set_defaults(fn=cmd_draft)
    sp = sub.add_parser("report", help="write an HTML lead report")
    sp.add_argument("campaign", type=int)
    sp.add_argument("-o", "--out", default="leads-report.html")
    sp.set_defaults(fn=cmd_report)
    sp = sub.add_parser("hint", help="steer the planner, e.g. 'focus on agencies on LinkedIn'")
    sp.add_argument("campaign", type=int)
    sp.add_argument("text")
    sp.set_defaults(fn=cmd_hint)
    sp = sub.add_parser("mark", help="track outreach status of a lead")
    sp.add_argument("lead", type=int)
    sp.add_argument("status", choices=["new", "contacted", "replied", "won", "dismissed"])
    sp.set_defaults(fn=cmd_mark)
    sp = sub.add_parser("user", help="manage console accounts (list, add, reset-password)")
    sp.add_argument("action", choices=["list", "add", "reset-password"])
    sp.add_argument("username", nargs="?")
    sp.add_argument("--admin", action="store_true", help="with add: make the user an admin")
    sp.set_defaults(fn=cmd_user)
    sp = sub.add_parser("graph", help="print the exploration graph")
    sp.add_argument("campaign", type=int)
    sp.set_defaults(fn=cmd_graph)
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    s = Settings.load()
    st = Store(s.db_path)
    a.fn(a, s, st)


if __name__ == "__main__":
    main()
