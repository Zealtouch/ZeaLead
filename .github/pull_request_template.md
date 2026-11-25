## What and why

<!-- One change per PR. Link the issue if there is one. -->

## Checklist

- [ ] `python -m pytest -q` passes, with no network or API keys
- [ ] `ruff check .` is clean
- [ ] New behaviour has a test
- [ ] Untrusted text still goes through `Envelope.wrap` (agents) and `textContent` (console)
- [ ] No scraping of platforms whose terms forbid it, and nothing sends messages to people
- [ ] CHANGELOG.md updated under "Unreleased"
- [ ] Screenshot attached (if the UI changed)
