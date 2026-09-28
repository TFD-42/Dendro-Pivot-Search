## Summary

<!-- What does this change do and why? Link the issue: Closes #123 -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (CLI flag, JSON schema or HTTP API change)
- [ ] Documentation
- [ ] Refactoring / maintenance

## Checklist

- [ ] `python3 -m py_compile websearch.py` passes
- [ ] `python3 -m unittest discover -s tests -v` passes offline
- [ ] New behavior is covered by tests that do not hit the network
- [ ] No new third-party dependency (standard library only)
- [ ] No secrets, tokens, personal paths, IPs or hostnames added
- [ ] Web server changes keep loopback-only binding and input limits
- [ ] `README.md`, `README.fr.md` and `CHANGELOG.md` updated when user-facing
- [ ] Tested on: <!-- Linux / macOS / Windows / Termux -->

## Notes for reviewers

<!-- Risks, trade-offs, screenshots of the web view if relevant -->
