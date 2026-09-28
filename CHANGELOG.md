# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/TFD-42/dendropivot-search/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/TFD-42/dendropivot-search/releases/tag/v1.0.0
