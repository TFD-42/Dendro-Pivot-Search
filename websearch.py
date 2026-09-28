"""
websearch.py — recherche web interactive à deux colonnes, boucle
d'enrichissement continue, backends gratuits sans clé API.

Principe
--------
Une requête "graine" saisie par l'utilisateur alimente deux colonnes :

  COLONNE 1 (focus)   : la requête reformulée selon 5 angles différents
                        (définition, pratique, comparaison, actualité,
                        technique) puis, au fil des rounds, enrichie par le
                        champ lexical observé dans les résultats et dans
                        ce que l'utilisateur consulte.
  COLONNE 2 (adjacent): 5 sujets connexes mais non demandés directement
                        (ex. "llm" -> modèles open source, benchmarks,
                        dernières versions, formats, outillage...), dérivés
                        des termes co-occurrents et — si Ollama est joignable —
                        proposés par un modèle local.

Chaque requête forme un TOPIC avec sa couleur. Un thread de fond exécute
les rounds : plan des 10 requêtes -> recherche (avec délais de politesse)
-> fusion/déduplication -> pause -> round suivant. Chaque résultat consulté
(Entrée / ouverture) renforce les termes de ce résultat, ce qui oriente les
requêtes du round suivant. La touche 'f' pivote : le résultat courant
devient la nouvelle graine.

Backends (rotation + fallback, cooldown après échec) :
  bing-rss    : https://www.bing.com/search?q=...&format=rss  (XML propre)
  marginalia  : https://old-search.marginalia.nu/search        (index indépendant,
                interstitiel anti-bot suivi automatiquement)
  yahoo       : https://search.yahoo.com/search               (HTML best-effort)

Expansion de requêtes :
  - heuristique stdlib (toujours disponible)
  - Ollama si OLLAMA_HOST joignable (défaut http://127.0.0.1:11434),
    modèle OLLAMA_MODEL (défaut : premier modèle listé par /api/tags).
    Désactivable avec --no-ollama.

Vue web (optionnelle, --web [PORT]) : arbre haut -> bas auto-actualisé (polling 2 s) :
graine en tête, deux groupes (focus / adjacent), une carte par topic (couleur, angle,
round, compteur) dépliable sur ses résultats. Historique de navigation (fil d'Ariane,
retour/avant) : chaque pivot ou nouvelle graine archive l'état complet, restaurable.
Clic feuille = ouvre le lien ET signale la consultation (adaptation) ; Maj+clic = pivot.

Serveur sur machine distante, accès depuis une machine locale connectée en SSH :
le serveur reste sur 127.0.0.1 par défaut (pas d'exposition réseau) ; si une session
SSH est détectée (SSH_CONNECTION), les instructions de tunnel exact (ssh -L ...) sont
affichées au démarrage et journalisées (touche 'l'). --no-web-ssh-hint désactive. --html-out PATH écrit un
snapshot statique après chaque round. --web-only : serveur + rounds sans TUI.

Aucune dépendance hors bibliothèque standard.
Termux (Android), Linux, macOS, Windows (cmd/PowerShell/Windows Terminal).
Largeur < 90 colonnes (Termux portrait) -> colonnes empilées verticalement.

Touches (liste) : ↑/↓ ou chiffre = sélection ; ←/→ ou Tab = changer de colonne ;
Entrée = détail ; o = ouvrir ; f = pivoter la graine ; b/n = historique arrière/avant ; r = round immédiat ;
p = pause/reprise ; l = journal ; q = nouvelle recherche ; Ctrl-C = quitter.
"""

from __future__ import annotations

__version__ = "1.1.0"
APP_NAME = "DendroPivot"

import argparse
import concurrent.futures
import html as htmlmod
import json
import logging
import os
import random
import re
import shutil
import socket
import subprocess  # usage limité à open_url (arguments fixes)  # nosec B404
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET  # DTD/ENTITY rejetés avant parsing  # nosec B405
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15
N_REFORMULATIONS = 5
N_RELATED = 5
DEFAULT_LIMIT_PER_QUERY = 6
DEFAULT_ROUND_INTERVAL = 60.0   # secondes entre deux rounds
DEFAULT_REQUEST_DELAY = 1.5     # secondes entre deux requêtes HTTP de recherche
BACKEND_COOLDOWN = 180.0        # secondes de mise à l'écart d'un backend après échec
BACKEND_POOL_WORKERS = 3        # backends lancés en parallèle via ThreadPoolExecutor
BACKEND_MIN_INTERVAL = 1.0      # intervalle minimum (s) entre deux appels au même backend
MAX_RESULTS_PER_TOPIC = 12
MAX_PER_DOMAIN = 2             # par topic, évite qu'un site monopolise une requête
# domaines "bruit générique" (dictionnaires) exclus sauf si la requête vise une définition
NOISE_DOMAINS = {"merriam-webster.com", "dictionary.cambridge.org", "dictionary.com",
                 "thefreedictionary.com", "wiktionary.org", "en.wiktionary.org", "vocabulary.com",
                 "collinsdictionary.com", "askdifference.com", "twominenglish.com"}
OLLAMA_TIMEOUT = 40
DEFAULT_WEB_PORT = 8765
MAX_HTTP_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_POST_BODY_BYTES = 64 * 1024
MAX_SEED_LENGTH = 200
MAX_TIMELINE_ENTRIES = 50

log = logging.getLogger("websearch")


@dataclass
class Config:
    limit: int = DEFAULT_LIMIT_PER_QUERY
    round_interval: float = DEFAULT_ROUND_INTERVAL
    request_delay: float = DEFAULT_REQUEST_DELAY
    rounds: int = 0                    # 0 = illimité (mode interactif)
    use_ollama: bool = True
    ollama_host: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    ollama_model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", ""))
    color: bool = True
    debug: bool = False
    web_port: int = 0                  # 0 = serveur web désactivé
    web_host: str = "127.0.0.1"
    html_out: str = ""                 # snapshot HTML statique réécrit à chaque round
    lang: str = ""                     # langue de recherche/interface ("" = détection automatique)


# --------------------------------------------------------------------------
# Modèle de données
# --------------------------------------------------------------------------

@dataclass
class Topic:
    id: int
    column: int            # 1 = focus, 2 = adjacent
    query: str
    label: str
    color: int             # index dans la palette
    round: int
    method: str            # angle de reformulation / origine


@dataclass
class Result:
    title: str
    url: str
    snippet: str
    topic_id: int = -1
    backend: str = ""
    rank: int = 0
    ts: float = field(default_factory=time.time)

    @property
    def text(self) -> str:
        return f"{self.title} {self.snippet}"


