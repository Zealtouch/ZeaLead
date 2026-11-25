# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private reporting
instead: **Security → Report a vulnerability** on this repository. Include the steps to
reproduce it and the version (`leadscout --version` or `pip show leadscout`).

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
- **Secrets leaking.** API keys should never show up in the console, the database, logs or
  reports.
- **Connectors sending data somewhere other than the platform they serve.**

## Running it safely

- The console is reachable only from this machine by default (`127.0.0.1`, also for the Docker
  port). If you expose it, put it behind TLS and a reverse proxy.
- Create the admin account right after the first start: until then, anyone who can reach the
  console can claim it. Setup is refused once any account exists.
- Accounts: passwords are scrypt-hashed (minimum 10 characters). Sessions are HS256-signed
  tokens that expire after 7 days and stop working when the password changes. Failed sign-ins
  are limited to 10 per 5 minutes per address. The signing key is `keys/jwt.key` (mode 0600;
  the `leadscout-keys` volume under Docker, `LEADSCOUT_KEYS_DIR` otherwise). Deleting it signs
  everyone out.
- Forgot a password: `./reset-password.sh <username>` (or `leadscout user reset-password`).
- The Content Security Policy allows inline scripts and styles because the statically exported
  console needs them. Everything else is limited to the same origin, and collected text is only
  ever rendered as text or sanitized Markdown, never as HTML.
- API keys belong in `.env` only. The console can't read or change them.
- The lead database holds personal data: public handles, profile links and quotes. Protect
  it, and delete campaigns once you no longer need them.
