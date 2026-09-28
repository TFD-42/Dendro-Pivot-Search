# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-09-28

### Added

- Launcher (`launcher.py`, `run.sh`, `run.bat`) with a four-choice menu: install/check dependencies, select language, new query, quit.
- Dependency setup: Ollama install per platform (Linux script, Termux `pkg`, Homebrew, download page on Windows) and local `ollama serve` start.
- Model selection without an imposed default: installed models are listed and picked (a single one is selected automatically); a catalog of verified tags (`qwen2.5` 1.5b/3b/7b/14b, `llama3.2:3b`) is offered only when Ollama has no model; downloads go through `/api/pull` with progress.
- Non-interactive launcher commands: `--check`, `--install [--yes]`, `--set-lang`, `--model`, `-q`.
- `--lang fr|en|es|it|zh|ru`: search templates, LLM expansion language, interface and result translation; built-in English interface without Ollama.
- `--tui`, `--text`, `--no-browser`, `--version`.
- Automatic fallback to a free port when the web port is busy.
- README screenshot of the live HTML tree (`docs/dendropivot-live-tree.png`, metadata-free).
- 63 new offline tests (modes, languages, web hardening, launcher, model selection).

### Changed

- **Default output is HTML**: from a terminal, a live tree opens in the browser; without a terminal, a self-contained HTML snapshot is written and its path printed. The terminal interface moves behind `--tui`.
- `--web-only` kept as a hidden alias of the default web mode.
- HTML pages titled "DendroPivot", with description, `noindex`, referrer and theme metadata, and the `lang` attribute of the selected language.
- `OLLAMA_HOST` accepts `host:port` and is validated.

### Security

- Host header validation on the local web server (DNS rebinding).
- POST requires `Content-Type: application/json` and a same-origin `Origin` when present (CSRF).
- Negative `Content-Length` rejected; concurrent translation requests rejected (409).
- `Content-Security-Policy`, `X-Frame-Options: DENY`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`.
- `::1` binding fixed (IPv6 server class) and non-loopback binding refused in `WebServer` itself.
- RSS responses containing a DTD or entity declaration rejected before XML parsing.
- Single-pass HTML templating: template markers inside a query can no longer be expanded.

## [1.0.0] - 2026-09-28

### Added

- First public release of DendroPivot (`websearch.py`).
- Focus / adjacent two-column search driven by rounds.
- Bing RSS, Marginalia and Yahoo backends with rotation, fallback and cooldown.
- Interactive terminal, JSON, static HTML and local web view modes.
- Navigation history with back / forward and pivot on a result.
- Optional Ollama query expansion and web UI translation.
- Offline unit tests.
- Community health files: contributing guide, code of conduct, security policy, support guide, issue and pull request templates, CODEOWNERS, citation metadata.

### Security

- Size limits on network responses (5 MiB) and JSON POST bodies (64 KiB).
- Strict HTTP(S) URL validation for results and opened links.
- Navigation history bounded to 50 states.
- Non-local web hosts rejected by default.

[Unreleased]: https://github.com/TFD-42/dendropivot-search/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/TFD-42/dendropivot-search/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/TFD-42/dendropivot-search/releases/tag/v1.0.0