class BackendError(Exception):
    """Échec réseau/HTTP/parsing d'un backend — géré par le pool."""


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def strip_tags(fragment: str) -> str:
    fragment = re.sub(r"<wbr\s*/?>", "", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", htmlmod.unescape(fragment)).strip()


def _read_limited(resp, limit: int = MAX_HTTP_RESPONSE_BYTES) -> bytes:
    """Read an HTTP response with a hard memory bound."""
    content_length = resp.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > limit:
                raise BackendError(f"réponse HTTP trop volumineuse (> {limit} octets)")
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = resp.read(min(64 * 1024, limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise BackendError(f"réponse HTTP trop volumineuse (> {limit} octets)")
        chunks.append(chunk)
    return b"".join(chunks)


def http_get(url: str, timeout: int = REQUEST_TIMEOUT, headers: Optional[dict] = None) -> str:
    hdrs = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # http(s) validé  # nosec B310
            status = resp.status
            raw = _read_limited(resp)
    except urllib.error.HTTPError as exc:
        raise BackendError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise BackendError(f"réseau ({exc.reason})") from exc
    except (TimeoutError, OSError) as exc:
        raise BackendError(f"timeout/socket ({exc})") from exc
    if status != 200:
        raise BackendError(f"HTTP {status}")
    return raw.decode("utf-8", errors="replace")


_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_SLEEP = 60.0


def _http_get_with_retry(
    url: str,
    timeout: int = REQUEST_TIMEOUT,
    headers: Optional[dict] = None,
    max_retries: int = 3,
) -> str:
    delay = 1.0
    for attempt in range(max_retries + 1):
        try:
            return http_get(url, timeout=timeout, headers=headers)
        except BackendError as exc:
            msg = str(exc)
            # Extract HTTP status code if present
            status: Optional[int] = None
            retry_after: Optional[float] = None
            if msg.startswith("HTTP "):
                try:
                    status = int(msg.split()[1])
                except (IndexError, ValueError):
                    pass
            if status not in _RETRY_STATUSES and status is not None:
                raise
            if attempt >= max_retries:
                raise
            # Try to honour Retry-After by re-issuing the raw request
            try:
                hdrs = {"User-Agent": USER_AGENT}
                if headers:
                    hdrs.update(headers)
                req = urllib.request.Request(url, headers=hdrs)
                urllib.request.urlopen(req, timeout=timeout)  # nosec B310
            except urllib.error.HTTPError as raw_exc:
                ra = raw_exc.headers.get("Retry-After") if raw_exc.headers else None
                if ra:
                    try:
                        retry_after = min(float(ra), _MAX_RETRY_SLEEP)
                    except ValueError:
                        pass
            except Exception:
                pass
            sleep_time = retry_after if retry_after is not None else min(
                delay * (2 ** attempt) + random.uniform(0, 1), _MAX_RETRY_SLEEP
            )
            time.sleep(sleep_time)
    raise BackendError("max retries exceeded")  # unreachable


def _extract_json_object(text: str) -> dict:
    """Extract the first balanced {...} JSON object from *text*.

    Uses brace-depth counting so nested objects/arrays inside string values
    are handled correctly, unlike a greedy ``re.search(r'\\{.*\\}', ..., re.S)``.
    Raises ValueError if no valid object is found.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError("no '{' found")
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced braces — no complete JSON object found")


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------

def backend_bing_rss(query: str, limit: int) -> list[Result]:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode(
        {"q": query, "format": "rss", "count": max(limit, 10)}
    )
    page = _http_get_with_retry(url)
    head = page[:4096].upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in head:
        # un flux RSS n'a jamais besoin de DTD : on refuse toute déclaration d'entité
        raise BackendError("RSS refusé (DTD/ENTITY présent)")
    try:
        root = ET.fromstring(page.encode("utf-8"))  # DTD/ENTITY rejetés ci-dessus  # nosec B314
    except ET.ParseError as exc:
        raise BackendError(f"RSS illisible ({exc})") from exc
    results: list[Result] = []
    for item in root.iter("item"):
        title = strip_tags(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        desc = strip_tags(item.findtext("description") or "")
        if not (title and safe_http_url(link)):
            continue
        results.append(Result(title=title, url=link, snippet=desc, rank=len(results) + 1))
        if len(results) >= limit:
            break
    return results  # vide = index sans réponse, pas une panne


_MARG_BASE = "https://old-search.marginalia.nu"
_MARG_THROTTLE_RE = re.compile(r'data-tr="(\d+)".*?href="(/search\?[^"]+)"', re.S)
_MARG_CARD_RE = re.compile(r'<section[^>]*class="card search-result"[^>]*>(.*?)</section>', re.S)


def backend_marginalia(query: str, limit: int) -> list[Result]:
    url = _MARG_BASE + "/search?" + urllib.parse.urlencode({"query": query})
    page = _http_get_with_retry(url)
    throttle = _MARG_THROTTLE_RE.search(page)
    if throttle:
        wait = min(int(throttle.group(1)), 8)
        time.sleep(wait + 0.5)
        page = _http_get_with_retry(_MARG_BASE + htmlmod.unescape(throttle.group(2)))
        if _MARG_THROTTLE_RE.search(page):
            raise BackendError("interstitiel anti-bot persistant")
    results: list[Result] = []
    for card in _MARG_CARD_RE.findall(page):
        m_title = re.search(r'<a[^>]*class="title"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', card, re.S)
        m_desc = re.search(r'<p class="description">(.*?)</p>', card, re.S)
        if not m_title:
            continue
        results.append(
            Result(
                title=strip_tags(m_title.group(2)),
                url=safe_http_url(htmlmod.unescape(m_title.group(1))) or "",
                snippet=strip_tags(m_desc.group(1)) if m_desc else "",
                rank=len(results) + 1,
            )
        )
        if len(results) >= limit:
            break
    if not results and "search-result" not in page and "No results" not in page:
        raise BackendError("structure HTML Marginalia inconnue")
    return results


_YAHOO_RU_RE = re.compile(r"/RU=([^/]+)/")


def _decode_yahoo_redirect(raw_url: str) -> str:
    match = _YAHOO_RU_RE.search(raw_url)
    return urllib.parse.unquote(match.group(1)) if match else raw_url


def backend_yahoo(query: str, limit: int) -> list[Result]:
    url = "https://search.yahoo.com/search?" + urllib.parse.urlencode({"p": query})
    page = _http_get_with_retry(url)
    chunks = re.split(r'(?=<div class="dd(?: \w+)* algo algo-sr relsrch Sr")', page)
    results: list[Result] = []
    for chunk in chunks[1:]:
        m_url = re.search(r'href="(https?://[^"]+)"', chunk)
        m_title = re.search(r'<span class="d-b fz-20[^"]*"[^>]*>(.*?)</span>', chunk, re.S)
        m_snip = re.search(r'<p class="fc-dustygray fz-14[^"]*"[^>]*>(.*?)</p>', chunk, re.S)
        if not (m_url and m_title):
            continue
        results.append(
            Result(
                title=strip_tags(m_title.group(1)),
                url=safe_http_url(_decode_yahoo_redirect(m_url.group(1))) or "",
                snippet=strip_tags(m_snip.group(1)) if m_snip else "",
                rank=len(results) + 1,
            )
        )
        if len(results) >= limit:
            break
    if not results and "algo-sr" not in page and len(page) < 20000:
        raise BackendError("réponse Yahoo anormale (blocage probable)")
    return results


BACKENDS: list[tuple[str, Callable[[str, int], list[Result]]]] = [
    ("bing-rss", backend_bing_rss),
    ("marginalia", backend_marginalia),
    ("yahoo", backend_yahoo),
]


class BackendPool:
    """Backends lancés en parallèle (ThreadPoolExecutor), fusionnés par reciprocal-rank scoring."""

    def __init__(self, backends: list[tuple[str, Callable[[str, int], list[Result]]]]):
        self._backends = backends
        self._cooldown_until: dict[str, float] = {}
        self._last_request: dict[str, float] = {}  # rate limiting par backend
        self._cursor = 0
        self._lock = threading.Lock()

    def _order(self, precise: bool) -> list[tuple[str, Callable[[str, int], list[Result]]]]:
        if not self._backends:
            return []
        if precise:
            rotated = list(self._backends)
        else:
            with self._lock:
                start = self._cursor
                self._cursor = (self._cursor + 1) % len(self._backends)
            rotated = self._backends[start:] + self._backends[:start]
        now = time.time()
        live = [b for b in rotated if self._cooldown_until.get(b[0], 0) <= now]
        cold = [b for b in rotated if b not in live]
        return live + cold

    @staticmethod
    def _degenerate(results: list[Result]) -> bool:
        """Vrai si un seul domaine occupe >= 60 % des résultats."""
        if len(results) < 4:
            return False
        doms = Counter(domain_of(r.url) for r in results)
        return doms.most_common(1)[0][1] / len(results) >= 0.6

    def _call_backend(self, name: str, fn: Callable[[str, int], list[Result]],
                      query: str, fetch: int) -> tuple[str, list[Result]]:
        """Appelle un backend en respectant le rate-limit, met à jour le cooldown si échec."""
        with self._lock:
            last = self._last_request.get(name, 0.0)
            wait = BACKEND_MIN_INTERVAL - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        with self._lock:
            self._last_request[name] = time.time()
        try:
            results = fn(query, fetch)
            for r in results:
                r.backend = name
            return name, results
        except BackendError as exc:
            with self._lock:
                self._cooldown_until[name] = time.time() + BACKEND_COOLDOWN
            log.debug("backend %s échec sur %r: %s", name, query, exc)
            raise

    @staticmethod
    def _reciprocal_rank_fuse(
        per_backend: list[tuple[str, list[Result]]],
        seen: set[str],
        limit: int,
    ) -> tuple[list[Result], str]:
        """Fusionne les listes par Reciprocal Rank Fusion (k=60).
        Retourne les *limit* meilleurs résultats frais + le nom des backends qui ont contribué."""
        scores: dict[str, float] = {}
        result_by_url: dict[str, Result] = {}
        backends_used: list[str] = []
        for name, results in per_backend:
            backends_used.append(name)
            for rank, r in enumerate(results):
                if not r.url:
                    continue
                scores[r.url] = scores.get(r.url, 0.0) + 1.0 / (rank + 60)
                if r.url not in result_by_url:
                    result_by_url[r.url] = r
        ranked = sorted(scores.keys(), key=lambda u: scores[u], reverse=True)
        fresh = [result_by_url[u] for u in ranked if u not in seen][:limit]
        label = "+".join(backends_used) if backends_used else ""
        return fresh, label

    def search(self, query: str, limit: int, precise: bool = True,
               seen: Optional[set[str]] = None) -> tuple[list[Result], str]:
        """Lance jusqu'à BACKEND_POOL_WORKERS backends en parallèle, fusionne par RR scoring.
        Retourne le meilleur lot (éventuellement vide) ; lève BackendError si tous échouent."""
        seen = seen or set()
        ordered = self._order(precise)
        if not ordered:
            return [], ""

        errors: list[str] = []
        per_backend: list[tuple[str, list[Result]]] = []

        workers = min(BACKEND_POOL_WORKERS, len(ordered))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(self._call_backend, name, fn, query, limit * 2): name
                for name, fn in ordered
            }
            for fut in concurrent.futures.as_completed(futs):
                name = futs[fut]
                try:
                    _, results = fut.result()
                    per_backend.append((name, results))
                except BackendError as exc:
                    errors.append(f"{name}: {exc}")

        if not per_backend:
            if errors and len(errors) == len(self._backends):
                raise BackendError(" | ".join(errors))
            return [], ""

        fused, label = self._reciprocal_rank_fuse(per_backend, seen, limit)
        if fused:
            return fused, label
        # fallback: renvoie ce qu'on a même si dégénéré
        all_results = [r for _, rs in per_backend for r in rs]
        fresh_all = [r for r in all_results if r.url not in seen]
        return fresh_all[:limit], label


def safe_http_url(url: str) -> Optional[str]:
    """Return a usable HTTP(S) URL, otherwise None."""
    try:
        parts = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None
    return url.strip()


_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "twclid",
    "mc_cid", "mc_eid", "yclid", "_ga", "_gl",
})


def strip_tracking_params(url: str) -> str:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    cleaned = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                if k.lower() not in _TRACKING_PARAMS]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(cleaned)))


def domain_of(url: str) -> str:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


# --------------------------------------------------------------------------
# Analyse lexicale
# --------------------------------------------------------------------------

_STOP = set("""
a an and are as at be by for from has have in is it its of on or that the this to was were will with
what which who how why when where your you we our they their them there here about into than then
also can could should would may might more most other some such only over under after before between
not no but if all any each into onto out up down new best top guide via use using used per like just
le la les un une des du de et en est sont au aux ce cet cette ces ses son sa pour par sur dans avec
sans pas plus moins que qui quoi dont où ou mais donc car ne nous vous ils elles il elle je tu on se
sa son leur leurs être avoir fait faire comme tout tous toute toutes très bien aussi
com www http https html htm php org net blog post article page news read learn free online
one two three example examples include including get got need make want way ways time day days ago
view see help find work works know based using used many much well good great things thing
""".split())

_TOKEN_RE = re.compile(r"[a-zA-Z\u00C0-\u024F][a-zA-Z0-9\u00C0-\u024F\-\+\.#]{1,}")
_FR_MARKERS = {"le", "la", "les", "de", "des", "du", "un", "une", "pour", "avec", "dans", "sur", "est", "et", "ou", "qui", "que", "au", "aux"}


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for tok in _TOKEN_RE.findall(text.lower()):
        tok = tok.strip(".-+")
        if len(tok) < 3 or tok in _STOP or tok.isdigit():
            continue
        out.append(tok)
    return out


def detect_lang(text: str) -> str:
    toks = set(re.findall(r"[a-zà-ÿ]+", text.lower()))
    return "fr" if len(toks & _FR_MARKERS) >= 1 and len(toks) <= 8 else "en"


def norm(tok: str) -> str:
    """Normalisation légère pour dédupliquer singulier/pluriel."""
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss") else tok


class KeywordStats:
    """Poids des termes : fréquence pondérée x consensus inter-topics (df) + boost fort à la consultation.

    Un terme présent dans plusieurs requêtes différentes est central au sujet ; un terme
    concentré dans une seule requête (ex. homonyme parasite) reste marginal."""

    def __init__(self, seed: str):
        self.seed_terms = {norm(t) for t in tokenize(seed)}
        self.weights: Counter[str] = Counter()
        self.bigrams: Counter[str] = Counter()
        self.term_topics: dict[str, set[int]] = {}
        self.bigram_topics: dict[str, set[int]] = {}
        self.viewed_titles: list[str] = []

    def _add(self, text: str, topic_id: int, w_term: float, w_bigram: float) -> None:
        toks = [norm(t) for t in tokenize(text)]
        for t in set(toks):
            self.weights[t] += w_term
            self.term_topics.setdefault(t, set()).add(topic_id)
        for a, b in zip(toks, toks[1:], strict=False):
            if a == b:
                continue
            bg = f"{a} {b}"
            self.bigrams[bg] += w_bigram
            self.bigram_topics.setdefault(bg, set()).add(topic_id)

    def ingest(self, result: Result) -> None:
        self._add(result.text, result.topic_id, 0.15, 0.15)

    def view(self, result: Result) -> None:
        # topic_id négatif distinct : une consultation compte comme une source à part entière
        self._add(result.text, -1 - len(self.viewed_titles), 3.0, 1.5)
        self.viewed_titles.append(result.title)
        self.viewed_titles = self.viewed_titles[-8:]

    def _score(self, key: str, table: Counter, topics: dict[str, set[int]]) -> float:
        df = len(topics.get(key, ()))
        return table[key] * (1.0 + 0.6 * max(df - 1, 0))

    def ranked_terms(self) -> list[tuple[str, float, int]]:
        out = [(t, self._score(t, self.weights, self.term_topics), len(self.term_topics.get(t, ())))
               for t in self.weights if t not in self.seed_terms]
        out.sort(key=lambda x: (-x[1], -len(x[0]), x[0]))  # égalité -> terme le plus spécifique (long)
        return out

    def top_terms(self, n: int, exclude: Iterable[str] = (), min_df: int = 1) -> list[str]:
        excl = {norm(e) for e in exclude}
        return [t for t, _, df in self.ranked_terms() if t not in excl and df >= min_df][:n]

    def core_terms(self, n: int = 3) -> list[str]:
        """Termes les plus centraux (champ propre de la graine)."""
        return self.top_terms(n, min_df=2) or self.top_terms(n)

    def best_bigram_with(self, term: str, exclude_terms: Iterable[str] = ()) -> Optional[str]:
        """Meilleur bigramme contenant `term` dont l'autre terme n'est ni la graine ni exclu."""
        excl = set(exclude_terms) | self.seed_terms
        best, best_score = None, 0.0
        for bg in self.bigrams:
            parts = bg.split()
            if term not in parts:
                continue
            other = parts[0] if parts[1] == term else parts[1]
            if other in excl:
                continue
            sc = self._score(bg, self.bigrams, self.bigram_topics)
            if sc > best_score:
                best, best_score = bg, sc
        return best if best_score >= 0.3 else None

    def top_bigrams(self, n: int, exclude_terms: Iterable[str] = (), min_df: int = 1) -> list[str]:
        excl = set(exclude_terms)
        scored = [(bg, self._score(bg, self.bigrams, self.bigram_topics), len(self.bigram_topics.get(bg, ())))
                  for bg in self.bigrams]
        scored.sort(key=lambda x: (-x[1], -len(x[0]), x[0]))
        out: list[str] = []
        covered: set[str] = set()
        for bg, sc, df in scored:
            parts = set(bg.split())
            if sc < 0.3 or df < min_df or parts <= self.seed_terms or parts <= excl or parts <= covered:
                continue
            out.append(bg)
            covered |= parts
            if len(out) >= n:
                break
        return out


# --------------------------------------------------------------------------
# Expansion de requêtes
# --------------------------------------------------------------------------

_TEMPLATES = {
    "en": {
        "definition": ["what is {s}", "{s} explained", "{s} overview"],
        "practical": ["how to use {s}", "{s} tutorial", "getting started {s}"],
        "comparison": ["{s} comparison", "{s} vs alternatives", "best {s}"],
        "recent": ["{s} 2026", "latest {s} news", "{s} release"],
        "technical": ["{s} architecture", "{s} internals deep dive", "{s} paper"],
    },
    "fr": {
        "definition": ["qu'est-ce que {s}", "{s} définition", "{s} présentation"],
        "practical": ["comment utiliser {s}", "{s} tutoriel", "débuter avec {s}"],
        "comparison": ["{s} comparatif", "{s} alternatives", "meilleur {s}"],
        "recent": ["{s} 2026", "{s} actualités", "{s} nouveautés"],
        "technical": ["{s} architecture", "{s} fonctionnement détaillé", "{s} article scientifique"],
    },
}
_RELATED_TEMPLATES = {
    "en": ["open source {s}", "{s} benchmark", "{s} ecosystem tools", "{s} alternatives", "{s} community"],
    "fr": ["{s} open source", "{s} benchmark", "{s} outils écosystème", "{s} alternatives", "{s} communauté"],
}


class HeuristicExpander:
    name = "heuristic"

    def __init__(self, lang: str = ""):
        self.lang = lang if lang in _TEMPLATES else ""

    def expand(self, seed: str, stats: KeywordStats, round_no: int, used: set[str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        lang = self.lang or detect_lang(seed)
        col1: list[tuple[str, str]] = []
        col2: list[tuple[str, str]] = []
        core = stats.core_terms(4)               # champ propre de la graine (df >= 2)
        adjacent = stats.top_terms(12, exclude=core, min_df=2) or stats.top_terms(12, exclude=core)
        bigrams = stats.top_bigrams(8, exclude_terms=core, min_df=2) or stats.top_bigrams(8, exclude_terms=core)

        # Colonne 1 : 5 angles ; rotation des variantes par round ; à partir du round 2,
        # les angles "comparison"/"technical" sont ancrés sur le champ lexical central.
        for k, (method, variants) in enumerate(_TEMPLATES[lang].items()):
            candidates = [variants[(round_no - 1 + j) % len(variants)].format(s=seed) for j in range(len(variants))]
            if round_no >= 2 and core:
                term = core[(round_no + k) % len(core)]
                if method == "technical":
                    candidates.insert(0, f"{seed} {term}")
                elif method == "comparison":
                    candidates.insert(0, f"{seed} {term} {method_hint(method, lang)}")
                elif method == "recent":
                    candidates.insert(0, f"{seed} {term} {method_hint(method, lang)}")
            for c in candidates:
                if c.lower() not in used:
                    col1.append((c, method))
                    break

        # Colonne 2 : sujets adjacents = bigrammes/termes mi-fréquents hors champ central
        covered: set[str] = set(core) | stats.seed_terms
        for bg in bigrams:
            if len(col2) >= N_RELATED:
                break
            parts = set(bg.split())
            if bg.lower() not in used and not parts <= covered:
                col2.append((bg, "lexical"))
                covered |= parts
        for term in adjacent:
            if len(col2) >= N_RELATED:
                break
            if term in covered:
                continue
            cand = stats.best_bigram_with(term, exclude_terms=covered) or f"{term} {seed}"
            if cand.lower() not in used and not set(cand.split()) <= covered:
                col2.append((cand, "cooccurrence"))
                covered.add(term)
        for tpl in _RELATED_TEMPLATES[lang]:
            if len(col2) >= N_RELATED:
                break
            cand = tpl.format(s=seed)
            if cand.lower() not in used:
                col2.append((cand, "template"))
        return col1[:N_REFORMULATIONS], col2[:N_RELATED]


def method_hint(method: str, lang: str) -> str:
    hints = {
        "en": {"comparison": "vs", "recent": "2026"},
        "fr": {"comparison": "comparatif", "recent": "2026"},
    }
    return hints[lang].get(method, "")


LANGUAGES = {"fr": "Français", "en": "English", "es": "Español",
             "it": "Italiano", "zh": "中文", "ru": "Русский"}
LANGUAGE_NAMES_EN = {"fr": "French", "en": "English", "es": "Spanish",
                     "it": "Italian", "zh": "Chinese", "ru": "Russian"}
UI_SOURCE_LANG = "fr"  # langue des libellés UI_STRINGS / METHOD_LABELS
# Libellés de l'interface web (source = français). Traduits par le même chemin LLM que les
# données, puis substitués côté navigateur. Les URLs, noms de backend et domaines ne sont
# jamais traduits : ce sont des identifiants. La page distante ouverte dans le navigateur
# n'est jamais touchée non plus — la traduction s'arrête à la plateforme.
UI_STRINGS = {
    "btn_round": "round maintenant", "btn_pause": "pause", "btn_resume": "reprendre",
    "ph_newseed": "nouvelle graine…", "btn_tree": "arbre", "btn_history": "historique complet",
    "btn_expand": "tout déplier", "btn_collapse": "tout replier",
    "lbl_history": "historique :", "btn_back": "retour", "btn_fwd": "avant",
    "hint_actions": "clic carte = déplier/replier · clic feuille = ouvrir + signaler consulté · Maj+clic = pivoter",
    "lbl_translate": "traduction (LLM) :", "opt_original": "Original",
    "lbl_lexical": "champ lexical :", "lbl_viewed": "consultés :",
    "lbl_round": "round", "lbl_time": "heure", "lbl_results": "résultats",
    "lbl_method": "méthode", "lbl_query": "requête", "lbl_column": "colonne",
    "col_focus": "focus", "col_adjacent": "adjacent",
    "paused": "PAUSE", "next_round": "prochain round dans {s}s",
    "live": "live", "static": "snapshot statique", "unreachable": "serveur injoignable",
    "no_rounds": "(aucun round terminé pour l'instant)", "none": "aucun",
    "tr_running": "traduction vers {lang} en cours…", "tr_done": "traduit : {lang}",
    "st_start": "démarrage", "st_plan": "round {r} : planification",
    "st_search": "round {r} : {i}/{n} « {q} »", "st_done": "round {r} terminé : +{added} résultats",
    "st_limit": "{r} round(s) effectués (limite atteinte)",
    "st_hist": "historique {i}/{n} : « {seed} » (round {r})",
}
# Noms de méthode affichés (clé technique -> libellé traduisible)
METHOD_LABELS = {
    "seed": "graine", "definition": "définition", "practical": "pratique",
    "comparison": "comparaison", "recent": "actualité", "technical": "technique",
    "lexical": "lexical", "cooccurrence": "co-occurrence", "template": "gabarit", "ollama": "ollama",
}

# Traduction anglaise intégrée des libellés : l'interface est utilisable en anglais sans Ollama.
# Clés = clés de UI_STRINGS / METHOD_LABELS ; les gabarits gardent les mêmes {paramètres}.
UI_STRINGS_EN = {
    "btn_round": "run round now", "btn_pause": "pause", "btn_resume": "resume",
    "ph_newseed": "new seed…", "btn_tree": "tree", "btn_history": "full history",
    "btn_expand": "expand all", "btn_collapse": "collapse all",
    "lbl_history": "history:", "btn_back": "back", "btn_fwd": "forward",
    "hint_actions": "click card = expand/collapse · click leaf = open + mark as read · Shift+click = pivot",
    "lbl_translate": "translation (LLM):", "opt_original": "Original",
    "lbl_lexical": "lexical field:", "lbl_viewed": "read:",
    "lbl_round": "round", "lbl_time": "time", "lbl_results": "results",
    "lbl_method": "method", "lbl_query": "query", "lbl_column": "column",
    "col_focus": "focus", "col_adjacent": "adjacent",
    "paused": "PAUSED", "next_round": "next round in {s}s",
    "live": "live", "static": "static snapshot", "unreachable": "server unreachable",
    "no_rounds": "(no round finished yet)", "none": "none",
    "tr_running": "translating to {lang}…", "tr_done": "translated: {lang}",
    "st_start": "starting", "st_plan": "round {r}: planning",
    "st_search": "round {r}: {i}/{n} “{q}”", "st_done": "round {r} done: +{added} results",
    "st_limit": "{r} round(s) done (limit reached)",
    "st_hist": "history {i}/{n}: “{seed}” (round {r})",
}
METHOD_LABELS_EN = {
    "seed": "seed", "definition": "definition", "practical": "practical",
    "comparison": "comparison", "recent": "recent", "technical": "technical",
    "lexical": "lexical", "cooccurrence": "co-occurrence", "template": "template", "ollama": "ollama",
}
BUILTIN_UI_TRANSLATIONS = {"en": (UI_STRINGS_EN, METHOD_LABELS_EN)}


def builtin_translation_cache(lang: str) -> dict[str, str]:
    """Cache source->cible pour les libellés d'interface, sans LLM. Vide si langue non intégrée."""
    pair = BUILTIN_UI_TRANSLATIONS.get(lang)
    if not pair:
        return {}
    ui, methods = pair
    cache = {UI_STRINGS[k]: v for k, v in ui.items() if k in UI_STRINGS}
    cache.update({METHOD_LABELS[k]: v for k, v in methods.items() if k in METHOD_LABELS})
    return cache


TRANSLATE_CHUNK = 20  # textes par appel Ollama : garde le prompt/la réponse JSON gérables


def _fmt_status(template: str, params: dict, tx, fallback: str) -> str:
    """Reconstruit une phrase de statut depuis son gabarit (traduit ou non) et ses paramètres.
    Les valeurs textuelles (graine, requête) passent par le cache de traduction ; les nombres
    restent tels quels. Retombe sur `fallback` si le gabarit traduit ne correspond plus."""
    safe = {k: (tx(v) if isinstance(v, str) else v) for k, v in (params or {}).items()}
    try:
        return template.format(**safe)
    except (KeyError, IndexError, ValueError):
        return fallback


def probe_ollama(host: str, model_hint: str = "") -> Optional[str]:
    """Sonde /api/tags et retourne un nom de modèle disponible, ou None si Ollama est injoignable
    ou n'a aucun modèle installé. Indépendant de l'expansion de requêtes (peut servir même avec
    --no-ollama, qui ne désactive que l'expansion, pas la traduction à la demande)."""
    try:
        req = urllib.request.Request(host.rstrip("/") + "/api/tags", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=3) as resp:  # http(s) validé  # nosec B310
            data = json.loads(_read_limited(resp).decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    models = [m.get("name") for m in data.get("models", []) if m.get("name")]
    if not models:
        return None
    if model_hint:
        if model_hint in models:
            return model_hint
        hit = next((m for m in models if m.startswith(model_hint)), None)
        if hit:
            return hit
    return models[0]


def ollama_translate(host: str, model: str, lang_name: str, texts: list[str]) -> list[str]:
    """Traduit `texts` vers lang_name via Ollama (un lot <= TRANSLATE_CHUNK à la fois, voir l'appelant).
    Lève BackendError si Ollama est injoignable ou renvoie une sortie invalide/mal alignée."""
    if not texts:
        return []
    prompt = (
        f"Translate each of the following texts to {lang_name}. Preserve meaning and tone, "
        f"keep proper nouns and technical terms as-is, do not add explanations or notes.\n"
        f"Return JSON only: {{\"translations\": [...]}} with exactly {len(texts)} strings, same order "
        f"as the input array.\n\nTexts:\n{json.dumps(texts, ensure_ascii=False)}"
    )
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json",
                       "options": {"temperature": 0.2}}).encode("utf-8")
    req = urllib.request.Request(host.rstrip("/") + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:  # http(s) validé  # nosec B310
            payload = json.loads(_read_limited(resp).decode("utf-8"))
        raw = payload.get("response", "")
        data = _extract_json_object(raw)
        out = data.get("translations")
    except (urllib.error.URLError, OSError, ValueError, AttributeError) as exc:
        raise BackendError(f"ollama translate: {exc}") from exc
    if not isinstance(out, list) or len(out) != len(texts):
        raise BackendError(f"ollama translate: sortie invalide (attendu {len(texts)} traductions)")
    return [str(x) for x in out]


class OllamaExpander:
    """Reformulations + sujets adjacents via un modèle local. API vérifiée :
    POST /api/generate {model, prompt, stream:false, format:"json"} ; GET /api/tags."""

    name = "ollama"

    def __init__(self, host: str, model: str, lang: str = ""):
        self.host = host.rstrip("/")
        self.model = model
        self.lang = lang
        self.available = False

    def probe(self) -> bool:
        try:
            req = urllib.request.Request(self.host + "/api/tags", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=3) as resp:  # http(s) validé  # nosec B310
                data = json.loads(_read_limited(resp).decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.debug("ollama injoignable: %s", exc)
            self.available = False
            return False
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        if not models:
            self.available = False
            return False
        if not self.model or self.model not in models:
            self.model = self.model if self.model and any(m.startswith(self.model) for m in models) else models[0]
        self.available = True
        return True

    def expand(self, seed: str, stats: KeywordStats, round_no: int, used: set[str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        if self.lang in LANGUAGE_NAMES_EN:
            lang = LANGUAGE_NAMES_EN[self.lang]
        else:
            lang = "French" if detect_lang(seed) == "fr" else "English"
        prompt = (
            f"You generate web search queries. Language: {lang}.\n"
            f"Seed query: {seed!r}\n"
            f"Terms frequently co-occurring in results: {', '.join(stats.top_terms(15))}\n"
            f"Titles the user opened (strong interest signal): {json.dumps(stats.viewed_titles, ensure_ascii=False)}\n"
            f"Already used queries (do not repeat): {json.dumps(sorted(used)[-40:], ensure_ascii=False)}\n\n"
            f"Return JSON only: {{\"reformulations\": [5 strings], \"related\": [5 strings]}}.\n"
            f"- reformulations: SAME intent as the seed, 5 different angles "
            f"(definition, practical, comparison, recent developments, technical depth), "
            f"using synonyms and the lexical field, each 2-6 words, must keep the seed's core concept.\n"
            f"- related: 5 ADJACENT topics the user did not ask for but likely cares about "
            f"(e.g. for 'llm': open-source models, latest releases, quantization formats, benchmarks, inference engines), "
            f"biased toward the opened titles, each 2-6 words, must NOT be a rephrasing of the seed."
        )
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False, "format": "json",
                           "options": {"temperature": 0.7}}).encode("utf-8")
        req = urllib.request.Request(self.host + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:  # http(s) validé  # nosec B310
                payload = json.loads(_read_limited(resp).decode("utf-8"))
            raw = payload.get("response", "")
            data = _extract_json_object(raw)
        except (urllib.error.URLError, OSError, ValueError, AttributeError) as exc:
            raise BackendError(f"ollama: {exc}") from exc

        def clean(items: object) -> list[str]:
            if not isinstance(items, list):
                return []
            out: list[str] = []
            for it in items:
                if isinstance(it, str):
                    s = re.sub(r"\s+", " ", it).strip(" \"'.")
                    if 2 <= len(s) <= 80 and s.lower() not in used and s not in out:
                        out.append(s)
            return out

        methods = ["definition", "practical", "comparison", "recent", "technical"]
        col1 = [(q, methods[i % 5]) for i, q in enumerate(clean(data.get("reformulations"))[:N_REFORMULATIONS])]
        col2 = [(q, "ollama") for q in clean(data.get("related"))[:N_RELATED]]
        if len(col1) < 3:
            raise BackendError("ollama: sortie insuffisante")
        return col1, col2


class Planner:
    """Combine Ollama (si dispo) et heuristique ; complète toujours à 5+5."""

    def __init__(self, cfg: Config):
        self.heuristic = HeuristicExpander(cfg.lang)
        self.ollama: Optional[OllamaExpander] = None
        if cfg.use_ollama:
            cand = OllamaExpander(cfg.ollama_host, cfg.ollama_model, cfg.lang)
            if cand.probe():
                self.ollama = cand
                log.info("ollama actif (%s, modèle %s)", cand.host, cand.model)
            else:
                log.info("ollama indisponible -> expansion heuristique")

    def plan(self, seed: str, stats: KeywordStats, round_no: int, used: set[str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]], str]:
        col1: list[tuple[str, str]] = []
        col2: list[tuple[str, str]] = []
        source = "heuristic"
        if self.ollama is not None:
            try:
                col1, col2 = self.ollama.expand(seed, stats, round_no, used)
                source = f"ollama:{self.ollama.model}"
            except BackendError as exc:
                log.warning("expansion ollama échouée (%s), fallback heuristique", exc)
        h1, h2 = self.heuristic.expand(seed, stats, round_no, used | {q.lower() for q, _ in col1 + col2})
        for q, m in h1:
            if len(col1) >= N_REFORMULATIONS:
                break
            if q.lower() not in {c.lower() for c, _ in col1}:
                col1.append((q, m))
        for q, m in h2:
            if len(col2) >= N_RELATED:
                break
            if q.lower() not in {c.lower() for c, _ in col2}:
                col2.append((q, m))
        if round_no == 1 and seed.lower() not in used:
            col1.insert(0, (seed, "seed"))
            col1 = col1[:N_REFORMULATIONS + 1]
        return col1, col2, source


# --------------------------------------------------------------------------
# Session (état partagé thread-safe) + worker de rounds
# --------------------------------------------------------------------------

PALETTE_16 = [34, 32, 33, 35, 36, 94, 92, 93, 95, 96, 31, 91]  # codes SGR fg
SGR_HEX = {34: "#4c8dff", 32: "#3ecf8e", 33: "#e5b843", 35: "#c77dff", 36: "#38c6d9", 94: "#8fb3ff",
           92: "#8de0b0", 93: "#ffd580", 95: "#e0a8ff", 96: "#8ee3ee", 31: "#ff6b6b", 91: "#ff9b9b"}


class Session:
    def __init__(self, seed: str, cfg: Config, planner: Planner, pool: BackendPool):
        self.cfg = cfg
        self.planner = planner
        self.pool = pool
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.paused = False
        self.version = 0
        self.web_url = ""
        self.ssh_hint = ""
        self.translations: dict[str, dict[str, str]] = {}
        self.translate_lang = ""
        self.translate_status = ""
        self._llm_translation_warned = False
        self.log: list[str] = []
        self.reset(seed)

    _STATE_KEYS = ("seed", "stats", "topics", "results", "seen_urls", "viewed_urls", "used_queries",
                   "round_no", "status", "status_key", "status_params",
                   "_next_topic_id", "_color_cursor", "round_started_at")

    def _blank_state(self, seed: str) -> None:
        self.seed = seed
        self.stats = KeywordStats(seed)
        self.topics: dict[int, Topic] = {}
        self.results: dict[int, list[Result]] = {}
        self.seen_urls: set[str] = set()
        self.viewed_urls: set[str] = set()
        self.used_queries: set[str] = set()
        self.round_no = 0
        self.status = UI_STRINGS["st_start"]
        self.status_key = "st_start"
        self.status_params: dict = {}
        self._next_topic_id = 0
        self._color_cursor = 0
        self.round_started_at: dict[int, float] = {}

    def _bundle(self) -> dict:
        b = {k: getattr(self, k) for k in self._STATE_KEYS}
        b["ts"] = time.time()
        return b

    def _restore(self, b: dict) -> None:
        for k in self._STATE_KEYS:
            setattr(self, k, b[k])

    def _switch(self, status_hint: str) -> None:
        """Après tout changement d'état courant : invalide le round en cours, réveille le worker."""
        self.generation += 1
        self.next_round_at = 0.0
        self.version += 1
        self.wake_event.set()

    def reset(self, seed: str) -> None:
        """Nouvelle graine : l'état courant est archivé dans l'historique (navigation type navigateur :
        les entrées 'avant' au-delà du curseur sont abandonnées)."""
        with self.lock:
            if not hasattr(self, "timeline"):
                self.timeline: list[dict] = []
                self.cursor = -1
                self.generation = 0
            if self.cursor >= 0:
                self.timeline[self.cursor] = self._bundle()
                del self.timeline[self.cursor + 1:]
            self._blank_state(seed)
            self.timeline.append(self._bundle())
            if len(self.timeline) > MAX_TIMELINE_ENTRIES:
                self.timeline = self.timeline[-MAX_TIMELINE_ENTRIES:]
            self.cursor = len(self.timeline) - 1
            self._switch("reset")

    def goto(self, index: int) -> bool:
        """Revient à une graine de l'historique (résultats, consultations, champ lexical restaurés)."""
        with self.lock:
            if not (0 <= index < len(self.timeline)) or index == self.cursor:
                return False
            self.timeline[self.cursor] = self._bundle()
            self.cursor = index
            self._restore(self.timeline[index])
            self._set_status("st_hist", i=index + 1, n=len(self.timeline), seed=self.seed, r=self.round_no)
            self._switch("goto")
        self.note(f"retour historique -> « {self.seed} »")
        return True

    def back(self) -> bool:
        return self.goto(self.cursor - 1)

    def forward(self) -> bool:
        return self.goto(self.cursor + 1)

    def history_view(self) -> list[dict]:
        with self.lock:
            out = []
            for i, b in enumerate(self.timeline):
                cur = i == self.cursor
                n = sum(len(v) for v in self.results.values()) if cur else sum(len(v) for v in b["results"].values())
                out.append({"index": i, "seed": self.seed if cur else b["seed"], "round": self.round_no if cur else b["round_no"],
                            "results": n, "current": cur, "ts": time.strftime("%H:%M", time.localtime(b["ts"]))})
            return out

    def _set_status(self, key: str, **params: object) -> None:
        """Statut structuré : la clé + ses paramètres permettent au navigateur de reconstruire
        la phrase dans la langue choisie, sans renvoyer chaque statut au LLM à chaque round."""
        self.status_key = key
        self.status_params = params
        try:
            self.status = UI_STRINGS[key].format(**params)
        except (KeyError, IndexError):
            self.status = key

    def note(self, msg: str) -> None:
        with self.lock:
            self.log.append(time.strftime("%H:%M:%S ") + msg)
            self.log = self.log[-200:]
            self.version += 1
        log.info(msg)

    def _new_topic(self, column: int, query: str, method: str) -> Topic:
        t = Topic(
            id=self._next_topic_id, column=column, query=query, label=query,
            color=PALETTE_16[self._color_cursor % len(PALETTE_16)],
            round=self.round_no, method=method,
        )
        self._next_topic_id += 1
        self._color_cursor += 1
        self.topics[t.id] = t
        self.results[t.id] = []
        self.used_queries.add(query.lower())
        return t

    def column_topics(self, column: int) -> list[Topic]:
        with self.lock:
            return sorted((t for t in self.topics.values() if t.column == column), key=lambda t: (-t.round, t.id))

    def mark_viewed(self, r: Result) -> None:
        with self.lock:
            if r.url not in self.viewed_urls:
                self.viewed_urls.add(r.url)
                self.stats.view(r)
                self.version += 1
        self.note(f"consulté: {r.title[:60]}")

    def force_round(self) -> None:
        with self.lock:
            self.next_round_at = 0.0
        self.wake_event.set()

    def snapshot(self) -> dict:
        """État sérialisable pour la vue web (tree graph) et le snapshot HTML. Si une langue de
        traduction est active, substitue les textes affichés (graine, requêtes, titres, snippets)
        par leur traduction en cache — texte original si pas encore traduit (aucun appel réseau ici,
        pour rester rapide et non bloquant ; les traductions arrivent via un round de fond)."""
        with self.lock:
            lang = self.translate_lang
            cache = self.translations.get(lang, {}) if lang else {}
            tx = (lambda x: cache.get(x, x)) if lang else (lambda x: x)
            cols = {}
            for c in (1, 2):
                cols[str(c)] = [
                    {"id": t.id, "query": tx(t.query), "method": t.method, "round": t.round,
                     "color": SGR_HEX.get(t.color, "#cccccc"),
                     "results": [{"title": tx(r.title), "url": r.url, "snippet": tx(r.snippet), "backend": r.backend,
                                  "viewed": r.url in self.viewed_urls} for r in self.results.get(t.id, [])]}
                    for t in sorted((t for t in self.topics.values() if t.column == c), key=lambda t: (t.round, t.id))
                ]
            return {
                "seed": tx(self.seed), "round": self.round_no, "status": _fmt_status(
                    tx(UI_STRINGS.get(self.status_key, self.status_key)), self.status_params, tx, self.status),
                "paused": self.paused,
                "version": self.version, "next_round_in": max(0, int(self.next_round_at - time.time())) if self.next_round_at else 0,
                "columns": cols, "lexical": self.stats.top_terms(15), "viewed_titles": [tx(x) for x in self.stats.viewed_titles],
                "log": self.log[-30:], "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "history": self.history_view(), "cursor": self.cursor,
                "round_times": {str(r): time.strftime("%H:%M:%S", time.localtime(ts))
                                for r, ts in self.round_started_at.items()},
                "languages": LANGUAGES, "translate_lang": lang,
                "html_lang": lang or UI_SOURCE_LANG, "app": APP_NAME, "app_version": __version__, "translate_status": self.translate_status,
                "status_key": self.status_key, "status_params": self.status_params,
                "ui": {k: tx(v) for k, v in UI_STRINGS.items()},
                "methods": {k: tx(v) for k, v in METHOD_LABELS.items()},
            }

    def write_html_snapshot(self) -> None:
        if not self.cfg.html_out:
            return
        try:
            tmp = self.cfg.html_out + ".tmp." + os.urandom(3).hex()
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(render_html(self.snapshot(), live=False))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.cfg.html_out)
        except OSError as exc:
            log.warning("snapshot HTML non écrit (%s): %s", self.cfg.html_out, exc)

    def find_result(self, url: str) -> Optional[Result]:
        with self.lock:
            for rs in self.results.values():
                for r in rs:
                    if r.url == url:
                        return r
        return None

    def collect_translatable_texts(self) -> list[str]:
        """Tout le texte affiché par la plateforme : libellés d'interface, noms de méthode,
        gabarits de statut, graine, requêtes de topics, titres et snippets des résultats.
        Jamais les URLs, domaines ou noms de backend (identifiants), ni le champ lexical
        (signal interne de pilotage des requêtes). La page distante ouverte dans le
        navigateur n'est pas concernée : la traduction s'arrête à la plateforme."""
        with self.lock:
            texts = {self.seed}
            texts.update(UI_STRINGS.values())
            texts.update(METHOD_LABELS.values())
            for t in self.topics.values():
                texts.add(t.query)
            for rs in self.results.values():
                for r in rs:
                    texts.add(r.title)
                    if r.snippet:
                        texts.add(r.snippet)
        return list(texts)

    def retranslate_if_active(self) -> None:
        """Après un round : traduit le contenu nouvellement arrivé si une langue est active,
        sinon les résultats du round suivant s'afficheraient en langue d'origine."""
        with self.lock:
            lang = self.translate_lang
        if not lang:
            return
        try:
            self.translate_batch(lang, self.collect_translatable_texts())
        except BackendError as exc:
            if not self._llm_translation_warned:
                self._llm_translation_warned = True
                self.note(f"traduction LLM indisponible, libellés intégrés/originaux conservés: {exc}")

    def translate_batch(self, lang: str, texts: list[str]) -> None:
        """Traduit les textes pas encore en cache pour `lang`, par lots de TRANSLATE_CHUNK.
        Lève BackendError si Ollama est injoignable — le cache partiel déjà obtenu est conservé."""
        with self.lock:
            cache = self.translations.setdefault(lang, {})
            missing = [t for t in dict.fromkeys(texts) if t not in cache]
        if not missing:
            return
        host, model_hint = self.cfg.ollama_host, self.cfg.ollama_model
        model = probe_ollama(host, model_hint)
        if not model:
            raise BackendError("Ollama injoignable sur " + host)
        lang_name = LANGUAGES.get(lang, lang)
        for i in range(0, len(missing), TRANSLATE_CHUNK):
            batch = missing[i:i + TRANSLATE_CHUNK]
            translated = ollama_translate(host, model, lang_name, batch)
            with self.lock:
                cache = self.translations.setdefault(lang, {})
                for orig, tr in zip(batch, translated, strict=True):
                    cache[orig] = tr
                self.version += 1

    def set_language(self, lang: str, translate_content: bool = True) -> None:
        """Active une langue d'affichage : libellés intégrés (sans LLM) immédiatement, puis
        traduction LLM du reste (graine, requêtes, résultats) en arrière-plan si demandé.
        Sans Ollama, l'échec est journalisé une fois et les textes originaux restent affichés."""
        if lang and lang not in LANGUAGES:
            raise ValueError(f"langue inconnue: {lang}")
        with self.lock:
            if not lang:
                self.translate_lang = ""
                self.translate_status = ""
                self.version += 1
                return
            cache = self.translations.setdefault(lang, {})
            for src, dst in builtin_translation_cache(lang).items():
                cache.setdefault(src, dst)
            self.translate_lang = lang
            self.version += 1
        if translate_content:
            threading.Thread(target=_run_translation, args=(self, lang), daemon=True,
                             name="translate").start()

    def toggle_pause(self) -> bool:
        with self.lock:
            self.paused = not self.paused
            self.version += 1
            p = self.paused
        self.wake_event.set()
        return p

    # -- exécution d'un round -------------------------------------------------

    def run_round(self) -> int:
        with self.lock:
            self.round_no += 1
            rn = self.round_no
            self.round_started_at[rn] = time.time()
            seed = self.seed
            gen = self.generation
            used = set(self.used_queries)
            stats = self.stats
            self._set_status("st_plan", r=rn)
            self.version += 1
        col1, col2, source = self.planner.plan(seed, stats, rn, used)
        self.note(f"round {rn} planifié via {source}: {len(col1)} focus + {len(col2)} adjacents")
        plan: list[Topic] = []
        with self.lock:
            for q, m in col1:
                plan.append(self._new_topic(1, q, m))
            for q, m in col2:
                plan.append(self._new_topic(2, q, m))
            self.version += 1

        added = 0
        for i, topic in enumerate(plan):
            if self.stop_event.is_set():
                break
            with self.lock:
                if gen != self.generation:  # pivot / retour historique pendant le round -> abandon
                    return added
                self._set_status("st_search", r=rn, i=i + 1, n=len(plan), q=topic.query)
                self.version += 1
            try:
                with self.lock:
                    seen_snapshot = set(self.seen_urls)
                results, backend = self.pool.search(topic.query, self.cfg.limit,
                                                    precise=(topic.column == 1), seen=seen_snapshot)
            except BackendError as exc:
                self.note(f"échec « {topic.query} »: {exc}")
                results, backend = [], ""
            with self.lock:
                if gen != self.generation:
                    return added
                # garde de pertinence : le résultat doit rester dans le champ du sujet.
                # accepte si : terme de la graine, OU terme central du champ (df >= 2),
                # OU au moins 2 termes de la requête elle-même (reformulations par synonymes).
                seed_terms = set(self.stats.seed_terms) or {seed.lower()}
                core_terms = set(self.stats.core_terms(6))
                query_terms = {norm(t) for t in tokenize(topic.query)}
                need_q = min(2, len(query_terms)) if query_terms else 0
                wants_definition = any(w in topic.query.lower() for w in ("definition", "définition", "meaning", "what is", "qu'est"))
                per_domain: Counter[str] = Counter()
                for r in results:
                    r.url = strip_tracking_params(r.url)
                    if not safe_http_url(r.url) or r.url in self.seen_urls:
                        continue
                    dom = domain_of(r.url)
                    if per_domain[dom] >= MAX_PER_DOMAIN:
                        continue
                    if dom in NOISE_DOMAINS and not wants_definition:
                        continue
                    text_terms = {norm(t) for t in tokenize(r.text)}
                    low = r.text.lower()
                    relevant = bool(seed_terms & text_terms) or seed.lower() in low or bool(core_terms & text_terms) \
                        or (need_q and len(query_terms & text_terms) >= need_q)
                    if not relevant:
                        continue
                    self.seen_urls.add(r.url)
                    per_domain[dom] += 1
                    r.topic_id = topic.id
                    self.results[topic.id].append(r)
                    self.stats.ingest(r)
                    added += 1
                    if len(self.results[topic.id]) >= MAX_RESULTS_PER_TOPIC:
                        break
                self.version += 1
            if backend:
                log.debug("« %s » -> %d nouveaux (%s)", topic.query, len(self.results[topic.id]), backend)
            if i < len(plan) - 1:
                self.stop_event.wait(self.cfg.request_delay)
        with self.lock:
            if gen != self.generation:
                return added
            # purge des topics sans résultat pour garder la vue lisible
            for t in plan:
                if not self.results.get(t.id):
                    self.topics.pop(t.id, None)
                    self.results.pop(t.id, None)
            self._set_status("st_done", r=rn, added=added)
            self.version += 1
        return added

    def worker(self) -> None:
        while not self.stop_event.is_set():
            with self.lock:
                paused = self.paused
                due = time.time() >= self.next_round_at
                done = self.cfg.rounds and self.round_no >= self.cfg.rounds
            if done:
                with self.lock:
                    self._set_status("st_limit", r=self.round_no)
                    self.version += 1
                return
            if paused or not due:
                self.wake_event.wait(1.0)
                self.wake_event.clear()
                continue
            try:
                self.run_round()
                self.retranslate_if_active()
            except Exception as exc:  # noqa: BLE001 — un round ne doit jamais tuer le worker
                log.exception("round en erreur")
                self.note(f"round en erreur: {exc}")
            with self.lock:
                self.next_round_at = time.time() + self.cfg.round_interval
            self.write_html_snapshot()


# --------------------------------------------------------------------------
# Vue web : tree graph SVG auto-actualisé (serveur local stdlib) + snapshot HTML
# --------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!doctype html><html lang="__LANG__"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="__APP__ · exploration tree for “__SEED__”: focus reformulations and adjacent topics, round by round.">
<meta name="generator" content="__APP__ __VERSION__">
<meta name="robots" content="noindex,nofollow">
<meta name="referrer" content="no-referrer">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0f1218">
<title>__APP__ · __SEED__</title>
<style>
:root{--bg:#0f1218;--fg:#e6e9ef;--mut:#8b93a5;--line:#2a3140;--card:#161c28;--acc:#4c8dff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:3;background:var(--bg);padding:8px 14px;border-bottom:1px solid var(--line)}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.row+.row{margin-top:6px}
h1{font-size:15px;margin:0 6px 0 0}h1 b{color:var(--acc)}
.badge{padding:2px 8px;border-radius:10px;background:#1a2030;color:var(--mut);font-size:12px}
button,input,select{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:4px 9px;font:inherit}
button:hover:not(:disabled){border-color:var(--acc);cursor:pointer}button:disabled{opacity:.4}input{min-width:180px}
.hint{color:var(--mut);font-size:11px}
#crumbs{display:flex;flex-wrap:wrap;gap:4px;align-items:center;font-size:12px}
#crumbs .crumb{padding:2px 8px;border-radius:6px;border:1px solid var(--line);color:var(--mut);cursor:pointer;background:var(--card)}
#crumbs .crumb.cur{color:#fff;border-color:var(--acc);cursor:default}#crumbs .crumb:hover:not(.cur){border-color:var(--fg);color:var(--fg)}
#crumbs .sep{color:var(--mut)}
#wrap{position:relative;overflow:auto}#canvas{position:relative}#edges{position:absolute;left:0;top:0;pointer-events:none}
.node{position:absolute;border-radius:8px}
.seed{background:var(--acc);color:#fff;font-weight:700;font-size:15px;padding:6px 16px;white-space:nowrap;transform:translateX(-50%)}
.group{background:var(--card);border:1px solid var(--line);color:var(--mut);padding:4px 12px;transform:translateX(-50%);white-space:nowrap}
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--c);padding:6px 8px 6px 10px;cursor:pointer;user-select:none}
.card:hover{border-color:var(--c)}.card.fresh{box-shadow:0 0 0 1px var(--c),0 0 14px -4px var(--c)}
.card .q{font-weight:650;color:var(--c);line-height:1.25;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;max-height:2.5em}
.card .m{color:var(--mut);font-size:11px;display:flex;justify-content:space-between;gap:6px}
.card .m .n{background:var(--c);color:#0f1218;border-radius:8px;padding:0 6px;font-weight:700}
.leaf{position:absolute;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;padding-left:14px;font-size:12px}
.leaf:before{content:"";position:absolute;left:2px;top:7px;width:7px;height:7px;border-radius:50%;border:1.5px solid var(--c);background:var(--bg)}
.leaf.viewed{color:var(--mut)}.leaf.viewed:before{background:var(--c)}.leaf:hover{text-decoration:underline;color:#fff}
#nav{display:flex;gap:4px}#nav button{padding:4px 12px}#nav button.active{border-color:var(--acc);color:#fff;background:#1a2030}
#histview{padding:10px 16px 30px;max-width:920px}
#histview section.round{margin-bottom:18px;border-left:3px solid var(--line);padding-left:12px}
#histview section.round.fresh{border-left-color:var(--acc)}
#histview h2{font-size:14px;margin:0 0 8px;color:#fff;display:flex;align-items:baseline;gap:6px}
#histview h2 .ic{color:var(--acc)}
#histview h3{font-size:12px;margin:10px 0 4px;color:var(--mut);font-weight:600;letter-spacing:.02em}
.hentry{margin:6px 0 6px 4px;border-left:3px solid var(--c);padding-left:8px}
.hentry .hq{font-size:12.5px}.hentry .hq b{color:var(--c)}.hentry .hq .ic{color:var(--c);display:inline-block;width:1.2em}
ul.hres{list-style:none;margin:4px 0 2px;padding:0}
ul.hres li{padding:2px 0 2px 2px;cursor:pointer;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
ul.hres li:hover{color:#fff;text-decoration:underline}
ul.hres li.seen{color:var(--mut)}
ul.hres li .mark{display:inline-block;width:1.3em;color:var(--c)}
#side{padding:6px 14px 20px;color:var(--mut);font-size:12px}#side b{color:var(--fg)}
#log{white-space:pre-wrap;font-family:ui-monospace,Menlo,monospace;font-size:11px;max-height:140px;overflow:auto;border-top:1px solid var(--line);margin-top:8px;padding-top:6px}
</style></head><body>
<header>
<div class="row"><h1>__APP__ · <b id="seed">__SEED__</b></h1><span class="badge" id="round"></span><span class="badge" id="status"></span><span class="badge" id="eta"></span>
<span id="ctl" class="row" style="display:__CTL__"><button data-action="round" data-ui="btn_round">round maintenant</button><button id="pause" data-action="pause">pause</button>
<input id="newseed" placeholder="nouvelle graine…"></span>
<div id="nav" class="row"><button data-view="tree" data-action="view-tree">&#9652; <span data-ui="btn_tree">arbre</span></button><button data-view="history" data-action="view-history">&#9776; <span data-ui="btn_history">historique complet</span></button></div>
<button data-action="expand-all" data-ui="btn_expand">tout déplier</button><button data-action="collapse-all" data-ui="btn_collapse">tout replier</button><span class="hint" id="gen"></span></div>
<div class="row"><span class="hint" data-ui="lbl_history">historique :</span><button id="back" data-action="back" style="display:__CTL__">&#8592; <span data-ui="btn_back">retour</span></button><span id="crumbs"></span><button id="fwd" data-action="forward" style="display:__CTL__"><span data-ui="btn_fwd">avant</span> &#8594;</button>
<span class="hint">· <span data-ui="hint_actions">clic carte = déplier/replier · clic feuille = ouvrir + signaler consulté · Maj+clic = pivoter</span></span></div>
<div class="row" id="trrow" style="display:__CTL__"><span class="hint" data-ui="lbl_translate">traduction (LLM) :</span>
<select id="trlang">
<option value="" data-ui="opt_original">Original</option>
<option value="fr">FR · Français</option>
<option value="en">EN · English</option>
<option value="es">SP · Español</option>
<option value="it">IT · Italiano</option>
<option value="zh">CN · 中文</option>
<option value="ru">RU · Русский</option>
</select><span class="hint" id="trstatus"></span></div>
</header>
<div id="wrap"><div id="canvas"><svg id="edges" xmlns="http://www.w3.org/2000/svg"></svg><div id="nodes" role="tree" aria-label="résultats de recherche"></div></div></div>
<div id="histview" style="display:none"></div>
<div id="side"><div><b data-ui="lbl_lexical">champ lexical :</b> <span id="lex"></span></div><div><b data-ui="lbl_viewed">consultés :</b> <span id="viewed"></span></div><div id="log"></div></div>
<script nonce="__NONCE__">
const LIVE=__LIVE__;let STATE=__STATE__;let lastVersion=-1;const open_=new Map();let touchedGen="";
const ICON={round:"\u25A3",col1:"\u25B8",col2:"\u25B9",seen:"\u2713",unseen:"\u00B7",
 method:{seed:"\u25C6",definition:"?",practical:"\u2699",comparison:"\u21C4",recent:"\u21BB",technical:"\u00A7",
         lexical:"\u2248",cooccurrence:"\u2218",template:"\u25AA",ollama:"\u25CE",_:"\u2022"}};
const UI_FALLBACK={};
function U(k,params){let t=(STATE.ui&&STATE.ui[k])||UI_FALLBACK[k]||k;
  if(params)for(const p in params)t=t.split("{"+p+"}").join(params[p]);return t;}
function M(k){return (STATE.methods&&STATE.methods[k])||k;}
function applyUiLabels(){document.querySelectorAll("[data-ui]").forEach(el=>{const k=el.dataset.ui;
  if(!UI_FALLBACK[k])UI_FALLBACK[k]=el.textContent;el.textContent=U(k);});
  const ns=document.getElementById("newseed");if(ns)ns.placeholder=U("ph_newseed");}
function currentView(){return location.hash==="#history"?"history":"tree";}
function setView(v){location.hash=v==="history"?"#history":"#tree";draw(STATE);}
function domainOf(u){try{return new URL(u).hostname.replace(/^www\./,"");}catch(e){return u;}}
window.addEventListener("hashchange",()=>draw(STATE));
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const cut=(s,n)=>s.length>n?s.slice(0,n-1)+"…":s;
function api(path,body){if(!LIVE)return;fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})}).then(()=>poll(true)).catch(e=>console.error(e));}
function isOpen(st,t){const k=st.seed+"#"+t.id;if(open_.has(k))return open_.get(k);return t.round===st.round||t.results.some(r=>r.viewed);}
function toggleAll(v){for(const c of ["1","2"])for(const t of STATE.columns[c])open_.set(STATE.seed+"#"+t.id,v);draw(STATE);}
function leafClick(ev,url){ev.preventDefault();ev.stopPropagation();if(ev.shiftKey){api('/api/pivot',{url});return;}api('/api/viewed',{url});window.open(url,"_blank","noopener");}
document.getElementById("histview").addEventListener("click",ev=>{const l=ev.target.closest("li[data-url]");if(l)leafClick(ev,l.dataset.url);});
document.getElementById("nodes").addEventListener("click",ev=>{const l=ev.target.closest(".leaf");if(l){leafClick(ev,l.dataset.url);return;}
  const c=ev.target.closest(".card");if(c){const k=STATE.seed+"#"+c.dataset.id;open_.set(k,!isOpen(STATE,STATE.columns[c.dataset.col].find(t=>String(t.id)===c.dataset.id)));draw(STATE);}});
document.getElementById("crumbs").addEventListener("click",ev=>{const c=ev.target.closest(".crumb");if(c&&!c.classList.contains("cur"))api('/api/goto',{index:+c.dataset.i});});
function roundGroups(st){
  const all=[];for(const c of ["1","2"])for(const t of st.columns[c])all.push({...t,col:c});
  const byRound=new Map();for(const t of all){if(!byRound.has(t.round))byRound.set(t.round,[]);byRound.get(t.round).push(t);}
  return [...byRound.keys()].sort((a,b)=>b-a).map(r=>({round:r,time:(st.round_times||{})[r]||"",topics:byRound.get(r)}));
}
function renderHistory(st){
  const groups=roundGroups(st);
  if(!groups.length){document.getElementById("histview").innerHTML='<p class="hint">'+esc(U("no_rounds"))+'</p>';return;}
  let html="";
  for(const g of groups){
    const fresh=g.round===st.round?" fresh":"";
    const n=g.topics.reduce((a,t)=>a+t.results.length,0);
    html+=`<section class="round${fresh}"><h2><span class="ic">${ICON.round}</span> ${esc(U("lbl_round"))}: <b>${g.round}</b>${g.time?` &middot; ${esc(U("lbl_time"))}: <b>${g.time}</b>`:""} &middot; ${esc(U("lbl_results"))}: <b>${n}</b></h2>`;
    for(const colKey of ["1","2"]){
      const items=g.topics.filter(t=>t.col===colKey).sort((a,b)=>a.id-b.id);
      if(!items.length)continue;
      html+=`<h3>${colKey==="1"?ICON.col1:ICON.col2} ${esc(U("lbl_column"))} ${colKey} &middot; ${esc(U(colKey==="1"?"col_focus":"col_adjacent"))}</h3>`;
      for(const t of items){
        const ic=ICON.method[t.method]||ICON.method._;
        html+=`<div class="hentry" style="--c:${t.color}"><div class="hq"><span class="ic">${ic}</span> ${esc(U("lbl_method"))}: <b>${esc(M(t.method))}</b> &middot; ${esc(U("lbl_query"))}: "${esc(t.query)}" &middot; ${esc(U("lbl_results"))}: <b>${t.results.length}</b></div>`;
        if(t.results.length){
          html+='<ul class="hres">';
          for(const r of t.results)html+=`<li class="${r.viewed?"seen":""}" data-url="${esc(r.url)}" title="${esc(r.title)}&#10;${esc(r.url)}&#10;${esc(r.snippet)}"><span class="mark">${r.viewed?ICON.seen:ICON.unseen}</span>${esc(cut(r.title,84))} <span class="hint">&mdash; ${esc(domainOf(r.url))} [${esc(r.backend)}]</span></li>`;
          html+='</ul>';
        }
        html+='</div>';
      }
    }
    html+='</section>';
  }
  document.getElementById("histview").innerHTML=html;
}
const CW=250,CH=66,LH=22,GX=14,GY=26;
function layoutSide(topics,x0,width,y0,st){const per=Math.max(1,Math.floor((width+GX)/(CW+GX)));const ox=x0+(width-(per*CW+(per-1)*GX))/2;
  let y=y0,row=[],placed=[];const flush=()=>{if(!row.length)return;let h=CH;for(const p of row)h=Math.max(h,CH+(p.open?p.t.results.length*LH+8:0));y+=h+GY;row=[];};
  topics.forEach((t,i)=>{if(row.length===per)flush();const open=isOpen(st,t);const p={t,open,x:ox+row.length*(CW+GX),y};row.push(p);placed.push(p);});flush();
  return {placed,h:y-y0};}
function drawTree(st){
  const W=Math.max(1100,window.innerWidth-6),cx=W/2,half=(W-40)/2,seedY=14,groupY=70,topY=126;
  const L=layoutSide(st.columns["1"],20,half-10,topY,st),R=layoutSide(st.columns["2"],cx+10,half-10,topY,st);
  const H=topY+Math.max(L.h,R.h,60)+20;let nodes="",edges="";
  const gx1=cx-half/2,gx2=cx+half/2;
  const n1=st.columns["1"].reduce((a,t)=>a+t.results.length,0),n2=st.columns["2"].reduce((a,t)=>a+t.results.length,0);
  nodes+=`<div class="node seed" style="left:${cx}px;top:${seedY}px">${esc(st.seed)}</div>`;
  nodes+=`<div class="node group" style="left:${gx1}px;top:${groupY}px">${esc(U("lbl_column"))} 1 · ${esc(U("col_focus"))} · ${n1}</div><div class="node group" style="left:${gx2}px;top:${groupY}px">${esc(U("lbl_column"))} 2 · ${esc(U("col_adjacent"))} · ${n2}</div>`;
  const bez=(x0,y0,x1,y1,col,w)=>`<path d="M${x0},${y0} C${x0},${(y0+y1)/2} ${x1},${(y0+y1)/2} ${x1},${y1}" stroke="${col}" stroke-width="${w}" fill="none" stroke-opacity=".7"/>`;
  edges+=bez(cx,seedY+34,gx1,groupY,"#4c8dff",2)+bez(cx,seedY+34,gx2,groupY,"#4c8dff",2);
  const side=(lay,gx,col)=>{for(const p of lay.placed){const t=p.t,fresh=t.round===st.round?" fresh":"";
    edges+=bez(gx,groupY+28,p.x+CW/2,p.y,t.color,1.2).replace('stroke-opacity=".7"','stroke-opacity=".45"');
    nodes+=`<div class="node card${fresh}" data-id="${t.id}" data-col="${col}" style="--c:${t.color};left:${p.x}px;top:${p.y}px;width:${CW}px;height:${CH}px" title="${esc(U("lbl_round"))} ${t.round} · ${esc(M(t.method))}&#10;${esc(t.query)}" tabindex="0" role="treeitem" aria-expanded="${p.open}" aria-label="${esc(t.query)}">
      <div class="q">${esc(t.query)}</div><div class="m"><span>r${t.round} · ${esc(M(t.method))} ${p.open?"▾":"▸"}</span><span class="n">${t.results.length}</span></div></div>`;
    if(p.open)t.results.forEach((r,i)=>{nodes+=`<div class="leaf${r.viewed?" viewed":""}" data-url="${esc(r.url)}" style="--c:${t.color};left:${p.x+6}px;top:${p.y+CH+6+i*LH}px;width:${CW-10}px;height:${LH}px" title="${esc(r.title)}\n${esc(r.url)}\n${esc(r.snippet)}\n[${esc(r.backend)}]" tabindex="0" role="treeitem" aria-label="${esc(r.title)}">${esc(r.title)}</div>`;});}};
  side(L,gx1,"1");side(R,gx2,"2");
  const cv=document.getElementById("canvas");cv.style.width=W+"px";cv.style.height=H+"px";
  const sv=document.getElementById("edges");sv.setAttribute("width",W);sv.setAttribute("height",H);sv.innerHTML=edges;document.getElementById("nodes").innerHTML=nodes;
}
function draw(st){
  const view=currentView();
  applyUiLabels();
  document.getElementById("wrap").style.display=view==="tree"?"":"none";
  document.getElementById("histview").style.display=view==="history"?"":"none";
  document.querySelectorAll("#nav button").forEach(b=>b.classList.toggle("active",b.dataset.view===view));
  if(view==="tree")drawTree(st);else renderHistory(st);
  document.getElementById("seed").textContent=st.seed;document.getElementById("round").textContent="round "+st.round;
  document.getElementById("status").textContent=st.status;
  document.getElementById("eta").textContent=st.paused?U("paused"):(st.next_round_in?U("next_round",{s:st.next_round_in}):"");
  document.getElementById("pause").textContent=st.paused?U("btn_resume"):U("btn_pause");
  document.getElementById("crumbs").innerHTML=(st.history||[]).map((h,i)=>(i?'<span class="sep">›</span>':'')+`<span class="crumb${h.current?" cur":""}" data-i="${h.index}" title="${h.ts} · round ${h.round} · ${h.results} résultats">${esc(h.seed)} <span class="hint">(${h.results})</span></span>`).join("");
  const hl=(st.history||[]).length;document.getElementById("back").disabled=!(st.cursor>0);document.getElementById("fwd").disabled=!(st.cursor<hl-1);
  document.getElementById("lex").textContent=st.lexical.join(", ");document.getElementById("viewed").textContent=st.viewed_titles.join(" · ")||U("none");
  document.getElementById("log").textContent=st.log.join("\n");document.getElementById("gen").textContent=(LIVE?U("live"):U("static"))+" · "+st.generated;
  const trsel=document.getElementById("trlang");if(trsel&&document.activeElement!==trsel)trsel.value=st.translate_lang||"";
  if(trsel)trsel.disabled=!!st.translate_status;
  document.getElementById("trstatus").textContent=st.translate_status||(st.translate_lang?U("tr_done",{lang:st.languages[st.translate_lang]||st.translate_lang}):"");
}
let lastEtag="";let errBanner=null;function getOrCreateBanner(){if(!errBanner){errBanner=document.createElement("div");errBanner.id="errbanner";errBanner.style.cssText="display:none;position:fixed;top:0;left:0;right:0;background:#c0392b;color:#fff;padding:6px 12px;font-size:13px;z-index:9999;text-align:center;";document.body.prepend(errBanner);}return errBanner;}function showError(msg){const b=getOrCreateBanner();b.textContent=msg;b.style.display="block";}function clearError(){if(errBanner)errBanner.style.display="none";}async function poll(force){if(!LIVE)return;try{const hdrs={"Cache-Control":"no-cache"};if(lastEtag&&!force)hdrs["If-None-Match"]=lastEtag;const r=await fetch("/state.json",{headers:hdrs});if(r.status===304){clearError();return;}if(!r.ok){showError(U("unreachable")+" (HTTP "+r.status+")");return;}const et=r.headers.get("ETag")||"";const st=await r.json();if(force||st.version!==lastVersion||st.next_round_in!==STATE.next_round_in){lastVersion=st.version;STATE=st;lastEtag=et;draw(st);}clearError();}catch(e){showError(U("unreachable"));}}
document.addEventListener("click",ev=>{const b=ev.target.closest("[data-action]");if(!b)return;const a=b.dataset.action;if(a==="round")api('/api/round');else if(a==="pause")api('/api/pause');else if(a==="back")api('/api/back');else if(a==="forward")api('/api/forward');else if(a==="expand-all")toggleAll(true);else if(a==="collapse-all")toggleAll(false);else if(a==="view-tree")setView('tree');else if(a==="view-history")setView('history');});
document.getElementById("newseed").addEventListener("keydown",ev=>{if(ev.key==="Enter"){api('/api/seed',{seed:ev.target.value});ev.target.value="";}});
document.getElementById("trlang").addEventListener("change",ev=>{api('/api/translate',{lang:ev.target.value});});
document.getElementById("nodes").addEventListener("keydown",ev=>{const el=ev.target;const isCard=el.classList.contains("card");const isLeaf=el.classList.contains("leaf");if(!isCard&&!isLeaf)return;if(ev.key==="Enter"||ev.key===" "){ev.preventDefault();if(isLeaf)leafClick(ev,el.dataset.url);else el.click();}else if(ev.key==="ArrowDown"||ev.key==="ArrowUp"){ev.preventDefault();const items=Array.from(document.querySelectorAll("#nodes [tabindex='0']"));const idx=items.indexOf(el);const next=items[ev.key==="ArrowDown"?idx+1:idx-1];if(next)next.focus();}else if((ev.key==="ArrowRight"||ev.key==="ArrowLeft")&&isCard){ev.preventDefault();const col=el.dataset.col;const tid=el.dataset.id;if(col&&tid){const t=STATE.columns[col].find(x=>String(x.id)===tid);if(t){const want=ev.key==="ArrowRight";if(isOpen(STATE,t)!==want){open_.set(STATE.seed+"#"+tid,want);draw(STATE);}}}}});
draw(STATE);if(LIVE){poll(true);setInterval(poll,2000);}window.addEventListener("resize",()=>draw(STATE));
</script></body></html>"""


_TEMPLATE_TOKEN_RE = re.compile(r"__(LANG|APP|VERSION|SEED|STATE|LIVE|CTL|NONCE)__")


def render_html(state: dict, live: bool, nonce: str = "static") -> str:
    """Substitution en une seule passe : une graine contenant « __STATE__ » ou un autre
    marqueur ne peut pas déclencher une seconde substitution."""
    lang = state.get("html_lang") or UI_SOURCE_LANG
    if lang not in LANGUAGES:
        lang = UI_SOURCE_LANG
    values = {
        "LANG": lang,
        "APP": htmlmod.escape(APP_NAME),
        "VERSION": htmlmod.escape(__version__),
        "SEED": htmlmod.escape(state["seed"]),
        "STATE": json.dumps(state, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--"),
        "LIVE": "true" if live else "false",
        "CTL": "flex" if live else "none",
        "NONCE": nonce,
    }
    return _TEMPLATE_TOKEN_RE.sub(lambda m: values[m.group(1)], HTML_TEMPLATE)


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def detect_ssh() -> Optional[dict]:
    """Lit SSH_CONNECTION ("client_ip client_port server_ip server_port"), posé par sshd
    dans l'environnement de la session. Absent -> pas dans une session SSH (ou sshd trop
    ancien / variable effacée par un sudo/su intermédiaire)."""
    raw = os.environ.get("SSH_CONNECTION", "")
    parts = raw.split()
    if len(parts) != 4:
        return None
    client_ip, client_port, server_ip, server_port = parts
    try:
        return {"client_ip": client_ip, "client_port": int(client_port),
                "server_ip": server_ip, "server_port": int(server_port)}
    except ValueError:
        return None


def ssh_tunnel_hint(ssh: dict, port: int) -> str:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "<user>"
    return (
        f"Accès depuis la machine locale (tunnel SSH, port {port}) :\n"
        f"  ssh -L {port}:127.0.0.1:{port} -p {ssh['server_port']} {user}@{ssh['server_ip']}\n"
        f"  puis ouvrir http://127.0.0.1:{port}/ sur la machine locale.\n"
        f"  IP/port serveur détectés via SSH_CONNECTION (peuvent différer de l'hôte tapé "
        f"pour se connecter si NAT/rebond) ; adapter user@host si besoin.\n"
        f"  Session déjà ouverte sans -L ? Rouvrir avec -L, ou si un ControlMaster tourne : "
        f"ssh -O forward -L {port}:127.0.0.1:{port} <alias-de-connexion>."
    )


def attach_ssh_hint(session: Session, port: int, host: str, suppress: bool = False) -> Optional[str]:
    """Détecte une session SSH et journalise le tunnel à ouvrir depuis la machine locale.
    Ne fait rien si --web-host n'est pas en boucle locale (déjà accessible sans tunnel) ou
    si suppress est vrai (--no-web-ssh-hint). Retourne le texte du hint, ou None."""
    if suppress:
        return None
    ssh = detect_ssh()
    if ssh is None:
        return None
    if host not in LOOPBACK_HOSTS:
        session.note(f"web sur {host} (SSH détecté mais hôte non local -> "
                     f"pas de tunnel nécessaire si le pare-feu autorise le port {port})")
        return None
    hint = ssh_tunnel_hint(ssh, port)
    session.ssh_hint = hint
    for line in hint.splitlines():
        session.note(line)
    return hint


def _run_translation(session: Session, lang: str) -> None:
    """Exécuté en thread de fond par /api/translate : traduit tout le contenu affichable
    actuel vers `lang`, puis active l'affichage traduit. Un échec (Ollama injoignable, sortie
    invalide) est journalisé et n'active pas la langue — le texte original reste affiché."""
    lang_name = LANGUAGES.get(lang, lang)
    with session.lock:
        session.translate_status = UI_STRINGS["tr_running"].format(lang=lang_name)
        session.version += 1
    texts = session.collect_translatable_texts()
    session.note(f"traduction -> {lang_name} demandée ({len(texts)} textes)")
    try:
        session.translate_batch(lang, texts)
    except BackendError as exc:
        with session.lock:
            session.translate_status = ""
            if builtin_translation_cache(lang):
                session.translate_lang = lang  # libellés intégrés toujours utilisables
            session.version += 1
        session.note(f"traduction échouée: {exc}")
        return
    with session.lock:
        session.translate_lang = lang
        session.translate_status = ""
        session.version += 1
    session.note(f"traduction -> {lang_name} terminée")


_CSP_TEMPLATE = (
    "default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
    "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
CONTENT_SECURITY_POLICY = _CSP_TEMPLATE.format(nonce="static")  # fallback sans nonce


def _host_for_url(host: str) -> str:
    return f"[{host}]" if ":" in host else host


def allowed_host_headers(port: int) -> set[str]:
    """Valeurs d'en-tête Host acceptées : boucle locale + port exact (anti DNS rebinding)."""
    return {f"{h}:{port}" for h in ("127.0.0.1", "localhost", "[::1]")}


class _LocalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _LocalHTTPServerV6(_LocalHTTPServer):
    address_family = socket.AF_INET6


class WebServer:
    """Serveur HTTP local (thread daemon). GET / (tree graph), GET /state.json ;
    POST /api/* (JSON). Boucle locale uniquement ; en-tête Host vérifié (DNS rebinding),
    POST exigeant Content-Type JSON et Origin locale (CSRF)."""

    def __init__(self, session: Session, host: str, port: int):
        if host not in LOOPBACK_HOSTS:
            raise ValueError(f"hôte web non local refusé: {host}")
        self.session = session
        outer = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "websearch/1"

            def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
                log.debug("web %s", fmt % args)

            def _send(self, code: int, body: bytes, ctype: str,
                      etag: Optional[str] = None, csp: Optional[str] = None) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                cache = "no-store" if etag is None else "no-cache"
                self.send_header("Cache-Control", cache)
                if etag:
                    self.send_header("ETag", etag)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", csp or CONTENT_SECURITY_POLICY)
                self.send_header("Cross-Origin-Opener-Policy", "same-origin")
                self.send_header("Cross-Origin-Resource-Policy", "same-origin")
                self.end_headers()
                self.wfile.write(body)

            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").strip().lower()
                if host in outer.allowed_hosts:
                    return True
                log.warning("requête web refusée: Host %r non autorisé", host)
                self._send(403, b'{"error":"host"}', "application/json")
                return False

            def _origin_ok(self) -> bool:
                origin = (self.headers.get("Origin") or "").strip().lower()
                if not origin:
                    return True  # clients non navigateur (curl, tests) : pas d'Origin
                if origin in outer.allowed_origins:
                    return True
                log.warning("requête web refusée: Origin %r non autorisée", origin)
                self._send(403, b'{"error":"origin"}', "application/json")
                return False

            def do_GET(self) -> None:  # noqa: N802
                if not self._host_ok():
                    return
                path = urllib.parse.urlsplit(self.path).path
                if path == "/":
                    nonce = os.urandom(16).hex()
                    csp = _CSP_TEMPLATE.format(nonce=nonce)
                    self._send(200, render_html(outer.session.snapshot(), live=True, nonce=nonce).encode("utf-8"), "text/html; charset=utf-8", csp=csp)
                elif path == "/state.json":
                    body = json.dumps(outer.session.snapshot(), ensure_ascii=False).encode("utf-8")
                    etag = f'"{outer.session.version}"'
                    if self.headers.get("If-None-Match") == etag:
                        self.send_response(304)
                        self.send_header("ETag", etag)
                        self.send_header("Cache-Control", "no-cache")
                        self.end_headers()
                    else:
                        self._send(200, body, "application/json; charset=utf-8", etag=etag)
                else:
                    self._send(404, b"not found", "text/plain")

            def do_POST(self) -> None:  # noqa: N802
                if not self._host_ok() or not self._origin_ok():
                    return
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if ctype != "application/json":
                    # un formulaire / text/plain inter-sites ne déclenche pas de preflight CORS :
                    # exiger JSON force le preflight, que ce serveur ne satisfait jamais
                    self._send(415, b'{"error":"content-type must be application/json"}', "application/json")
                    return
                path = urllib.parse.urlsplit(self.path).path
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n < 0:
                        self._send(400, b'{"error":"content-length"}', "application/json")
                        return
                    if n > MAX_POST_BODY_BYTES:
                        self._send(413, b'{"error":"body too large"}', "application/json")
                        return
                    body = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
                    if not isinstance(body, dict):
                        self._send(400, b'{"error":"json object required"}', "application/json")
                        return
                except (ValueError, UnicodeDecodeError):
                    self._send(400, b'{"error":"json"}', "application/json")
                    return
                sess = outer.session
                if path == "/api/viewed":
                    r = sess.find_result(str(body.get("url", "")))
                    if r is None:
                        self._send(404, b'{"error":"unknown url"}', "application/json")
                        return
                    sess.mark_viewed(r)
                elif path == "/api/pivot":
                    r = sess.find_result(str(body.get("url", "")))
                    if r is None:
                        self._send(404, b'{"error":"unknown url"}', "application/json")
                        return
                    sess.mark_viewed(r)
                    seed = pivot_seed(r)
                    sess.note(f"pivot (web) -> « {seed} »")
                    sess.reset(seed)
                elif path == "/api/round":
                    sess.force_round()
                elif path == "/api/back":
                    sess.back()
                elif path == "/api/forward":
                    sess.forward()
                elif path == "/api/goto":
                    try:
                        idx = int(body.get("index"))
                    except (TypeError, ValueError):
                        self._send(400, b'{"error":"index"}', "application/json")
                        return
                    if not sess.goto(idx):
                        self._send(404, b'{"error":"index"}', "application/json")
                        return
                elif path == "/api/pause":
                    sess.note("pause (web)" if sess.toggle_pause() else "reprise (web)")
                elif path == "/api/seed":
                    seed = re.sub(r"\s+", " ", str(body.get("seed", ""))).strip()[:MAX_SEED_LENGTH]
                    if not seed:
                        self._send(400, b'{"error":"empty seed"}', "application/json")
                        return
                    sess.note(f"nouvelle graine (web): « {seed} »")
                    sess.reset(seed)
                    if sess.paused:
                        sess.toggle_pause()
                elif path == "/api/translate":
                    lang = str(body.get("lang", "")).strip().lower()
                    if not lang:
                        with sess.lock:
                            sess.translate_lang = ""
                            sess.translate_status = ""
                            sess.version += 1
                        sess.note("traduction désactivée (texte original)")
                    elif lang not in LANGUAGES:
                        self._send(400, b'{"error":"lang"}', "application/json")
                        return
                    else:
                        with sess.lock:
                            busy = bool(sess.translate_status)
                        if busy:
                            self._send(409, b'{"error":"translation already running"}', "application/json")
                            return
                        sess.set_language(lang)
                else:
                    self._send(404, b'{"error":"route"}', "application/json")
                    return
                self._send(200, b'{"ok":true}', "application/json")

        server_cls = _LocalHTTPServerV6 if ":" in host else _LocalHTTPServer
        self.httpd = server_cls((host, port), Handler)
        self.port = self.httpd.server_address[1]
        self.url = f"http://{_host_for_url(host)}:{self.port}/"
        self.allowed_hosts = allowed_host_headers(self.port)
        self.allowed_origins = {f"http://{h}" for h in self.allowed_hosts}
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="web", daemon=True)

    def start(self) -> "WebServer":
        self.thread.start()
        log.debug("serveur web démarré: %s", self.url)  # visibilité utilisateur via attach_web -> session.note()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


# --------------------------------------------------------------------------
# Terminal : couleurs, clavier, ouverture d'URL
# --------------------------------------------------------------------------

def enable_vt_windows() -> None:
    if sys.platform.startswith("win"):
        os.system("")  # commande vide constante : active le VT100 sous Windows  # nosec B605 B607


class Style:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def c(self, text: str, *codes: int) -> str:
        if not self.enabled or not codes:
            return text
        return "\x1b[" + ";".join(str(c) for c in codes) + "m" + text + "\x1b[0m"

    def bold(self, text: str) -> str:
        return self.c(text, 1)

    def dim(self, text: str) -> str:
        return self.c(text, 2)

    def inv(self, text: str) -> str:
        return self.c(text, 7)


def open_url(url: str) -> tuple[bool, str]:
    if not safe_http_url(url):
        return False, "URL refusée : seuls http:// et https:// sont autorisés"
    if os.environ.get("TERMUX_VERSION"):
        cmd = ["termux-open-url", url]
    elif sys.platform.startswith("darwin"):
        cmd = ["open", url]
    elif sys.platform.startswith("win"):
        try:
            os.startfile(url)  # type: ignore[attr-defined]  # URL validée http(s)  # nosec B606
            return True, "ouvert (os.startfile)"
        except OSError as exc:
            return False, f"échec os.startfile: {exc}"
    else:
        cmd = ["xdg-open", url]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,  # nosec B603
                       timeout=10)  # liste d'arguments fixe, URL validée http(s), aucun shell
        return True, f"ouvert ({cmd[0]})"
    except FileNotFoundError:
        return False, f"commande introuvable: {cmd[0]}"
    except subprocess.CalledProcessError as exc:
        return False, f"{cmd[0]} a échoué (code {exc.returncode})"
    except subprocess.TimeoutExpired:
        return False, f"{cmd[0]} timeout"


class Key:
    UP, DOWN, LEFT, RIGHT, TAB, ENTER, QUIT, DIGIT, BACKSPACE, CHAR, NONE = (
        "UP", "DOWN", "LEFT", "RIGHT", "TAB", "ENTER", "QUIT", "DIGIT", "BACKSPACE", "CHAR", "NONE")


class RawTerminal:
    """cbreak (POSIX) le temps d'un écran interactif ; no-op sous Windows."""

    def __enter__(self) -> "RawTerminal":
        self._saved = None
        if not sys.platform.startswith("win"):
            import termios
            import tty
            self._fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._saved is not None:
            import termios
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)


