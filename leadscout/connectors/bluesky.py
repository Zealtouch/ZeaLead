"""Bluesky post search via the AT Protocol (app password recommended)."""

from __future__ import annotations

import time

from .base import Connector, Ctx, Item, ToolSpec, parse_iso, record_items


class Bluesky(Connector):
    platform = "bluesky"
    label = "Bluesky"

    def __init__(self, env: dict):
        super().__init__(env)
        self._jwt: str | None = None
        self._jwt_at = 0.0

    def enabled(self):
        return (bool(self.env.get("BSKY_HANDLE") and self.env.get("BSKY_APP_PASSWORD")),
                "set BSKY_HANDLE and BSKY_APP_PASSWORD")

    async def _auth(self, ctx: Ctx) -> dict:
        if not self._jwt or time.time() - self._jwt_at > 3600:
            r = await ctx.gov.post("https://bsky.social/xrpc/com.atproto.server.createSession",
                                   json={"identifier": self.env["BSKY_HANDLE"], "password": self.env["BSKY_APP_PASSWORD"]})
            r.raise_for_status()
            self._jwt, self._jwt_at = r.json()["accessJwt"], time.time()
        return {"Authorization": f"Bearer {self._jwt}"}

    async def search(self, ctx: Ctx, a: dict):
        params = {"q": a["query"], "limit": min(int(a.get("limit", 25)), 100), "sort": "latest",
                  "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ctx.since_ts))}
        if a.get("lang"):
            params["lang"] = a["lang"]
        r = await ctx.gov.get("https://bsky.social/xrpc/app.bsky.feed.searchPosts", params=params,
                              headers=await self._auth(ctx))
        if r.status_code != 200:
            return {"error": f"bluesky search HTTP {r.status_code}", "body": r.text[:300]}
        items = []
        for p in r.json().get("posts", []):
            handle = p.get("author", {}).get("handle")
            rkey = p.get("uri", "").rsplit("/", 1)[-1]
            items.append(Item(
                platform="bluesky", kind="post", url=f"https://bsky.app/profile/{handle}/post/{rkey}",
                text=p.get("record", {}).get("text", ""), author=handle, author_url=f"https://bsky.app/profile/{handle}",
                posted_at=parse_iso(p.get("record", {}).get("createdAt")), thread_key=rkey,
                engagement={"likes": p.get("likeCount"), "replies": p.get("replyCount")},
            ))
        return {"results": record_items(ctx, items, limit=params["limit"])}

    def tools(self):
        return [ToolSpec("bluesky_search", "Search recent Bluesky posts.",
                         {"type": "object", "properties": {
                             "query": {"type": "string"}, "lang": {"type": "string"},
                             "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                          "required": ["query"]}, self.search)]
