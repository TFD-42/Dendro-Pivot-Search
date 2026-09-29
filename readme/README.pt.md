<div align="center">

# DendroPivot

### Explorador web local com privacidade para Python — transforma uma consulta numa árvore de conhecimento navegável

**Sem chave API. LLM Ollama local opcional. Apenas biblioteca padrão do Python.**

DendroPivot transforma uma única pesquisa num caminho de exploração guiado. Em cada ronda, a consulta semente ramifica-se em cinco reformulações de *foco* e cinco tópicos *adjacentes*; o que lê reforça a árvore, e qualquer resultado pode tornar-se a nova raiz. Funciona no terminal ou como página web local ao vivo, consulta vários índices de pesquisa gratuitos sem chave API, pode usar um LLM local via [Ollama](https://ollama.com) e requer apenas a biblioteca padrão do Python.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Licença: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)
[![Sem chave API](https://img.shields.io/badge/chave%20API-n%C3%A3o%20necess%C3%A1ria-success)](#backends-de-pesquisa)

[English](../README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Русский](README.ru.md) · [中文](README.zh.md) · [日本語](README.ja.md) · **Português**

</div>

---

## Por que DendroPivot?

Uma única consulta de pesquisa mostra apenas um ângulo de um tópico. DendroPivot trata a sua consulta como uma **semente**, expande-a em cinco reformulações e cinco tópicos adjacentes, executa-as contra vários índices de pesquisa gratuitos e usa o que realmente abre para guiar a próxima ronda. O resultado é uma árvore de exploração em vez de uma lista plana de dez links.

## A metodologia pivot

| Passo | O que acontece | Por que ajuda |
|---|---|---|
| 1. **Semente** | Introduz uma consulta inicial. | Estabelece a raiz da árvore. |
| 2. **Ramificação** | Expande-se em 5 ângulos de foco e 5 tópicos adjacentes. | Várias perspetivas em vez de um ranking. |
| 3. **Leitura** | Abrir um resultado reforça o seu vocabulário. | O seu interesse guia a próxima ronda. |
| 4. **Crescimento** | Novas rondas ancoram consultas em termos comuns. | Conceitos-chave do domínio tornam-se visíveis. |
| 5. **Pivot** | `f` ou Shift+clique: o resultado torna-se a nova raiz. | Aprofundar um sub-tópico sem perder o contexto. |
| 6. **Voltar** | O histórico guarda cada árvore; `b`/`n` para navegar. | Comparar ramos e voltar a qualquer momento. |

## Funcionalidades

- **Duas colunas por ronda**: Foco (5 reformulações) + Adjacente (5 tópicos relacionados)
- **Enriquecimento contínuo**: resultados lidos influenciam a próxima ronda
- **Pesquisa multi-backend**: Bing RSS, Marginalia, Yahoo, DDG Lite — com rotação, fallback e cooldown
- **HTML em primeiro lugar**: abre uma árvore ao vivo no browser; fora do terminal cria um snapshot HTML
- **Seis idiomas**: `--lang fr|en|es|it|zh|ru`
- **Ollama opcional**: expansão de consultas LLM e tradução a pedido
- **Apenas biblioteca padrão**: sem `pip install`, funciona em qualquer lugar com Python 3.10+

## Requisitos

| Componente | Requisito |
|---|---|
| Python | **3.10 ou superior** |
| Rede | HTTPS de saída para os backends de pesquisa |
| Ollama | Opcional, apenas para expansão LLM e tradução |
| Pacotes Python | Nenhum |

## Instalação

```bash
git clone https://github.com/TFD-42/dendropivot-search.git
cd dendropivot-search
python3 websearch.py -q "modelos de linguagem locais"
```

## Início rápido

```bash
# Árvore HTML ao vivo no browser (predefinição no terminal)
python3 websearch.py -q "aprendizagem automática"

# Uma ronda como JSON
python3 websearch.py -q "aprendizagem automática" --rounds 1 --no-ollama --json

# Interface de terminal de duas colunas
python3 websearch.py -q "aprendizagem automática" --tui
```

## Modos de saída

| Contexto | Saída predefinida | Substituir |
|---|---|---|
| A partir do terminal | Árvore HTML ao vivo em `http://127.0.0.1:8765/` | `--tui`, `--json`, `--text` |
| Pipe/script (sem TTY) | Snapshot HTML no diretório atual | `--html-out CAMINHO`, `--json` |

## Opções de linha de comandos

| Opção | Predefinição | Descrição |
|---|---|---|
| `-q`, `--query TEXTO` | prompt | Consulta semente inicial |
| `-n`, `--limit N` | `6` | Máx. resultados por consulta |
| `--interval SEG` | `60` | Atraso entre rondas |
| `--rounds N` | `0` | Número de rondas (0 = ilimitado) |
| `--lang CÓDIGO` | auto | `fr`, `en`, `es`, `it`, `zh`, `ru` |
| `--no-ollama` | desl. | Apenas expansão heurística |
| `--tui` | desl. | Interface de terminal |
| `--json` | desl. | JSON no stdout |
| `--text` | desl. | Texto simples no stdout |
| `--html-out CAMINHO` | auto | Caminho do snapshot |

## Backends de pesquisa

| Backend | Endpoint | Notas |
|---|---|---|
| `bing-rss` | `bing.com/search?format=rss` | RSS estruturado |
| `marginalia` | `old-search.marginalia.nu` | Índice independente |
| `yahoo` | `search.yahoo.com` | Análise HTML |
| `ddg-lite` | `lite.duckduckgo.com/lite/` | Baseado em POST |

## Licença

Lançado sob a [Licença MIT](../LICENSE).

---

<div align="center">

Mantido por [@TFD-42](https://github.com/TFD-42) · [Reportar um bug](https://github.com/TFD-42/dendropivot-search/issues/new?template=bug_report.yml)

</div>
