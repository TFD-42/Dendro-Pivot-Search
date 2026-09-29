<div align="center">

# DendroPivot

### Explorador web local con privacidad para Python — convierte una consulta en un árbol de conocimiento navegable

**No requiere clave API. LLM Ollama local opcional. Solo biblioteca estándar de Python.**

DendroPivot convierte una búsqueda en un camino de exploración guiado. En cada ronda, la consulta semilla se ramifica en cinco reformulaciones de *enfoque* y cinco temas *adyacentes*; lo que lees refuerza el árbol, y cualquier resultado puede convertirse en la nueva raíz. Funciona en la terminal o como página web local en vivo, consulta varios índices de búsqueda gratuitos sin clave API, puede usar un LLM local a través de [Ollama](https://ollama.com) y solo requiere la biblioteca estándar de Python.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Licencia: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)
[![Sin clave API](https://img.shields.io/badge/clave%20API-no%20requerida-success)](#backends-de-búsqueda)

[English](../README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · **Español** · [Italiano](README.it.md) · [Русский](README.ru.md) · [中文](README.zh.md) · [日本語](README.ja.md) · [Português](README.pt.md)

</div>

---

## ¿Por qué DendroPivot?

Una sola consulta de búsqueda solo muestra un ángulo de un tema. DendroPivot trata tu consulta como una **semilla**, la despliega en cinco reformulaciones y cinco temas adyacentes, las ejecuta contra varios índices de búsqueda gratuitos y usa lo que realmente abres para orientar la siguiente ronda. El resultado es un árbol de exploración en lugar de una lista plana de diez enlaces.

## La metodología de pivote

| Paso | Qué ocurre | Por qué ayuda |
|---|---|---|
| 1. **Semilla** | Introduces una consulta inicial. | Establece la raíz del árbol. |
| 2. **Ramificación** | Se despliega en 5 ángulos de enfoque y 5 temas adyacentes. | Varias perspectivas en lugar de un ranking. |
| 3. **Lectura** | Abrir un resultado refuerza su vocabulario. | Tu curiosidad orienta la siguiente ronda. |
| 4. **Crecimiento** | Nuevas rondas anclan consultas en términos compartidos. | Conceptos clave del dominio se hacen visibles. |
| 5. **Pivote** | `f` o Mayús+clic: el resultado se convierte en la nueva raíz. | Profundizar en un subtema sin perder el contexto. |
| 6. **Retroceder** | El historial guarda cada árbol; `b`/`n` para navegar. | Comparar ramas y volver al camino principal. |

## Características

- **Dos columnas por ronda**: Enfoque (5 reformulaciones) + Adyacente (5 temas relacionados)
- **Enriquecimiento continuo**: los resultados leídos influyen en la siguiente ronda
- **Búsqueda multi-backend**: Bing RSS, Marginalia, Yahoo, DDG Lite — con rotación, fallback y cooldown
- **HTML primero**: abre un árbol en vivo en el navegador; fuera de la terminal crea un snapshot HTML
- **Seis idiomas**: `--lang fr|en|es|it|zh|ru`
- **Ollama opcional**: expansión de consultas LLM y traducción bajo demanda
- **Solo biblioteca estándar**: sin `pip install`, funciona en cualquier lugar con Python 3.10+

## Requisitos

| Componente | Requisito |
|---|---|
| Python | **3.10 o superior** |
| Red | HTTPS saliente a los backends de búsqueda |
| Ollama | Opcional, solo para expansión LLM y traducción |
| Paquetes Python | Ninguno |

## Instalación

```bash
git clone https://github.com/TFD-42/dendropivot-search.git
cd dendropivot-search
python3 websearch.py -q "modelos de lenguaje locales"
```

## Inicio rápido

```bash
# Árbol HTML en vivo en el navegador (por defecto en la terminal)
python3 websearch.py -q "aprendizaje automático"

# Una ronda como JSON
python3 websearch.py -q "aprendizaje automático" --rounds 1 --no-ollama --json

# Interfaz de terminal de dos columnas
python3 websearch.py -q "aprendizaje automático" --tui
```

## Modos de salida

| Contexto | Salida por defecto | Anular |
|---|---|---|
| Desde la terminal | Árbol HTML en vivo en `http://127.0.0.1:8765/` | `--tui`, `--json`, `--text` |
| Tubería/script (sin TTY) | Snapshot HTML en el directorio actual | `--html-out RUTA`, `--json` |

## Opciones de línea de comandos

| Opción | Por defecto | Descripción |
|---|---|---|
| `-q`, `--query TEXTO` | solicitud | Consulta semilla inicial |
| `-n`, `--limit N` | `6` | Máx. resultados por consulta |
| `--interval SEGS` | `60` | Retraso entre rondas |
| `--rounds N` | `0` | Número de rondas (0 = ilimitado) |
| `--lang CÓDIGO` | auto | `fr`, `en`, `es`, `it`, `zh`, `ru` |
| `--no-ollama` | off | Solo expansión heurística |
| `--tui` | off | Interfaz de terminal |
| `--json` | off | JSON en stdout |
| `--text` | off | Texto plano en stdout |
| `--html-out RUTA` | auto | Ruta del snapshot |

## Backends de búsqueda

| Backend | Endpoint | Notas |
|---|---|---|
| `bing-rss` | `bing.com/search?format=rss` | RSS estructurado |
| `marginalia` | `old-search.marginalia.nu` | Índice independiente |
| `yahoo` | `search.yahoo.com` | Análisis HTML |
| `ddg-lite` | `lite.duckduckgo.com/lite/` | Basado en POST |

## Licencia

Publicado bajo la [Licencia MIT](../LICENSE).

---

<div align="center">

Mantenido por [@TFD-42](https://github.com/TFD-42) · [Reportar un error](https://github.com/TFD-42/dendropivot-search/issues/new?template=bug_report.yml)

</div>
