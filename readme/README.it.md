<div align="center">

# DendroPivot

### Esploratore web locale per Python orientato alla privacy — trasforma una query in un albero di conoscenza navigabile

**Nessuna chiave API richiesta. LLM Ollama locale opzionale. Solo libreria standard di Python.**

DendroPivot trasforma una singola ricerca in un percorso di esplorazione guidato. In ogni round, la query seme si ramifica in cinque riformulazioni di *focus* e cinque argomenti *adiacenti*; ciò che leggi rafforza l'albero, e qualsiasi risultato può diventare la nuova radice. Funziona nel terminale o come pagina web locale live, interroga diversi indici di ricerca gratuiti senza chiave API, può usare un LLM locale tramite [Ollama](https://ollama.com) e richiede solo la libreria standard di Python.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Licenza: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)
[![Senza chiave API](https://img.shields.io/badge/chiave%20API-non%20richiesta-success)](#backend-di-ricerca)

[English](../README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · **Italiano** · [Русский](README.ru.md) · [中文](README.zh.md) · [日本語](README.ja.md) · [Português](README.pt.md)

</div>

---

## Perché DendroPivot?

Una singola query di ricerca mostra solo un angolo di un argomento. DendroPivot tratta la tua query come un **seme**, la espande in cinque riformulazioni e cinque argomenti adiacenti, le esegue contro diversi indici di ricerca gratuiti e usa ciò che apri realmente per guidare il round successivo. Il risultato è un albero di esplorazione invece di una lista piatta.

## La metodologia pivot

| Passo | Cosa accade | Perché aiuta |
|---|---|---|
| 1. **Seme** | Inserisci una query iniziale. | Stabilisce la radice dell'albero. |
| 2. **Ramificazione** | Si espande in 5 angoli di focus e 5 argomenti adiacenti. | Più prospettive invece di un ranking. |
| 3. **Lettura** | Aprire un risultato ne rafforza il vocabolario. | Il tuo interesse guida il round successivo. |
| 4. **Crescita** | Nuovi round ancorano le query su termini condivisi. | I concetti chiave del dominio diventano visibili. |
| 5. **Pivot** | `f` o Shift+clic: il risultato diventa la nuova radice. | Approfondire un sotto-argomento senza perdere il contesto. |
| 6. **Indietro** | La cronologia salva ogni albero; `b`/`n` per navigare. | Confrontare rami e tornare in qualsiasi momento. |

## Funzionalità

- **Due colonne per round**: Focus (5 riformulazioni) + Adiacente (5 argomenti correlati)
- **Arricchimento continuo**: i risultati letti influenzano il round successivo
- **Ricerca multi-backend**: Bing RSS, Marginalia, Yahoo, DDG Lite — con rotazione, fallback e cooldown
- **HTML prima**: apre un albero live nel browser; fuori dal terminale crea uno snapshot HTML
- **Sei lingue**: `--lang fr|en|es|it|zh|ru`
- **Ollama opzionale**: espansione query LLM e traduzione su richiesta
- **Solo libreria standard**: nessun `pip install`, funziona ovunque con Python 3.10+

## Requisiti

| Componente | Requisito |
|---|---|
| Python | **3.10 o superiore** |
| Rete | HTTPS in uscita verso i backend di ricerca |
| Ollama | Opzionale, solo per espansione LLM e traduzione |
| Pacchetti Python | Nessuno |

## Installazione

```bash
git clone https://github.com/TFD-42/dendropivot-search.git
cd dendropivot-search
python3 websearch.py -q "modelli linguistici locali"
```

## Avvio rapido

```bash
# Albero HTML live nel browser (predefinito nel terminale)
python3 websearch.py -q "apprendimento automatico"

# Un round come JSON
python3 websearch.py -q "apprendimento automatico" --rounds 1 --no-ollama --json

# Interfaccia terminale a due colonne
python3 websearch.py -q "apprendimento automatico" --tui
```

## Modalità di output

| Contesto | Output predefinito | Override |
|---|---|---|
| Dal terminale | Albero HTML live su `http://127.0.0.1:8765/` | `--tui`, `--json`, `--text` |
| Pipe/script (no TTY) | Snapshot HTML nella directory corrente | `--html-out PERCORSO`, `--json` |

## Opzioni riga di comando

| Opzione | Predefinito | Descrizione |
|---|---|---|
| `-q`, `--query TESTO` | prompt | Query seme iniziale |
| `-n`, `--limit N` | `6` | Max risultati per query |
| `--interval SEC` | `60` | Ritardo tra round |
| `--rounds N` | `0` | Numero di round (0 = illimitato) |
| `--lang CODICE` | auto | `fr`, `en`, `es`, `it`, `zh`, `ru` |
| `--no-ollama` | off | Solo espansione euristica |
| `--tui` | off | Interfaccia terminale |
| `--json` | off | JSON su stdout |
| `--text` | off | Testo normale su stdout |
| `--html-out PERCORSO` | auto | Percorso snapshot |

## Backend di ricerca

| Backend | Endpoint | Note |
|---|---|---|
| `bing-rss` | `bing.com/search?format=rss` | RSS strutturato |
| `marginalia` | `old-search.marginalia.nu` | Indice indipendente |
| `yahoo` | `search.yahoo.com` | Parsing HTML |
| `ddg-lite` | `lite.duckduckgo.com/lite/` | Basato su POST |

## Licenza

Rilasciato sotto la [Licenza MIT](../LICENSE).

---

<div align="center">

Mantenuto da [@TFD-42](https://github.com/TFD-42) · [Segnala un bug](https://github.com/TFD-42/dendropivot-search/issues/new?template=bug_report.yml)

</div>
