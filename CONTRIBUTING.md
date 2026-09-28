# Contributing to DendroPivot

Thank you for considering a contribution. This document describes how to propose changes so they can be reviewed and merged quickly.

## Ground rules

- Be respectful: all participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
- Security problems go through [SECURITY.md](SECURITY.md), never through public issues.
- **Standard library only.** DendroPivot has no third-party runtime dependency. A pull request that adds one must justify why the standard library cannot do the job.
- Keep the single-file layout (`websearch.py`) unless a refactor is discussed in an issue first.

## Development setup

```bash
git clone https://github.com/TFD-42/dendropivot-search.git
cd dendropivot-search
python3 --version          # 3.10 or newer
python3 -m py_compile websearch.py
python3 -m unittest discover -s tests -v
```

No virtual environment is required. If you use one, keep it out of the repository (`.venv/` is ignored).

## Workflow

1. Open or pick an issue and describe the intended change.
2. Fork the repository and create a branch from `main`:
   `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>` or `chore/<short-name>`.
3. Make focused commits using [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):
   `feat: add Mojeek backend`, `fix(web): reject oversized POST bodies`.
4. Add or update tests. Tests must run **offline**: mock `http_get` or pass fake backends to `BackendPool`.
5. Update `README.md`, `README.fr.md` and the `Unreleased` section of `CHANGELOG.md` for user-facing changes.
6. Open a pull request and complete the checklist in the template.

## Coding standards

- Python 3.10+ syntax, type hints on public functions.
- Real error handling: catch specific exceptions, log them, never `except: pass`.
- Network access goes through `http_get` / `_read_limited` so size limits and timeouts stay enforced.
- Validate every URL with `safe_http_url` before storing, rendering or opening it.
- Escape all untrusted text rendered in HTML.
- No hard-coded secrets, personal paths, hostnames or IP addresses.
- Cross-platform behavior must keep working on Linux, macOS, Windows and Termux (Android).

## Adding a search backend

A backend is a function `(query: str, limit: int) -> list[Result]` that:

- builds its URL with `urllib.parse.urlencode`;
- fetches through `http_get`;
- raises `BackendError` on network failure, blocking or unknown markup;
- returns an empty list when the index simply has no answer;
- passes every URL through `safe_http_url`.

Register it in `BACKENDS` and add offline parsing tests with a saved HTML/RSS fixture.

## Release process (maintainers)

1. Move `Unreleased` entries in `CHANGELOG.md` under the new version and date.
2. Commit: `chore(release): vX.Y.Z`.
3. Tag: `git tag -a vX.Y.Z -m "DendroPivot vX.Y.Z"` and push the tag.
4. Publish a GitHub release from the tag with the changelog section as notes.

Versioning follows [Semantic Versioning](https://semver.org/).
