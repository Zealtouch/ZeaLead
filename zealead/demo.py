"""Seed a sample campaign so the console can be explored without keys or API spend.

Everything here is fictional: handles are invented and every link points to
example.com. The campaign is labelled as sample data.
"""

from __future__ import annotations

import time

from .store import Store

BRIEF = {
    "name": "Sample data: Acme Invoicing",
    "product": "Acme Invoicing (fictional)",
    "url": "https://example.com",
    "description": "Invoicing and automatic payment reminders for freelancers and small agencies.",
    "ideal_customer": "Freelancers, consultants and agencies with 1-30 people who bill clients monthly.",
    "pain_points": ["clients pay late", "current tool too expensive", "manual invoicing in spreadsheets"],
    "competitors": ["CompetitorOne", "CompetitorTwo"],
    "keywords": ["invoicing software", "late payments", "payment reminders"],
    "platforms": [], "exclude_platforms": [], "recency_days": 45,
    "objective": "Find 12 warm or hot leads (sample)", "target_leads": 12,
    "notes": "B2B only. This campaign is generated sample data.",
    "outreach": {"sender": "Sam, founder of Acme Invoicing", "tone": "friendly, plain, no hype",
                 "offer": "a free 30-day trial"},
}

# Hand-written sample drafts for the hot leads (keyed by author); the rest are left for the writer,
# so the console shows both states.
DRAFTS = {
    "sample_designer_mia": (
        "Three clients at 60 days in one quarter is rough. What helped me most: put the due date and a late fee "
        "in the invoice itself, then send reminders on a fixed schedule (3 days before, on the day, 7 days after) "
        "so it never feels personal. Disclosure: I built Acme Invoicing (fictional), which automates exactly that "
        "schedule, but even a calendar reminder works.",
        "Hi Mia, saw your r/freelance post about three clients paying 60 days late this quarter. Polite, automatic "
        "reminders are the main thing Acme Invoicing (fictional) does: you set the schedule once and it follows up "
        "for you. I'm Sam, the founder. If you want to try it on those three invoices, there's a free 30-day trial "
        "at https://example.com. Would that help?",
        "three clients 60 days late this quarter; happy to pay for automatic reminders"),
    "sample_founder_lee": (
        "For a 6-person consultancy I'd shortlist on two things: native Stripe sync (so paid invoices close "
        "themselves) and reminder schedules you can set per client. Disclosure: I work on Acme Invoicing "
        "(fictional), which does both; CompetitorOne and CompetitorTwo are worth a look too.",
        "Hi Lee, read your Ask HN about choosing an invoicing tool for your 6-person consultancy this month, with "
        "Stripe sync and reminders as must-haves. Acme Invoicing (fictional) covers both, and I'm happy to walk "
        "you through how other small consultancies set it up. I'm Sam, the founder. Want a 15-minute look, or the "
        "free 30-day trial to test it yourself?",
        "evaluating tools this month; Stripe sync and reminders are must-haves"),
    "sample-agency-owner-ravi": (
        "Late payers hitting agency cash flow before Q1 is a common story. Two things that move the needle: deposits "
        "on new projects, and reminders that go out automatically so nobody has to chase. Disclosure: I'm the founder "
        "of Acme Invoicing (fictional), which handles the reminder side.",
        "Hi Ravi, your post about late payers wrecking agency cash flow, and wanting a better invoicing setup before "
        "Q1, caught my eye. I'm Sam, founder of Acme Invoicing (fictional): it sends the follow-ups automatically and "
        "shows who owes what at a glance. There's a free 30-day trial if you want to set it up before the quarter "
        "starts. Open to a quick chat about your setup?",
        "cash flow hit by late payers; wants a new setup before Q1"),
    "sample_studio_nia": (
        "Since you're switching this month: check whether the new tool lets you set different reminder schedules per "
        "client, so your slowest payers get firmer nudges. Disclosure: I built Acme Invoicing (fictional), which "
        "does that and can import your existing clients.",
        "Hi Nia, saw your reply in r/agency that your studio is switching invoicing tools this month and wants "
        "automatic reminders. That's the core of Acme Invoicing (fictional), and it can import your clients so the "
        "switch takes an afternoon. I'm Sam, the founder; the 30-day trial is free. Want me to send a short setup "
        "guide?",
        "switching tools this month; wants automatic reminders"),
}

