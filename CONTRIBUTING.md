# Contributing to ZeaLead

Thanks for helping. Bug reports, new connectors and prompt improvements are all welcome.

## Set up

```bash
git clone https://github.com/Zealtouch/ZeaLead && cd ZeaLead
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

Work on the console (Next.js, in `web/`) with hot reload, against the API on :8790:

```bash
ZEALEAD_DB=demo.db .venv/bin/zealead demo     # fictional sample data, no API keys
ZEALEAD_DB=demo.db .venv/bin/zealead serve &
cd web && npm ci && npm run dev                     # http://localhost:3000
npm run typecheck && npm run build:static           # what CI runs
```

`npm run dev` proxies `/api` to `ZEALEAD_API` (default `http://localhost:8790`). For a
production-like check, copy `web/out` to `zealead/webui` and open the API port instead, or
run `./start.sh`.

## Ground rules

- **Tests need no network and no API spend.** Use `ScriptedLLM` and the fake connectors in
  `tests/test_engine.py`. A pull request that needs a real key to pass its tests will not be merged.
- **Keep the gates intact.** `report_lead` checks that the quote is verbatim in a captured post, that
  the post is recent, and that the person is not a duplicate. `prove_goal` refuses early proof.
  Changes that weaken these need a clear reason in the pull request.
- **Everything from the web is untrusted.** Any text a connector returns must reach the model
  through `Envelope.wrap`. In the console, render it as React text or through the `Markdown`
  component, never `dangerouslySetInnerHTML`, and turn URLs into links only through `ExtLink` /
  `safeHref` (http and https only).
- **Official APIs and search engines only.** Connectors must not scrape platforms whose terms
  forbid it (LinkedIn, X, Facebook, Instagram, Threads), get past logins or CAPTCHAs, or send
  messages to people. ZeaLead finds people; it never contacts them.
- **Follow the console's patterns.** It is adapted from the ZeaLead web console: shadcn/ui
  components, Tailwind, `usePoll` for data, `api.*` in `src/lib/api.ts` for every request, and
  the shared pieces in `src/components/ls/`. Pages use `?id=` query parameters because the
  console is a static export.

## Adding a connector

See [docs/connectors.md](docs/connectors.md). In short: subclass `Connector`, return `Item`s
through `record_items`, add an `enabled()` check for the keys it needs, register it in
`connectors/__init__.py`, document the keys in `.env.example`, and add a test with a fake HTTP
response.

## Pull requests

- Keep each pull request to one change, and include a test when behaviour changes.
- Run `pytest` and `ruff check .` before pushing, and `npm run typecheck` if you touched `web/`.
  CI runs the Python tests on 3.10 to 3.13, builds the console, and builds the Docker image.
- If you change the UI, attach a screenshot.
- Add a line under "Unreleased" in [CHANGELOG.md](CHANGELOG.md).

By contributing, you agree that your contribution is licensed under AGPL-3.0-or-later, the
project's license.

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
