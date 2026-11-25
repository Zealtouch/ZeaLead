"""X (Twitter) through the official API v2 recent search.

Requires a paid API tier and X_BEARER_TOKEN. Recent search covers the last
seven days. Without a token this connector stays off and the planner reaches
public X posts only through web_search snippets.
"""

from __future__ import annotations

from .base import Connector, Ctx, Item, ToolSpec, parse_iso, record_items

API = "https://api.twitter.com/2/tweets/search/recent"


class X(Connector):
    platform = "x"
    label = "X / Twitter"

    def enabled(self):
        return (bool(self.env.get("X_BEARER_TOKEN")), "set X_BEARER_TOKEN (paid X API tier)")

    async def search(self, ctx: Ctx, a: dict):
        q = a["query"]
        if "-is:retweet" not in q:
            q += " -is:retweet"
        if a.get("lang"):
            q += f" lang:{a['lang']}"
        params = {"query": q, "max_results": max(10, min(int(a.get("limit", 25)), 100)),
                  "tweet.fields": "created_at,author_id,public_metrics,conversation_id,lang",
                  "expansions": "author_id", "user.fields": "username,name,description,public_metrics"}
        r = await ctx.gov.get(API, params=params, headers={"Authorization": f"Bearer {self.env['X_BEARER_TOKEN']}"})
        if r.status_code != 200:
            return {"error": f"x search HTTP {r.status_code}", "body": r.text[:300]}
        j = r.json()
        users = {u["id"]: u for u in j.get("includes", {}).get("users", [])}
        items = []
        for t in j.get("data", []):
            u = users.get(t.get("author_id"), {})
            handle = u.get("username") or t.get("author_id")
            items.append(Item(
                platform="x", kind="post", url=f"https://x.com/{handle}/status/{t['id']}", text=t.get("text", ""),
                author=handle, author_url=f"https://x.com/{handle}", posted_at=parse_iso(t.get("created_at")),
                thread_key=t.get("conversation_id"), engagement=t.get("public_metrics") or {},
            ))
        bios = {u.get("username"): (u.get("description") or "")[:200] for u in users.values()}
        return {"results": record_items(ctx, items, limit=params["max_results"]), "author_bios": bios}

    def tools(self):
        return [ToolSpec(
            "x_search",
            "Search recent X posts (last 7 days) with X query syntax, e.g. '(\"looking for\" OR \"recommend\") crm -from:hubspot'. "
            "Returns author bios to help judge fit.",
            {"type": "object", "properties": {
                "query": {"type": "string"}, "lang": {"type": "string", "description": "ISO code, e.g. en"},
                "limit": {"type": "integer", "minimum": 10, "maximum": 100}},
             "required": ["query"]}, self.search)]
