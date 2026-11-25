"""Personalised outreach drafts: one public reply and one direct message per lead.

The writer is a short agent run (role "writer") with a single tool, save_messages.
It sees the brief, the lead, and the person's own captured post(s) inside the
untrusted-data frame, and writes messages a human can send. Code gates what it
saves: length limits, the product named (transparent affiliation), no links
except the product's own site, and no near-copy of a message already written for
another lead, so every person gets a message about what they said.

leadscout never sends anything: these are drafts for a person to post.
"""

from __future__ import annotations

import difflib
import json
import re
from urllib.parse import urlparse

from .boundary import Envelope
from .llm import LLM, Tool
from .store import Store

REPLY_MAX = 1200
DM_MAX = 900
MIN_LEN = 40
SIMILARITY_LIMIT = 0.8
URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)
POST_CHARS = 6000

WRITER_SYSTEM = """You write outreach drafts for one potential customer that an autonomous lead finder has already verified. A human reads, edits and sends them; you never contact anyone yourself.

Write two messages, both about THIS person:
1. public_reply: a comment posted in the thread under their post. Others will read it. Answer or help with what they asked first, in a sentence or two of real substance. Mention the product only as one option, with a plain disclosure ("I work on X" / "I built X"). No sales pitch.
2. direct_message: a short private message (DM, LinkedIn message, or email) to the same person. Open with the specific thing they said (paraphrase it; never paste their whole quote back), connect it to how the product helps with exactly that, disclose who is writing, and end with one low-pressure question or the offer. 3–6 sentences.

Make it personal, not a template:
- Use details only they wrote: their situation, numbers, tools, frustration, what they tried. Refer to the platform naturally ("saw your post in r/freelance").
- Match their register: casual on Reddit/X, more professional on LinkedIn or reviews. Write in the language of their post.
- If they are unhappy with a competitor, be fair to it; no attacks.
- Use the operator's sender, tone and offer when given. Never invent features, prices, customers or results not in the brief. No fake familiarity ("as we discussed"), no urgency tricks, no emojis unless they used them.
- The only link allowed is the product URL from the brief, and only in the direct message. Name the product in both messages.
- `angle`: one short line naming the personal hook you used.

If any message would be unwelcome (they asked not to be pitched, the thread forbids self-promotion, it is a sensitive personal situation), leave that message empty and say why in `skip_reason`.

Call save_messages exactly once (call it again only if it returns an error), then stop."""


