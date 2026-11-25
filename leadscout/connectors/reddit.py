"""Reddit through the official Data API (OAuth app-only).

Reddit blocks unauthenticated API clients (the public .json endpoints answer
403), so REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are required. Commercial use
needs Reddit's separate data agreement. Without credentials, the planner can
still reach Reddit threads through web_search with site='reddit.com'.
"""

from __future__ import annotations

import time

from .base import Connector, Ctx, Item, ToolSpec, html_to_text, record_items

T_WINDOW = [(1, "day"), (7, "week"), (31, "month"), (366, "year")]


class Reddit(Connector):
    platform = "reddit"
    label = "Reddit"

    def __init__(self, env: dict):
        super().__init__(env)
        self._token: str | None = None
        self._token_exp = 0.0

    def enabled(self):
        return (bool(self.env.get("REDDIT_CLIENT_ID") and self.env.get("REDDIT_CLIENT_SECRET")),
                "set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET (Reddit blocks unauthenticated API access)")

    async def _base(self, ctx: Ctx) -> tuple[str, dict]:
        cid, secret = self.env["REDDIT_CLIENT_ID"], self.env["REDDIT_CLIENT_SECRET"]
        if not self._token or time.time() > self._token_exp - 60:
            r = await ctx.gov.post("https://www.reddit.com/api/v1/access_token", auth=(cid, secret),
                                   data={"grant_type": "client_credentials"})
            r.raise_for_status()
            j = r.json()
            self._token, self._token_exp = j["access_token"], time.time() + j.get("expires_in", 3600)
        return "https://oauth.reddit.com", {"Authorization": f"bearer {self._token}"}

    def _window(self, days: int) -> str:
        for d, name in T_WINDOW:
            if days <= d:
                return name
        return "all"

    def _post_item(self, d: dict) -> Item:
        return Item(
            platform="reddit", kind="post",
            url="https://www.reddit.com" + d.get("permalink", ""),
            title=d.get("title"), text=d.get("selftext") or "",
            author=d.get("author"), author_url=f"https://www.reddit.com/user/{d.get('author')}",
            posted_at=d.get("created_utc"),
            community="r/" + d.get("subreddit", ""), community_url=f"https://www.reddit.com/r/{d.get('subreddit')}",
            thread_key=d.get("id"), thread_title=d.get("title"),
            engagement={"score": d.get("score"), "comments": d.get("num_comments")},
        )

    async def search(self, ctx: Ctx, a: dict):
        base, hdr = await self._base(ctx)
        sub = (a.get("subreddit") or "").removeprefix("r/").strip()
        path = f"/r/{sub}/search" if sub else "/search"
        params = {"q": a["query"], "sort": a.get("sort", "new"), "t": self._window(ctx.recency_days),
                  "limit": min(int(a.get("limit", 25)), 50), "restrict_sr": "1" if sub else "0", "raw_json": 1}
        r = await ctx.gov.get(base + path, params=params, headers=hdr)
        if r.status_code != 200:
            return {"error": f"reddit search HTTP {r.status_code}", "body": r.text[:300]}
        items = [self._post_item(c["data"]) for c in r.json().get("data", {}).get("children", [])]
        return {"results": record_items(ctx, items, limit=params["limit"])}

    async def thread(self, ctx: Ctx, a: dict):
        url = a["url"].split("?")[0].rstrip("/")
        if "reddit.com" not in url:
            return {"error": "not a reddit thread url"}
        path = url.split("reddit.com", 1)[1]
        base, hdr = await self._base(ctx)
        r = await ctx.gov.get(base + path,
                              params={"limit": 200, "depth": 4, "sort": a.get("sort", "top"), "raw_json": 1}, headers=hdr)
        if r.status_code != 200:
            return {"error": f"reddit thread HTTP {r.status_code}"}
        data = r.json()
        post = data[0]["data"]["children"][0]["data"]
        items = [self._post_item(post)]
        sub = post.get("subreddit", "")

        def walk(children: list, depth: int = 0):
            for c in children:
                if c.get("kind") != "t1":
                    continue
                d = c["data"]
                items.append(Item(
                    platform="reddit", kind="comment",
                    url="https://www.reddit.com" + d.get("permalink", ""), text=d.get("body") or "",
                    author=d.get("author"), author_url=f"https://www.reddit.com/user/{d.get('author')}",
                    posted_at=d.get("created_utc"), community="r/" + sub,
                    community_url=f"https://www.reddit.com/r/{sub}", thread_key=post.get("id"),
                    thread_title=post.get("title"), engagement={"score": d.get("score"), "depth": depth},
                ))
                rep = d.get("replies")
                if isinstance(rep, dict):
                    walk(rep["data"]["children"], depth + 1)

        walk(data[1]["data"]["children"])
        items = [i for i in items if i.author not in ("[deleted]", "AutoModerator")]
        return {"thread_title": post.get("title"), "results": record_items(ctx, items, limit=int(a.get("limit", 60)))}

    async def communities(self, ctx: Ctx, a: dict):
        base, hdr = await self._base(ctx)
        r = await ctx.gov.get(base + "/subreddits/search",
                              params={"q": a["query"], "limit": 15, "raw_json": 1}, headers=hdr)
        if r.status_code != 200:
            return {"error": f"reddit community search HTTP {r.status_code}"}
        out = []
        for c in r.json().get("data", {}).get("children", []):
            d = c["data"]
            name = "r/" + d.get("display_name", "")
            sid = ctx.store.community_source("reddit", name, name, "https://www.reddit.com" + d.get("url", ""))
            ctx.touched_sources.add(sid)
            out.append({"source_id": sid, "community": name, "subscribers": d.get("subscribers"),
                        "description": html_to_text(d.get("public_description") or "")[:300]})
        return {"communities": out}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec("reddit_search",
                     "Search Reddit posts (newest first by default) within the campaign's recency window. "
                     "Use Reddit search syntax, e.g. '\"alternative to\" (Notion OR Coda)'. Optionally restrict to one subreddit.",
                     {"type": "object", "properties": {
                         "query": {"type": "string"},
                         "subreddit": {"type": "string", "description": "e.g. SaaS or r/SaaS; omit for all of Reddit"},
                         "sort": {"type": "string", "enum": ["new", "relevance", "top", "comments"]},
                         "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                      "required": ["query"]}, self.search),
            ToolSpec("reddit_thread",
                     "Fetch a Reddit thread with its comment tree. Commenters asking for recommendations or "
                     "complaining about a competitor are often better leads than the original poster.",
                     {"type": "object", "properties": {
                         "url": {"type": "string"},
                         "sort": {"type": "string", "enum": ["top", "new", "best"]},
                         "limit": {"type": "integer", "minimum": 1, "maximum": 150}},
                      "required": ["url"]}, self.thread),
            ToolSpec("reddit_find_communities",
                     "Find subreddits about a topic (returns name, subscribers, description). Registers them as communities.",
                     {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                     self.communities),
        ]