INTENTS = [
    ("reddit", "done", "Reddit r/freelance: search 'clients paying late' and 'payment reminder tool' to find freelancers asking for help chasing invoices (serves goal #G)"),
    ("hackernews", "done", "Hacker News: Ask HN threads about invoicing for consultancies, to find founders comparing invoicing tools (serves goal #G)"),
    ("linkedin", "done", "LinkedIn via web_search site:linkedin.com/posts: agency owners posting about late client payments (serves goal #G)"),
    ("g2", "exhausted", "G2 reviews of CompetitorOne: 'cons' and 'too expensive' to find small teams unhappy with pricing (serves goal #G)"),
    ("reddit", "running", "Reddit r/agency: mine the comment tree of the top 'how do you handle late payers' thread found by intent #I1 (serves goal #G)"),
    ("x", "open", "X: '\"alternative to CompetitorTwo\"' and '\"switching from CompetitorTwo\"' in the last 7 days (serves goal #G)"),
]

LEADS = [
    # intent index, platform, author, community, level, fit, pain, text, quote
    (0, "reddit", "sample_designer_mia", "r/freelance", "hot", 92, "late payments, wants automated reminders",
     "Third client this quarter paying 60 days late. Is there a tool that sends polite automatic payment reminders? Happy to pay for it.",
     "Is there a tool that sends polite automatic payment reminders? Happy to pay for it."),
    (0, "reddit", "sample_dev_omar", "r/freelance", "warm", 74, "chasing invoices is awkward",
     "Chasing invoices is the worst part of freelancing. I hate sending those emails myself.",
     "Chasing invoices is the worst part of freelancing."),
    (1, "hackernews", "sample_founder_lee", "hackernews", "hot", 88, "evaluating invoicing tools for a 6-person consultancy",
     "We're a 6 person consultancy evaluating invoicing tools this month. Needs Stripe sync and reminders. What do you use?",
     "We're a 6 person consultancy evaluating invoicing tools this month."),
    (1, "hackernews", "sample_pm_ana", "hackernews", "warm", 61, "spreadsheet invoicing does not scale",
     "Still doing invoices in a spreadsheet and it is starting to hurt now that we have 15 clients.",
     "Still doing invoices in a spreadsheet and it is starting to hurt"),
    (2, "linkedin", "sample-agency-owner-ravi", None, "hot", 85, "agency cash flow hit by late payers",
     "Our agency cash flow is wrecked by late payers. Looking for a better invoicing setup before Q1, recommendations welcome.",
     "Looking for a better invoicing setup before Q1, recommendations welcome."),
    (2, "linkedin", "sample-consultant-jo", None, "warm", 66, "spends hours on billing admin",
     "I spend about four hours a month just on billing admin. There has to be a better way.",
     "I spend about four hours a month just on billing admin."),
    (3, "g2", "sample_reviewer_kim", "g2.com", "warm", 70, "CompetitorOne too expensive for small team",
     "CompetitorOne works but the price jumped and it is too expensive for a team of three.",
     "the price jumped and it is too expensive for a team of three"),
    (3, "g2", "sample_reviewer_sam", "g2.com", "cold", 48, "missing multi-currency",
     "Wish CompetitorOne handled multi-currency invoices better for our EU clients.",
     "Wish CompetitorOne handled multi-currency invoices better"),
    (4, "reddit", "sample_studio_nia", "r/agency", "hot", 90, "switching invoicing tool now",
     "Same problem here. We are switching invoicing tools this month, did you find anything with automatic reminders?",
     "We are switching invoicing tools this month, did you find anything with automatic reminders?"),
]

