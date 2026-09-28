# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 1.x | Yes |
| < 1.0 | No |

## Reporting a vulnerability

**Do not open a public issue, discussion or pull request for a security problem.**

Report it privately through GitHub: [**Report a vulnerability**](https://github.com/TFD-42/dendropivot-search/security/advisories/new) (Security tab → Advisories → Report a vulnerability).

Include:

- affected version or commit SHA;
- execution mode (TUI, `--json`, `--html-out`, `--web`, `--web-only`);
- web server configuration (`--web-host`, port, proxy or tunnel in front);
- operating system and Python version;
- minimal reproduction steps or proof of concept;
- observed impact.

### Response targets

| Step | Target |
|---|---|
| Acknowledgement | 72 hours |
| Initial assessment | 7 days |
| Fix or mitigation for confirmed high-severity issues | 30 days |

Reporters are credited in the advisory and the changelog unless they ask otherwise. Please allow a coordinated disclosure window before publishing details.

## Threat model

DendroPivot (`websearch.py`) is a **local, single-user** tool.

- The built-in HTTP server binds to loopback only (`127.0.0.1`, `localhost`, `::1`) and has **no authentication**. Non-local `--web-host` values are rejected by design.
- Anyone able to reach the port can drive the session. Use an SSH tunnel for remote access.
- A public reverse proxy in front of the server must add authentication, access control, HTTPS and CSRF protection.
- Search results come from third-party pages and are treated as untrusted: URLs are restricted to HTTP(S) and all text is HTML-escaped.
- Network responses are capped (5 MiB), as are POST bodies (64 KiB), seeds (200 characters) and history (50 states).

## Out of scope

- Availability or content of third-party search engines.
- Behavior of the user's local Ollama instance or models.
- Deployments that deliberately bypass the loopback restriction.
