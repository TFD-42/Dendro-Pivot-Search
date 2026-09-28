"""
launcher.py — lanceur interactif de DendroPivot (websearch.py).

Menu :
  1  Installer / vérifier les dépendances (Python, Ollama, serveur Ollama, modèle)
  2  Choisir la langue (recherche + interface)
  3  Nouvelle requête (ouvre la vue HTML dans le navigateur)
  4  Quitter

Usage non interactif (scripts, raccourcis Termux, contrôle reproductible) :
  python3 launcher.py --check              état des dépendances, code 0 si tout est prêt
  python3 launcher.py --install [--yes]    installation/vérification sans menu
  python3 launcher.py --set-lang en        mémorise la langue
  python3 launcher.py -q "requête"         lance directement une requête

Bibliothèque standard uniquement. Linux, macOS, Windows, Android (Termux).
Réglages persistés en JSON dans le répertoire de configuration utilisateur
(surchargeable par TOK_CONFIG_DIR). Variables : OLLAMA_HOST, OLLAMA_MODEL.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess  # commandes d'installation fixes, confirmées par l'utilisateur  # nosec B404
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

__version__ = "1.1.0"
APP_NAME = "DendroPivot"

HERE = Path(__file__).resolve().parent
APP_SCRIPT = HERE / "websearch.py"
MIN_PYTHON = (3, 10)
# Aucun modèle imposé : les modèles installés sont listés et choisis. Ce catalogue n'est proposé
# que si Ollama n'a aucun modèle. Tags et tailles vérifiés sur ollama.com/library (2026-09-28).
SUGGESTED_MODELS: list[tuple[str, str, dict[str, str]]] = [
    ("qwen2.5:1.5b", "986 MB", {"en": "Termux / low RAM", "fr": "Termux / peu de RAM"}),
    ("qwen2.5:3b", "1.9 GB", {"en": "recommended: FR/EN/ES/IT/ZH/RU", "fr": "recommandé : FR/EN/ES/IT/ZH/RU"}),
    ("qwen2.5:7b", "4.7 GB", {"en": "better quality, 8 GB+ RAM or GPU", "fr": "meilleure qualité, 8 Go+ RAM ou GPU"}),
    ("qwen2.5:14b", "9.0 GB", {"en": "GPU", "fr": "GPU"}),
    ("llama3.2:3b", "2.0 GB", {"en": "no official ZH/RU support", "fr": "ZH/RU non officiellement supportés"}),
]
RECOMMENDED_MODEL = "qwen2.5:3b"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"
LINUX_INSTALL_SCRIPT = "curl -fsSL https://ollama.com/install.sh | sh"  # https://docs.ollama.com/linux
SERVER_START_TIMEOUT = 30.0
PULL_READ_TIMEOUT = 300
MAX_QUERY_LENGTH = 200
LOOPBACK = {"127.0.0.1", "localhost", "::1"}

LANGUAGES: list[tuple[str, str]] = [
    ("fr", "Français"), ("en", "English"), ("es", "Español"),
    ("it", "Italiano"), ("zh", "中文"), ("ru", "Русский"),
]
LANG_NAMES = dict(LANGUAGES)

log = logging.getLogger("tok.launcher")

# --------------------------------------------------------------------------
# Messages (FR / EN ; autres langues -> EN)
# --------------------------------------------------------------------------

MESSAGES: dict[str, dict[str, str]] = {
    "fr": {
        "title": "{app} {ver} · lanceur",
        "status": "Langue : {lang} | Modèle : {model} | Ollama : {ollama}",
        "menu": "1) Installer / vérifier les dépendances\n2) Choisir la langue\n3) Nouvelle requête (vue HTML)\n4) Quitter",
        "choice": "Choix [1-4] > ",
        "invalid": "Choix invalide.",
        "auto": "auto (détection)",
        "st_running": "actif ({n} modèle(s))",
        "st_installed": "installé, serveur arrêté",
        "st_missing": "non installé",
        "py_ok": "[ok] Python {v}",
        "py_bad": "[ÉCHEC] Python {v} : {req} ou plus récent requis",
        "app_ok": "[ok] {path} compile",
        "app_bad": "[ÉCHEC] {path} : {err}",
        "ol_found": "[ok] Ollama trouvé : {path}",
        "ol_missing": "[--] Ollama absent.",
        "ol_cmd": "Commande d'installation ({plat}) :\n    {cmd}",
        "ol_confirm": "Exécuter cette commande maintenant ? [o/N] > ",
        "ol_skipped": "Installation d'Ollama ignorée : la recherche fonctionne sans (expansion heuristique).",
        "ol_manual": "Installation manuelle : {url} ; relancez l'option 1 ensuite.",
        "ol_failed": "[ÉCHEC] installation d'Ollama (code {code}).",
        "srv_ok": "[ok] Serveur Ollama joignable : {host}",
        "srv_start": "Démarrage du serveur Ollama (journal : {log})…",
        "srv_fail": "[ÉCHEC] serveur Ollama injoignable sur {host} après {t:.0f} s.",
        "srv_down": "[--] Serveur Ollama injoignable : {host} (option 1 pour le démarrer)",
        "srv_remote": "[--] OLLAMA_HOST={host} n'est pas local : démarrez le serveur sur cette machine.",
        "model_none": "aucun (choix automatique)",
        "models_installed": "Modèles installés :",
        "model_pick": "Modèle [1-{n}, t = télécharger un autre, Entrée = {default}] > ",
        "catalog": "Modèles suggérés :",
        "catalog_empty": "Aucun modèle installé dans Ollama.",
        "catalog_pick": "Modèle à télécharger [1-{n}, ou nom exact, Entrée = {default}, s = passer] > ",
        "model_selected": "[ok] Modèle sélectionné : {model}",
        "model_auto": "[ok] Modèle unique installé, sélectionné : {model}",
        "model_skip": "Aucun modèle : recherche en expansion heuristique.",
        "model_missing": "[--] Modèle enregistré absent d'Ollama : {model}",
        "model_ok": "[ok] Modèle présent : {model}",
        "model_pull": "Téléchargement du modèle {model}…",
        "model_fail": "[ÉCHEC] téléchargement de {model} : {err}",
        "model_done": "[ok] Modèle installé : {model}",
        "all_ok": "Tout est prêt.",
        "partial": "Prêt en mode dégradé : recherche sans Ollama (expansion heuristique).",
        "lang_menu": "0) auto (détection)",
        "lang_prompt": "Langue [0-{n}] > ",
        "lang_set": "Langue enregistrée : {lang}",
        "q_prompt": "Requête (vide = retour) > ",
        "q_run": "Lancement : {cmd}",
        "q_back": "Retour au menu (code {code}).",
        "bye": "Au revoir.",
    },
    "en": {
        "title": "{app} {ver} · launcher",
        "status": "Language: {lang} | Model: {model} | Ollama: {ollama}",
        "menu": "1) Install / check dependencies\n2) Select language\n3) New query (HTML view)\n4) Quit",
        "choice": "Choice [1-4] > ",
        "invalid": "Invalid choice.",
        "auto": "auto (detect)",
        "st_running": "running ({n} model(s))",
        "st_installed": "installed, server stopped",
        "st_missing": "not installed",
        "py_ok": "[ok] Python {v}",
        "py_bad": "[FAIL] Python {v}: {req} or newer required",
        "app_ok": "[ok] {path} compiles",
        "app_bad": "[FAIL] {path}: {err}",
        "ol_found": "[ok] Ollama found: {path}",
        "ol_missing": "[--] Ollama not installed.",
        "ol_cmd": "Install command ({plat}):\n    {cmd}",
        "ol_confirm": "Run this command now? [y/N] > ",
        "ol_skipped": "Ollama install skipped: search still works without it (heuristic expansion).",
        "ol_manual": "Manual install: {url} ; then run option 1 again.",
        "ol_failed": "[FAIL] Ollama installation (exit code {code}).",
        "srv_ok": "[ok] Ollama server reachable: {host}",
        "srv_start": "Starting the Ollama server (log: {log})…",
        "srv_fail": "[FAIL] Ollama server unreachable at {host} after {t:.0f} s.",
        "srv_down": "[--] Ollama server unreachable: {host} (option 1 starts it)",
        "srv_remote": "[--] OLLAMA_HOST={host} is not local: start the server on that machine.",
        "model_none": "none (auto select)",
        "models_installed": "Installed models:",
        "model_pick": "Model [1-{n}, d = download another, Enter = {default}] > ",
        "catalog": "Suggested models:",
        "catalog_empty": "No model installed in Ollama.",
        "catalog_pick": "Model to download [1-{n}, or exact name, Enter = {default}, s = skip] > ",
        "model_selected": "[ok] Selected model: {model}",
        "model_auto": "[ok] Only one model installed, selected: {model}",
        "model_skip": "No model: search uses heuristic expansion.",
        "model_missing": "[--] Saved model not found in Ollama: {model}",
        "model_ok": "[ok] Model present: {model}",
        "model_pull": "Downloading model {model}…",
        "model_fail": "[FAIL] downloading {model}: {err}",
        "model_done": "[ok] Model installed: {model}",
        "all_ok": "Everything is ready.",
        "partial": "Ready in degraded mode: search without Ollama (heuristic expansion).",
        "lang_menu": "0) auto (detect)",
        "lang_prompt": "Language [0-{n}] > ",
        "lang_set": "Language saved: {lang}",
        "q_prompt": "Query (empty = back) > ",
        "q_run": "Running: {cmd}",
        "q_back": "Back to menu (exit code {code}).",
        "bye": "Goodbye.",
    },
}

# --------------------------------------------------------------------------
# Plateforme et configuration
# --------------------------------------------------------------------------


def detect_platform() -> str:
    """termux | macos | windows | linux."""
    if os.environ.get("TERMUX_VERSION") or "com.termux" in sys.prefix:
        return "termux"
    if sys.platform.startswith("darwin"):
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def config_dir(plat: Optional[str] = None) -> Path:
    override = os.environ.get("TOK_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    plat = plat or detect_platform()
    home = Path.home()
    if plat == "windows":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
    elif plat == "macos":
        base = home / "Library" / "Application Support"
    else:  # linux, termux
        base = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return base / "dendropivot"


@dataclass
class Settings:
    lang: str = ""                 # "" = détection automatique
    model: str = ""                # "" = choix automatique parmi les modèles installés

    @classmethod
    def load(cls, path: Path) -> Settings:
        s = cls()
        if os.environ.get("OLLAMA_MODEL"):
            s.model = os.environ["OLLAMA_MODEL"]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return s
        except (OSError, ValueError) as exc:
            log.warning("réglages illisibles (%s), valeurs par défaut: %s", path, exc)
            return s
        if isinstance(data, dict):
            lang = data.get("lang", "")
            if lang in LANG_NAMES or lang == "":
                s.lang = lang
            model = data.get("model")
            if isinstance(model, str) and valid_model_name(model):
                s.model = model
        return s

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)


def valid_model_name(name: str) -> bool:
    """Nom de modèle Ollama : [namespace/]nom[:tag], caractères sûrs uniquement."""
    if not name or len(name) > 128 or name.startswith(("-", ".", "/")):
        return False
    return all(c.isalnum() or c in "._-:/" for c in name)


def ollama_host() -> str:
    raw = (os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).strip()
    if "://" not in raw:
        raw = "http://" + raw
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        log.warning("OLLAMA_HOST invalide (%r), valeur par défaut utilisée", raw)
        return DEFAULT_OLLAMA_HOST
    return raw.rstrip("/")


def host_is_local(host: str) -> bool:
    name = urllib.parse.urlsplit(host).hostname or ""
    return name in LOOPBACK or name == "0.0.0.0"  # comparaison, aucun bind  # nosec B104

# --------------------------------------------------------------------------
# Ollama
# --------------------------------------------------------------------------


def find_ollama() -> Optional[str]:
    path = shutil.which("ollama")
    if path:
        return path
    candidates = [
        Path("/Applications/Ollama.app/Contents/Resources/ollama"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
    ]
    for c in candidates:
        if str(c) not in {"", "."} and c.is_file():
            return str(c)
    return None


def list_models(host: str, timeout: float = 3.0) -> Optional[list[str]]:
    """Noms des modèles installés, ou None si le serveur est injoignable."""
    req = urllib.request.Request(host + "/api/tags", headers={"User-Agent": f"dendropivot/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # host http(s) validé  # nosec B310
            data = json.loads(resp.read(2 * 1024 * 1024).decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return [m["name"] for m in data.get("models", []) if isinstance(m, dict) and isinstance(m.get("name"), str)]


def model_present(model: str, installed: list[str]) -> bool:
    if model in installed:
        return True
    if ":" not in model:
        return f"{model}:latest" in installed
    return False


def install_plan(plat: str, which: Callable[[str], Optional[str]] = shutil.which) -> tuple[Optional[list[str]], str]:
    """(commande à exécuter ou None si installation manuelle, texte affiché)."""
    if plat == "termux":
        cmd = ["pkg", "install", "-y", "ollama"]
        return cmd, " ".join(cmd)
    if plat == "linux":
        if which("curl") and which("sh"):
            return ["sh", "-c", LINUX_INSTALL_SCRIPT], LINUX_INSTALL_SCRIPT
        return None, f"{LINUX_INSTALL_SCRIPT}   (curl requis)"
    if plat == "macos":
        if which("brew"):
            return ["brew", "install", "ollama"], "brew install ollama"
        return None, OLLAMA_DOWNLOAD_URL
    return None, OLLAMA_DOWNLOAD_URL  # windows : installeur OllamaSetup.exe


def start_ollama_server(binary: str, log_path: Path) -> subprocess.Popen:
    """Lance `ollama serve` détaché du terminal ; sortie redirigée vers un journal."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log_path, "ab")  # noqa: SIM115 - handle transmis au processus fils
    kwargs: dict = {"stdout": fh, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen([binary, "serve"], **kwargs)  # binaire localisé, arguments fixes  # nosec B603
    finally:
        fh.close()  # le fils garde son propre descripteur


def wait_for_server(host: str, timeout: float = SERVER_START_TIMEOUT, interval: float = 0.5) -> Optional[list[str]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        models = list_models(host, timeout=2.0)
        if models is not None:
            return models
        time.sleep(interval)
    return None


class PullError(Exception):
    pass


def pull_model(host: str, model: str, on_progress: Callable[[str, int, int], None],
               opener: Callable = urllib.request.urlopen) -> None:
    """POST /api/pull {model, stream:true} ; flux de lignes JSON {status, total, completed}
    (https://docs.ollama.com/api/pull). Lève PullError sur erreur réseau ou message d'erreur."""
    body = json.dumps({"model": model, "stream": True}).encode("utf-8")
    req = urllib.request.Request(host + "/api/pull", data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": f"dendropivot/{__version__}"})
    last_status = ""
    try:
        with opener(req, timeout=PULL_READ_TIMEOUT) as resp:
            for raw in resp:
                line = raw.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    log.debug("ligne /api/pull ignorée: %r", line[:200])
                    continue
                if event.get("error"):
                    raise PullError(str(event["error"]))
                last_status = str(event.get("status", ""))
                on_progress(last_status, int(event.get("completed") or 0), int(event.get("total") or 0))
    except (urllib.error.URLError, OSError) as exc:
        raise PullError(str(exc)) from exc
    if last_status != "success":
        raise PullError(f"flux terminé sans succès (dernier statut: {last_status or 'aucun'})")

# --------------------------------------------------------------------------
# Lanceur
# --------------------------------------------------------------------------


class Launcher:
    def __init__(self, settings_path: Optional[Path] = None,
                 ask: Callable[[str], str] = input, say: Callable[[str], None] = print,
                 plat: Optional[str] = None):
        self.plat = plat or detect_platform()
        self.cfg_dir = config_dir(self.plat)
        self.settings_path = settings_path or self.cfg_dir / "settings.json"
        self.settings = Settings.load(self.settings_path)
        self.ask = ask
        self.say = say
        self.host = ollama_host()

    # -- i18n ----------------------------------------------------------------
    def ui_lang(self) -> str:
        if self.settings.lang in MESSAGES:
            return self.settings.lang
        if self.settings.lang:
            return "en"
        env = (os.environ.get("LC_ALL") or os.environ.get("LANG") or "").lower()
        return "fr" if env.startswith("fr") else "en"

    def t(self, key: str, **kw: object) -> str:
        return MESSAGES[self.ui_lang()][key].format(**kw)

    def prompt(self, key: str, **kw: object) -> Optional[str]:
        try:
            return self.ask(self.t(key, **kw)).strip()
        except EOFError:
            return None

    # -- état ------------------------------------------------------------------
    def ollama_state(self) -> str:
        models = list_models(self.host, timeout=1.5)
        if models is not None:
            return self.t("st_running", n=len(models))
        return self.t("st_installed") if find_ollama() else self.t("st_missing")

    def header(self) -> None:
        lang = LANG_NAMES.get(self.settings.lang, self.t("auto"))
        self.say("")
        self.say(self.t("title", app=APP_NAME, ver=__version__))
        self.say(self.t("status", lang=lang, model=self.settings.model or self.t("model_none"),
                        ollama=self.ollama_state()))
        self.say(self.t("menu"))

    # -- 1. dépendances --------------------------------------------------------
    def check_python(self) -> bool:
        v = ".".join(map(str, sys.version_info[:3]))
        if sys.version_info[:2] < MIN_PYTHON:
            self.say(self.t("py_bad", v=v, req=".".join(map(str, MIN_PYTHON))))
            return False
        self.say(self.t("py_ok", v=v))
        try:
            # compilation en mémoire : aucun fichier .pyc écrit
            compile(APP_SCRIPT.read_text(encoding="utf-8"), str(APP_SCRIPT), "exec")
        except (SyntaxError, ValueError, OSError) as exc:
            self.say(self.t("app_bad", path=APP_SCRIPT.name, err=exc))
            return False
        self.say(self.t("app_ok", path=APP_SCRIPT.name))
        return True

    def ensure_ollama_binary(self, assume_yes: bool) -> Optional[str]:
        binary = find_ollama()
        if binary:
            self.say(self.t("ol_found", path=binary))
            return binary
        self.say(self.t("ol_missing"))
        cmd, shown = install_plan(self.plat)
        self.say(self.t("ol_cmd", plat=self.plat, cmd=shown))
        if cmd is None:
            try:
                webbrowser.open(OLLAMA_DOWNLOAD_URL)
            except webbrowser.Error as exc:
                log.debug("navigateur indisponible: %s", exc)
            self.say(self.t("ol_manual", url=OLLAMA_DOWNLOAD_URL))
            return None
        if not assume_yes:
            answer = (self.prompt("ol_confirm") or "").lower()
            if answer not in {"o", "oui", "y", "yes"}:
                self.say(self.t("ol_skipped"))
                return None
        log.info("installation Ollama: %s", shown)
        try:
            code = subprocess.call(cmd)  # commande fixe affichée et confirmée  # nosec B603
        except OSError as exc:
            log.error("installation Ollama impossible: %s", exc)
            code = -1
        if code != 0:
            self.say(self.t("ol_failed", code=code))
            return None
        binary = find_ollama()
        if binary:
            self.say(self.t("ol_found", path=binary))
        return binary

    def ensure_server(self, binary: Optional[str]) -> Optional[list[str]]:
        models = list_models(self.host)
        if models is not None:
            self.say(self.t("srv_ok", host=self.host))
            return models
        if not host_is_local(self.host):
            self.say(self.t("srv_remote", host=self.host))
            return None
        if not binary:
            return None
        log_path = self.cfg_dir / "ollama-serve.log"
        self.say(self.t("srv_start", log=log_path))
        try:
            start_ollama_server(binary, log_path)
        except OSError as exc:
            log.error("ollama serve impossible: %s", exc)
            self.say(self.t("srv_fail", host=self.host, t=0))
            return None
        models = wait_for_server(self.host)
        if models is None:
            self.say(self.t("srv_fail", host=self.host, t=SERVER_START_TIMEOUT))
            return None
        self.say(self.t("srv_ok", host=self.host))
        return models

    def _save_model(self, model: str, key: str = "model_selected") -> str:
        self.settings.model = model
        self.settings.save(self.settings_path)
        self.say(self.t(key, model=model))
        return model

    def pick_installed_model(self, models: list[str], interactive: bool) -> Optional[str]:
        """Liste les modèles installés et en fait choisir un. Retourne None si l'utilisateur
        demande à en télécharger un autre."""
        ordered = sorted(models)
        saved = self.settings.model
        default = saved if saved and model_present(saved, ordered) else ordered[0]
        if saved and not model_present(saved, ordered):
            self.say(self.t("model_missing", model=saved))
        if not interactive:
            return self._save_model(default)
        if len(ordered) == 1:
            return self._save_model(ordered[0], "model_auto")
        self.say(self.t("models_installed"))
        for i, name in enumerate(ordered, 1):
            self.say(f"{i}) {name}{'  *' if name == default else ''}")
        while True:
            answer = self.prompt("model_pick", n=len(ordered), default=default)
            if answer is None or answer == "":
                return self._save_model(default)
            if answer.lower() in {"t", "d"}:
                return None
            if answer.isdigit() and 1 <= int(answer) <= len(ordered):
                return self._save_model(ordered[int(answer) - 1])
            if answer in ordered:
                return self._save_model(answer)
            self.say(self.t("invalid"))

    def choose_model_to_download(self, interactive: bool) -> Optional[str]:
        """Catalogue proposé uniquement quand aucun modèle ne convient ; None = passer."""
        if not interactive:
            return self.settings.model or RECOMMENDED_MODEL
        self.say(self.t("catalog"))
        for i, (tag, size, notes) in enumerate(SUGGESTED_MODELS, 1):
            self.say(f"{i}) {tag:<14} {size:>7}  {notes.get(self.ui_lang(), notes['en'])}")
        while True:
            answer = self.prompt("catalog_pick", n=len(SUGGESTED_MODELS), default=RECOMMENDED_MODEL)
            if answer is None or answer.lower() == "s":
                self.say(self.t("model_skip"))
                return None
            if answer == "":
                return RECOMMENDED_MODEL
            if answer.isdigit() and 1 <= int(answer) <= len(SUGGESTED_MODELS):
                return SUGGESTED_MODELS[int(answer) - 1][0]
            if valid_model_name(answer):
                return answer
            self.say(self.t("invalid"))

    def download_model(self, model: str) -> bool:
        self.say(self.t("model_pull", model=model))
        state = {"last": ""}

        def progress(status: str, done: int, total: int) -> None:
            line = f"  {status} {done * 100 // total:3d}%" if total else f"  {status}"
            if line != state["last"]:
                state["last"] = line
                self.say(line)

        try:
            pull_model(self.host, model, progress)
        except PullError as exc:
            self.say(self.t("model_fail", model=model, err=exc))
            return False
        self.say(self.t("model_done", model=model))
        self._save_model(model)
        return True

    def ensure_model(self, models: list[str], interactive: bool) -> bool:
        """Modèles installés -> liste + choix. Aucun modèle (ou « télécharger un autre ») ->
        catalogue + téléchargement. En non interactif : modèle enregistré ou premier installé,
        sinon téléchargement du modèle enregistré ou recommandé."""
        if models:
            if self.pick_installed_model(models, interactive):
                return True
        else:
            self.say(self.t("catalog_empty"))
        model = self.choose_model_to_download(interactive)
        if model is None:
            return bool(models) and bool(self.settings.model)
        if model_present(model, models):
            self._save_model(model)
            return True
        return self.download_model(model)

    def install(self, assume_yes: bool = False, interactive: bool = True) -> bool:
        """Retourne True si tout est prêt (Ollama + modèle) ; la recherche reste possible sinon."""
        if not self.check_python():
            return False
        binary = self.ensure_ollama_binary(assume_yes)
        models = self.ensure_server(binary)
        ready = models is not None and self.ensure_model(models, interactive)
        self.say(self.t("all_ok") if ready else self.t("partial"))
        return ready

    # -- 2. langue -------------------------------------------------------------
    def select_language(self) -> None:
        self.say(self.t("lang_menu"))
        for i, (code, name) in enumerate(LANGUAGES, 1):
            self.say(f"{i}) {name} ({code})")
        answer = self.prompt("lang_prompt", n=len(LANGUAGES))
        if answer is None:
            return
        if answer.isdigit() and 0 <= int(answer) <= len(LANGUAGES):
            idx = int(answer)
            self.set_language("" if idx == 0 else LANGUAGES[idx - 1][0])
        elif answer.lower() in LANG_NAMES:
            self.set_language(answer.lower())
        else:
            self.say(self.t("invalid"))

    def set_language(self, code: str) -> None:
        if code and code not in LANG_NAMES:
            raise ValueError(f"langue inconnue: {code}")
        self.settings.lang = code
        self.settings.save(self.settings_path)
        self.say(self.t("lang_set", lang=LANG_NAMES.get(code, self.t("auto"))))

    # -- 3. requête ------------------------------------------------------------
    def build_command(self, query: str) -> list[str]:
        cmd = [sys.executable, str(APP_SCRIPT), "-q", query]
        if self.settings.lang:
            cmd += ["--lang", self.settings.lang]
        if self.settings.model:
            cmd += ["--ollama-model", self.settings.model]  # sinon websearch.py prend le premier installé
        return cmd

    def resolve_model(self, interactive: bool) -> None:
        """Avant une requête : si aucun modèle n'est enregistré, ou si l'enregistré a disparu,
        liste les modèles installés et en choisit un (automatique s'il n'y en a qu'un).
        Ollama injoignable ou sans modèle : rien n'est imposé, la recherche reste heuristique."""
        models = list_models(self.host, timeout=1.5)
        if not models:
            return
        if self.settings.model and model_present(self.settings.model, models):
            return
        self.pick_installed_model(models, interactive)

    def run_query(self, query: Optional[str] = None) -> int:
        interactive = query is None
        if query is None:
            query = self.prompt("q_prompt")
        query = " ".join((query or "").split())[:MAX_QUERY_LENGTH]
        if not query:
            return 0
        self.resolve_model(interactive)
        cmd = self.build_command(query)
        self.say(self.t("q_run", cmd=" ".join(cmd[1:])))
        env = dict(os.environ, OLLAMA_HOST=self.host)
        proc = subprocess.Popen(cmd, env=env)  # sys.executable + script local, argv sans shell  # nosec B603
        while True:
            try:
                code = proc.wait()
                break
            except KeyboardInterrupt:
                continue  # Ctrl-C est aussi reçu par le fils, qui s'arrête proprement
        self.say(self.t("q_back", code=code))
        return code

    # -- boucle ----------------------------------------------------------------
    def menu(self) -> int:
        while True:
            self.header()
            choice = self.prompt("choice")
            if choice is None or choice == "4" or choice.lower() in {"q", "quit", "quitter"}:
                self.say(self.t("bye"))
                return 0
            if choice == "1":
                self.install(assume_yes=False, interactive=True)
            elif choice == "2":
                self.select_language()
            elif choice == "3":
                self.run_query()
            else:
                self.say(self.t("invalid"))

    def check(self) -> int:
        ok = self.check_python()
        binary = find_ollama()
        self.say(self.t("ol_found", path=binary) if binary else self.t("ol_missing"))
        models = list_models(self.host)
        if models is None:
            self.say(self.t("srv_down", host=self.host))
            return 1
        self.say(self.t("srv_ok", host=self.host))
        if not models:
            self.say(self.t("catalog_empty"))
            return 1
        if self.settings.model and not model_present(self.settings.model, models):
            self.say(self.t("model_missing", model=self.settings.model))
            return 1
        self.say(self.t("model_ok", model=self.settings.model or f"{sorted(models)[0]} (auto)"))
        return 0 if ok else 1


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="launcher.py", description=f"{APP_NAME} — lanceur")
    p.add_argument("--version", action="version", version=f"{APP_NAME} launcher {__version__}")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="état des dépendances (code 0 = prêt)")
    g.add_argument("--install", action="store_true", help="installer/vérifier Ollama et le modèle sans menu")
    g.add_argument("-q", "--query", help="lancer directement une requête")
    p.add_argument("--yes", action="store_true", help="avec --install : pas de confirmation")
    p.add_argument("--set-lang", choices=[c for c, _ in LANGUAGES] + ["auto"], help="mémoriser la langue")
    p.add_argument("--model", help="modèle Ollama à mémoriser (défaut : choix parmi les modèles installés)")
    p.add_argument("--debug", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    launcher = Launcher()
    launcher.cfg_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(launcher.cfg_dir / "launcher.log", encoding="utf-8")])
    log.info("launcher %s démarré (plateforme %s)", __version__, launcher.plat)
    if args.model:
        if not valid_model_name(args.model):
            print(f"nom de modèle invalide: {args.model!r}", file=sys.stderr)
            return 2
        launcher.settings.model = args.model
        launcher.settings.save(launcher.settings_path)
    if args.set_lang:
        launcher.set_language("" if args.set_lang == "auto" else args.set_lang)
    if args.check:
        return launcher.check()
    if args.install:
        return 0 if launcher.install(assume_yes=args.yes, interactive=False) else 1
    if args.query:
        return launcher.run_query(args.query)
    if args.set_lang or args.model:
        return 0
    return launcher.menu()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
