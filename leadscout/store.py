"""SQLite persistence for the two linked graphs.

Source graph (shared across campaigns): platform -> community -> thread, plus
authors. Parent links and dedup keys are computed here; agents only submit raw
observations.

Exploration graph (per campaign): goal / intent / fact / lead / hint nodes joined
by spawns / derived_from / yields / proves edges. Anchors tie exploration nodes
to the sources they touched, which is what powers community coverage.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    brief       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'created',
    end_reason  TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id           INTEGER PRIMARY KEY,
    campaign_id  INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL CHECK (kind IN ('goal','intent','fact','lead','hint')),
    payload      TEXT NOT NULL DEFAULT '{}',
    state        TEXT NOT NULL,
    origin       TEXT,
    owner        TEXT,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    CHECK (
        (kind='goal'   AND state IN ('open','met','abandoned')) OR
        (kind='intent' AND state IN ('open','running','done','exhausted','blocked','stopped')) OR
        (kind='fact'   AND state IN ('confirmed','dismissed')) OR
        (kind='lead'   AND state IN ('confirmed','dismissed')) OR
        (kind='hint'   AND state IN ('active','consumed'))
    )
);
CREATE INDEX IF NOT EXISTS idx_nodes_campaign ON nodes(campaign_id, kind, state);

CREATE TABLE IF NOT EXISTS edges (
    campaign_id INTEGER NOT NULL,
    src_id      INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    dst_id      INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    rel         TEXT NOT NULL CHECK (rel IN ('spawns','derived_from','yields','proves')),
    PRIMARY KEY (campaign_id, src_id, rel, dst_id),
    CHECK (src_id <> dst_id)
);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id, rel);

CREATE TABLE IF NOT EXISTS sources (
    id         INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL CHECK (kind IN ('platform','community','thread','author')),
    platform   TEXT NOT NULL,
    key        TEXT NOT NULL,
    title      TEXT,
    url        TEXT,
    parent_id  INTEGER REFERENCES sources(id),
    meta       TEXT NOT NULL DEFAULT '{}',
    first_seen REAL NOT NULL,
    UNIQUE (kind, platform, key)
);

CREATE TABLE IF NOT EXISTS anchors (
    node_id   INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    PRIMARY KEY (node_id, source_id)
);
CREATE INDEX IF NOT EXISTS idx_anchor_source ON anchors(source_id);

CREATE TABLE IF NOT EXISTS captures (
    id          INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL,
    intent_id   INTEGER,
    platform    TEXT NOT NULL,
    url         TEXT NOT NULL,
    author      TEXT,
    author_url  TEXT,
    title       TEXT,
    text        TEXT NOT NULL,
    posted_at   REAL,
    fetched_at  REAL NOT NULL,
    meta        TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_captures_url ON captures(campaign_id, url);

CREATE TABLE IF NOT EXISTS leads (
    node_id         INTEGER PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
    campaign_id     INTEGER NOT NULL,
    dedup_key       TEXT NOT NULL,
    platform        TEXT NOT NULL,
    author          TEXT,
    author_url      TEXT,
    url             TEXT NOT NULL,
    quote           TEXT NOT NULL,
    posted_at       REAL,
    intent_level    TEXT NOT NULL CHECK (intent_level IN ('hot','warm','cold')),
    fit_score       INTEGER NOT NULL,
    pain            TEXT,
    reason          TEXT,
    suggested_reply TEXT,
    capture_id      INTEGER NOT NULL REFERENCES captures(id),
    status          TEXT NOT NULL DEFAULT 'new'
                    CHECK (status IN ('new','contacted','replied','won','dismissed')),
    created_at      REAL NOT NULL,
    UNIQUE (campaign_id, dedup_key)
);

CREATE TABLE IF NOT EXISTS lead_evidence (
    lead_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    capture_id   INTEGER NOT NULL REFERENCES captures(id),
    quote        TEXT NOT NULL,
    PRIMARY KEY (lead_node_id, capture_id)
);

CREATE TABLE IF NOT EXISTS constraints (
    id          INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('allow','deny')),
    text        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS todos (
    campaign_id INTEGER PRIMARY KEY,
    items       TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS activity (
    id          INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL,
    intent_id   INTEGER,
    role        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    summary     TEXT NOT NULL,
    detail      TEXT,
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity ON activity(campaign_id, intent_id);

CREATE TABLE IF NOT EXISTS llm_usage (
    id            INTEGER PRIMARY KEY,
    campaign_id   INTEGER NOT NULL,
    role          TEXT NOT NULL,
    intent_id     INTEGER,
    model         TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read    INTEGER NOT NULL DEFAULT 0,
    cache_write   INTEGER NOT NULL DEFAULT 0,
    ts            REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- The businesses leads are found for (your own products, or clients if you are an agency).
CREATE TABLE IF NOT EXISTS companies (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    website     TEXT,
    description TEXT,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin','member')),
    created_at    REAL NOT NULL,
    last_login_at REAL
);

-- One agent session: a decomposition, a planner round, or one worker intent.
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL,
    role        TEXT NOT NULL,
    intent_id   INTEGER,
    model       TEXT NOT NULL,
    title       TEXT,
    state       TEXT NOT NULL DEFAULT 'running',
    error       TEXT,
    started_at  REAL NOT NULL,
    ended_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_runs ON runs(campaign_id, role);

-- The transcript of a run: the prompt, each model reply, and the tool results sent back.
CREATE TABLE IF NOT EXISTS run_messages (
    id      INTEGER PRIMARY KEY,
    run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    role    TEXT NOT NULL CHECK (role IN ('user','assistant','tool')),
    content TEXT NOT NULL,
    ts      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_messages ON run_messages(run_id, id);

-- Every tool an agent called, with its input, (truncated) output and timing.
CREATE TABLE IF NOT EXISTS tool_calls (
    id          INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL,
    run_id      INTEGER,
    intent_id   INTEGER,
    role        TEXT NOT NULL,
    tool        TEXT NOT NULL,
    input       TEXT NOT NULL,
    output      TEXT,
    is_error    INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_calls ON tool_calls(campaign_id, id);
"""

