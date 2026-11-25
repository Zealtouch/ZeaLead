"""Shared connector plumbing.

A connector turns a platform API into worker tools. Each result item is stored
as a capture (the evidence a lead must quote verbatim) and registered in the
source graph (platform -> community -> thread, plus the author) by code, so the
model never invents URLs or authors: it refers to items by capture_id.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Awaitable, Callable

from ..governor import Governor
from ..store import Store

MAX_ITEM_CHARS = 1500


@dataclass
class Item:
    platform: str
    url: str
    text: str
    author: str | None = None
    author_url: str | None = None
    title: str | None = None
    posted_at: float | None = None
    community: str | None = None          # subreddit, SE site, repo, domain ...
    community_url: str | None = None
    thread_key: str | None = None
    thread_title: str | None = None
    engagement: dict = field(default_factory=dict)
    kind: str = "post"                    # post | comment | review | issue | page | snippet


@dataclass
class Ctx:
    store: Store
    gov: Governor
    campaign_id: int
    intent_id: int | None
    recency_days: int
    env: dict
    touched_sources: set[int] = field(default_factory=set)

    @property
    def since_ts(self) -> float:
        return time.time() - self.recency_days * 86400


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: dict
    handler: Callable[[Ctx, dict], Awaitable[Any]]


class Connector:
    platform = "base"
    label = "base"

    def __init__(self, env: dict):
        self.env = env

    def enabled(self) -> tuple[bool, str]:
        return True, ""

    def tools(self) -> list[ToolSpec]:
        raise NotImplementedError


def iso(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def parse_iso(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


class _Stripper(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in ("p", "br", "li", "div", "h1", "h2", "h3", "tr"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def html_to_text(s: str) -> str:
    if not s:
        return ""
    if "<" not in s:
        return html.unescape(s).strip()
    p = _Stripper()
    p.feed(s)
    text = html.unescape("".join(p.out))
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def record_items(ctx: Ctx, items: list[Item], limit: int = 25) -> list[dict]:
    """Persist items as captures + source-graph nodes; return the model-facing view."""
    out = []
    st = ctx.store
    for it in items[:limit]:
        if it.posted_at and it.posted_at < ctx.since_ts:
            continue
        if not (it.text or "").strip() and not it.title:
            continue
        full_text = ((it.title + "\n\n") if it.title and it.kind != "comment" else "") + (it.text or "")
        cap = st.add_capture(ctx.campaign_id, ctx.intent_id, it.platform, it.url, full_text, it.author, it.author_url,
                             it.title, it.posted_at, {"engagement": it.engagement, "kind": it.kind,
                                                      "community": it.community})
        sids = [st.platform_source(it.platform)]
        parent = sids[0]
        if it.community:
            parent = st.community_source(it.platform, it.community, it.community, it.community_url)
            sids.append(parent)
        if it.thread_key:
            sids.append(st.upsert_source("thread", it.platform, it.thread_key, it.thread_title or it.title, it.url, parent))
        if it.author:
            sids.append(st.upsert_source("author", it.platform, it.author, it.author, it.author_url))
        ctx.touched_sources.update(sids)
        text = full_text if len(full_text) <= MAX_ITEM_CHARS else full_text[:MAX_ITEM_CHARS] + " …(truncated)"
        out.append({
            "capture_id": cap,
            "kind": it.kind,
            "url": it.url,
            "author": it.author,
            "community": it.community,
            "posted": iso(it.posted_at),
            "engagement": it.engagement or None,
            "text": text,
        })
    return out