def _classify(ch: str) -> tuple[str, str]:
    if ch in ("\r", "\n"):
        return Key.ENTER, ""
    if ch == "\t":
        return Key.TAB, ""
    if ch in ("q", "Q"):
        return Key.QUIT, ""
    if ch in ("\x7f", "\x08"):
        return Key.BACKSPACE, ""
    if ch.isdigit():
        return Key.DIGIT, ch
    if ch == "\x03":
        raise KeyboardInterrupt
    return Key.CHAR, ch.lower()


def read_key(timeout: float) -> tuple[str, str]:
    """Lecture non bloquante (timeout en s). Suppose RawTerminal actif sous POSIX."""
    if sys.platform.startswith("win"):
        import msvcrt
        deadline = time.time() + timeout
        while not msvcrt.kbhit():
            if time.time() >= deadline:
                return Key.NONE, ""
            time.sleep(0.02)
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            return {"H": Key.UP, "P": Key.DOWN, "K": Key.LEFT, "M": Key.RIGHT}.get(ch2, Key.NONE), ""
        return _classify(ch)
    import select
    r, _, _ = select.select([sys.stdin], [], [], timeout)
    if not r:
        return Key.NONE, ""
    ch = sys.stdin.read(1)
    if ch == "\x1b":
        r, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not r:
            return Key.NONE, ""
        seq = sys.stdin.read(1)
        if seq in ("[", "O"):
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if not r:
                return Key.NONE, ""
            code = sys.stdin.read(1)
            return {"A": Key.UP, "B": Key.DOWN, "C": Key.RIGHT, "D": Key.LEFT}.get(code, Key.NONE), ""
        return Key.NONE, ""
    return _classify(ch)


