# Getting started with DendroPivot

> **Prerequisites:** Python 3.10 or later. No other runtime dependencies.

DendroPivot is a single Python file (`websearch.py`) with no third-party dependencies. You can run it anywhere Python 3.10+ is installed.

## Install

```bash
git clone https://github.com/TFD-42/dendropivot-search.git
cd dendropivot-search
```

That's it. There is no `pip install` step — the tool uses only the Python standard library.

**Alternative: download a release archive**

Prebuilt archives (`dendropivot-v1.1.0-linux.zip`, `-macos.zip`, `-windows.zip`) are available on the [Releases page](https://github.com/TFD-42/dendropivot-search/releases). Each includes `websearch.py`, a launcher, and a setup script that checks your Python version.

## First run

```bash
python3 websearch.py -q "local LLM inference" --rounds 1
```

What you'll see:

- A browser window opens at `http://127.0.0.1:PORT` showing the live HTML knowledge tree.
- If no browser is available (remote server, CI), a self-contained HTML snapshot is written to disk and its path printed.
- The terminal shows the seed query, the focus reformulations, and adjacent topics it generated.

To use the terminal interface instead:

```bash
python3 websearch.py -q "local LLM inference" --rounds 1 --tui
```

## Expected output

After one round (`--rounds 1`) on a typical connection:

```
[seed]  local LLM inference
  [focus]  local LLM inference definition
  [focus]  local LLM inference practical guide
  [focus]  local LLM inference vs cloud
  [focus]  local LLM inference recent developments
  [focus]  local LLM inference technical architecture
  [adjacent]  Ollama setup
  [adjacent]  llama.cpp
  ...
DendroPivot  →  http://127.0.0.1:5678
```

The tree is navigable in the browser: click any card to open its results, press `f` (or Shift+click) on any result to pivot it into a new root.

## Without Ollama

Ollama is **optional**. Without it, DendroPivot generates focus and adjacent queries using built-in heuristic expansion — it works immediately without any LLM setup. The `--no-ollama` flag forces this mode explicitly:

```bash
python3 websearch.py -q "quantum computing" --no-ollama --rounds 2
```

## With Ollama

If [Ollama](https://ollama.com) is running locally, DendroPivot detects it automatically and uses it for richer query expansion. No configuration needed beyond having Ollama running with at least one model installed. See [Ollama integration](ollama.md) for model selection and details.

## Troubleshooting

**Port already in use**  
DendroPivot automatically finds a free port if the default is busy. If you always want a specific port: `--web 8080`.

**0 results from a backend**  
Some backends (Yahoo, DDG Lite) may temporarily block an IP. DendroPivot queries multiple backends in parallel and merges results — one failing backend does not stop the search. See [Search backends](search-backends.md).

**Python 3.9 or earlier**  
DendroPivot requires Python 3.10+. Check your version: `python3 --version`. On macOS, `brew install python@3.12` installs a current version. On Windows, download from [python.org](https://www.python.org/downloads/).

**Windows: browser doesn't open**  
Run `python websearch.py -q "..." --no-browser` — the HTML file path is printed to the terminal. Open it manually.

---

Next: [Live HTML tree](live-html-tree.md) · [CLI reference](cli-reference.md) · [FAQ](faq.md)
