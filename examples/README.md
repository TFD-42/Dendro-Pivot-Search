# DendroPivot — Examples

Ready-to-run examples. Each command works with no setup beyond `git clone` and Python 3.10+.

## 1. Simple search — no Ollama, no API key

```bash
python3 websearch.py -q "quantum computing basics" --rounds 1 --no-ollama --text
```

Opens a plain-text tree in the terminal. Good for quick exploration or scripts.

## 2. Live HTML knowledge tree (default)

```bash
python3 websearch.py -q "climate change solutions" --rounds 2
```

Opens `http://127.0.0.1:PORT` — navigate, pivot any result with `f`, go back with `b`.

## 3. JSON output for scripting

```bash
python3 websearch.py -q "machine learning python" --rounds 1 --json --no-ollama \
  | python3 -c "import sys,json; [print(r['title'], r['url']) for r in json.loads(sys.stdin.read()).get('results',[])]"
```

Pipes result list to stdout; add `--json` to any invocation to get structured output.

## 4. French-language search

```bash
python3 websearch.py -q "intelligence artificielle éthique" --lang fr --rounds 1 --no-ollama
```

Search templates, interface, and Ollama prompts all adapt to the selected language.

## 5. Privacy-focused search — loopback only, no Ollama, verbose debug

```bash
python3 websearch.py -q "tor network privacy" --rounds 1 --no-ollama --debug --no-browser --text
```

`--debug` shows backend latency, cooldown events, and result counts per backend.

## 6. Multi-round deep dive

```bash
python3 websearch.py -q "CRISPR gene editing" --rounds 3 --no-ollama
```

3 rounds of branching: the lexical field grows across rounds, steering queries toward the domain's core vocabulary.

## 7. Static HTML snapshot (for sharing or archiving)

```bash
python3 websearch.py -q "renewable energy storage" --rounds 2 --no-ollama --html-out report.html
```

Writes a self-contained HTML file; no server, no live connection needed to view it.

## 8. Remote server usage (SSH port forward)

On the server:
```bash
python3 websearch.py -q "distributed systems" --rounds 1 --no-browser --web 5678
```

On your local machine:
```bash
ssh -L 5678:127.0.0.1:5678 user@your-server
# then open http://127.0.0.1:5678 in your browser
```

## 9. With Ollama (richer query expansion)

Requires [Ollama](https://ollama.com) running locally with at least one model installed.

```bash
# Check Ollama is running
curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; print([m['name'] for m in json.load(sys.stdin)['models']])"

python3 websearch.py -q "graph neural networks" --rounds 2
```

Ollama expands queries contextually; without it the tool falls back to heuristic expansion automatically.