# Additive migrations for databases created by earlier versions.
MIGRATIONS = [
    "ALTER TABLE campaigns ADD COLUMN runner TEXT",
    "ALTER TABLE campaigns ADD COLUMN heartbeat_at REAL",
    "ALTER TABLE campaigns ADD COLUMN company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL",
    "ALTER TABLE llm_usage ADD COLUMN run_id INTEGER",
    "ALTER TABLE llm_usage ADD COLUMN stop_reason TEXT",
    "ALTER TABLE llm_usage ADD COLUMN duration_ms INTEGER",
    "ALTER TABLE llm_usage ADD COLUMN message_id INTEGER",
    "CREATE INDEX IF NOT EXISTS idx_llm_usage_run ON llm_usage(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign_id)",
    # personalised outreach drafts (suggested_reply holds the public in-thread reply)
    "ALTER TABLE leads ADD COLUMN dm_message TEXT",
    "ALTER TABLE leads ADD COLUMN message_angle TEXT",
    "ALTER TABLE leads ADD COLUMN message_note TEXT",
    "ALTER TABLE leads ADD COLUMN drafted_at REAL",
    "ALTER TABLE leads ADD COLUMN message_edited INTEGER NOT NULL DEFAULT 0",
]

TRANSCRIPT_TEXT_LIMIT = 12000   # characters kept per tool result / text block in a transcript
TOOL_OUTPUT_LIMIT = 20000       # characters kept per tool call output

HEARTBEAT_STALE_SECONDS = 45

ACTIVE_INTENT_STATES = ("open", "running")
INTENT_LEVEL_RANK = {"cold": 0, "warm": 1, "hot": 2}


@dataclass
class Node:
    id: int
    campaign_id: int
    kind: str
    payload: dict
    state: str
    origin: str | None
    owner: str | None
    created_at: float
    updated_at: float

    @property
    def summary(self) -> str:
        return str(self.payload.get("summary") or self.payload.get("text") or "")


def _now() -> float:
    return time.time()