def interactive_available() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


# --------------------------------------------------------------------------
# Rendu deux colonnes
# --------------------------------------------------------------------------

def fit(text: str, width: int) -> str:
    text = text.replace("\n", " ")
    if width <= 0:
        return ""
    if len(text) <= width:
        return text.ljust(width)
    return (text[: max(width - 1, 0)] + "…") if width > 1 else text[:1]


@dataclass
class ColumnView:
    column: int
    items: list[tuple[str, object]]           # ("topic", Topic) | ("result", Result)
    result_indices: list[int]                 # index dans items des résultats


def build_column(session: Session, column: int) -> ColumnView:
    items: list[tuple[str, object]] = []
    ridx: list[int] = []
    with session.lock:
        for t in session.column_topics(column):
            items.append(("topic", t))
            for r in session.results.get(t.id, []):
                ridx.append(len(items))
                items.append(("result", r))
    return ColumnView(column, items, ridx)


def render_column(view: ColumnView, width: int, height: int, sel: int, focused: bool,
                  session: Session, st: Style, title: str) -> list[str]:
    lines: list[str] = []
    head = fit(title, width)
    lines.append(st.bold(st.inv(head)) if focused else st.bold(head))
    body_h = max(height - 1, 1)
    if not view.items:
        lines.append(fit(st.dim("(en attente de résultats…)"), width))
        return lines + [" " * width] * (body_h - 1)

    # chaque résultat occupe 2 lignes (titre + url) ; topic 1 ligne
    heights = [1 if kind == "topic" else 2 for kind, _ in view.items]
    sel_item = view.result_indices[sel] if view.result_indices and 0 <= sel < len(view.result_indices) else 0
    # scroll : garantir sel_item visible
    start = 0
    while start < sel_item and sum(heights[start:sel_item + 1]) > body_h:
        start += 1
    used_h = 0
    n_result = 0
    for i, (kind, obj) in enumerate(view.items):
        if i < start:
            if kind == "result":
                n_result += 1
            continue
        if used_h + heights[i] > body_h:
            break
        if kind == "topic":
            t = obj  # type: ignore[assignment]
            tag = f"■ r{t.round} {t.method}: {t.query}"
            lines.append(st.c(fit(tag, width), t.color, 1))
            used_h += 1
        else:
            r = obj  # type: ignore[assignment]
            topic = session.topics.get(r.topic_id)
            color = topic.color if topic else 37
            is_sel = focused and i == sel_item
            n_result += 1
            mark = ">" if is_sel else " "
            seen = "•" if r.url in session.viewed_urls else " "
            t_line = fit(f"{mark}{seen}{n_result:>2}. {r.title}", width)
            u_line = fit(f"      {r.url}", width)
            if is_sel:
                lines.append(st.inv(t_line))
                lines.append(st.c(u_line, color))
            else:
                lines.append(st.c(t_line, color))
                lines.append(st.dim(u_line))
            used_h += 2
    while len(lines) < height:
        lines.append(" " * width)
    return lines[:height]


