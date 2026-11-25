"""Stack Exchange and GitHub issues: where developers ask for tools and complain."""

from __future__ import annotations

from .base import Connector, Ctx, Item, ToolSpec, html_to_text, parse_iso, record_items


class StackExchange(Connector):
    platform = "stackexchange"
    label = "Stack Exchange"

    async def search(self, ctx: Ctx, a: dict):
        site = a.get("site", "stackoverflow")
        params = {"q": a["query"], "site": site, "sort": "creation", "order": "desc",
                  "pagesize": min(int(a.get("limit", 20)), 50), "fromdate": int(ctx.since_ts), "filter": "withbody"}
        if self.env.get("STACKEXCHANGE_KEY"):
            params["key"] = self.env["STACKEXCHANGE_KEY"]
        r = await ctx.gov.get("https://api.stackexchange.com/2.3/search/advanced", params=params)
        if r.status_code != 200:
            return {"error": f"stackexchange HTTP {r.status_code}", "body": r.text[:300]}
        items = []
        for q in r.json().get("items", []):
            owner = q.get("owner", {})
            items.append(Item(
                platform="stackexchange", kind="post", url=q.get("link"), title=html_to_text(q.get("title", "")),
                text=html_to_text(q.get("body", "")), author=owner.get("display_name"), author_url=owner.get("link"),
                posted_at=q.get("creation_date"), community=site, community_url=f"https://{site}.com",
                thread_key=f"{site}:{q.get('question_id')}", engagement={"score": q.get("score"), "answers": q.get("answer_count")},
            ))
        return {"results": record_items(ctx, items, limit=params["pagesize"])}

    def tools(self):
        return [ToolSpec("stackexchange_search",
                         "Search Stack Exchange questions (stackoverflow, superuser, serverfault, webmasters, ux, softwarerecs, ...).",
                         {"type": "object", "properties": {
                             "query": {"type": "string"}, "site": {"type": "string"},
                             "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                          "required": ["query"]}, self.search)]


class GitHubIssues(Connector):
    platform = "github"
    label = "GitHub issues"

    def enabled(self):
        return (bool(self.env.get("GITHUB_TOKEN")), "set GITHUB_TOKEN (search API needs auth for useful limits)")

    async def search(self, ctx: Ctx, a: dict):
        from datetime import datetime, timezone
        since = datetime.fromtimestamp(ctx.since_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        q = f"{a['query']} created:>={since}"
        if a.get("repo"):
            q += f" repo:{a['repo']}"
        r = await ctx.gov.get("https://api.github.com/search/issues",
                              params={"q": q, "sort": "created", "order": "desc", "per_page": min(int(a.get("limit", 20)), 50)},
                              headers={"Authorization": f"Bearer {self.env['GITHUB_TOKEN']}",
                                       "Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            return {"error": f"github HTTP {r.status_code}", "body": r.text[:300]}
        items = []
        for i in r.json().get("items", []):
            repo = i.get("repository_url", "").split("/repos/")[-1]
            user = i.get("user", {})
            items.append(Item(
                platform="github", kind="issue", url=i.get("html_url"), title=i.get("title"), text=i.get("body") or "",
                author=user.get("login"), author_url=user.get("html_url"), posted_at=parse_iso(i.get("created_at")),
                community=repo, community_url=f"https://github.com/{repo}", thread_key=i.get("html_url"),
                engagement={"comments": i.get("comments"), "reactions": (i.get("reactions") or {}).get("total_count")},
            ))
        return {"results": record_items(ctx, items)}

    def tools(self):
        return [ToolSpec("github_issue_search",
                         "Search GitHub issues/discussions, e.g. complaints or feature requests on a competitor's repo.",
                         {"type": "object", "properties": {
                             "query": {"type": "string"}, "repo": {"type": "string", "description": "owner/name"},
                             "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                          "required": ["query"]}, self.search)]
