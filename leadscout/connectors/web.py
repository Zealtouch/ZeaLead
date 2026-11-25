"""Web search (Brave or Tavily) and a public-page fetcher.

LinkedIn, X (without the paid API), G2, Capterra, Product Hunt, Quora and
Indie Hackers are reached through search-engine results with `site:` filters.
Login-walled networks are never fetched directly: their terms forbid scraping,
so the snippet the search engine returns is the evidence.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .base import Connector, Ctx, Item, ToolSpec, html_to_text, parse_iso, record_items

DOMAIN_PLATFORM = {
    "linkedin.com": "linkedin", "x.com": "x", "twitter.com": "x", "reddit.com": "reddit",
    "news.ycombinator.com": "hackernews", "g2.com": "g2", "capterra.com": "capterra",
    "trustpilot.com": "trustpilot", "producthunt.com": "producthunt", "quora.com": "quora",
    "indiehackers.com": "indiehackers", "facebook.com": "facebook", "youtube.com": "youtube",
    "medium.com": "medium", "dev.to": "devto", "stackoverflow.com": "stackexchange",
    "github.com": "github", "threads.net": "threads", "bsky.app": "bluesky",
}

NO_FETCH = ("linkedin.com", "x.com", "twitter.com", "facebook.com", "instagram.com", "threads.net")


def platform_for(url: str) -> str:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    for dom, plat in DOMAIN_PLATFORM.items():
        if host == dom or host.endswith("." + dom):
            return plat
    return "web"


def author_from_url(url: str, platform: str) -> tuple[str | None, str | None]:
    path = urlparse(url).path
    if platform == "linkedin":
        m = re.match(r"/posts/([^_/]+)_", path) or re.match(r"/in/([^/]+)", path)
        if m:
            return m.group(1), f"https://www.linkedin.com/in/{m.group(1)}"
    if platform == "x":
        m = re.match(r"/([A-Za-z0-9_]{1,15})/status/", path)
        if m:
            return m.group(1), f"https://x.com/{m.group(1)}"
    if platform == "reddit":
        m = re.match(r"/user/([^/]+)", path)
        if m:
            return m.group(1), f"https://www.reddit.com/user/{m.group(1)}"
    return None, None


class WebSearch(Connector):
    platform = "web"
    label = "Web search (LinkedIn, G2, Capterra, Product Hunt, Quora, ...)"

    def enabled(self):
        return (bool(self.env.get("BRAVE_API_KEY") or self.env.get("TAVILY_API_KEY")),
                "set BRAVE_API_KEY or TAVILY_API_KEY")

    def _blocked(self, ctx: Ctx, platform: str) -> bool:
        blocked = ctx.env.get("_BLOCKED_PLATFORMS", set())
        return platform in blocked

    async def search(self, ctx: Ctx, a: dict):
        q = a["query"]
        site = (a.get("site") or "").strip()
        if site:
            if self._blocked(ctx, platform_for("https://" + site)):
                return {"error": f"platform for {site} is excluded by the campaign brief"}
            q = f"site:{site} {q}"
        n = min(int(a.get("limit", 15)), 20)
        results = []
        if self.env.get("BRAVE_API_KEY"):
            fresh = "pd" if ctx.recency_days <= 1 else "pw" if ctx.recency_days <= 7 else "pm" if ctx.recency_days <= 31 else "py"
            r = await ctx.gov.get("https://api.search.brave.com/res/v1/web/search",
                                  params={"q": q, "count": n, "freshness": fresh, "extra_snippets": "true"},
                                  headers={"X-Subscription-Token": self.env["BRAVE_API_KEY"], "Accept": "application/json"})
            if r.status_code != 200:
                return {"error": f"brave HTTP {r.status_code}", "body": r.text[:300]}
            for w in r.json().get("web", {}).get("results", []):
                snippet = " … ".join([w.get("description", "")] + (w.get("extra_snippets") or []))
                results.append((w.get("url"), w.get("title"), snippet, parse_iso(w.get("page_age"))))
        else:
            r = await ctx.gov.post("https://api.tavily.com/search",
                                   json={"query": q, "max_results": n, "search_depth": "advanced",
                                         "days": ctx.recency_days, "topic": "general"},
                                   headers={"Authorization": f"Bearer {self.env['TAVILY_API_KEY']}"})
            if r.status_code != 200:
                return {"error": f"tavily HTTP {r.status_code}", "body": r.text[:300]}
            for w in r.json().get("results", []):
                results.append((w.get("url"), w.get("title"), w.get("content", ""), parse_iso(w.get("published_date"))))
        items = []
        for url, title, snippet, ts in results:
            if not url:
                continue
            plat = platform_for(url)
            if self._blocked(ctx, plat):
                continue
            author, author_url = author_from_url(url, plat)
            host = (urlparse(url).hostname or "").removeprefix("www.")
            items.append(Item(platform=plat, kind="snippet", url=url, title=html_to_text(title or ""),
                              text=html_to_text(snippet), author=author, author_url=author_url, posted_at=ts,
                              community=host if plat in ("web", "g2", "capterra", "trustpilot", "producthunt") else None,
                              community_url=f"https://{host}"))
        return {"note": "Snippets only. For login-walled sites (LinkedIn, X) the snippet is the evidence; quote from it.",
                "results": record_items(ctx, items, limit=n)}

    async def fetch(self, ctx: Ctx, a: dict):
        url = a["url"]
        host = (urlparse(url).hostname or "").removeprefix("www.")
        if any(host == d or host.endswith("." + d) for d in NO_FETCH):
            return {"error": f"{host} is login-walled and its terms forbid scraping; use web_search snippets instead"}
        plat = platform_for(url)
        if self._blocked(ctx, plat):
            return {"error": f"platform {plat} is excluded by the campaign brief"}
        r = await ctx.gov.get(url, headers={"Accept": "text/html,application/xhtml+xml"})
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        if "html" not in r.headers.get("content-type", "") and "text" not in r.headers.get("content-type", ""):
            return {"error": "not a text page"}
        text = html_to_text(r.text)[:12000]
        item = Item(platform=plat, kind="page", url=str(r.url), text=text, community=host, community_url=f"https://{host}")
        return {"results": record_items(ctx, [item], limit=1)}

    def tools(self):
        return [
            ToolSpec("web_search",
                     "Search the web within the recency window. Use `site` to target one platform, e.g. "
                     "site='linkedin.com/posts' with query '\"looking for\" invoicing tool', site='g2.com' with "
                     "'<competitor> reviews cons', site='producthunt.com', 'quora.com', 'indiehackers.com', 'x.com'.",
                     {"type": "object", "properties": {
                         "query": {"type": "string"}, "site": {"type": "string"},
                         "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                      "required": ["query"]}, self.search),
            ToolSpec("fetch_page",
                     "Fetch a public page (forum thread, review page, blog comments) as text. Refuses login-walled networks.",
                     {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}, self.fetch),
        ]
