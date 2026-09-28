# DendroPivot Documentation

> Back to [main README](../README.md)

## Guides

| Page | What you'll find |
|------|-----------------|
| [Getting started](getting-started.md) | Install, first run, expected output, troubleshooting |
| [Live HTML tree](live-html-tree.md) | Launch the web view, navigate, pivot, keyboard shortcuts |
| [Terminal interface](terminal-interface.md) | `--tui` mode, keyboard shortcuts, performance |
| [JSON output & pipelines](json-and-pipelines.md) | `--json` mode, schema, shell/Python examples |
| [Ollama integration](ollama.md) | Optional setup, model selection, fallback without LLM |
| [Remote access over SSH](remote-ssh.md) | Port forwarding, security considerations |
| [Multilingual search](multilingual-search.md) | `--lang`, supported languages, translation notes |

## Reference

| Page | What you'll find |
|------|-----------------|
| [CLI reference](cli-reference.md) | All flags and environment variables |
| [Search backends](search-backends.md) | Bing RSS, Marginalia, Yahoo, DuckDuckGo Lite — how each works, what to expect |
| [Privacy and security](privacy-and-security.md) | What goes over the network, loopback server, DNS-rebinding protection |

## Development

| Page | What you'll find |
|------|-----------------|
| [Architecture](architecture.md) | Seed → expansion → backends → lexical field pipeline |
| [Adding a backend](adding-a-backend.md) | How to write and register a new search source |
| [Testing](testing.md) | Running the test suite, fixture-based regression tests |

## FAQ

- [Does DendroPivot work without internet access?](faq.md#offline)
- [Do I need an API key?](faq.md#api-key)
- [Do I need Ollama?](faq.md#ollama-required)
- [Does it work on Windows / Termux?](faq.md#platforms)
- [Why does it sometimes return 0 results from a backend?](faq.md#zero-results)
