"""Self-contained HTML lead report."""

from __future__ import annotations

import html
from datetime import datetime, timezone

from .store import Store
from .tools import goal_progress

CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#e6e6e6;--card:#fafafa;--hot:#c2410c;--warm:#a16207;--cold:#475569}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--muted:#9a9a9a;--line:#2a2a2a;--card:#1c1c1c;--hot:#fb923c;--warm:#facc15;--cold:#94a3b8}}
body{font:15px/1.5 system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--fg);max-width:1000px;margin:2rem auto;padding:0 1rem}
h1{font-size:1.5rem;margin:0 0 .25rem}.muted{color:var(--muted)}
.stats{display:flex;gap:1.5rem;margin:1.25rem 0;flex-wrap:wrap}.stat b{font-size:1.4rem;display:block}
.lead{border:1px solid var(--line);background:var(--card);border-radius:8px;padding:.9rem 1rem;margin:.75rem 0}
.lead h3{margin:0;font-size:1rem}.tag{font-size:.75rem;font-weight:600;text-transform:uppercase;margin-right:.5rem}
.hot{color:var(--hot)}.warm{color:var(--warm)}.cold{color:var(--cold)}
blockquote{margin:.5rem 0;padding-left:.75rem;border-left:3px solid var(--line)}
details{margin-top:.4rem}a{color:inherit}
"""


def _d(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else "date unknown"


def render_html(st: Store, cid: int) -> str:
    c = st.campaign(cid)
    e = html.escape
    lc = st.lead_counts(cid)
    goals = "".join(
        f"<li>{e(g.payload.get('text', ''))} — <b>{goal_progress(st, cid, g.payload)[0]}/{g.payload.get('target_count')}</b> [{g.state}]</li>"
        for g in st.nodes(cid, "goal"))
    cards = []
    for r in st.leads(cid):
        reply = "".join(
            f"<details><summary>{label}</summary><p style='white-space:pre-wrap'>{e(r[k])}</p></details>"
            for label, k in (("Public reply (draft)", "suggested_reply"), ("Direct message (draft)", "dm_message"))
            if r.get(k))
        author = (f"<a href='{e(r['author_url'])}'>{e(r['author'] or '?')}</a>" if r.get("author_url")
                  else e(r.get("author") or "unknown author"))
        cards.append(
            f"<div class='lead'><h3><span class='tag {r['intent_level']}'>{r['intent_level']}</span>"
            f"{author} · {e(r['platform'])} · fit {r['fit_score']}</h3>"
            f"<div class='muted'>{_d(r['posted_at'])} · {e(r['pain'] or '')} · status: {r['status']} · lead #{r['node_id']}</div>"
            f"<blockquote>“{e(r['quote'])}”</blockquote>"
            f"<div><a href='{e(r['url'])}'>Open post</a></div>"
            f"<details><summary>Why this is a lead</summary><p>{e(r['reason'] or '')}</p></details>{reply}</div>")
    by_plat = ", ".join(f"{e(p)}: {sum(v.values())}" for p, v in lc["by_platform"].items()) or "none yet"
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(c['name'])} — leads</title><style>{CSS}</style></head><body>
<h1>{e(c['name'])}: potential customers</h1>
<div class="muted">Campaign #{cid} · {e(c['status'])} {e(c['end_reason'] or '')}</div>
<div class="stats"><div class="stat"><b class="hot">{lc['hot']}</b>hot</div><div class="stat"><b class="warm">{lc['warm']}</b>warm</div>
<div class="stat"><b class="cold">{lc['cold']}</b>cold</div><div class="stat"><b>{by_plat}</b>by platform</div></div>
<h2>Goals</h2><ul>{goals}</ul><h2>Leads</h2>{''.join(cards) or '<p class="muted">No leads yet.</p>'}
</body></html>"""
