"""Connector registry: which platforms are usable for a campaign."""

from __future__ import annotations

from .base import Connector, Ctx, ToolSpec
from .bluesky import Bluesky
from .devcommunities import GitHubIssues, StackExchange
from .hackernews import HackerNews
from .reddit import Reddit
from .web import WebSearch
from .x import X

ALL = [Reddit, HackerNews, X, Bluesky, StackExchange, GitHubIssues, WebSearch]


def available(env: dict, brief: dict) -> tuple[list[Connector], list[str]]:
    """Connectors enabled by credentials AND allowed by the brief; plus reasons for the rest."""
    allow = {p.lower() for p in brief.get("platforms") or []}
    deny = {p.lower() for p in brief.get("exclude_platforms") or []}
    on, off = [], []
    for cls in ALL:
        c = cls(env)
        if c.platform in deny or (allow and c.platform not in allow and c.platform != "web"):
            off.append(f"{c.label}: excluded by brief")
            continue
        ok, why = c.enabled()
        (on if ok else off).append(c if ok else f"{c.label}: {why}")
    return on, off


__all__ = ["ALL", "available", "Connector", "Ctx", "ToolSpec"]
