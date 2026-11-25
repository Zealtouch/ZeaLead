# Writing a connector

A connector gives the worker agents tools for one platform. It talks to the platform's
official API or a search engine, turns the results into `Item`s, and passes them to
`record_items`. `record_items` handles the rest: storing evidence, updating the source graph,
and building what the model sees.

## Rules

- **Official APIs and search engines only.** Don't scrape sites whose terms forbid it, don't
  get past logins, paywalls or CAPTCHAs, and don't impersonate a browser. For LinkedIn, X,
  Facebook, Instagram and Threads, the search-engine snippet is the evidence (see `NO_FETCH`
  in `web.py`).
- **Read only.** A connector never posts, likes, follows or sends messages.
- **Make every request through `ctx.gov`.** The governor paces each host and backs off on 429
  and 503. Don't create your own HTTP client.
- **Return whatever text the platform gave you, untouched.** `connector_tools` wraps every result
  in the nonce envelope before the model sees it. Never put the text into a prompt yourself.
- **Respect the recency window.** Filter with `ctx.since_ts` on the server side where the API
  allows it.

## Skeleton

```python
# zealead/connectors/example.py
from .base import Connector, Ctx, Item, ToolSpec, record_items

class Example(Connector):
    platform = "example"          # stable id: used in lead dedup keys and brief allow/deny lists
    label = "Example Forum"       # shown in the CLI and the console

    def enabled(self) -> tuple[bool, str]:
        if not self.env.get("EXAMPLE_TOKEN"):
            return False, "set EXAMPLE_TOKEN"
        return True, ""

    async def search(self, ctx: Ctx, a: dict):
        r = await ctx.gov.get("https://api.example.com/search",
                              params={"q": a["query"], "since": int(ctx.since_ts)},
                              headers={"Authorization": f"Bearer {self.env['EXAMPLE_TOKEN']}"})
        if r.status_code != 200:
            return {"error": f"example search HTTP {r.status_code}"}
        items = [Item(
            platform="example", kind="post",
            url=h["url"], text=h["body"], title=h.get("title"),
            author=h["user"], author_url=h.get("user_url"),
            posted_at=h["created_ts"],
            community=h.get("board"), community_url=h.get("board_url"),
            thread_key=str(h["thread_id"]), thread_title=h.get("thread_title"),
            engagement={"replies": h.get("replies")},
        ) for h in r.json()["results"]]
        return {"results": record_items(ctx, items)}

    def tools(self) -> list[ToolSpec]:
        return [ToolSpec(
            "example_search",
            "Search Example Forum posts within the recency window. Good for <who posts here>.",
            {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            self.search,
        )]
```

Then:

1. Add the class to `ALL` in `zealead/connectors/__init__.py`.
2. Document the keys it needs in `.env.example` and in the platform table in the README.
3. Add a test that returns a fake HTTP response (no network). The `FakeReddit` connector in
   `tests/test_engine.py` shows the shape.

## The `Item` fields that matter

| Field | Why it matters |
|---|---|
| `url` | Becomes the lead's link. It must point at the post itself, not a search page. |
| `text` | The gate checks the lead's evidence quote against this text **verbatim**. Convert HTML with `html_to_text`. |
| `author`, `author_url` | Leads are deduplicated by `platform:author`. Leave them as `None` for anonymous content. That content can still produce facts, but never a lead. |
| `posted_at` | Unix seconds. Posts older than the brief's recency window are refused as leads. |
| `community`, `community_url` | Become nodes in the source graph. The planner uses their coverage to decide where to dig next. |
| `thread_key`, `thread_title` | Group posts and comments into threads in the source graph. |

## Writing good tool descriptions

The planner and workers choose tools by their descriptions. Say what the tool returns, which
time window it covers, and what kinds of buyers tend to post there. Keep schemas small: a query
plus one or two optional filters works better than many knobs.