class Store:
    """Thread-safe wrapper over one SQLite connection.

    Every call is short, so a single lock is enough for the asyncio engine
    (calls run inline on the event loop thread).
    """

    def __init__(self, path: str):
        self.path = path
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        with self._lock:
            self._db.executescript(SCHEMA)
            for m in MIGRATIONS:
                try:
                    self._db.execute(m)
                except sqlite3.OperationalError:
                    pass  # column already exists

    # ---------- low level ----------
    def _q(self, sql: str, args: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, tuple(args)).fetchall()

    def _x(self, sql: str, args: Iterable[Any] = ()) -> int:
        with self._lock:
            cur = self._db.execute(sql, tuple(args))
            return cur.lastrowid or cur.rowcount

    # ---------- campaigns ----------
    def create_campaign(self, name: str, brief: dict, company_id: int | None = None) -> int:
        t = _now()
        return self._x(
            "INSERT INTO campaigns(name, brief, status, created_at, updated_at, company_id) VALUES (?,?,?,?,?,?)",
            (name, json.dumps(brief), "created", t, t, company_id),
        )

    def campaign(self, cid: int) -> dict | None:
        rows = self._q("SELECT * FROM campaigns WHERE id=?", (cid,))
        if not rows:
            return None
        r = dict(rows[0])
        r["brief"] = json.loads(r["brief"])
        return r

    def campaigns(self, company_id: int | None = None) -> list[dict]:
        sql = "SELECT id, name, status, end_reason, created_at, company_id FROM campaigns"
        args: tuple = ()
        if company_id is not None:
            sql, args = sql + " WHERE company_id=?", (company_id,)
        return [dict(r) for r in self._q(sql + " ORDER BY id DESC", args)]

    def set_campaign_company(self, cid: int, company_id: int | None) -> None:
        self._x("UPDATE campaigns SET company_id=?, updated_at=? WHERE id=?", (company_id, _now(), cid))

    def set_campaign_status(self, cid: int, status: str, reason: str | None = None) -> None:
        self._x("UPDATE campaigns SET status=?, end_reason=?, updated_at=? WHERE id=?", (status, reason, _now(), cid))

    def heartbeat(self, cid: int, runner: str | None) -> None:
        self._x("UPDATE campaigns SET runner=?, heartbeat_at=? WHERE id=?", (runner, _now() if runner else None, cid))

    def runner_alive(self, cid: int) -> str | None:
        """Name of the process currently running this campaign, if its heartbeat is fresh."""
        rows = self._q("SELECT runner, heartbeat_at FROM campaigns WHERE id=?", (cid,))
        if not rows or not rows[0]["runner"] or not rows[0]["heartbeat_at"]:
            return None
        return rows[0]["runner"] if _now() - rows[0]["heartbeat_at"] < HEARTBEAT_STALE_SECONDS else None

    def update_brief(self, cid: int, brief: dict, name: str) -> None:
        self._x("UPDATE campaigns SET brief=?, name=?, updated_at=? WHERE id=?", (json.dumps(brief), name, _now(), cid))

    def delete_campaign(self, cid: int) -> None:
        with self._lock:
            node_ids = "SELECT id FROM nodes WHERE campaign_id=?"
            self._db.execute(f"DELETE FROM lead_evidence WHERE lead_node_id IN ({node_ids})", (cid,))
            self._db.execute(f"DELETE FROM anchors WHERE node_id IN ({node_ids})", (cid,))
            self._db.execute("DELETE FROM run_messages WHERE run_id IN (SELECT id FROM runs WHERE campaign_id=?)", (cid,))
            for t in ("leads", "edges", "nodes", "captures", "constraints", "todos", "activity", "llm_usage",
                      "runs", "tool_calls"):
                self._db.execute(f"DELETE FROM {t} WHERE campaign_id=?", (cid,))
            self._db.execute("DELETE FROM campaigns WHERE id=?", (cid,))

    # ---------- settings (non-secret overrides; secrets stay in the environment) ----------
    def get_settings(self) -> dict[str, str]:
        return {r["key"]: r["value"] for r in self._q("SELECT key, value FROM settings")}

    def set_setting(self, key: str, value: str | None) -> None:
        if value is None or value == "":
            self._x("DELETE FROM settings WHERE key=?", (key,))
        else:
            self._x("INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value))

    # ---------- read models for the console ----------
    def graph(self, cid: int) -> dict:
        nodes = [{"id": r["id"], "kind": r["kind"], "state": r["state"],
                  "summary": (json.loads(r["payload"]).get("summary") or json.loads(r["payload"]).get("text") or "")[:300],
                  "platform": json.loads(r["payload"]).get("platform")}
                 for r in self._q("SELECT id, kind, state, payload FROM nodes WHERE campaign_id=? AND kind<>'hint'", (cid,))]
        edges = [dict(r) for r in self._q("SELECT src_id AS source, dst_id AS target, rel FROM edges WHERE campaign_id=?", (cid,))]
        return {"nodes": nodes, "edges": edges}

    def intent_rows(self, cid: int) -> list[dict]:
        rows = self._q(
            """SELECT n.id, n.state, n.owner, n.payload, n.created_at, n.updated_at,
                      (SELECT COUNT(*) FROM edges e JOIN nodes y ON y.id=e.dst_id WHERE e.src_id=n.id AND e.rel='yields' AND y.kind='lead') AS leads,
                      (SELECT COUNT(*) FROM edges e JOIN nodes y ON y.id=e.dst_id WHERE e.src_id=n.id AND e.rel='yields' AND y.kind='fact') AS facts,
                      (SELECT COALESCE(SUM(input_tokens+output_tokens+cache_read+cache_write),0) FROM llm_usage u WHERE u.intent_id=n.id) AS tokens
               FROM nodes n WHERE n.campaign_id=? AND n.kind='intent' ORDER BY n.id DESC""", (cid,))
        out = []
        for r in rows:
            p = json.loads(r["payload"])
            out.append({"id": r["id"], "state": r["state"], "owner": r["owner"], "summary": p.get("summary"),
                        "platform": p.get("platform"), "goal_id": p.get("goal_id"), "leads": r["leads"], "facts": r["facts"],
                        "tokens": r["tokens"], "created_at": r["created_at"], "updated_at": r["updated_at"]})
        return out

    def activity(self, cid: int, after: int = 0, intent_id: int | None = None, limit: int = 200) -> list[dict]:
        sql = "SELECT id, intent_id, role, kind, summary, ts FROM activity WHERE campaign_id=? AND id>?"
        args: list[Any] = [cid, after]
        if intent_id is not None:
            sql += " AND intent_id=?"
            args.append(intent_id)
        if after:
            sql += " ORDER BY id ASC LIMIT ?"
            args.append(limit)
            return [dict(r) for r in self._q(sql, args)]
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in reversed(self._q(sql, args))]

    def activity_detail(self, activity_id: int) -> dict | None:
        rows = self._q("SELECT * FROM activity WHERE id=?", (activity_id,))
        return dict(rows[0]) if rows else None

    def community_rows(self, cid: int) -> list[dict]:
        rows = self._q(
            """SELECT s.id, s.platform, s.key, s.url,
                 MAX(CASE WHEN n.kind='intent' THEN 1 ELSE 0 END) AS targeted,
                 MAX(CASE WHEN n.kind='intent' AND n.state IN ('done','exhausted') THEN 1 ELSE 0 END) AS mined,
                 SUM(CASE WHEN n.kind='lead' THEN 1 ELSE 0 END) AS leads,
                 SUM(CASE WHEN n.kind='fact' THEN 1 ELSE 0 END) AS facts
               FROM sources s JOIN anchors a ON a.source_id=s.id JOIN nodes n ON n.id=a.node_id
               WHERE s.kind='community' AND n.campaign_id=? GROUP BY s.id ORDER BY leads DESC, s.id DESC""", (cid,))
        return [dict(r) for r in rows]

    def lead_evidence_rows(self, lead_node_id: int) -> list[dict]:
        return [dict(r) for r in self._q(
            """SELECT e.quote, c.url, c.platform, c.posted_at, c.text FROM lead_evidence e JOIN captures c ON c.id=e.capture_id
               WHERE e.lead_node_id=?""", (lead_node_id,))]

    def lead(self, node_id: int) -> dict | None:
        rows = self._q("SELECT * FROM leads WHERE node_id=?", (node_id,))
        return dict(rows[0]) if rows else None

    def leads_filtered(self, cid: int, min_intent: str = "cold", platform: str | None = None,
                       status: str | None = None, q: str | None = None) -> list[dict]:
        rows = self.leads(cid, min_intent=min_intent, platform=platform, include_dismissed=(status == "dismissed"))
        if status:
            rows = [r for r in rows if r["status"] == status]
        if q:
            ql = q.lower()
            rows = [r for r in rows if ql in " ".join(str(r.get(k) or "") for k in ("author", "pain", "quote", "reason")).lower()]
        return rows

    # ---------- nodes / edges ----------
    def _node(self, r: sqlite3.Row) -> Node:
        return Node(r["id"], r["campaign_id"], r["kind"], json.loads(r["payload"]), r["state"],
                    r["origin"], r["owner"], r["created_at"], r["updated_at"])

    def add_node(self, cid: int, kind: str, payload: dict, state: str, origin: str | None = None) -> int:
        t = _now()
        return self._x(
            "INSERT INTO nodes(campaign_id, kind, payload, state, origin, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (cid, kind, json.dumps(payload), state, origin, t, t),
        )

    def get_node(self, nid: int) -> Node | None:
        rows = self._q("SELECT * FROM nodes WHERE id=?", (nid,))
        return self._node(rows[0]) if rows else None

    def nodes(self, cid: int, kind: str, states: Iterable[str] | None = None,
              limit: int = 500, newest_first: bool = False) -> list[Node]:
        sql = "SELECT * FROM nodes WHERE campaign_id=? AND kind=?"
        args: list[Any] = [cid, kind]
        if states:
            st = list(states)
            sql += f" AND state IN ({','.join('?' * len(st))})"
            args += st
        sql += " ORDER BY id " + ("DESC" if newest_first else "ASC") + " LIMIT ?"
        args.append(limit)
        return [self._node(r) for r in self._q(sql, args)]

    def set_state(self, nid: int, state: str) -> None:
        self._x("UPDATE nodes SET state=?, updated_at=? WHERE id=?", (state, _now(), nid))

    def update_payload(self, nid: int, **fields: Any) -> None:
        n = self.get_node(nid)
        if not n:
            return
        n.payload.update(fields)
        self._x("UPDATE nodes SET payload=?, updated_at=? WHERE id=?", (json.dumps(n.payload), _now(), nid))

    def add_edge(self, cid: int, src: int, dst: int, rel: str) -> None:
        if src == dst:
            return
        self._x("INSERT OR IGNORE INTO edges(campaign_id, src_id, dst_id, rel) VALUES (?,?,?,?)", (cid, src, dst, rel))

    def parents(self, nid: int) -> list[int]:
        return [r[0] for r in self._q("SELECT src_id FROM edges WHERE dst_id=? AND rel IN ('spawns','derived_from')", (nid,))]

    def producers(self, nid: int) -> list[int]:
        """Intents that yielded this fact or lead."""
        return [r[0] for r in self._q("SELECT src_id FROM edges WHERE dst_id=? AND rel='yields'", (nid,))]

    def yields(self, nid: int) -> list[int]:
        return [r[0] for r in self._q("SELECT dst_id FROM edges WHERE src_id=? AND rel='yields'", (nid,))]

    def claim_next_intent(self, cid: int, owner: str) -> Node | None:
        """Atomically move the highest-priority open intent to running."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id FROM nodes WHERE campaign_id=? AND kind='intent' AND state='open' "
                "ORDER BY json_extract(payload,'$.priority') DESC, id ASC LIMIT 1", (cid,)
            ).fetchall()
            if not rows:
                return None
            nid = rows[0][0]
            cur = self._db.execute(
                "UPDATE nodes SET state='running', owner=?, updated_at=? WHERE id=? AND state='open'",
                (owner, _now(), nid),
            )
            if cur.rowcount != 1:
                return None
        return self.get_node(nid)

    def reset_running(self, cid: int) -> int:
        """On restart, running intents have no live worker: return them to the frontier."""
        return self._x("UPDATE nodes SET state='open', owner=NULL WHERE campaign_id=? AND kind='intent' AND state='running'", (cid,))

    def count_intents(self, cid: int, states: Iterable[str]) -> int:
        st = list(states)
        return self._q(
            f"SELECT COUNT(*) FROM nodes WHERE campaign_id=? AND kind='intent' AND state IN ({','.join('?' * len(st))})",
            [cid, *st],
        )[0][0]

    # ---------- source graph ----------
    def upsert_source(self, kind: str, platform: str, key: str, title: str | None = None,
                      url: str | None = None, parent_id: int | None = None, meta: dict | None = None) -> int:
        key = key.strip().lower()
        rows = self._q("SELECT id FROM sources WHERE kind=? AND platform=? AND key=?", (kind, platform, key))
        if rows:
            sid = rows[0][0]
            if title or url or parent_id:
                self._x(
                    "UPDATE sources SET title=COALESCE(title,?), url=COALESCE(url,?), parent_id=COALESCE(parent_id,?) WHERE id=?",
                    (title, url, parent_id, sid),
                )
            return sid
        return self._x(
            "INSERT INTO sources(kind, platform, key, title, url, parent_id, meta, first_seen) VALUES (?,?,?,?,?,?,?,?)",
            (kind, platform, key, title, url, parent_id, json.dumps(meta or {}), _now()),
        )

    def platform_source(self, platform: str) -> int:
        return self.upsert_source("platform", platform, platform, title=platform)

    def community_source(self, platform: str, key: str, title: str | None = None, url: str | None = None) -> int:
        return self.upsert_source("community", platform, key, title or key, url, self.platform_source(platform))

    def anchor(self, node_id: int, source_ids: Iterable[int]) -> None:
        for sid in source_ids:
            self._x("INSERT OR IGNORE INTO anchors(node_id, source_id) VALUES (?,?)", (node_id, sid))

    def anchored_sources(self, node_id: int) -> list[int]:
        return [r[0] for r in self._q("SELECT source_id FROM anchors WHERE node_id=?", (node_id,))]

    def list_sources(self, kind: str | None = None, platform: str | None = None, q: str | None = None,
                     ids: list[int] | None = None, limit: int = 50) -> list[dict]:
        sql, args = "SELECT * FROM sources WHERE 1=1", []
        if ids:
            sql += f" AND id IN ({','.join('?' * len(ids))})"
            args += ids
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if platform:
            sql += " AND platform=?"
            args.append(platform)
        if q:
            sql += " AND (key LIKE ? OR title LIKE ?)"
            args += [f"%{q.lower()}%", f"%{q}%"]
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self._q(sql, args)]

    def unmined_communities(self, cid: int, limit: int = 15) -> list[dict]:
        """Communities seen in this campaign's captures/facts that no intent has anchored yet."""
        return [dict(r) for r in self._q(
            """
            SELECT s.id, s.platform, s.key, s.title, s.url FROM sources s
            WHERE s.kind='community'
              AND s.id IN (SELECT a.source_id FROM anchors a JOIN nodes n ON n.id=a.node_id
                           WHERE n.campaign_id=? AND n.kind IN ('fact','lead'))
              AND s.id NOT IN (SELECT a.source_id FROM anchors a JOIN nodes n ON n.id=a.node_id
                               WHERE n.campaign_id=? AND n.kind='intent')
            ORDER BY s.id DESC LIMIT ?
            """, (cid, cid, limit))]

    def community_coverage(self, cid: int) -> dict:
        seen = self._q(
            """SELECT COUNT(DISTINCT s.id) FROM sources s JOIN anchors a ON a.source_id=s.id
               JOIN nodes n ON n.id=a.node_id WHERE s.kind='community' AND n.campaign_id=?""", (cid,))[0][0]
        mined = self._q(
            """SELECT COUNT(DISTINCT s.id) FROM sources s JOIN anchors a ON a.source_id=s.id
               JOIN nodes n ON n.id=a.node_id WHERE s.kind='community' AND n.campaign_id=?
               AND n.kind='intent' AND n.state IN ('done','exhausted')""", (cid,))[0][0]
        return {"communities_seen": seen, "communities_mined": mined}

    # ---------- captures (evidence) ----------
    def add_capture(self, cid: int, intent_id: int | None, platform: str, url: str, text: str,
                    author: str | None = None, author_url: str | None = None, title: str | None = None,
                    posted_at: float | None = None, meta: dict | None = None) -> int:
        return self._x(
            "INSERT INTO captures(campaign_id, intent_id, platform, url, author, author_url, title, text, posted_at, fetched_at, meta)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (cid, intent_id, platform, url, author, author_url, title, text, posted_at, _now(), json.dumps(meta or {})),
        )

    def get_capture(self, capture_id: int) -> dict | None:
        rows = self._q("SELECT * FROM captures WHERE id=?", (capture_id,))
        return dict(rows[0]) if rows else None

    # ---------- leads ----------
    def lead_by_key(self, cid: int, dedup_key: str) -> dict | None:
        rows = self._q("SELECT * FROM leads WHERE campaign_id=? AND dedup_key=?", (cid, dedup_key))
        return dict(rows[0]) if rows else None

    def insert_lead(self, cid: int, node_id: int, **f: Any) -> None:
        self._x(
            "INSERT INTO leads(node_id, campaign_id, dedup_key, platform, author, author_url, url, quote, posted_at,"
            " intent_level, fit_score, pain, reason, suggested_reply, capture_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (node_id, cid, f["dedup_key"], f["platform"], f.get("author"), f.get("author_url"), f["url"], f["quote"],
             f.get("posted_at"), f["intent_level"], f["fit_score"], f.get("pain"), f.get("reason"),
             f.get("suggested_reply"), f["capture_id"], _now()),
        )
        self.add_lead_evidence(node_id, f["capture_id"], f["quote"])

    def add_lead_evidence(self, lead_node_id: int, capture_id: int, quote: str) -> None:
        self._x("INSERT OR IGNORE INTO lead_evidence(lead_node_id, capture_id, quote) VALUES (?,?,?)",
                (lead_node_id, capture_id, quote))

    def upgrade_lead(self, node_id: int, intent_level: str, fit_score: int) -> None:
        self._x(
            "UPDATE leads SET intent_level=CASE WHEN ? > (CASE intent_level WHEN 'hot' THEN 2 WHEN 'warm' THEN 1 ELSE 0 END)"
            " THEN ? ELSE intent_level END, fit_score=MAX(fit_score, ?) WHERE node_id=?",
            (INTENT_LEVEL_RANK[intent_level], intent_level, fit_score, node_id),
        )

    def leads(self, cid: int, min_intent: str = "cold", platform: str | None = None,
              limit: int = 1000, include_dismissed: bool = False) -> list[dict]:
        sql = "SELECT l.* FROM leads l JOIN nodes n ON n.id=l.node_id WHERE l.campaign_id=?"
        args: list[Any] = [cid]
        if not include_dismissed:
            sql += " AND n.state='confirmed' AND l.status<>'dismissed'"
        levels = [k for k, v in INTENT_LEVEL_RANK.items() if v >= INTENT_LEVEL_RANK[min_intent]]
        sql += f" AND l.intent_level IN ({','.join('?' * len(levels))})"
        args += levels
        if platform:
            sql += " AND l.platform=?"
            args.append(platform)
        sql += " ORDER BY CASE l.intent_level WHEN 'hot' THEN 0 WHEN 'warm' THEN 1 ELSE 2 END, l.fit_score DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self._q(sql, args)]

    def lead_counts(self, cid: int) -> dict:
        out = {"hot": 0, "warm": 0, "cold": 0, "by_platform": {}}
        for r in self._q(
            "SELECT l.platform, l.intent_level, COUNT(*) c FROM leads l JOIN nodes n ON n.id=l.node_id"
            " WHERE l.campaign_id=? AND n.state='confirmed' AND l.status<>'dismissed' GROUP BY 1,2", (cid,)):
            out[r["intent_level"]] += r["c"]
            out["by_platform"].setdefault(r["platform"], {}).setdefault(r["intent_level"], r["c"])
        return out

    def set_lead_status(self, node_id: int, status: str) -> None:
        self._x("UPDATE leads SET status=? WHERE node_id=?", (status, node_id))

    # ---------- outreach drafts ----------
    def save_draft(self, node_id: int, reply: str | None, dm: str | None, angle: str | None,
                   note: str | None = None, edited: bool = False) -> None:
        self._x("UPDATE leads SET suggested_reply=?, dm_message=?, message_angle=?, message_note=?, drafted_at=?,"
                " message_edited=? WHERE node_id=?", (reply, dm, angle, note, _now(), int(edited), node_id))

    def edit_draft(self, node_id: int, reply: str | None = None, dm: str | None = None) -> None:
        """Operator edits: keep the other field, mark the draft as hand-edited."""
        sets, args = ["message_edited=1"], []
        if reply is not None:
            sets.append("suggested_reply=?")
            args.append(reply)
        if dm is not None:
            sets.append("dm_message=?")
            args.append(dm)
        self._x(f"UPDATE leads SET {', '.join(sets)} WHERE node_id=?", (*args, node_id))

    def undrafted_leads(self, cid: int, limit: int = 50) -> list[int]:
        """Leads still waiting for personalised messages, best first (dismissed ones are skipped)."""
        return [r[0] for r in self._q(
            """SELECT l.node_id FROM leads l JOIN nodes n ON n.id=l.node_id
               WHERE l.campaign_id=? AND l.drafted_at IS NULL AND n.state='confirmed' AND l.status<>'dismissed'
               ORDER BY CASE l.intent_level WHEN 'hot' THEN 0 WHEN 'warm' THEN 1 ELSE 2 END, l.fit_score DESC
               LIMIT ?""", (cid, limit))]

    def recent_drafts(self, cid: int, exclude: int, limit: int = 60) -> list[dict]:
        return [dict(r) for r in self._q(
            """SELECT node_id, suggested_reply, dm_message FROM leads
               WHERE campaign_id=? AND node_id<>? AND drafted_at IS NOT NULL ORDER BY drafted_at DESC LIMIT ?""",
            (cid, exclude, limit))]

    # ---------- constraints / todos ----------
    def add_constraint(self, cid: int, kind: str, text: str) -> None:
        self._x("INSERT INTO constraints(campaign_id, kind, text) VALUES (?,?,?)", (cid, kind, text))

    def constraints(self, cid: int) -> list[dict]:
        return [dict(r) for r in self._q("SELECT kind, text FROM constraints WHERE campaign_id=? ORDER BY id", (cid,))]

    def get_todos(self, cid: int) -> list[dict]:
        rows = self._q("SELECT items FROM todos WHERE campaign_id=?", (cid,))
        return json.loads(rows[0][0]) if rows else []

    def set_todos(self, cid: int, items: list[dict]) -> None:
        self._x("INSERT INTO todos(campaign_id, items) VALUES (?,?) ON CONFLICT(campaign_id) DO UPDATE SET items=excluded.items",
                (cid, json.dumps(items)))

    # ---------- activity / usage ----------
    def log(self, cid: int, role: str, kind: str, summary: str, detail: str | None = None,
            intent_id: int | None = None) -> None:
        self._x("INSERT INTO activity(campaign_id, intent_id, role, kind, summary, detail, ts) VALUES (?,?,?,?,?,?,?)",
                (cid, intent_id, role, kind, summary[:500], detail, _now()))

    def worker_output(self, intent_id: int) -> str:
        rows = self._q("SELECT summary, detail FROM activity WHERE intent_id=? AND kind='result' ORDER BY id DESC LIMIT 1",
                       (intent_id,))
        if not rows:
            return "(this work has no output yet)"
        return rows[0]["detail"] or rows[0]["summary"]

    def record_usage(self, cid: int, role: str, intent_id: int | None, model: str, usage: Any,
                     run_id: int | None = None, stop_reason: str | None = None, duration_ms: int | None = None,
                     message_id: int | None = None) -> int:
        return self._x(
            "INSERT INTO llm_usage(campaign_id, role, intent_id, model, input_tokens, output_tokens, cache_read, cache_write, ts,"
            " run_id, stop_reason, duration_ms, message_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, role, intent_id, model, getattr(usage, "input_tokens", 0) or 0, getattr(usage, "output_tokens", 0) or 0,
             getattr(usage, "cache_read_input_tokens", 0) or 0, getattr(usage, "cache_creation_input_tokens", 0) or 0, _now(),
             run_id, stop_reason, duration_ms, message_id),
        )

    def tokens_spent(self, cid: int) -> int:
        r = self._q("SELECT COALESCE(SUM(input_tokens+output_tokens+cache_read+cache_write),0) FROM llm_usage WHERE campaign_id=?",
                    (cid,))
        return int(r[0][0])

    def usage_summary(self, cid: int) -> dict:
        r = self._q("SELECT COALESCE(SUM(input_tokens),0) i, COALESCE(SUM(output_tokens),0) o, COALESCE(SUM(cache_read),0) cr,"
                    " COALESCE(SUM(cache_write),0) cw, COUNT(*) calls FROM llm_usage WHERE campaign_id=?", (cid,))[0]
        return dict(r)

    # ---------- companies ----------
    def companies(self) -> list[dict]:
        return [dict(r) for r in self._q(
            """SELECT c.*, (SELECT COUNT(*) FROM campaigns k WHERE k.company_id=c.id) AS tasks,
                      (SELECT COUNT(*) FROM leads l JOIN campaigns k ON k.id=l.campaign_id JOIN nodes n ON n.id=l.node_id
                       WHERE k.company_id=c.id AND n.state='confirmed' AND l.status<>'dismissed') AS leads
               FROM companies c ORDER BY c.name COLLATE NOCASE""")]

    def company(self, company_id: int) -> dict | None:
        rows = self._q("SELECT * FROM companies WHERE id=?", (company_id,))
        return dict(rows[0]) if rows else None

    def create_company(self, name: str, website: str | None = None, description: str | None = None) -> int:
        return self._x("INSERT INTO companies(name, website, description, created_at) VALUES (?,?,?,?)",
                       (name, website, description, _now()))

    def update_company(self, company_id: int, name: str, website: str | None, description: str | None) -> None:
        self._x("UPDATE companies SET name=?, website=?, description=? WHERE id=?", (name, website, description, company_id))

    def delete_company(self, company_id: int) -> None:
        with self._lock:
            self._db.execute("UPDATE campaigns SET company_id=NULL WHERE company_id=?", (company_id,))
            self._db.execute("DELETE FROM companies WHERE id=?", (company_id,))

    # ---------- users ----------
    def users(self) -> list[dict]:
        return [dict(r) for r in self._q("SELECT id, username, role, created_at, last_login_at FROM users ORDER BY id")]

    def user_count(self) -> int:
        return int(self._q("SELECT COUNT(*) FROM users")[0][0])

    def user_by_name(self, username: str) -> dict | None:
        rows = self._q("SELECT * FROM users WHERE username=?", (username,))
        return dict(rows[0]) if rows else None

    def user(self, uid: int) -> dict | None:
        rows = self._q("SELECT * FROM users WHERE id=?", (uid,))
        return dict(rows[0]) if rows else None

    def create_user(self, username: str, password_hash: str, role: str = "member") -> int:
        return self._x("INSERT INTO users(username, password_hash, role, created_at) VALUES (?,?,?,?)",
                       (username, password_hash, role, _now()))

    def set_user_password(self, uid: int, password_hash: str) -> None:
        self._x("UPDATE users SET password_hash=? WHERE id=?", (password_hash, uid))

    def set_user_role(self, uid: int, role: str) -> None:
        self._x("UPDATE users SET role=? WHERE id=?", (role, uid))

    def touch_login(self, uid: int) -> None:
        self._x("UPDATE users SET last_login_at=? WHERE id=?", (_now(), uid))

    def delete_user(self, uid: int) -> None:
        self._x("DELETE FROM users WHERE id=?", (uid,))

    def admin_count(self) -> int:
        return int(self._q("SELECT COUNT(*) FROM users WHERE role='admin'")[0][0])

    # ---------- runs, transcripts, tool calls ----------
    def start_run(self, cid: int, role: str, intent_id: int | None, model: str, title: str | None) -> int:
        return self._x("INSERT INTO runs(campaign_id, role, intent_id, model, title, started_at) VALUES (?,?,?,?,?,?)",
                       (cid, role, intent_id, model, (title or "")[:300], _now()))

    def end_run(self, run_id: int, state: str, error: str | None = None) -> None:
        self._x("UPDATE runs SET state=?, error=?, ended_at=? WHERE id=?", (state, error, _now(), run_id))

    def close_open_runs(self, cid: int) -> None:
        """Runs left 'running' by a stopped or crashed process."""
        self._x("UPDATE runs SET state='stopped', ended_at=? WHERE campaign_id=? AND state='running'", (_now(), cid))

    def add_message(self, run_id: int, role: str, content: list | str) -> int:
        return self._x("INSERT INTO run_messages(run_id, role, content, ts) VALUES (?,?,?,?)",
                       (run_id, role, json.dumps(content, ensure_ascii=False, default=str), _now()))

    def add_tool_call(self, cid: int, run_id: int | None, intent_id: int | None, role: str, tool: str, input: dict,
                      output: str, is_error: bool, duration_ms: int) -> int:
        return self._x(
            "INSERT INTO tool_calls(campaign_id, run_id, intent_id, role, tool, input, output, is_error, duration_ms, ts)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, run_id, intent_id, role, tool, json.dumps(input, ensure_ascii=False, default=str),
             (output or "")[:TOOL_OUTPUT_LIMIT], int(is_error), duration_ms, _now()))

    _RUN_COLS = """r.*, (SELECT COALESCE(SUM(input_tokens),0) FROM llm_usage u WHERE u.run_id=r.id) AS input_tokens,
                      (SELECT COALESCE(SUM(output_tokens),0) FROM llm_usage u WHERE u.run_id=r.id) AS output_tokens,
                      (SELECT COALESCE(SUM(cache_read),0) FROM llm_usage u WHERE u.run_id=r.id) AS cache_read,
                      (SELECT COUNT(*) FROM tool_calls t WHERE t.run_id=r.id) AS tool_calls"""

    def runs(self, cid: int) -> list[dict]:
        return [dict(r) for r in self._q(
            f"SELECT {self._RUN_COLS} FROM runs r WHERE r.campaign_id=? ORDER BY r.id", (cid,))]

    def run(self, run_id: int) -> dict | None:
        rows = self._q(f"SELECT {self._RUN_COLS} FROM runs r WHERE r.id=?", (run_id,))
        return dict(rows[0]) if rows else None

    def run_messages(self, run_id: int, after: int = 0, limit: int = 500) -> list[dict]:
        out = []
        for r in self._q("SELECT id, role, content, ts FROM run_messages WHERE run_id=? AND id>? ORDER BY id LIMIT ?",
                         (run_id, after, limit)):
            d = dict(r)
            d["content"] = json.loads(d["content"])
            out.append(d)
        return out

    def message(self, mid: int) -> dict | None:
        rows = self._q("SELECT id, run_id, role, content, ts FROM run_messages WHERE id=?", (mid,))
        if not rows:
            return None
        d = dict(rows[0])
        d["content"] = json.loads(d["content"])
        return d

    # ---------- cross-campaign read models (company filter = campaigns of that company) ----------
    @staticmethod
    def _scope(alias: str, company_id: int | None, cid: int | None) -> tuple[str, list]:
        sql, args = "", []
        if cid is not None:
            sql += f" AND {alias}.campaign_id=?"
            args.append(cid)
        if company_id is not None:
            sql += f" AND {alias}.campaign_id IN (SELECT id FROM campaigns WHERE company_id=?)"
            args.append(company_id)
        return sql, args

    def all_leads(self, company_id: int | None = None, cid: int | None = None, level: str | None = None,
                  status: str | None = None, platform: str | None = None, q: str | None = None,
                  sort: str = "level", offset: int = 0, limit: int = 50) -> dict:
        where, args = "WHERE n.state='confirmed'", []
        s, a = self._scope("l", company_id, cid)
        where += s
        args += a
        if status:
            where += " AND l.status=?"
            args.append(status)
        else:
            where += " AND l.status<>'dismissed'"
        if level:
            where += " AND l.intent_level=?"
            args.append(level)
        if platform:
            where += " AND l.platform=?"
            args.append(platform)
        if q:
            where += " AND (l.author LIKE ? OR l.pain LIKE ? OR l.quote LIKE ? OR l.reason LIKE ?)"
            args += [f"%{q}%"] * 4
        order = {
            "level": "CASE l.intent_level WHEN 'hot' THEN 0 WHEN 'warm' THEN 1 ELSE 2 END, l.fit_score DESC",
            "fit": "l.fit_score DESC",
            "newest": "l.created_at DESC",
            "posted": "COALESCE(l.posted_at,0) DESC",
        }.get(sort, "l.created_at DESC")
        base = f"FROM leads l JOIN nodes n ON n.id=l.node_id JOIN campaigns k ON k.id=l.campaign_id {where}"
        total = int(self._q(f"SELECT COUNT(*) {base}", args)[0][0])
        rows = self._q(f"SELECT l.*, k.name AS campaign_name, k.company_id {base} ORDER BY {order} LIMIT ? OFFSET ?",
                       args + [limit, offset])
        return {"items": [dict(r) for r in rows], "total": total}

    def lead_stats(self, company_id: int | None = None, cid: int | None = None) -> dict:
        s, a = self._scope("l", company_id, cid)
        out = {"total": 0, "hot": 0, "warm": 0, "cold": 0, "new": 0, "contacted": 0, "replied": 0, "won": 0,
               "dismissed": 0, "platforms": {}}
        for r in self._q(f"SELECT l.intent_level, l.status, l.platform, COUNT(*) c FROM leads l JOIN nodes n ON n.id=l.node_id"
                         f" WHERE n.state='confirmed'{s} GROUP BY 1,2,3", a):
            out[r["status"]] += r["c"]
            if r["status"] != "dismissed":
                out["total"] += r["c"]
                out[r["intent_level"]] += r["c"]
                out["platforms"][r["platform"]] = out["platforms"].get(r["platform"], 0) + r["c"]
        return out

    def dashboard(self, company_id: int | None = None, days: int = 14) -> dict:
        s, a = self._scope("x", company_id, None)
        camp_where = " WHERE company_id=?" if company_id is not None else ""
        camp_args = [company_id] if company_id is not None else []
        tasks = {r["status"]: r["c"] for r in self._q(f"SELECT status, COUNT(*) c FROM campaigns{camp_where} GROUP BY 1",
                                                      camp_args)}
        since = _now() - days * 86400
        lead_days = {r["d"]: dict(r) for r in self._q(
            f"""SELECT date(x.created_at,'unixepoch') d, SUM(x.intent_level='hot') hot, SUM(x.intent_level='warm') warm,
                       SUM(x.intent_level='cold') cold FROM leads x JOIN nodes n ON n.id=x.node_id
                WHERE n.state='confirmed' AND x.created_at>=?{s} GROUP BY 1""", [since] + a)}
        token_days = {r["d"]: r["t"] for r in self._q(
            f"""SELECT date(x.ts,'unixepoch') d, SUM(x.input_tokens+x.output_tokens+x.cache_read+x.cache_write) t
                FROM llm_usage x WHERE x.ts>=?{s} GROUP BY 1""", [since] + a)}
        series = []
        for i in range(days - 1, -1, -1):
            d = time.strftime("%Y-%m-%d", time.gmtime(_now() - i * 86400))
            ld = lead_days.get(d, {})
            series.append({"date": d, "hot": ld.get("hot") or 0, "warm": ld.get("warm") or 0, "cold": ld.get("cold") or 0,
                           "tokens": token_days.get(d) or 0})
        tok = self._q(f"SELECT COALESCE(SUM(x.input_tokens),0) i, COALESCE(SUM(x.output_tokens),0) o,"
                      f" COALESCE(SUM(x.cache_read),0) cr, COALESCE(SUM(x.cache_write),0) cw, COUNT(*) calls"
                      f" FROM llm_usage x WHERE 1=1{s}", a)[0]
        tools = self._q(f"SELECT COUNT(*) c, COALESCE(SUM(x.is_error),0) e FROM tool_calls x WHERE 1=1{s}", a)[0]
        recent = self.all_leads(company_id=company_id, sort="newest", limit=8)["items"]
        top_comm = [dict(r) for r in self._q(
            f"""SELECT s.platform, s.key, s.url, COUNT(DISTINCT n.id) leads FROM sources s
                JOIN anchors an ON an.source_id=s.id JOIN nodes n ON n.id=an.node_id
                WHERE s.kind='community' AND n.kind='lead' AND n.state='confirmed'
                {"AND n.campaign_id IN (SELECT id FROM campaigns WHERE company_id=?)" if company_id is not None else ""}
                GROUP BY s.id ORDER BY leads DESC LIMIT 8""", camp_args)]
        return {"tasks": tasks, "leads": self.lead_stats(company_id), "series": series, "tokens": dict(tok),
                "tool_calls": {"total": tools["c"], "errors": tools["e"]}, "recent_leads": recent,
                "top_communities": top_comm}

    def all_communities(self, company_id: int | None = None, platform: str | None = None, q: str | None = None,
                        offset: int = 0, limit: int = 50) -> dict:
        camp = "AND n.campaign_id IN (SELECT id FROM campaigns WHERE company_id=?)" if company_id is not None else ""
        args: list[Any] = [company_id] if company_id is not None else []
        where = ""
        if platform:
            where += " AND s.platform=?"
            args.append(platform)
        if q:
            where += " AND (s.key LIKE ? OR s.title LIKE ?)"
            args += [f"%{q}%", f"%{q}%"]
        base = f"""FROM sources s JOIN anchors an ON an.source_id=s.id JOIN nodes n ON n.id=an.node_id
                   WHERE s.kind='community' {camp}{where}"""
        total = int(self._q(f"SELECT COUNT(DISTINCT s.id) {base}", args)[0][0])
        rows = self._q(
            f"""SELECT s.id, s.platform, s.key, s.title, s.url, s.first_seen,
                   COUNT(DISTINCT n.campaign_id) campaigns,
                   COUNT(DISTINCT CASE WHEN n.kind='lead' AND n.state='confirmed' THEN n.id END) leads,
                   COUNT(DISTINCT CASE WHEN n.kind='fact' THEN n.id END) facts,
                   COUNT(DISTINCT CASE WHEN n.kind='intent' THEN n.id END) intents,
                   MAX(CASE WHEN n.kind='intent' AND n.state IN ('done','exhausted') THEN 1 ELSE 0 END) mined
                {base} GROUP BY s.id ORDER BY leads DESC, facts DESC, s.id DESC LIMIT ? OFFSET ?""",
            args + [limit, offset])
        return {"items": [dict(r) for r in rows], "total": total}

    def tool_call_list(self, company_id: int | None = None, cid: int | None = None, tool: str | None = None,
                       errors_only: bool = False, run_id: int | None = None, offset: int = 0, limit: int = 50) -> dict:
        s, a = self._scope("t", company_id, cid)
        if tool:
            s += " AND t.tool=?"
            a.append(tool)
        if errors_only:
            s += " AND t.is_error=1"
        if run_id is not None:
            s += " AND t.run_id=?"
            a.append(run_id)
        base = f"FROM tool_calls t JOIN campaigns k ON k.id=t.campaign_id WHERE 1=1{s}"
        total = int(self._q(f"SELECT COUNT(*) {base}", a)[0][0])
        rows = self._q(f"SELECT t.id, t.campaign_id, k.name campaign_name, t.run_id, t.intent_id, t.role, t.tool,"
                       f" substr(t.input,1,300) input, t.is_error, t.duration_ms, length(t.output) output_len, t.ts"
                       f" {base} ORDER BY t.id DESC LIMIT ? OFFSET ?", a + [limit, offset])
        tools = [r[0] for r in self._q("SELECT DISTINCT tool FROM tool_calls ORDER BY 1")]
        return {"items": [dict(r) for r in rows], "total": total, "tools": tools}

    def tool_call(self, tid: int) -> dict | None:
        rows = self._q("SELECT t.*, k.name campaign_name FROM tool_calls t JOIN campaigns k ON k.id=t.campaign_id"
                       " WHERE t.id=?", (tid,))
        if not rows:
            return None
        d = dict(rows[0])
        d["input"] = json.loads(d["input"])
        return d

    def llm_call_list(self, company_id: int | None = None, cid: int | None = None, role: str | None = None,
                      model: str | None = None, offset: int = 0, limit: int = 50) -> dict:
        s, a = self._scope("u", company_id, cid)
        if role:
            s += " AND u.role=?"
            a.append(role)
        if model:
            s += " AND u.model=?"
            a.append(model)
        base = f"FROM llm_usage u JOIN campaigns k ON k.id=u.campaign_id WHERE 1=1{s}"
        total = int(self._q(f"SELECT COUNT(*) {base}", a)[0][0])
        rows = self._q(f"SELECT u.*, k.name campaign_name {base} ORDER BY u.id DESC LIMIT ? OFFSET ?", a + [limit, offset])
        sums = self._q(f"SELECT COALESCE(SUM(u.input_tokens),0) i, COALESCE(SUM(u.output_tokens),0) o,"
                       f" COALESCE(SUM(u.cache_read),0) cr, COALESCE(SUM(u.cache_write),0) cw {base}", a)[0]
        models = [r[0] for r in self._q("SELECT DISTINCT model FROM llm_usage ORDER BY 1")]
        by_model = [dict(r) for r in self._q(
            f"SELECT u.model, COUNT(*) calls, SUM(u.input_tokens) i, SUM(u.output_tokens) o, SUM(u.cache_read) cr"
            f" {base} GROUP BY u.model ORDER BY calls DESC", a)]
        return {"items": [dict(r) for r in rows], "total": total, "totals": dict(sums), "models": models,
                "by_model": by_model}

    def llm_call(self, uid: int) -> dict | None:
        rows = self._q("SELECT u.*, k.name campaign_name FROM llm_usage u JOIN campaigns k ON k.id=u.campaign_id"
                       " WHERE u.id=?", (uid,))
        if not rows:
            return None
        d = dict(rows[0])
        d["message"] = self.message(d["message_id"]) if d.get("message_id") else None
        d["run"] = self.run(d["run_id"]) if d.get("run_id") else None
        return d

    def logs(self, company_id: int | None = None, cid: int | None = None, role: str | None = None,
             kind: str | None = None, q: str | None = None, offset: int = 0, limit: int = 100) -> dict:
        s, a = self._scope("x", company_id, cid)
        if role:
            s += " AND x.role=?"
            a.append(role)
        if kind:
            s += " AND x.kind=?"
            a.append(kind)
        if q:
            s += " AND x.summary LIKE ?"
            a.append(f"%{q}%")
        base = f"FROM activity x JOIN campaigns k ON k.id=x.campaign_id WHERE 1=1{s}"
        total = int(self._q(f"SELECT COUNT(*) {base}", a)[0][0])
        rows = self._q(f"SELECT x.id, x.campaign_id, k.name campaign_name, x.intent_id, x.role, x.kind, x.summary, x.ts,"
                       f" x.detail IS NOT NULL has_detail {base} ORDER BY x.id DESC LIMIT ? OFFSET ?", a + [limit, offset])
        return {"items": [dict(r) for r in rows], "total": total}
