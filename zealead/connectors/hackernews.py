"""Hacker News via the free Algolia API (no key)."""

from __future__ import annotations

from .base import Connector, Ctx, Item, ToolSpec, html_to_text, record_items

API = "https://hn.algolia.com/api/v1"


class HackerNews(Connector):
    platform = "hackernews"
    label = "Hacker News"

    def _item(self, h: dict) -> Item:
        oid = h.get("objectID") or str(h.get("id"))
        is_comment = "comment" in (h.get("_tags") or []) or h.get("type") == "comment"
        story_id = str(h.get("story_id") or h.get("parent_id") or oid)
        return Item(
            platform="hackernews", kind="comment" if is_comment else "post",
            url=f"https://news.ycombinator.com/item?id={oid}",
            title=h.get("title") or h.get("story_title"),
            text=html_to_text(h.get("comment_text") or h.get("story_text") or h.get("text") or ""),
            author=h.get("author"), author_url=f"https://news.ycombinator.com/user?id={h.get('author')}",
            posted_at=h.get("created_at_i"), community="hackernews",
            community_url="https://news.ycombinator.com",
            thread_key=story_id, thread_title=h.get("story_title") or h.get("title"),
            engagement={"points": h.get("points"), "comments": h.get("num_comments")},
        )

    async def search(self, ctx: Ctx, a: dict):
        tags = {"stories": "story", "comments": "comment", "ask_hn": "ask_hn", "show_hn": "show_hn"}.get(a.get("type", "all"))
        params = {"query": a["query"], "hitsPerPage": min(int(a.get("limit", 25)), 50),
                  "numericFilters": f"created_at_i>{int(ctx.since_ts)}"}
        if tags:
            params["tags"] = tags
        r = await ctx.gov.get(f"{API}/search_by_date", params=params)
        if r.status_code != 200:
            return {"error": f"hn search HTTP {r.status_code}"}
        return {"results": record_items(ctx, [self._item(h) for h in r.json().get("hits", [])], limit=params["hitsPerPage"])}

    async def item(self, ctx: Ctx, a: dict):
        r = await ctx.gov.get(f"{API}/items/{int(a['id'])}")
        if r.status_code != 200:
            return {"error": f"hn item HTTP {r.status_code}"}
        root = r.json()
        items: list[Item] = []

        def walk(node: dict, story: dict):
            h = dict(node)
            h["story_title"] = story.get("title")
            h["story_id"] = story.get("id")
            items.append(self._item(h))
            for ch in node.get("children") or []:
                walk(ch, story)

        walk(root, root)
        items = [i for i in items if i.author]
        return {"results": record_items(ctx, items, limit=int(a.get("limit", 80)))}

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec("hn_search", "Search Hacker News stories and comments by date within the recency window.",
                     {"type": "object", "properties": {
                         "query": {"type": "string"},
                         "type": {"type": "string", "enum": ["all", "stories", "comments", "ask_hn", "show_hn"]},
                         "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                      "required": ["query"]}, self.search),
            ToolSpec("hn_item", "Fetch a Hacker News story or comment with its full reply tree, by numeric id.",
                     {"type": "object", "properties": {
                         "id": {"type": "integer"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}},
                      "required": ["id"]}, self.item),
        ]