def render_screen(session: Session, sel: list[int], focus: int, st: Style, digit_buffer: str,
                  show_log: bool) -> str:
    cols, rows = shutil.get_terminal_size((100, 30))
    cols = max(cols, 40)
    rows = max(rows, 12)
    v1, v2 = build_column(session, 1), build_column(session, 2)
    with session.lock:
        status, seed, paused, rn = session.status, session.seed, session.paused, session.round_no
        nxt = session.next_round_at
        logs = list(session.log[-(rows - 4):])
    eta = max(0, int(nxt - time.time())) if nxt else 0
    state = "PAUSE" if paused else f"prochain round dans {eta}s"
    web = f"  |  web {session.web_url}" if session.web_url else ""
    ssh_badge = "  |  ssh: tunnel -> voir log (l)" if session.ssh_hint else ""
    with session.lock:
        hist = f"  |  hist {session.cursor + 1}/{len(session.timeline)}" if len(session.timeline) > 1 else ""
    header = fit(f" websearch  graine: {seed}  |  round {rn}  |  {state}{hist}{web}{ssh_badge}", cols)
    footer = fit((f" saisie:{digit_buffer} |" if digit_buffer else "") +
                 " ↑↓ sél  ←→/Tab col  Entrée détail  o ouvrir  f pivot  b/n hist  r round  p pause  l log" + ("  w web" if session.web_url else "") + "  q retour", cols)
    status_line = fit(" " + status, cols)
    clear = "\x1b[H\x1b[2J" if st.enabled else ""
    out: list[str] = [clear + st.bold(header)]

    if show_log:
        out.append(st.dim(fit(" journal", cols)))
        for ln in logs:
            out.append(fit("  " + ln, cols))
        while len(out) < rows - 1:
            out.append(" " * cols)
        out.append(st.dim(status_line))
        return "\n".join(out[:rows]).rstrip("\n")

    body_h = rows - 3
    t1 = f"COL 1 · focus ({len(v1.result_indices)})"
    t2 = f"COL 2 · adjacent ({len(v2.result_indices)})"
    if cols >= 90:
        w1 = cols // 2
        w2 = cols - w1 - 1
        l1 = render_column(v1, w1, body_h, sel[0], focus == 0, session, st, t1)
        l2 = render_column(v2, w2, body_h, sel[1], focus == 1, session, st, t2)
        sep = st.dim("│")
        for a, b in zip(l1, l2, strict=False):
            out.append(f"{a}{sep}{b}")
    else:
        h1 = body_h // 2
        h2 = body_h - h1
        out.extend(render_column(v1, cols, h1, sel[0], focus == 0, session, st, t1))
        out.extend(render_column(v2, cols, h2, sel[1], focus == 1, session, st, t2))
    out.append(st.dim(status_line))
    out.append(st.dim(footer))
    return "\n".join(out[:rows + 1])


