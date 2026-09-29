<div align="center">

# DendroPivot

### Datenschutzorientierter lokaler Web-Such-Explorer für Python — eine Anfrage zu einem navigierbaren Wissensbaum ausbauen

**Kein API-Schlüssel erforderlich. Optionaler lokaler Ollama-LLM. Nur Python-Standardbibliothek.**

DendroPivot verwandelt eine einzelne Suche in einen geführten Erkundungspfad. In jeder Runde verzweigt sich die Startabfrage in fünf *Fokus*-Umformulierungen und fünf *benachbarte* Themen; was Sie lesen, verstärkt den Baum, und jedes Ergebnis kann zur neuen Wurzel werden. Läuft im Terminal oder als lokale Live-Web-Seite, fragt mehrere kostenlose Suchindizes ohne API-Schlüssel ab, kann einen lokalen LLM über [Ollama](https://ollama.com) verwenden und benötigt nur die Python-Standardbibliothek.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Lizenz: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)
[![Keine API-Key](https://img.shields.io/badge/API--Schlüssel-nicht%20erforderlich-success)](#suchbackends)

[English](../README.md) · [Français](README.fr.md) · **Deutsch** · [Español](README.es.md) · [Italiano](README.it.md) · [Русский](README.ru.md) · [中文](README.zh.md) · [日本語](README.ja.md) · [Português](README.pt.md)

</div>

---

## Warum DendroPivot?

Eine einzelne Suchanfrage zeigt nur einen Blickwinkel auf ein Thema. DendroPivot behandelt Ihre Anfrage als **Samen**, fächert sie in fünf Umformulierungen und fünf benachbarte Themen auf, durchsucht mehrere kostenlose Suchindizes und nutzt das, was Sie tatsächlich öffnen, um die nächste Runde zu steuern. Das Ergebnis ist ein Erkundungsbaum statt einer flachen Liste.

## Die Pivot-Methodik

| Schritt | Was passiert | Warum es hilft |
|---|---|---|
| 1. **Samen** | Sie geben eine Startabfrage ein. | Setzt die Baumwurzel. |
| 2. **Verzweigen** | Fächert in 5 Fokus-Winkel und 5 benachbarte Themen auf. | Mehrere Perspektiven statt eines Rankings. |
| 3. **Lesen** | Öffnen eines Ergebnisses verstärkt sein Vokabular. | Ihr Interesse steuert die nächste Runde. |
| 4. **Wachsen** | Neue Runden verankern Abfragen auf gemeinsamen Begriffen. | Kernkonzepte des Fachgebiets werden sichtbar. |
| 5. **Pivot** | `f` drücken oder Umschalt+Klick: Ergebnis wird neue Wurzel. | In ein Unterthema eintauchen ohne Kontext zu verlieren. |
| 6. **Zurück** | Der Verlauf speichert jeden Baum; `b`/`n` navigieren. | Vergleichen und jederzeit zurückkehren. |

## Funktionen

- **Zwei Spalten pro Runde**: Fokus (5 Umformulierungen) + Benachbart (5 verwandte Themen)
- **Kontinuierliche Anreicherung**: gelesene Ergebnisse beeinflussen die nächste Runde
- **Multi-Backend-Suche**: Bing RSS, Marginalia, Yahoo, DDG Lite — mit Rotation, Fallback und Cooldown
- **HTML zuerst**: öffnet einen Live-Baum im Browser; außerhalb eines Terminals wird ein HTML-Snapshot erstellt
- **Sechs Sprachen**: `--lang fr|en|es|it|zh|ru`
- **Optionaler Ollama**: LLM-Abfrageerweiterung und On-Demand-Übersetzung
- **Nur Standardbibliothek**: kein `pip install`, läuft überall mit Python 3.10+

## Anforderungen

| Komponente | Anforderung |
|---|---|
| Python | **3.10 oder neuer** |
| Netzwerk | Ausgehendes HTTPS zu den Suchbackends |
| Ollama | Optional, nur für LLM-Erweiterung und Übersetzung |
| Python-Pakete | Keine |

## Installation

```bash
git clone https://github.com/TFD-42/dendropivot-search.git
cd dendropivot-search
python3 websearch.py -q "lokale KI-Modelle"
```

## Schnellstart

```bash
# Live-HTML-Baum im Browser (Standard bei Ausführung im Terminal)
python3 websearch.py -q "maschinelles Lernen"

# Einzelne Runde als JSON
python3 websearch.py -q "maschinelles Lernen" --rounds 1 --no-ollama --json

# Zwei-Spalten-Terminal-Oberfläche
python3 websearch.py -q "maschinelles Lernen" --tui
```

## Ausgabemodi

| Kontext | Standardausgabe | Überschreiben |
|---|---|---|
| Aus dem Terminal | Live-HTML-Baum auf `http://127.0.0.1:8765/` | `--tui`, `--json`, `--text` |
| Pipe/Skript (kein TTY) | HTML-Snapshot im aktuellen Verzeichnis | `--html-out PFAD`, `--json` |

## Befehlszeilenoptionen

| Option | Standard | Beschreibung |
|---|---|---|
| `-q`, `--query TEXT` | Eingabeaufforderung | Startabfrage |
| `-n`, `--limit N` | `6` | Max. Ergebnisse pro Abfrage |
| `--interval SEKUNDEN` | `60` | Verzögerung zwischen Runden |
| `--rounds N` | `0` | Anzahl der Runden (0 = unbegrenzt) |
| `--lang CODE` | auto | `fr`, `en`, `es`, `it`, `zh`, `ru` |
| `--no-ollama` | aus | Nur heuristische Erweiterung |
| `--tui` | aus | Terminal-Oberfläche |
| `--json` | aus | JSON auf stdout |
| `--text` | aus | Klartext auf stdout |
| `--html-out PFAD` | auto | Snapshot-Pfad |

## Suchbackends

| Backend | Endpunkt | Hinweise |
|---|---|---|
| `bing-rss` | `bing.com/search?format=rss` | Strukturiertes RSS |
| `marginalia` | `old-search.marginalia.nu` | Unabhängiger Index |
| `yahoo` | `search.yahoo.com` | HTML-Parsing |
| `ddg-lite` | `lite.duckduckgo.com/lite/` | POST-basiert |

## Sicherheitsmodell

- Nur Loopback (127.0.0.1); Nicht-lokale Hosts werden abgelehnt
- `Host`-Header-Prüfung (DNS-Rebinding-Schutz)
- `POST` erfordert `Content-Type: application/json` und gleichen Ursprung (CSRF-Schutz)
- Strikte CSP, keine Shell-Aufrufe aus Benutzereingaben

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Lizenz

Veröffentlicht unter der [MIT-Lizenz](../LICENSE).

---

<div align="center">

Gepflegt von [@TFD-42](https://github.com/TFD-42) · [Fehler melden](https://github.com/TFD-42/dendropivot-search/issues/new?template=bug_report.yml)

</div>
