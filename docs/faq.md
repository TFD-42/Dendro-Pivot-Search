# DendroPivot FAQ

## Does DendroPivot need an API key? {#api-key}

No. DendroPivot queries free public search indexes (Bing RSS, Marginalia, Yahoo, DuckDuckGo Lite) without any API key or account. You do not need to register anywhere to use it.

## Is Ollama required? {#ollama-required}

No. Ollama is entirely optional. Without it, DendroPivot uses built-in heuristic expansion to generate focus reformulations and adjacent topics. With Ollama, those expansions are richer and more contextual. You can run `--no-ollama` to force heuristic mode even if Ollama is installed.

## Does it work offline / without an internet connection? {#offline}

Partially. DendroPivot is **local-first**: it runs on your machine, stores nothing externally, and opens a local web server at `127.0.0.1`. However, the search backends (Bing RSS, Marginalia, Yahoo, DuckDuckGo Lite) require outbound HTTPS to their respective servers to return results. Without internet access, backends will fail and return empty results — the tool will run, but you will see no search results. A fully offline mode (importing a local document corpus) is not yet implemented.

## Does it work on Windows? {#platforms}

Yes. DendroPivot is tested on Linux, macOS, and Windows (Python 3.10–3.13). On Windows, use `python` instead of `python3` at the prompt:

```
python websearch.py -q "your query"
```

If the browser does not open automatically, add `--no-browser` and open the printed HTML path manually.

## Does it work on Termux (Android)? {#termux}

Yes. Install Python via `pkg install python`, clone the repo, and run normally. The HTML output works in Android browsers via `http://127.0.0.1:PORT`.

## Why does a backend sometimes return 0 results? {#zero-results}

Search backends (especially Yahoo and DuckDuckGo Lite) may temporarily block IPs that make too many requests in a short period. DendroPivot:

1. Queries up to 3 backends in parallel for each round.
2. Merges results using reciprocal rank fusion, so one failed backend still leaves you with results from the others.
3. Puts a failed backend in cooldown automatically — it is retried on the next round.

If all backends fail simultaneously (rare, usually a network outage or strict firewall), the tree shows empty results for that round. Try again in a few minutes or check your outbound HTTPS access.

## What data does DendroPivot send over the network?

Only the search queries themselves, sent via HTTPS to the search backend servers (Bing, Marginalia, Yahoo, DuckDuckGo). No personal information, no usage telemetry, no account credentials. Ollama requests go to `localhost` only. See [Privacy and security](privacy-and-security.md) for the full model.

## Can I use DendroPivot without Ollama for query expansion if I have a different LLM? {#other-llm}

Not directly yet. The LLM integration is coupled to the Ollama API (`/api/generate`). Any server that implements the same API endpoint should work by setting `OLLAMA_HOST`. Support for other LLM backends is not currently planned but contributions are welcome — see [Adding a backend](adding-a-backend.md).

## How do I change the interface language?

Use the `--lang` flag:

```bash
python3 websearch.py -q "votre requête" --lang fr
```

Supported: `en`, `fr`, `es`, `it`, `zh`, `ru`. The language affects search templates, Ollama expansion prompts, and the interface labels. Result translation (translating result snippets into your language) requires Ollama.

## Can I run it on a remote server and access it from my browser?

Yes, via SSH port forwarding:

```bash
ssh -L 5678:127.0.0.1:5678 user@your-server
# on the server:
python3 websearch.py -q "..." --no-browser --web 5678
```

Then open `http://127.0.0.1:5678` locally. The server binds to loopback only — it is not accessible from the internet directly. See [Remote access over SSH](remote-ssh.md).

## How do I get the output as JSON for use in a script?

```bash
python3 websearch.py -q "your query" --json --rounds 1 --no-ollama
```

Output goes to stdout as newline-delimited JSON. See [JSON output & pipelines](json-and-pipelines.md) for the schema and examples.

## Is DendroPivot production-ready?

DendroPivot is actively developed and used by its maintainer. It has a CI matrix (Python 3.10–3.13 × Linux/macOS/Windows), 95+ automated tests, no runtime dependencies, and a defined security model. It is not yet battle-tested at scale by many independent users. If you find an issue, please [open a bug report](https://github.com/TFD-42/dendropivot-search/issues/new/choose).

---

Back to [documentation index](README.md) · [Getting started](getting-started.md)