def render_detail(r: Result, session: Session, st: Style, msg: str = "") -> str:
    cols, _ = shutil.get_terminal_size((100, 30))
    topic = session.topics.get(r.topic_id)
    clear = "\x1b[H\x1b[2J" if st.enabled else ""
    lines = [clear + st.bold(fit(r.title, cols))]
    lines.append(st.dim("-" * min(len(r.title), cols)))
    lines.append(r.url)
    lines.append("")
    if r.snippet:
        # wrap simple
        words = r.snippet.split()
        cur = ""
        for w in words:
            if len(cur) + len(w) + 1 > cols - 2:
                lines.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        if cur:
            lines.append(cur)
        lines.append("")
    if topic:
        lines.append(st.c(f"topic: {topic.query}  (col {topic.column}, round {topic.round}, {topic.method})", topic.color))
    lines.append(st.dim(f"backend: {r.backend}   rang: {r.rank}   {time.strftime('%H:%M:%S', time.localtime(r.ts))}"))
    lines.append("")
    if msg:
        lines.append(msg)
    lines.append(st.dim("[o] ouvrir   [f] pivoter la graine sur ce résultat   [q] retour"))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Boucles interactives
# --------------------------------------------------------------------------

def detail_loop(r: Result, session: Session, st: Style) -> Optional[str]:
    """Retourne une nouvelle graine si pivot demandé, sinon None."""
    session.mark_viewed(r)
    msg = ""
    while True:
        sys.stdout.write(render_detail(r, session, st, msg))
        sys.stdout.flush()
        key, val = read_key(1.0)
        if key == Key.QUIT:
            return None
        if key == Key.CHAR and val == "o":
            ok, m = open_url(r.url)
            msg = st.c(f"-> {m}", 32 if ok else 31)
        elif key == Key.CHAR and val == "f":
            return pivot_seed(r)