FACTS = [
    (0, "r/freelance has several active threads a week about late payments; question-form queries surface buyers best",
     [("reddit", "r/freelance"), ("reddit", "r/agency")]),
    (1, "Ask HN invoicing threads are rare but high intent; commenters are often founders of small consultancies", []),
    (2, "LinkedIn snippets for 'late payments' + 'agency' return agency owners; 'invoice' alone returns vendors", []),
    (3, "G2 CompetitorOne cons cluster around price increases for small teams; review site pages limit depth", [("g2", "g2.com")]),
]


COMPANY = ("Sample: Acme Invoicing", "https://example.com",
           "Fictional company used for the sample task. Invoicing and payment reminders for freelancers.")

# (intent index, tool, input, short result) — the worker sessions of the sample task
WORKER_CALLS = {
    0: [("reddit_search", {"query": "clients paying late tool", "subreddit": "freelance"}, "12 posts"),
        ("reddit_thread", {"url": "https://example.com/sample/thread"}, "48 comments"),
        ("report_lead", {"capture_id": 1, "intent_level": "hot"}, "lead recorded"),
        ("report_lead", {"capture_id": 2, "intent_level": "warm"}, "lead recorded"),
        ("record_fact", {"summary": "r/freelance has several late-payment threads a week"}, "fact recorded")],
    1: [("hn_search", {"query": "invoicing consultancy", "type": "ask_hn"}, "9 results"),
        ("hn_item", {"id": 1000001}, "31 comments"),
        ("report_lead", {"capture_id": 3, "intent_level": "hot"}, "lead recorded")],
    2: [("web_search", {"site": "linkedin.com/posts", "query": "late payments agency"}, "10 snippets"),
        ("report_lead", {"capture_id": 5, "intent_level": "hot"}, "lead recorded")],
    3: [("web_search", {"site": "g2.com", "query": "CompetitorOne cons expensive"}, "8 snippets"),
        ("fetch_page", {"url": "https://example.com/g2/competitorone"}, "HTTP 429 from host"),
        ("report_lead", {"capture_id": 7, "intent_level": "warm"}, "lead recorded")],
    4: [("reddit_thread", {"url": "https://example.com/sample/agency-thread"}, "64 comments")],
}