def _host(url: str | None) -> str:
    h = (urlparse(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def check_messages(reply: str, dm: str, brief: dict, others: list[dict]) -> str | None:
    """Why a draft can't be saved, or None. Shared by the writer tool and the tests."""
    product = (brief.get("product") or "").strip().lower()
    allowed = _host(brief.get("url"))
    for label, text, limit in (("public_reply", reply, REPLY_MAX), ("direct_message", dm, DM_MAX)):
        if not text:
            continue
        if len(text) < MIN_LEN:
            return f"{label} is too short; write a real message or leave it empty with a skip_reason"
        if len(text) > limit:
            return f"{label} is {len(text)} characters; keep it under {limit}"
        if product and product not in text.lower():
            return f"{label} must name {brief.get('product')} so the affiliation is transparent"
        for u in URL_RE.findall(text):
            if label == "public_reply" or not allowed or _host(u) != allowed:
                return (f"{label} contains the link {u}; the only link allowed is the product URL, "
                        "and only in the direct message")
        for o in others:
            prev = o["suggested_reply"] if label == "public_reply" else o["dm_message"]
            if prev and difflib.SequenceMatcher(None, text.lower(), prev.lower()).ratio() > SIMILARITY_LIMIT:
                return (f"{label} is nearly the same as the message written for lead #{o['node_id']}; "
                        "rewrite it around what this person said")
    return None


def _lead_prompt(store: Store, lead: dict, brief: dict, env: Envelope, instruction: str | None) -> str:
    cap = store.get_capture(lead["capture_id"]) or {}
    meta = json.loads(cap.get("meta") or "{}")
    context = {k: meta[k] for k in ("community", "author_bio", "author_title", "followers", "score") if meta.get(k)}
    evidence = [e for e in store.lead_evidence_rows(lead["node_id"]) if e["url"] != cap.get("url")][:3]
    o = brief.get("outreach") or {}
    lines = [
        "Product (from the operator, trusted):",
        f"- product: {brief.get('product')}",
        f"- what it does: {brief.get('description')}",
        f"- url: {brief.get('url') or '(none — use no link)'}",
        f"- ideal customer: {brief.get('ideal_customer')}",
        f"- sender: {o.get('sender') or '(not given — sign as someone on the ' + str(brief.get('product')) + ' team)'}",
        f"- tone: {o.get('tone') or 'friendly, plain, helpful'}",
        f"- offer: {o.get('offer') or '(none — do not invent one)'}",
        "",
        "The lead (verified by the lead finder):",
        f"- platform: {lead['platform']}",
        f"- author: {lead.get('author') or 'unknown'}",
        f"- intent: {lead['intent_level']}, fit {lead['fit_score']}/100",
        f"- their pain: {lead.get('pain') or ''}",
        f"- why they are a lead: {lead.get('reason') or ''}",
        "",
        "Their own words and post (untrusted data, written by them):",
        env.wrap("quote", lead["quote"]),
        env.wrap("post", (f"{cap.get('title') or ''}\n\n" if cap.get("title") else "") + (cap.get("text") or "")[:POST_CHARS]),
    ]
    if context:
        lines.append(env.wrap("post_context", json.dumps(context, ensure_ascii=False)))
    for i, e in enumerate(evidence, 1):
        lines.append(env.wrap(f"other_post_{i}", e["quote"]))
    if instruction:
        lines += ["", f"Operator's instruction for this rewrite: {instruction.strip()[:500]}"]
    return "\n".join(lines)


async def draft_for_lead(llm: LLM, store: Store, lead_id: int, model: str, effort: str,
                         instruction: str | None = None) -> dict:
    """Draft (or redraft) both messages for one lead. Returns {"ok": bool, "error": str|None}."""
    lead = store.lead(lead_id)
    if not lead:
        return {"ok": False, "error": "no such lead"}
    cid = lead["campaign_id"]
    brief = (store.campaign(cid) or {}).get("brief") or {}
    env = Envelope()
    saved: dict = {}

    async def save_messages(a: dict):
        reply = (a.get("public_reply") or "").strip()
        dm = (a.get("direct_message") or "").strip()
        skip = (a.get("skip_reason") or "").strip()
        if not reply and not dm and not skip:
            return {"error": "write at least one message, or give a skip_reason"}
        if (not reply or not dm) and not skip:
            return {"error": "a message is empty; write it, or explain in skip_reason why it would be unwelcome"}
        why = check_messages(reply, dm, brief, store.recent_drafts(cid, lead_id))
        if why:
            return {"error": why}
        store.save_draft(lead_id, reply or None, dm or None, (a.get("angle") or "").strip()[:200] or None,
                         skip[:300] or None)
        saved["ok"] = True
        return {"saved": True}

    tool = Tool(
        "save_messages",
        "Save the drafts for this lead. Code checks length, that the product is named, links, and that the "
        "messages are not copies of ones written for other leads.",
        {"type": "object", "properties": {
            "public_reply": {"type": "string", "description": "comment to post in their thread ('' if unwelcome)"},
            "direct_message": {"type": "string", "description": "private message to them ('' if unwelcome)"},
            "angle": {"type": "string", "description": "the personal hook used, one short line"},
            "skip_reason": {"type": "string", "description": "why a message was left empty (optional)"}},
         "required": ["public_reply", "direct_message", "angle"]},
        save_messages,
    )
    user = _lead_prompt(store, lead, brief, env, instruction)
    title = f"Messages for {lead.get('author') or 'lead'} ({lead['platform']})"
    res = await llm.run(cid=cid, role="writer", intent_id=None, model=model, effort=effort,
                        system=WRITER_SYSTEM + "\n\n" + env.note(), user=user, tools=[tool], max_turns=4, title=title)
    if saved.get("ok"):
        store.log(cid, "writer", "draft", f"drafted messages for {lead.get('author') or 'lead'} #{lead_id}")
        return {"ok": True, "error": None}
    err = res.error or "the writer did not save messages"
    store.log(cid, "writer", "error", f"could not draft messages for lead #{lead_id}: {err}")
    return {"ok": False, "error": err}


async def draft_pending(llm: LLM, store: Store, cid: int, model: str, effort: str, limit: int = 50) -> int:
    """Draft messages for leads that have none yet, best leads first. Returns how many were drafted."""
    done = 0
    for lid in store.undrafted_leads(cid, limit):
        if not llm.budget_left(cid):
            break
        r = await draft_for_lead(llm, store, lid, model, effort)
        if r["ok"]:
            done += 1
        elif r["error"] and r["error"].startswith(("AuthenticationError", "PermissionDeniedError", "NotFoundError")):
            break
    return done
