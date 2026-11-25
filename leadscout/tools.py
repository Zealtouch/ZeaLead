"""Graph tools for the planner and the workers.

Quality gates that matter live here in code, not only in prompts:
- report_lead refuses a quote that is not verbatim in the referenced capture,
  posts outside the recency window, and duplicates (it extends instead);
- prove_goal refuses while the measured lead count is below the goal's target;
- add_intent refuses exact duplicates and caps a round at four intents.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .boundary import Envelope
from .connectors.base import Ctx, iso
from .llm import Tool
from .store import INTENT_LEVEL_RANK, Store
from .verify import quote_in_text

MAX_INTENTS_PER_ROUND = 4


def goal_progress(store: Store, cid: int, goal_payload: dict) -> tuple[int, int, str]:
    target = int(goal_payload.get("target_count") or 0)
    min_intent = goal_payload.get("min_intent") or "warm"
    have = len(store.leads(cid, min_intent=min_intent))
    return have, target, min_intent


def _node_view(store: Store, n, env: Envelope | None = None) -> dict:
    v = {"id": n.id, "kind": n.kind, "state": n.state, "summary": n.summary}
    for k in ("platform", "detail", "evidence", "confidence", "target_count", "min_intent"):
        if k in n.payload:
            v[k] = n.payload[k]
    v["parents"] = store.parents(n.id)
    v["yields"] = store.yields(n.id)
    return v


# ---------------------------------------------------------------- planner
def planner_tools(store: Store, cid: int, env: Envelope, round_state: dict) -> list[Tool]:
    async def add_intent(a: dict):
        items = a.get("intents") or []
        existing = {n.summary.strip().lower() for n in store.nodes(cid, "intent")}
        made, refused = [], []
        for it in items:
            if round_state["dispatched"] >= MAX_INTENTS_PER_ROUND:
                refused.append({"summary": it.get("summary"), "why": "round cap of 4 intents reached"})
                continue
            summary = (it.get("summary") or "").strip()
            if not summary:
                continue
            if summary.lower() in existing:
                refused.append({"summary": summary, "why": "an intent with this exact summary already exists"})
                continue
            nid = store.add_node(cid, "intent", {"summary": summary, "platform": it.get("platform"),
                                                 "goal_id": it.get("goal_id"), "priority": int(it.get("priority") or 0)},
                                 "open", origin="planner")
            parents = [int(p) for p in it.get("parent_ids") or []]
            for p in parents:
                store.add_edge(cid, p, nid, "derived_from")
            if not parents and it.get("goal_id"):
                store.add_edge(cid, int(it["goal_id"]), nid, "spawns")
            store.anchor(nid, [int(s) for s in it.get("source_ids") or []])
            existing.add(summary.lower())
            round_state["dispatched"] += 1
            made.append(nid)
        return {"created_intent_ids": made, "refused": refused}

    async def prove_goal(a: dict):
        g = store.get_node(int(a["goal_id"]))
        if not g or g.kind != "goal" or g.campaign_id != cid:
            return {"error": "no such goal"}
        have, target, min_intent = goal_progress(store, cid, g.payload)
        if target and have < target:
            return {"error": f"refused: goal needs {target} {min_intent}+ leads, measured {have}. Dispatch more intents."}
        store.set_state(g.id, "met")
        store.update_payload(g.id, proof=a.get("reason", ""))
        for lead in store.leads(cid, min_intent=min_intent)[: max(target, 1)]:
            store.add_edge(cid, lead["node_id"], g.id, "proves")
        open_goals = store.nodes(cid, "goal", ["open"])
        return {"ok": True, "remaining_open_goals": len(open_goals)}

    async def list_facts(a: dict):
        facts = store.nodes(cid, "fact", ["confirmed"], limit=500, newest_first=True)
        q = (a.get("q") or "").lower()
        if q:
            facts = [f for f in facts if q in json.dumps(f.payload).lower()]
        lim = min(int(a.get("limit", 20)), 50)
        view = [_node_view(store, f) for f in facts[:lim]]
        return env.wrap("facts", json.dumps({"total": len(facts), "facts": view}, ensure_ascii=False))

    async def list_leads(a: dict):
        rows = store.leads(cid, min_intent=a.get("min_intent", "cold"), platform=a.get("platform"),
                           limit=min(int(a.get("limit", 30)), 100))
        view = [{"lead_id": r["node_id"], "platform": r["platform"], "author": r["author"], "intent": r["intent_level"],
                 "fit": r["fit_score"], "pain": r["pain"], "url": r["url"]} for r in rows]
        return env.wrap("leads", json.dumps(view, ensure_ascii=False))

    async def node_detail(a: dict):
        n = store.get_node(int(a["id"]))
        if not n or n.campaign_id != cid:
            return {"error": "no such node"}
        v = _node_view(store, n)
        v["payload"] = n.payload
        return env.wrap("node", json.dumps(v, ensure_ascii=False, default=str))

    async def get_worker_output(a: dict):
        return env.wrap("worker_output", store.worker_output(int(a["intent_id"])))

    async def list_sources(a: dict):
        rows = store.list_sources(kind=a.get("kind"), platform=a.get("platform"), q=a.get("q"),
                                  limit=min(int(a.get("limit", 30)), 100))
        return env.wrap("sources", json.dumps([{k: r[k] for k in ("id", "kind", "platform", "key", "url")} for r in rows]))

    async def todo_write(a: dict):
        items = [{"content": str(i.get("content", "")), "status": i.get("status", "pending")} for i in a.get("items") or []]
        store.set_todos(cid, items)
        return {"ok": True, "count": len(items)}

    return [
        Tool("add_intent",
             "Dispatch up to 4 new search directions this round, in ONE call. Each intent is one sentence: platform + "
             "where (community/site) + query angle + why it should surface buyers.",
             {"type": "object", "properties": {"intents": {"type": "array", "maxItems": 4, "items": {
                 "type": "object", "properties": {
                     "summary": {"type": "string"},
                     "platform": {"type": "string"},
                     "goal_id": {"type": "integer"},
                     "source_ids": {"type": "array", "items": {"type": "integer"},
                                    "description": "community/thread source ids this intent targets"},
                     "parent_ids": {"type": "array", "items": {"type": "integer"},
                                    "description": "facts/intents/leads this direction is derived from"},
                     "priority": {"type": "integer", "description": "higher runs first; default 0"}},
                 "required": ["summary", "platform"]}}},
              "required": ["intents"]}, add_intent),
        Tool("prove_goal", "Mark a goal met. Refused while the measured lead count is below the goal's target.",
             {"type": "object", "properties": {"goal_id": {"type": "integer"}, "reason": {"type": "string"}},
              "required": ["goal_id", "reason"]}, prove_goal),
        Tool("list_facts", "List exploration facts (newest first), optional substring filter.",
             {"type": "object", "properties": {"q": {"type": "string"}, "limit": {"type": "integer"}}}, list_facts),
        Tool("list_leads", "List confirmed leads, best first.",
             {"type": "object", "properties": {"min_intent": {"type": "string", "enum": ["cold", "warm", "hot"]},
                                               "platform": {"type": "string"}, "limit": {"type": "integer"}}}, list_leads),
        Tool("node_detail", "Full payload, parents and yields of one node.",
             {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}, node_detail),
        Tool("get_worker_output", "The final summary a worker wrote for an intent.",
             {"type": "object", "properties": {"intent_id": {"type": "integer"}}, "required": ["intent_id"]}, get_worker_output),
        Tool("list_sources", "Search the source graph (platforms, communities, threads, authors).",
             {"type": "object", "properties": {"kind": {"type": "string", "enum": ["platform", "community", "thread", "author"]},
                                               "platform": {"type": "string"}, "q": {"type": "string"},
                                               "limit": {"type": "integer"}}}, list_sources),
        Tool("todo_write", "Replace your planning todo list (kept across wake-ups).",
             {"type": "object", "properties": {"items": {"type": "array", "items": {
                 "type": "object", "properties": {"content": {"type": "string"},
                                                  "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}},
                 "required": ["content", "status"]}}}, "required": ["items"]}, todo_write),
    ]


# ---------------------------------------------------------------- worker
def worker_tools(ctx: Ctx, env: Envelope, stats: dict) -> list[Tool]:
    store, cid, iid = ctx.store, ctx.campaign_id, ctx.intent_id

    async def record_fact(a: dict):
        nid = store.add_node(cid, "fact", {
            "summary": a["summary"], "detail": a.get("detail", ""), "evidence": a.get("evidence", ""),
            "confidence": a.get("confidence", "observed"), "from_intent": iid,
        }, "confirmed", origin="worker")
        store.add_edge(cid, iid, nid, "yields")
        sids = []
        for c in a.get("communities") or []:
            plat, name = (c.get("platform") or "").lower(), (c.get("name") or "").strip()
            if plat and name:
                sids.append(store.community_source(plat, name, name, c.get("url")))
        store.anchor(nid, sids)
        stats["facts"] += 1
        return {"fact_id": nid, "communities_registered": sids}

    async def report_lead(a: dict):
        cap = store.get_capture(int(a["capture_id"]))
        if not cap or cap["campaign_id"] != cid:
            return {"error": "unknown capture_id; use a capture_id returned by a search/fetch tool in this campaign"}
        ok, why = quote_in_text(a.get("quote", ""), cap["text"])
        if not ok:
            return {"error": why}
        if cap["posted_at"] and cap["posted_at"] < ctx.since_ts:
            return {"error": f"post is from {iso(cap['posted_at'])}, outside the {ctx.recency_days}-day window"}
        level = a.get("intent_level", "cold")
        if level not in INTENT_LEVEL_RANK:
            return {"error": "intent_level must be hot, warm or cold"}
        fit = max(0, min(100, int(a.get("fit_score", 0))))
        dedup = f"{cap['platform']}:{cap['author'].lower()}" if cap.get("author") else cap["url"]
        existing = store.lead_by_key(cid, dedup)
        if existing:
            store.add_lead_evidence(existing["node_id"], cap["id"], a["quote"])
            store.upgrade_lead(existing["node_id"], level, fit)
            store.add_edge(cid, iid, existing["node_id"], "yields")
            return {"extended_existing_lead": existing["node_id"],
                    "note": "same person already recorded; evidence added, level upgraded if higher"}
        summary = f"{cap['author'] or 'unknown'} on {cap['platform']}: {a.get('pain', '')}"[:300]
        nid = store.add_node(cid, "lead", {"summary": summary, "reason": a.get("reason", ""),
                                           "counterevidence": a.get("counterevidence", ""), "from_intent": iid},
                             "confirmed", origin="worker")
        store.insert_lead(cid, nid, dedup_key=dedup, platform=cap["platform"], author=cap["author"],
                          author_url=cap["author_url"], url=cap["url"], quote=a["quote"], posted_at=cap["posted_at"],
                          intent_level=level, fit_score=fit, pain=a.get("pain"), reason=a.get("reason"),
                          suggested_reply=a.get("suggested_reply"), capture_id=cap["id"])
        store.add_edge(cid, iid, nid, "yields")
        sids = []
        meta = json.loads(cap["meta"] or "{}")
        if meta.get("community"):
            sids.append(store.community_source(cap["platform"], meta["community"]))
        if cap.get("author"):
            sids.append(store.upsert_source("author", cap["platform"], cap["author"], cap["author"], cap["author_url"]))
        store.anchor(nid, sids)
        stats["leads"] += 1
        return {"lead_id": nid, "dedup_key": dedup}

    async def list_leads(a: dict):
        rows = store.leads(cid, platform=a.get("platform"), limit=200)
        q = (a.get("author") or "").lower()
        if q:
            rows = [r for r in rows if q in (r["author"] or "").lower()]
        return env.wrap("leads", json.dumps([{"lead_id": r["node_id"], "platform": r["platform"], "author": r["author"],
                                              "intent": r["intent_level"], "url": r["url"]} for r in rows[:50]]))

    async def list_facts(a: dict):
        facts = store.nodes(cid, "fact", ["confirmed"], limit=300, newest_first=True)
        q = (a.get("q") or "").lower()
        if q:
            facts = [f for f in facts if q in json.dumps(f.payload).lower()]
        return env.wrap("facts", json.dumps([{"id": f.id, "summary": f.summary} for f in facts[:20]], ensure_ascii=False))

    return [
        Tool("report_lead",
             "Register one potential customer found in a captured post/comment. Code checks the quote is verbatim in "
             "that capture, the post is inside the recency window, and dedups by platform+author.",
             {"type": "object", "properties": {
                 "capture_id": {"type": "integer"},
                 "quote": {"type": "string", "description": "the author's exact words showing the need (15+ chars)"},
                 "intent_level": {"type": "string", "enum": ["hot", "warm", "cold"]},
                 "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
                 "pain": {"type": "string", "description": "the problem in a short phrase"},
                 "reason": {"type": "string", "description": "why this is a buyer, including the adversarial check"},
                 "counterevidence": {"type": "string", "description": "what argues against (optional)"},
                 "suggested_reply": {"type": "string",
                                     "description": "normally empty: a writer drafts messages for every lead afterwards"}},
              "required": ["capture_id", "quote", "intent_level", "fit_score", "pain", "reason"]}, report_lead),
        Tool("record_fact",
             "Record one consolidated observation for the planner (where buyers gather, which angles work or failed, "
             "competitor complaint themes). Register communities worth mining with `communities`.",
             {"type": "object", "properties": {
                 "summary": {"type": "string"}, "detail": {"type": "string"},
                 "evidence": {"type": "string", "description": "query/tool + the most telling result line(s)"},
                 "confidence": {"type": "string", "enum": ["observed", "inferred"]},
                 "communities": {"type": "array", "items": {"type": "object", "properties": {
                     "platform": {"type": "string"}, "name": {"type": "string"}, "url": {"type": "string"}},
                     "required": ["platform", "name"]}}},
              "required": ["summary", "confidence"]}, record_fact),
        Tool("list_leads", "Check existing leads (dedup before reporting).",
             {"type": "object", "properties": {"platform": {"type": "string"}, "author": {"type": "string"}}}, list_leads),
        Tool("list_facts", "Search existing facts so you do not repeat known work.",
             {"type": "object", "properties": {"q": {"type": "string"}}}, list_facts),
    ]


def connector_tools(ctx: Ctx, env: Envelope, connectors) -> list[Tool]:
    tools = []
    for c in connectors:
        for spec in c.tools():
            async def handler(a: dict, _spec=spec) -> Any:
                out = await _spec.handler(ctx, a)
                if isinstance(out, dict) and "error" in out:
                    return out
                return env.wrap(_spec.name, json.dumps(out, ensure_ascii=False, default=str))
            tools.append(Tool(spec.name, spec.description, spec.schema, handler))
    return tools


def now() -> float:
    return time.time()