def _seed_sessions(store: Store, cid: int, intent_ids: list[int]) -> None:
    class Usage:
        def __init__(self, i, o, cr, cw):
            self.input_tokens, self.output_tokens = i, o
            self.cache_read_input_tokens, self.cache_creation_input_tokens = cr, cw

    def call(rid, role, iid, blocks, stop, usage):
        mid = store.add_message(rid, "assistant", blocks)
        store.record_usage(cid, role, iid, "claude-opus-5-5", Usage(*usage), run_id=rid, stop_reason=stop,
                           duration_ms=4200 + 900 * len(blocks), message_id=mid)

    rid = store.start_run(cid, "decomposer", None, "claude-opus-5-5", "Goal decomposition")
    store.add_message(rid, "user", [{"type": "text", "text": "Campaign brief:\n" + BRIEF["description"]}])
    call(rid, "decomposer", None, [{"type": "tool_use", "id": "d1", "name": "set_goals",
                                    "input": {"goals": [{"text": "Find 12 warm or hot leads", "target_count": 12}]}}],
         "tool_use", (3100, 240, 0, 2900))
    store.add_message(rid, "tool", [{"type": "tool_result", "tool_use_id": "d1", "content": "goal #1 created",
                                     "is_error": False}])
    store.add_tool_call(cid, rid, None, "decomposer", "set_goals", {"goals": 1}, "goal created", False, 3)
    call(rid, "decomposer", None, [{"type": "text", "text": "One countable goal recorded."}], "end_turn", (3500, 30, 2900, 0))
    store.end_run(rid, "done")

    for n, (title, dispatched) in enumerate([("Planning round (edge)", [0, 1, 2]), ("Planning round (edge)", [3, 4, 5])]):
        rid = store.start_run(cid, "planner", None, "claude-opus-5-5", title)
        store.add_message(rid, "user", [{"type": "text", "text": "[situation] goals: 1 open · frontier_open=0 · running=0"}])
        intents = [{"summary": INTENTS[i][2][:80], "platform": INTENTS[i][0]} for i in dispatched]
        call(rid, "planner", None, [
            {"type": "text", "text": "Frontier is empty and the goal is unmet. Dispatching diverse routes." if n == 0
             else "Reddit and LinkedIn are yielding. Going deeper on r/agency and widening to G2 and X."},
            {"type": "tool_use", "id": f"p{n}", "name": "add_intent", "input": {"intents": intents}}],
            "tool_use", (18000, 900, 9000 * n, 14000))
        store.add_message(rid, "tool", [{"type": "tool_result", "tool_use_id": f"p{n}",
                                         "content": f"{len(dispatched)} intents added", "is_error": False}])
        store.add_tool_call(cid, rid, None, "planner", "add_intent", {"intents": intents},
                            f"{len(dispatched)} intents added", False, 4)
        call(rid, "planner", None, [{"type": "text", "text": "Round done."}], "end_turn", (19000, 40, 18000, 0))
        store.end_run(rid, "done")

    for ii, calls in WORKER_CALLS.items():
        state = INTENTS[ii][1]
        rid = store.start_run(cid, "worker", intent_ids[ii], "claude-opus-5-5", INTENTS[ii][2].split(" (serves")[0])
        store.add_message(rid, "user", [{"type": "text", "text": f"Your intent: {INTENTS[ii][2]}"}])
        for k, (tool, args, result) in enumerate(calls):
            tid = f"w{ii}_{k}"
            call(rid, "worker", intent_ids[ii], [
                {"type": "text", "text": f"Next: {tool.replace('_', ' ')}."},
                {"type": "tool_use", "id": tid, "name": tool, "input": args}], "tool_use",
                (22000 + 3000 * k, 400, 20000 + 3000 * k, 2500))
            err = result.startswith("HTTP 4")
            store.add_message(rid, "tool", [{"type": "tool_result", "tool_use_id": tid, "content": result, "is_error": err}])
            store.add_tool_call(cid, rid, intent_ids[ii], "worker", tool, args, result, err, 300 + 450 * k)
        if state != "running":
            call(rid, "worker", intent_ids[ii], [{"type": "text", "text": "Done. Leads and facts written back."}],
                 "end_turn", (30000, 120, 28000, 0))
        store.end_run(rid, {"done": "done", "exhausted": "exhausted"}.get(state, "stopped"))