def pivot_seed(r: Result) -> str:
    toks = tokenize(r.title)
    return " ".join(toks[:5]) if toks else r.title[:60]


def picker_loop_interactive(session: Session, st: Style) -> str:
    """Retourne 'new' (nouvelle requête au prompt) ou 'quit'."""
    sel = [0, 0]
    focus = 0
    digit_buffer = ""
    show_log = False
    last_version = -1
    last_draw = 0.0
    with RawTerminal():
        while True:
            with session.lock:
                version = session.version
            now = time.time()
            if version != last_version or now - last_draw >= 1.0:
                v1, v2 = build_column(session, 1), build_column(session, 2)
                for c, v in ((0, v1), (1, v2)):
                    sel[c] = min(sel[c], max(len(v.result_indices) - 1, 0))
                sys.stdout.write(render_screen(session, sel, focus, st, digit_buffer, show_log))
                sys.stdout.flush()
                last_version, last_draw = version, now
            key, val = read_key(0.5)
            if key == Key.NONE:
                continue
            last_version = -1  # force redraw après toute touche
            view = build_column(session, focus + 1)
            n = len(view.result_indices)
            if key == Key.QUIT:
                return "new"
            if key == Key.TAB or key == Key.RIGHT or key == Key.LEFT:
                focus = 1 - focus
                digit_buffer = ""
            elif key == Key.UP and n:
                sel[focus] = (sel[focus] - 1) % n
                digit_buffer = ""
            elif key == Key.DOWN and n:
                sel[focus] = (sel[focus] + 1) % n
                digit_buffer = ""
            elif key == Key.DIGIT:
                digit_buffer += val
                idx = int(digit_buffer) - 1
                if 0 <= idx < n:
                    sel[focus] = idx
                if len(digit_buffer) >= len(str(max(n, 1))):
                    digit_buffer = ""
            elif key == Key.BACKSPACE:
                digit_buffer = digit_buffer[:-1]
            elif key == Key.ENTER and n:
                r = view.items[view.result_indices[sel[focus]]][1]
                new_seed = detail_loop(r, session, st)  # type: ignore[arg-type]
                if new_seed:
                    session.note(f"pivot -> « {new_seed} »")
                    session.reset(new_seed)
                    sel = [0, 0]
                digit_buffer = ""
            elif key == Key.CHAR:
                if val == "o" and n:
                    r = view.items[view.result_indices[sel[focus]]][1]
                    session.mark_viewed(r)  # type: ignore[arg-type]
                    ok, m = open_url(r.url)  # type: ignore[attr-defined]
                    session.note(m)
                elif val == "f" and n:
                    r = view.items[view.result_indices[sel[focus]]][1]
                    new_seed = pivot_seed(r)  # type: ignore[arg-type]
                    session.mark_viewed(r)  # type: ignore[arg-type]
                    session.note(f"pivot -> « {new_seed} »")
                    session.reset(new_seed)
                    sel = [0, 0]
                elif val == "r":
                    session.force_round()
                elif val == "p":
                    session.note("pause" if session.toggle_pause() else "reprise")
                elif val == "l":
                    show_log = not show_log
                elif val == "b":
                    if session.back():
                        sel = [0, 0]
                elif val == "n":
                    if session.forward():
                        sel = [0, 0]
                elif val == "w" and session.web_url:
                    ok, m = open_url(session.web_url)
                    session.note(m)


