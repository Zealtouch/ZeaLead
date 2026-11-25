# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Personal messages: a message writer drafts a public reply and a direct message for every lead
  from that person's own post, using the brief's new `outreach` section (sender, tone, offer).
  Drafts are refused if they don't name the product, link anywhere but the product URL, or nearly
  copy another lead's message. Edit or rewrite them in the lead view, draft missing ones per task,
  or use `zealead draft`. Auto-drafting, the writer model and effort are on the LLM page.

### Fixed
- Missing Anthropic credentials now stop a run with a clear message instead of an internal error.
- The brief editor showed an empty recency when the value wasn't one of the presets.

## [0.3.0] - 2026-11-25

### Added
- New web console adapted from the ARTEX console (Next.js, shadcn/ui), with its themes, sidebar
  and layout controls:
  - Dashboard: leads per day, leads by platform, newest leads, top communities, token spend.
  - Tasks with a detail view: Sessions (a live monitor of every agent session's transcript, with
    a hint box), Overview, Exploration graph, Intents, Leads, Communities, Tool calls, Brief.
  - Leads, Communities, Companies, Tool Execution and LLM Recording pages across all tasks.
  - System pages: LLM, Agent, Platforms, Users, Logs and System Settings.
- Companies: group tasks and leads; a sidebar switcher narrows every page to one company.
- User accounts with admin and member roles, replacing the shared access token. First-run setup
  creates the admin; `zealead user list|add|reset-password` and `./reset-password.sh` manage
  accounts from the command line.
- Every agent session is recorded: its messages, each tool call (input, output, timing) and each
  model call (tokens, stop reason, latency).
- `./start.sh` and a multi-stage Docker image that builds the console and serves it with the API
  on one port.

### Changed
- Campaigns are called tasks in the console. The API paths are unchanged.
- Docker keeps the database and the signing key in named volumes (`zealead-data`,
  `zealead-keys`) and publishes the port on `127.0.0.1` by default.
- The CSP allows inline scripts and styles, which the statically exported console needs.

### Removed
- The access token (`zealead.token`, `ZEALEAD_UI_TOKEN`) and the previous vanilla-JS console.

## [0.2.0] - 2026-11-25

### Added
- Web console (`zealead serve`), protected by an access token and bound to 127.0.0.1 by default.
  - Campaign list, a new-campaign form, and controls to start, pause and delete campaigns.
  - Overview with goals, usage and platform yield.
  - Live activity feed and an intents list.
  - Lead inbox with filters, a status for each lead, copy-reply, and CSV export.
  - Interactive exploration graph with a node inspector.
  - Communities and their coverage.
  - Brief editor and settings page.
  - Light and dark themes, and a mobile layout.
- `zealead demo` seeds a fictional campaign so the console can be tried without API keys.
- Campaigns are claimed by a single runner, with a heartbeat, so the CLI and the console never
  run the same campaign at once.
- Docker image and a compose file.

### Changed
- Reddit now requires OAuth credentials. Reddit blocks unauthenticated clients.

## [0.1.0] - 2026-11-24

### Added
- First release: goal decomposer, event-driven planner and single-intent workers.
- Source graph and exploration graph.
- Gates: verbatim quotes, recency, dedup and early-proof refusal.
- Connectors: Reddit, Hacker News, X, Bluesky, Stack Exchange, GitHub issues, and web search
  (Brave or Tavily).
- CLI, CSV export and a static HTML report.
