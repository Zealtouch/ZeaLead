# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private reporting
instead: **Security → Report a vulnerability** on this repository. Include the steps to
reproduce it and the version (`zealead --version` or `pip show zealead`).

You should get an acknowledgement within 7 days. Once a fix is released, we will credit you
unless you prefer to stay anonymous.

## Scope

These are the issues we most want to hear about:

- **Prompt injection through collected content.** For example, a post or page that makes an
  agent call tools it shouldn't, escape the nonce-tagged frame, or record a lead without a
  verbatim quote.
- **Console problems:** bypassing sign-in or the admin role, forging or replaying session
  tokens, re-running first-run setup once an admin exists, XSS (the console must never render
  untrusted text as HTML), CSV formula injection, or CSRF.
- **Secrets leaking.** API keys should never show up in the console, logs or reports, or in the
  database unencrypted, and a saved key must never be sent to a host other than the one it was
  entered for.
- **Connectors sending data somewhere other than the platform they serve.**

## Running it safely

- The console is reachable only from this machine by default (`127.0.0.1`, also for the Docker
  port). If you expose it, put it behind TLS and a reverse proxy.
- Create the admin account right after the first start: until then, anyone who can reach the
  console can claim it. Setup is refused once any account exists.
- Accounts: passwords are scrypt-hashed (minimum 10 characters). Sessions are HS256-signed
  tokens that expire after 7 days and stop working when the password changes. Failed sign-ins
  are limited to 10 per 5 minutes per address. The signing key is `keys/jwt.key` (mode 0600;
  the `zealead-keys` volume under Docker, `ZEALEAD_KEYS_DIR` otherwise). Deleting it signs
  everyone out.
- Forgot a password: `./reset-password.sh <username>` (or `zealead user reset-password`).
- The Content Security Policy allows inline scripts and styles because the statically exported
  console needs them. Everything else is limited to the same origin, and collected text is only
  ever rendered as text or sanitized Markdown, never as HTML.
- API keys: the environment key lives in `.env`, which the console can't read or change. Keys
  entered for model profiles (System → LLM, admins only) are write-only: stored AES-256-GCM
  encrypted under `keys/llm.key` (mode 0600, next to `jwt.key`), returned only as a masked hint,
  and kept bound to their endpoint: changing a profile's base URL or format requires entering the
  key again. Proxy passwords are masked in the API. Back up the keys directory with the database;
  without `llm.key`, saved keys can't be decrypted and must be entered again.
- "Test connection" and "load models" make outbound requests to the URL an admin enters. Only
  admins can call them.
- The lead database holds personal data: public handles, profile links and quotes. Protect
  it, and delete campaigns once you no longer need them.