def run_noninteractive(session: Session, cfg: Config, as_json: bool) -> None:
    """Pipe/redirection : exécute `rounds` rounds (défaut 1) et imprime les deux colonnes."""
    rounds = cfg.rounds or 1
    for _ in range(rounds):
        session.run_round()
    if as_json:
        payload = {
            "seed": session.seed,
            "rounds": session.round_no,
            "columns": {
                str(c): [
                    {"query": t.query, "method": t.method, "round": t.round,
                     "results": [{"title": r.title, "url": r.url, "snippet": r.snippet, "backend": r.backend}
                                 for r in session.results.get(t.id, [])]}
                    for t in session.column_topics(c)
                ] for c in (1, 2)
            },
            "lexical_field": session.stats.top_terms(20),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for c, title in ((1, "COLONNE 1 · focus"), (2, "COLONNE 2 · adjacent")):
        print(f"\n===== {title} =====")
        for t in session.column_topics(c):
            print(f"\n[r{t.round} {t.method}] {t.query}")
            for i, r in enumerate(session.results.get(t.id, []), 1):
                print(f"  {i:>2}. {r.title}")
                print(f"      {r.url}")
                if r.snippet:
                    print(f"      {r.snippet[:160]}")
    print(f"\nchamp lexical: {', '.join(session.stats.top_terms(15))}")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

MODE_WEB, MODE_TUI, MODE_HTML, MODE_JSON, MODE_TEXT = "web", "tui", "html", "json", "text"


def normalize_ollama_host(raw: str) -> Optional[str]:
    """OLLAMA_HOST accepte « host:port » (convention Ollama) ou une URL http(s) complète."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "http://" + raw
    url = safe_http_url(raw)
    return url.rstrip("/") if url else None


def parse_args(argv: Optional[list[str]] = None) -> tuple[Config, argparse.Namespace]:
    p = argparse.ArgumentParser(
        prog="websearch.py",
        description=f"{APP_NAME} — recherche web par pivots successifs, vue HTML par défaut (sans clé API).",
        epilog="Modes : vue web HTML live (défaut en terminal), --tui (interface terminal), "
               "snapshot HTML (défaut hors terminal), --json, --text.",
    )
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    p.add_argument("-q", "--query", help="graine initiale (sinon prompt interactif)")
    p.add_argument("-n", "--limit", type=int, default=DEFAULT_LIMIT_PER_QUERY, help="résultats max par requête")
    p.add_argument("--interval", type=float, default=DEFAULT_ROUND_INTERVAL, help="secondes entre rounds")
    p.add_argument("--delay", type=float, default=DEFAULT_REQUEST_DELAY, help="secondes entre requêtes HTTP")
    p.add_argument("--rounds", type=int, default=0,
                   help="nombre de rounds (0 = illimité en vue web/TUI ; snapshot/JSON/texte : défaut 1)")
    p.add_argument("--lang", choices=sorted(LANGUAGES), default="",
                   help="langue de recherche et d'affichage (fr, en intégrées ; autres via Ollama)")
    p.add_argument("--no-ollama", action="store_true", help="expansion heuristique seule")
    p.add_argument("--ollama-model", default=None, help="modèle Ollama (défaut: $OLLAMA_MODEL ou premier listé)")
    p.add_argument("--no-color", action="store_true")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--tui", action="store_true", help="interface terminal deux colonnes au lieu de la vue HTML")
    mode.add_argument("--json", action="store_true", help="sortie JSON sur stdout puis fin")
    mode.add_argument("--text", action="store_true", help="sortie texte brut sur stdout puis fin")
    p.add_argument("--log-file", default=os.environ.get("WEBSEARCH_LOG"), help="fichier de log (défaut: $WEBSEARCH_LOG)")
    p.add_argument("--web", type=int, nargs="?", const=DEFAULT_WEB_PORT, default=None, metavar="PORT",
                   help=f"port de la vue web (défaut {DEFAULT_WEB_PORT}, repli automatique si occupé) ; avec --tui : "
                        "sert aussi la vue web")
    p.add_argument("--web-host", default="127.0.0.1", help="interface d'écoute du serveur web (boucle locale uniquement)")
    p.add_argument("--web-only", action="store_true", help=argparse.SUPPRESS)  # compat v1.0 : vue web = défaut
    p.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur automatiquement")
    p.add_argument("--html-out", default=None, metavar="PATH",
                   help="chemin du snapshot HTML (réécrit après chaque round)")
    p.add_argument("--no-web-ssh-hint", action="store_true",
                   help="ne pas détecter/afficher les instructions de tunnel SSH au démarrage du serveur web")
    p.add_argument("--debug", action="store_true")
    a = p.parse_args(argv)
    if a.limit < 1 or a.delay < 0 or a.interval < 1 or a.rounds < 0:
        p.error("--limit >= 1, --delay >= 0, --interval >= 1, --rounds >= 0")
    if a.web_only and (a.tui or a.json or a.text):
        p.error("--web-only est incompatible avec --tui/--json/--text")
    cfg = Config(limit=a.limit, round_interval=a.interval, request_delay=a.delay, rounds=a.rounds,
                 use_ollama=not a.no_ollama, color=not a.no_color and os.environ.get("NO_COLOR") is None,
                 debug=a.debug, lang=a.lang)
    host = normalize_ollama_host(cfg.ollama_host)
    if host is None:
        p.error(f"OLLAMA_HOST invalide ({cfg.ollama_host!r}) : http(s)://hôte:port attendu")
    cfg.ollama_host = host
    if a.ollama_model:
        cfg.ollama_model = a.ollama_model
    if a.web_host not in LOOPBACK_HOSTS:
        p.error("--web-host doit rester local (127.0.0.1, localhost ou ::1); utilisez un tunnel SSH")
    port = DEFAULT_WEB_PORT if a.web is None else a.web
    if not (0 <= port <= 65535):
        p.error("--web PORT hors plage")
    cfg.web_port, cfg.web_host = port, a.web_host
    if a.html_out:
        cfg.html_out = os.path.abspath(os.path.expanduser(a.html_out))
    return cfg, a


def choose_mode(args: argparse.Namespace, interactive: bool) -> str:
    """Mode d'exécution : option explicite, sinon vue web HTML en terminal, snapshot HTML hors terminal."""
    if args.json:
        return MODE_JSON
    if args.text:
        return MODE_TEXT
    if args.tui:
        return MODE_TUI
    if args.web_only or interactive:
        return MODE_WEB
    return MODE_HTML


def default_snapshot_path(seed: str, directory: Optional[str] = None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", seed.lower()).strip("-")[:48] or "query"
    name = f"dendropivot-{slug}-{time.strftime('%Y%m%d-%H%M%S')}.html"
    return os.path.join(directory or os.getcwd(), name)


def start_web_server(session: Session, host: str, port: int) -> Optional[WebServer]:
    """Démarre le serveur ; si le port est occupé, repli sur un port libre attribué par l'OS."""
    for candidate in ([port, 0] if port else [0]):
        try:
            return WebServer(session, host, candidate).start()
        except OSError as exc:
            session.note(f"port {candidate} indisponible ({exc})" + (" -> port libre automatique" if candidate else ""))
            log.warning("serveur web sur %s:%s impossible: %s", host, candidate, exc)
    return None


def prompt_query(prompt: str = "Recherche (q pour quitter) > ") -> Optional[str]:
    try:
        query = input(prompt)
    except EOFError:
        print()
        return None
    query = re.sub(r"\s+", " ", query).strip()[:MAX_SEED_LENGTH]
    return None if not query or query.lower() == "q" else query


def _stop_session(session: Optional[Session], web: Optional[WebServer], worker: Optional[threading.Thread]) -> None:
    if session is not None:
        session.stop_event.set()
        session.wake_event.set()
    if web is not None:
        web.stop()
    if worker is not None:
        worker.join(timeout=2.0)


def run_web_mode(cfg: Config, args: argparse.Namespace, planner: Planner, pool: BackendPool, query: str) -> int:
    """Mode par défaut : vue HTML live dans le navigateur, rounds en continu jusqu'à Ctrl-C."""
    session = Session(query, cfg, planner, pool)
    if cfg.lang:
        session.set_language(cfg.lang)
    web = start_web_server(session, cfg.web_host, cfg.web_port)
    if web is None:
        print("serveur web indisponible (voir le journal)", file=sys.stderr)
        return 1
    worker: Optional[threading.Thread] = None
    try:
        session.web_url = web.url
        session.note(f"vue web: {web.url}")
        ssh_hint = attach_ssh_hint(session, web.port, cfg.web_host, args.no_web_ssh_hint)
        worker = threading.Thread(target=session.worker, name="rounds", daemon=True)
        worker.start()
        print(f"{APP_NAME} {__version__} · vue web : {web.url}  (Ctrl-C pour arrêter)", flush=True)
        if cfg.html_out:
            print(f"snapshot HTML : {cfg.html_out}", flush=True)
        if ssh_hint:
            print("\n" + ssh_hint + "\n", flush=True)
        elif not args.no_browser:
            ok, msg = open_url(web.url)
            if not ok:
                print(f"navigateur non ouvert ({msg}) : ouvrez {web.url}", file=sys.stderr, flush=True)
        while worker.is_alive():
            worker.join(timeout=1.0)
        print(session.status, flush=True)
        return 0
    finally:
        _stop_session(session, web, worker)


def run_snapshot_mode(cfg: Config, planner: Planner, pool: BackendPool, query: str, mode: str) -> int:
    """Hors terminal : exécute les rounds puis écrit un snapshot HTML (défaut), du JSON ou du texte."""
    session = Session(query, cfg, planner, pool)
    if mode == MODE_HTML:
        if not cfg.html_out:
            cfg.html_out = default_snapshot_path(query)
        rounds = cfg.rounds or 1
        for _ in range(rounds):
            session.run_round()
        if cfg.lang:
            session.set_language(cfg.lang, translate_content=False)
            session.retranslate_if_active()  # synchrone : le fichier écrit contient la traduction
        session.write_html_snapshot()
        if not os.path.exists(cfg.html_out):
            print(f"échec d'écriture du snapshot HTML : {cfg.html_out}", file=sys.stderr)
            return 1
        print(cfg.html_out)
        return 0
    run_noninteractive(session, cfg, as_json=(mode == MODE_JSON))
    session.write_html_snapshot()
    return 0


def run_tui_mode(cfg: Config, args: argparse.Namespace, planner: Planner, pool: BackendPool,
                 st: Style, pending: Optional[str]) -> int:
    """Interface terminal deux colonnes (v1.0), avec vue web optionnelle via --web."""
    session: Optional[Session] = None
    worker: Optional[threading.Thread] = None
    web: Optional[WebServer] = None
    try:
        while True:
            if pending is not None:
                query, pending = pending, None
            else:
                if session is not None and not session.paused:
                    session.toggle_pause()  # gèle les rounds pendant la saisie
                query = prompt_query()
                if query is None:
                    return 0
            if session is None:
                session = Session(query, cfg, planner, pool)
                if cfg.lang:
                    session.set_language(cfg.lang)
                if args.web is not None:
                    web = start_web_server(session, cfg.web_host, cfg.web_port)
                    if web is not None:
                        session.web_url = web.url
                        session.note(f"vue web: {web.url}")
                        ssh_hint = attach_ssh_hint(session, web.port, cfg.web_host, args.no_web_ssh_hint)
                        if ssh_hint:
                            print("\n" + ssh_hint + "\n", file=sys.stderr, flush=True)
                worker = threading.Thread(target=session.worker, name="rounds", daemon=True)
                worker.start()
            else:
                session.reset(query)
                if session.paused:
                    session.toggle_pause()
            action = picker_loop_interactive(session, st)
            sys.stdout.write("\x1b[0m\n" if st.enabled else "\n")
            if action == "quit":
                return 0
    finally:
        _stop_session(session, web, worker)


def setup_logging(cfg: Config, log_file: Optional[str], interactive: bool) -> None:
    level = logging.DEBUG if cfg.debug else logging.INFO
    handlers: list[logging.Handler] = []
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    elif not interactive:
        # en TUI, stderr casserait l'écran : stderr seulement en non-interactif, et
        # seulement en l'absence de fichier de log (sinon double émission de chaque ligne)
        handlers.append(logging.StreamHandler(sys.stderr))
    if not handlers:
        handlers.append(logging.NullHandler())
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers, force=True)


def main(argv: Optional[list[str]] = None) -> int:
    cfg, args = parse_args(argv)
    interactive = interactive_available()
    mode = choose_mode(args, interactive)
    if mode == MODE_TUI and not interactive:
        print("--tui requiert un terminal interactif (TTY)", file=sys.stderr)
        return 2
    # le logging stderr casserait l'écran de la TUI ; ailleurs il reste utile
    setup_logging(cfg, args.log_file, interactive=(mode == MODE_TUI))
    enable_vt_windows()
    st = Style(cfg.color and interactive)
    log.info("%s %s démarré (mode %s)", APP_NAME, __version__, mode)
    planner = Planner(cfg)
    pool = BackendPool(BACKENDS)

    query = re.sub(r"\s+", " ", args.query).strip()[:MAX_SEED_LENGTH] if args.query else None
    if mode == MODE_TUI:
        return run_tui_mode(cfg, args, planner, pool, st, query)
    if query is None:
        query = prompt_query("Recherche > ") if interactive else None
        if query is None:
            if not interactive:
                print("requête manquante : utilisez -q/--query", file=sys.stderr)
                return 2
            return 0
    if mode == MODE_WEB:
        return run_web_mode(cfg, args, planner, pool, query)
    return run_snapshot_mode(cfg, planner, pool, query, mode)


def cli() -> None:
    """Point d'entrée (codes de sortie : 0 ok, 1 erreur, 2 usage, 130 Ctrl-C)."""
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stdout.write("\x1b[0m\n")
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(0)


if __name__ == "__main__":
    cli()
