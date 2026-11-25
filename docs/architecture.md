# Architecture

ZeaLead is an event-driven multi-agent loop over two linked graphs. The design is adapted
from [ARTEX](https://github.com/BaaRai/ARTEX). ARTEX explores a target for vulnerabilities;
ZeaLead explores public conversations for people who need your product.

```
 brief ──▶ goal decomposer ──▶ goals + constraints
                                   │
          ┌────────────────────────▼────────────────────────┐
          │ planner: wakes on graph change (0.8s debounce),  │
          │ heartbeat, hard floor; adds ≤4 intents per round │
          │ or calls prove_goal when a goal is truly met     │
          └────────────────────────┬────────────────────────┘
                                   │ open intents (frontier)
        ┌──────────────┬───────────┴──────────┬──────────────┐
        ▼              ▼                      ▼              ▼
     worker 1       worker 2               worker N   claim ONE intent, call
                                                      platform tools, write back
        └──────────────┴───────────┬──────────┴──────────────┘
                                   ▼
  source graph  ◀──── anchors ────▶  exploration graph
  platform → community → thread       goal → intent → fact / lead
  + authors (shared by campaigns)     (one per campaign)
                                   │
                                   └── every write wakes the planner
```

## Modules

| Module | Role |
|---|---|
| `config.py` | Settings from the environment and `.env`; brief validation; the whitelist of settings the console may change |
| `store.py` | SQLite (WAL mode): companies, users, campaigns, nodes, edges, sources, anchors, captures, leads, evidence, todos, activity, runs and their messages, tool calls, usage, settings |
| `agents.py` | Decomposer, planner and worker prompts; `render_situation` builds the planner's view of the graph |
| `tools.py` | Planner tools (`add_intent`, `prove_goal`, `todo_write`, …) and worker tools (`report_lead`, `record_fact`, …), with their gates |
| `llm.py` | Manual tool loop: parallel tool calls, refusal and `pause_turn` handling, a wrap-up turn, the token budget; each model call goes through the role's profile chain; records each agent run's transcript, tool calls and model calls |
| `providers.py` | One call to any model: Anthropic (SDK), OpenAI Chat Completions, OpenAI Responses, Ollama and Bedrock gateways, converted to and from the Anthropic block shape; connect / empty / stream retries; rate limits; model list and connection test |
| `llmpool.py` | Model profiles from the database, per-role pins, the failover chain and the persisted breaker |
| `secretbox.py` | AES-GCM encryption of profile keys under `keys/llm.key` |
| `engine.py` | Runs the planner loop and worker pool for one campaign; heartbeat, stall and stagnation stops |
| `boundary.py` | Nonce envelope for untrusted text |
| `governor.py` | Per-host pacing and backoff; a shared HTTP client |
| `connectors/` | Platform tools (see [connectors.md](connectors.md)) |
| `server.py`, `auth.py` | FastAPI JSON API, user accounts and signed sessions; serves the built console from `zealead/webui` |
| `web/` (repo root) | The console: Next.js static export adapted from the ARTEX web console |
| `cli.py`, `report.py`, `demo.py` | Command line, static HTML report, sample data |

## The loop

1. **Decompose.** The brief becomes countable goals (for example, "40 leads at warm or above, 10
   hot") and constraints (excluded platforms, regions, competitors to ignore). If the model call
   fails, a rule-based fallback produces the same structure.
2. **Plan.** The planner wakes when the graph changes, waits 0.8 seconds so a burst of changes
   counts as one wake-up, and then reads a pre-built situation. The situation covers goal
   progress, open and running intents, recent results, platform yield, communities that showed
   signal but haven't been mined, operator hints, and its own todo list. It adds up to 4 intents
   per round. Duplicates of open, running or recently finished intents are refused. The prompt
   asks for depth over coverage (mine a community that produced a lead before opening new ones)
   and for a mix of routes. A heartbeat wakes it if nothing changes, and a hard floor keeps it
   from going quiet while workers sit idle.
3. **Work.** Each worker claims one open intent, calls platform tools, and writes back. It
   records facts (for example, "r/smallbusiness discusses invoicing weekly") and leads. Then
   it stops. Every write wakes the planner.
4. **Stop.** The campaign ends when every goal is proven, when it runs out of budget, or when it
   stalls. It stalls if there is no open work and the planner adds nothing, or if N rounds pass
   with no new lead. Ctrl-C or Pause marks it `paused`, and running intents go back to `open`
   so `resume` can pick them up.

## Gates (why leads can be trusted)

- **Verbatim evidence.** `report_lead` must cite a capture this campaign actually fetched, and
  its quote must appear in the captured text. Matching ignores whitespace and case, and the
  quote must be at least 15 characters. The URL and author come from the capture, never from
  the model.
- **Adversarial check.** Before reporting, the worker prompt makes it argue against the lead.
  Is the poster a vendor? The wrong customer profile? Already solved? A stale post? A bot? The
  objection is stored with the lead.
- **Recency.** Posts older than the brief's window are refused.
- **One person, one lead.** Leads are deduplicated by `platform:author`. Seeing the same person
  again adds evidence and can raise their intent level.
- **No early proof.** `prove_goal` refuses while the measured count is below target.

## Untrusted data

Every post, comment, snippet and page is written by a stranger and may contain instructions
aimed at the model. Connectors return raw text, and `connector_tools` wraps it in an envelope
tagged with a random nonce that is new for every agent run. Any copy of the marker inside the content is
neutralized, so a post can't close the frame. The system prompts tell both agents that text
inside the frame is data. In the console, untrusted text is rendered only as React text or
sanitized Markdown (never raw HTML), links are limited to `http(s)`, the CSP keeps every request
on the same origin, and CSV export neutralizes formula prefixes.

## Console and runner

`zealead serve` hosts the API and the console in a single process. Starting a campaign from
the console runs the same `Engine` in a background task. A campaign row records its runner
(`cli` or `console`) and a heartbeat. A second runner is refused while the heartbeat is less
than 45 seconds old, so the CLI and the console never run the same campaign at the same time.
Settings changed in the console are stored in the database and applied over `.env`, but only
for whitelisted, non-secret keys, and only admins may change them. API keys stay in `.env`.

### Personal messages

`outreach.py` runs a short `writer` agent per lead with one tool, `save_messages`. It sees the brief
(including `outreach.sender/tone/offer`) and the person's captured post inside the nonce frame, and
writes a public reply and a direct message. The tool refuses drafts that are too short or long,
don't name the product, contain links other than the product URL (and none in the public reply),
or are more than 80% similar to a draft already saved for another lead in the task. While a task
runs, the engine's writer loop drafts each new lead; a task that finishes on its own drafts any
lead still waiting. Drafting on request (`POST /api/leads/{id}/draft`, `zealead draft`) isn't
held to the task's token budget.

### Sessions

Each agent run (the decomposer, one planner round, one worker intent) is a row in `runs`. Its
messages go to `run_messages` (text, tool calls and summarized thinking; long tool output is
clipped), every tool call to `tool_calls` with its input, output and duration, and every model
response to `llm_usage` with tokens, stop reason and latency. The Sessions tab polls a run for
messages after the last one it has, so a running session streams into the page. When a task
starts or stops, runs left `running` by a crash are closed.

### Models

The agent loop speaks the Anthropic Messages shape: a system prompt, messages made of `text`,
`tool_use` and `tool_result` blocks, and tools with an `input_schema`. `providers.py` converts
that to each wire format (Chat Completions `tool_calls` and `tool` messages, Responses
`function_call` and `function_call_output` items, Bedrock InvokeModel bodies) and converts the
reply back, so the loop, the transcripts and the gates don't care which model answered, and the
pool can switch provider in the middle of a run. Replies are buffered until complete, which makes
replaying a broken stream safe.

For every model call, `llmpool.Router` builds the chain for the role: the pinned profile, or the
active one followed (pool on) by the other usable profiles by priority, with equal priorities
rotated and profiles in cooldown or with too small a context window left out. A call is retried on
the same profile first (connect, empty response, stream), then the chain moves on for failures
that say something about the profile (transport, 401–404, 408, 429, 5xx) but not for request
errors (400, 413, 422), which would fail everywhere. The breaker counts transient failures (trip
after 3 in a row by default) and trips at once on 401, 402, 403 or 404; its state is in the
`llm_health` table, so a restart doesn't forget it. A worker whose model call still fails is rerun
from scratch (the intent layer). Settings are read on every call, so profile edits, pins and the
retry policy apply to running tasks.

Without profiles the chain is one implicit profile: `ANTHROPIC_API_KEY` with the per-role model
names, which is how earlier versions behaved.

### Accounts

The first visit creates the admin (`POST /api/auth/setup`, refused once any account exists).
Passwords are scrypt-hashed. A session is an HS256 token with the user id, role, a 7-day expiry
and a fingerprint of the password hash, so changing a password ends old sessions. The signing
key is created on first start in the keys directory with mode 0600.

### Docker

The image has two stages: Node builds the console (`npm run build:static`), and the Python stage
installs the package with the console copied into `zealead/webui`. One process serves both on
port 8790. Compose keeps the database and the signing key in named volumes and publishes the port
on `127.0.0.1`.