def seed(store: Store) -> int:
    now = time.time()
    company = next((c["id"] for c in store.companies() if c["name"] == COMPANY[0]), None) \
        or store.create_company(*COMPANY)
    cid = store.create_campaign(BRIEF["name"], BRIEF, company)
    gid = store.add_node(cid, "goal", {"text": "Find 12 warm or hot leads (sample)", "summary": "Find 12 warm or hot leads (sample)",
                                       "target_count": 12, "min_intent": "warm"}, "open", origin="decomposer")
    store.add_constraint(cid, "deny", "Skip students and personal-budgeting questions")
    store.add_constraint(cid, "allow", "B2B buyers only")
    intent_ids = []
    for i, (plat, state, summary) in enumerate(INTENTS):
        s = summary.replace("#G", f"#{gid}").replace("#I1", f"#{intent_ids[0] if intent_ids else ''}")
        nid = store.add_node(cid, "intent", {"summary": s, "platform": plat, "goal_id": gid, "priority": 0}, state,
                             origin="planner")
        if i == 4:
            store.add_edge(cid, intent_ids[0], nid, "derived_from")
        else:
            store.add_edge(cid, gid, nid, "spawns")
        intent_ids.append(nid)
    store.anchor(intent_ids[0], [store.community_source("reddit", "r/freelance", url="https://example.com/r/freelance")])
    store.anchor(intent_ids[4], [store.community_source("reddit", "r/agency", url="https://example.com/r/agency")])

    for ii, summary, comms in FACTS:
        fid = store.add_node(cid, "fact", {"summary": summary, "confidence": "observed", "from_intent": intent_ids[ii],
                                           "evidence": "sample data"}, "confirmed", origin="worker")
        store.add_edge(cid, intent_ids[ii], fid, "yields")
        store.anchor(fid, [store.community_source(p, n, url=f"https://example.com/{n}") for p, n in comms])

    for n, (ii, plat, author, comm, level, fit, pain, text, quote) in enumerate(LEADS):
        url = f"https://example.com/sample/{plat}/{n}"
        posted = now - (n + 1) * 86400 * 2
        cap = store.add_capture(cid, intent_ids[ii], plat, url, text, author, f"https://example.com/sample/user/{author}",
                                posted_at=posted, meta={"community": comm})
        lid = store.add_node(cid, "lead", {"summary": f"{author} on {plat}: {pain}", "from_intent": intent_ids[ii],
                                           "reason": "Sample lead: the author describes the exact pain and asks for a tool.",
                                           "counterevidence": "Sample data."}, "confirmed", origin="worker")
        store.insert_lead(cid, lid, dedup_key=f"{plat}:{author}", platform=plat, author=author,
                          author_url=f"https://example.com/sample/user/{author}", url=url, quote=quote, posted_at=posted,
                          intent_level=level, fit_score=fit, pain=pain,
                          reason="Sample lead: the author describes the exact pain and asks for a tool.",
                          capture_id=cap)
        if author in DRAFTS:
            reply, dm, angle = DRAFTS[author]
            store.save_draft(lid, reply, dm, angle)
        store.add_edge(cid, intent_ids[ii], lid, "yields")
        sids = [store.upsert_source("author", plat, author, author)]
        if comm:
            sids.append(store.community_source(plat, comm))
        store.anchor(lid, sids)
    store.set_lead_status(store.leads(cid)[1]["node_id"], "contacted")

    store.set_todos(cid, [
        {"content": "Mine r/freelance late-payment threads", "status": "completed"},
        {"content": "Mine top r/agency thread comment tree", "status": "in_progress"},
        {"content": "Search X for CompetitorTwo switchers", "status": "pending"},
    ])
    log = [
        ("planner", "round", "planning round (edge)", None), ("planner", "tool_use", "add_intent 3 intents", None),
        ("worker", "tool_use", "reddit_search {\"query\": \"clients paying late tool\"}", 0),
        ("worker", "tool_use", "reddit_thread {\"url\": \"https://example.com/sample/thread\"}", 0),
        ("worker", "tool_use", "report_lead capture 1", 0),
        ("worker", "result", "Searched r/freelance with 4 phrasings, reported 2 leads; r/agency worth mining next.", 0),
        ("worker", "tool_use", "hn_search {\"query\": \"invoicing consultancy\", \"type\": \"ask_hn\"}", 1),
        ("worker", "result", "Two Ask HN threads, 2 leads (1 hot).", 1),
        ("planner", "round", "planning round (edge)", None), ("planner", "tool_use", "add_intent 2 intents", None),
        ("worker", "tool_use", "web_search {\"site\": \"linkedin.com/posts\", \"query\": \"late payments agency\"}", 2),
        ("worker", "result", "LinkedIn snippets: 2 leads from agency owners.", 2),
        ("worker", "tool_use", "reddit_thread {\"url\": \"https://example.com/sample/agency-thread\"}", 4),
    ]
    for role, kind, summary, ii in log:
        store.log(cid, role, kind, summary, summary, intent_id=intent_ids[ii] if ii is not None else None)

    _seed_sessions(store, cid, intent_ids)
    store.set_campaign_status(cid, "paused", "sample data")
    return cid
