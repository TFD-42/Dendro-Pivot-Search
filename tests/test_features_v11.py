"""Tests hors réseau de la v1.1 : mode HTML par défaut, langue, durcissement du serveur web, lanceur."""

import http.client
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ws = _load("websearch")
launcher = _load("launcher")


def fake_backend(query, limit):
    return [ws.Result(f"{query} result {i}", f"https://example{i}.org/{abs(hash(query)) % 997}",
                      f"snippet about {query}", rank=i + 1) for i in range(min(limit, 3))]


def make_session(seed="python testing", lang=""):
    argv = ["--no-ollama", "--rounds", "1", "--delay", "0"] + (["--lang", lang] if lang else [])
    cfg, _ = ws.parse_args(argv)
    return ws.Session(seed, cfg, ws.Planner(cfg), ws.BackendPool([("fake", fake_backend)]))


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------

class ModeSelectionTests(unittest.TestCase):
    def mode(self, argv, interactive):
        _, args = ws.parse_args(argv)
        return ws.choose_mode(args, interactive)

    def test_default_is_html_web_view_in_terminal(self):
        self.assertEqual(self.mode(["-q", "x"], True), ws.MODE_WEB)

    def test_default_is_html_snapshot_outside_terminal(self):
        self.assertEqual(self.mode(["-q", "x"], False), ws.MODE_HTML)

    def test_explicit_modes(self):
        self.assertEqual(self.mode(["--tui"], True), ws.MODE_TUI)
        self.assertEqual(self.mode(["--json"], True), ws.MODE_JSON)
        self.assertEqual(self.mode(["--text"], False), ws.MODE_TEXT)
        self.assertEqual(self.mode(["--web-only", "-q", "x"], False), ws.MODE_WEB)

    def test_modes_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            ws.parse_args(["--tui", "--json"])

    def test_non_loopback_web_host_rejected(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            ws.parse_args(["--web-host", "0.0.0.0"])  # nosec B104 - valeur de test refusée

    def test_invalid_ollama_host_rejected(self):
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": "file:///etc/passwd"}), \
                self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            ws.parse_args([])

    def test_ollama_host_without_scheme_accepted(self):
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": "127.0.0.1:11434"}):
            cfg, _ = ws.parse_args([])
        self.assertEqual(cfg.ollama_host, "http://127.0.0.1:11434")

    def test_snapshot_mode_writes_html_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "snap.html")
            cfg, _ = ws.parse_args(["--no-ollama", "--delay", "0", "--html-out", out])
            pool = ws.BackendPool([("fake", fake_backend)])
            with mock.patch("sys.stdout", io.StringIO()) as stdout:
                code = ws.run_snapshot_mode(cfg, ws.Planner(cfg), pool, "python testing", ws.MODE_HTML)
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue().strip(), out)
            page = Path(out).read_text(encoding="utf-8")
            self.assertIn("<title>DendroPivot · python testing</title>", page)
            self.assertIn('name="robots" content="noindex,nofollow"', page)
            self.assertIn("example0.org", page)

    def test_default_snapshot_path_is_safe(self):
        path = ws.default_snapshot_path("../../etc/passwd; rm -rf /", "/tmp")
        self.assertEqual(os.path.dirname(path), "/tmp")
        self.assertRegex(os.path.basename(path), r"^dendropivot-etc-passwd-rm-rf-\d{8}-\d{6}\.html$")

    def test_main_non_interactive_without_query_is_usage_error(self):
        with mock.patch.object(ws, "interactive_available", return_value=False), \
                mock.patch.object(ws.Planner, "__init__", lambda self, cfg: setattr(self, "ollama", None)), \
                mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(ws.main(["--no-ollama"]), 2)


# --------------------------------------------------------------------------
# Langue
# --------------------------------------------------------------------------

class LanguageTests(unittest.TestCase):
    def test_heuristic_language_forced(self):
        exp = ws.HeuristicExpander("fr")
        col1, _ = exp.expand("machine learning", ws.KeywordStats("machine learning"), 1, set())
        self.assertIn("qu'est-ce que machine learning", [q for q, _ in col1])
        exp_en = ws.HeuristicExpander("en")
        col1, _ = exp_en.expand("modèles de langage", ws.KeywordStats("modèles de langage"), 1, set())
        self.assertIn("what is modèles de langage", [q for q, _ in col1])

    def test_unsupported_template_language_falls_back_to_detection(self):
        self.assertEqual(ws.HeuristicExpander("zh").lang, "")

    def test_builtin_english_ui_without_llm(self):
        session = make_session(lang="en")
        session.set_language("en", translate_content=False)
        snap = session.snapshot()
        self.assertEqual(snap["ui"]["btn_pause"], "pause")
        self.assertEqual(snap["ui"]["btn_history"], "full history")
        self.assertEqual(snap["methods"]["recent"], "recent")
        self.assertEqual(snap["html_lang"], "en")
        self.assertIn('<html lang="en">', ws.render_html(snap, live=False))

    def test_builtin_translation_keys_are_complete(self):
        self.assertEqual(set(ws.UI_STRINGS_EN), set(ws.UI_STRINGS))
        self.assertEqual(set(ws.METHOD_LABELS_EN), set(ws.METHOD_LABELS))
        for key, src in ws.UI_STRINGS.items():  # mêmes paramètres de gabarit
            self.assertEqual(sorted(__import__("re").findall(r"\{(\w+)\}", src)),
                             sorted(__import__("re").findall(r"\{(\w+)\}", ws.UI_STRINGS_EN[key])), key)

    def test_unknown_language_rejected(self):
        with self.assertRaises(ValueError):
            make_session().set_language("xx")

    def test_retranslate_warns_once_when_ollama_down(self):
        session = make_session()
        session.set_language("es", translate_content=False)
        with mock.patch.object(ws, "probe_ollama", return_value=None):
            session.retranslate_if_active()
            session.retranslate_if_active()
        self.assertEqual(sum("traduction LLM indisponible" in line for line in session.log), 1)


# --------------------------------------------------------------------------
# Rendu HTML et parsing
# --------------------------------------------------------------------------

class RenderingTests(unittest.TestCase):
    def test_template_markers_in_seed_are_not_expanded(self):
        session = make_session(seed="__STATE__ __LIVE__ </script><!--")
        page = ws.render_html(session.snapshot(), live=False)
        self.assertEqual(page.count("const LIVE=false"), 1)
        self.assertNotIn("</script><!--", page)
        self.assertIn("__STATE__ __LIVE__ &lt;/script&gt;", page)

    def test_rss_with_doctype_rejected(self):
        evil = '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x "y">]><rss><channel></channel></rss>'
        with mock.patch.object(ws, "http_get", return_value=evil), self.assertRaises(ws.BackendError):
            ws.backend_bing_rss("q", 5)

    def test_rss_parsing_filters_unsafe_urls(self):
        rss = ("<rss><channel>"
               "<item><title>Good</title><link>https://ok.example/a</link><description>d</description></item>"
               "<item><title>Bad</title><link>javascript:alert(1)</link><description>d</description></item>"
               "</channel></rss>")
        with mock.patch.object(ws, "http_get", return_value=rss):
            results = ws.backend_bing_rss("q", 5)
        self.assertEqual([r.url for r in results], ["https://ok.example/a"])

    def test_full_round_with_fake_backend(self):
        session = make_session()
        added = session.run_round()
        self.assertGreater(added, 0)
        urls = [r.url for rs in session.results.values() for r in rs]
        self.assertEqual(len(urls), len(set(urls)))


# --------------------------------------------------------------------------
# Serveur web : DNS rebinding, CSRF, limites
# --------------------------------------------------------------------------

class WebServerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.session = make_session()
        self.server = ws.WebServer(self.session, "127.0.0.1", 0).start()
        self.port = self.server.port

    def tearDown(self):
        self.server.stop()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            hdrs = {"Host": f"127.0.0.1:{self.port}"}
            hdrs.update(headers or {})
            data = body.encode("utf-8") if isinstance(body, str) else body
            if data is not None and "Content-Length" not in hdrs:
                hdrs["Content-Length"] = str(len(data))
            for k, v in hdrs.items():
                if v is not None:
                    conn.putheader(k, v)
            conn.endheaders(data)
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    def test_get_ok_with_security_headers(self):
        status, headers, _ = self.request("GET", "/state.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_dns_rebinding_host_rejected(self):
        status, _, _ = self.request("GET", "/state.json", headers={"Host": f"evil.example:{self.port}"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("GET", "/", headers={"Host": "127.0.0.1:1"})
        self.assertEqual(status, 403)

    def test_localhost_host_accepted(self):
        status, _, _ = self.request("GET", "/state.json", headers={"Host": f"localhost:{self.port}"})
        self.assertEqual(status, 200)

    def test_csrf_text_plain_rejected(self):
        status, _, _ = self.request("POST", "/api/seed", '{"seed":"pwned"}', {"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        self.assertEqual(self.session.seed, "python testing")

    def test_cross_origin_rejected(self):
        status, _, _ = self.request("POST", "/api/seed", '{"seed":"pwned"}',
                                    {"Content-Type": "application/json", "Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.session.seed, "python testing")

    def test_same_origin_json_accepted(self):
        status, _, _ = self.request("POST", "/api/seed", '{"seed":"new seed"}',
                                    {"Content-Type": "application/json; charset=utf-8",
                                     "Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status, 200)
        self.assertEqual(self.session.seed, "new seed")

    def test_negative_content_length_rejected(self):
        status, _, _ = self.request("POST", "/api/round", b"", {"Content-Type": "application/json",
                                                                 "Content-Length": "-5"})
        self.assertEqual(status, 400)

    def test_oversized_body_rejected(self):
        status, _, _ = self.request("POST", "/api/seed", b"",
                                    {"Content-Type": "application/json",
                                     "Content-Length": str(ws.MAX_POST_BODY_BYTES + 1)})
        self.assertEqual(status, 413)

    def test_concurrent_translation_rejected(self):
        with self.session.lock:
            self.session.translate_status = "busy"
        status, _, _ = self.request("POST", "/api/translate", '{"lang":"es"}', {"Content-Type": "application/json"})
        self.assertEqual(status, 409)

    def test_non_loopback_bind_refused(self):
        with self.assertRaises(ValueError):
            ws.WebServer(self.session, "0.0.0.0", 0)  # nosec B104 - valeur de test refusée


@unittest.skipUnless(socket.has_ipv6, "IPv6 indisponible")
class WebServerIPv6Tests(unittest.TestCase):
    def test_ipv6_loopback_binds(self):
        session = make_session()
        try:
            server = ws.WebServer(session, "::1", 0).start()
        except OSError as exc:  # conteneur sans ::1 configuré
            self.skipTest(f"::1 non disponible: {exc}")
        try:
            self.assertTrue(server.url.startswith("http://[::1]:"))
            conn = http.client.HTTPConnection("::1", server.port, timeout=5)
            conn.request("GET", "/state.json", headers={"Host": f"[::1]:{server.port}"})
            self.assertEqual(conn.getresponse().status, 200)
            conn.close()
        finally:
            server.stop()


class StartWebServerTests(unittest.TestCase):
    def test_busy_port_falls_back_to_free_port(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        busy = blocker.getsockname()[1]
        session = make_session()
        server = ws.start_web_server(session, "127.0.0.1", busy)
        try:
            self.assertIsNotNone(server)
            self.assertNotEqual(server.port, busy)
        finally:
            if server:
                server.stop()
            blocker.close()


# --------------------------------------------------------------------------
# Lanceur
# --------------------------------------------------------------------------

class FakePullResponse:
    def __init__(self, lines):
        self.lines = [json.dumps(x).encode() + b"\n" if isinstance(x, dict) else x for x in lines]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self.lines)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"TOK_CONFIG_DIR": self.tmp.name, "LANG": "en_US.UTF-8"})
        self.env.start()
        os.environ.pop("OLLAMA_MODEL", None)
        os.environ.pop("OLLAMA_HOST", None)
        self.out = []

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def make(self, answers):
        it = iter(answers)

        def ask(_prompt):
            try:
                return next(it)
            except StopIteration:
                raise EOFError from None

        return launcher.Launcher(ask=ask, say=self.out.append, plat="linux")

    def test_platform_detection_termux(self):
        with mock.patch.dict(os.environ, {"TERMUX_VERSION": "0.118"}):
            self.assertEqual(launcher.detect_platform(), "termux")

    def test_config_dir_override(self):
        self.assertEqual(launcher.config_dir("linux"), Path(self.tmp.name))

    def test_settings_roundtrip_and_corruption(self):
        path = Path(self.tmp.name) / "settings.json"
        launcher.Settings(lang="es", model="llama3.2:3b").save(path)
        s = launcher.Settings.load(path)
        self.assertEqual((s.lang, s.model), ("es", "llama3.2:3b"))
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(launcher.Settings.load(path).model, "")
        path.write_text(json.dumps({"lang": "xx", "model": "--evil"}), encoding="utf-8")
        s = launcher.Settings.load(path)
        self.assertEqual((s.lang, s.model), ("", ""))

    def test_no_default_model(self):
        self.assertEqual(launcher.Settings().model, "")
        self.assertFalse(hasattr(launcher, "DEFAULT_MODEL"))
        with mock.patch.dict(os.environ, {"OLLAMA_MODEL": "qwen2.5:7b"}):
            self.assertEqual(launcher.Settings.load(Path(self.tmp.name) / "none.json").model, "qwen2.5:7b")

    def test_model_name_validation(self):
        self.assertTrue(launcher.valid_model_name("qwen2.5:3b"))
        self.assertTrue(launcher.valid_model_name("library/llama3.2:3b-instruct-q4_K_M"))
        for bad in ("", "-rm", "a b", "a;b", "$(x)", "x" * 200):
            self.assertFalse(launcher.valid_model_name(bad), bad)

    def test_model_present(self):
        self.assertTrue(launcher.model_present("qwen2.5:3b", ["qwen2.5:3b"]))
        self.assertTrue(launcher.model_present("llama3", ["llama3:latest"]))
        self.assertFalse(launcher.model_present("qwen2.5:3b", ["qwen2.5:7b"]))

    def test_install_plans(self):
        have = lambda name: f"/usr/bin/{name}"  # noqa: E731
        none = lambda name: None  # noqa: E731
        self.assertEqual(launcher.install_plan("termux", have)[0], ["pkg", "install", "-y", "ollama"])
        self.assertEqual(launcher.install_plan("linux", have)[0], ["sh", "-c", launcher.LINUX_INSTALL_SCRIPT])
        self.assertIsNone(launcher.install_plan("linux", none)[0])
        self.assertEqual(launcher.install_plan("macos", have)[0], ["brew", "install", "ollama"])
        self.assertIsNone(launcher.install_plan("macos", none)[0])
        self.assertIsNone(launcher.install_plan("windows", have)[0])

    def test_pull_model_progress_and_success(self):
        events = [{"status": "pulling manifest"}, {"status": "pulling abc", "total": 100, "completed": 50},
                  b"garbage\n", {"status": "success"}]
        seen = []
        launcher.pull_model("http://127.0.0.1:1", "m", lambda s, d, t: seen.append((s, d, t)),
                            opener=lambda req, timeout: FakePullResponse(events))
        self.assertIn(("pulling abc", 50, 100), seen)
        self.assertEqual(seen[-1][0], "success")

    def test_pull_model_error_event(self):
        with self.assertRaises(launcher.PullError):
            launcher.pull_model("http://127.0.0.1:1", "m", lambda *a: None,
                                opener=lambda req, timeout: FakePullResponse([{"error": "pull model manifest: file does not exist"}]))

    def test_pull_model_requires_success(self):
        with self.assertRaises(launcher.PullError):
            launcher.pull_model("http://127.0.0.1:1", "m", lambda *a: None,
                                opener=lambda req, timeout: FakePullResponse([{"status": "pulling"}]))

    def test_menu_select_language_then_quit(self):
        lnc = self.make(["2", "2", "4"])
        with mock.patch.object(launcher, "list_models", return_value=None), \
                mock.patch.object(launcher, "find_ollama", return_value=None):
            self.assertEqual(lnc.menu(), 0)
        self.assertEqual(launcher.Settings.load(lnc.settings_path).lang, "en")
        self.assertIn("Language saved: English", self.out)

    def test_menu_eof_quits(self):
        lnc = self.make([])
        with mock.patch.object(launcher, "list_models", return_value=None), \
                mock.patch.object(launcher, "find_ollama", return_value=None):
            self.assertEqual(lnc.menu(), 0)

    def test_menu_invalid_choice(self):
        lnc = self.make(["9", "q"])
        with mock.patch.object(launcher, "list_models", return_value=None), \
                mock.patch.object(launcher, "find_ollama", return_value=None):
            lnc.menu()
        self.assertIn("Invalid choice.", self.out)

    def test_build_command(self):
        lnc = self.make([])
        lnc.settings.lang = "es"
        cmd = lnc.build_command("rust async; rm -rf /")
        self.assertEqual(cmd[:4], [sys.executable, str(launcher.APP_SCRIPT), "-q", "rust async; rm -rf /"])
        self.assertEqual(cmd[4:], ["--lang", "es"])  # aucun modèle imposé
        lnc.settings.model = "qwen2.5:7b"
        self.assertEqual(lnc.build_command("x")[-2:], ["--ollama-model", "qwen2.5:7b"])

    def test_run_query_invokes_app(self):
        lnc = self.make([])
        proc = mock.Mock()
        proc.wait.return_value = 0
        with mock.patch.object(launcher.subprocess, "Popen", return_value=proc) as popen, \
                mock.patch.object(launcher, "list_models", return_value=None):
            self.assertEqual(lnc.run_query("  deep   learning  "), 0)
        argv = popen.call_args[0][0]
        self.assertEqual(argv[3], "deep learning")
        self.assertNotIn("--ollama-model", argv)  # Ollama absent : rien d'imposé
        self.assertIn("OLLAMA_HOST", popen.call_args[1]["env"])

    def test_menu_query_lists_and_picks_installed_model(self):
        lnc = self.make(["3", "graph theory", "2", "4"])
        proc = mock.Mock()
        proc.wait.return_value = 0
        with mock.patch.object(launcher.subprocess, "Popen", return_value=proc) as popen, \
                mock.patch.object(launcher, "list_models", return_value=["qwen2.5:7b", "llama3.2:3b"]):
            lnc.menu()
        self.assertIn("1) llama3.2:3b  *", self.out)
        self.assertEqual(popen.call_args[0][0][-2:], ["--ollama-model", "qwen2.5:7b"])
        self.assertEqual(launcher.Settings.load(lnc.settings_path).model, "qwen2.5:7b")

    def test_direct_query_auto_picks_saved_or_first(self):
        lnc = self.make([])
        proc = mock.Mock()
        proc.wait.return_value = 0
        with mock.patch.object(launcher.subprocess, "Popen", return_value=proc) as popen, \
                mock.patch.object(launcher, "list_models", return_value=["b:1b", "a:1b"]):
            lnc.run_query("x")
        self.assertEqual(popen.call_args[0][0][-1], "a:1b")

    def test_install_declined_is_degraded_not_fatal(self):
        lnc = self.make(["n"])
        with mock.patch.object(launcher, "find_ollama", return_value=None), \
                mock.patch.object(launcher, "list_models", return_value=None), \
                mock.patch.object(launcher.shutil, "which", return_value="/usr/bin/x"), \
                mock.patch.object(launcher.subprocess, "call") as call:
            self.assertFalse(lnc.install(interactive=True))
        call.assert_not_called()
        self.assertTrue(any("degraded" in line for line in self.out))

    def _install(self, answers, installed, interactive=True):
        lnc = self.make(answers)
        with mock.patch.object(launcher, "find_ollama", return_value="/usr/bin/ollama"), \
                mock.patch.object(launcher, "list_models", return_value=installed), \
                mock.patch.object(launcher, "pull_model") as pull:
            ok = lnc.install(interactive=interactive)
        return lnc, ok, pull

    def test_single_installed_model_auto_selected(self):
        lnc, ok, pull = self._install([], ["mistral:7b"])
        self.assertTrue(ok)
        pull.assert_not_called()
        self.assertEqual(lnc.settings.model, "mistral:7b")

    def test_installed_models_listed_and_picked(self):
        lnc, ok, pull = self._install(["2"], ["qwen2.5:7b", "llama3.2:3b", "gemma:2b"])
        self.assertTrue(ok)
        pull.assert_not_called()
        self.assertEqual(lnc.settings.model, "llama3.2:3b")  # tri : gemma, llama, qwen

    def test_installed_models_enter_keeps_saved(self):
        path = Path(self.tmp.name) / "settings.json"
        launcher.Settings(model="qwen2.5:7b").save(path)
        lnc, ok, _ = self._install([""], ["qwen2.5:7b", "llama3.2:3b"])
        self.assertEqual(lnc.settings.model, "qwen2.5:7b")

    def test_download_another_from_list(self):
        lnc, ok, pull = self._install(["d", "1"], ["gemma:2b", "llama3.2:3b"])
        self.assertTrue(ok)
        self.assertEqual(pull.call_args[0][1], launcher.SUGGESTED_MODELS[0][0])
        self.assertEqual(lnc.settings.model, launcher.SUGGESTED_MODELS[0][0])

    def test_no_model_installed_shows_catalog(self):
        lnc, ok, pull = self._install([""], [])
        self.assertTrue(ok)
        self.assertIn("No model installed in Ollama.", self.out)
        self.assertTrue(any(launcher.RECOMMENDED_MODEL in line for line in self.out))
        self.assertEqual(pull.call_args[0][1], launcher.RECOMMENDED_MODEL)

    def test_no_model_installed_custom_name(self):
        lnc, ok, pull = self._install(["mistral-nemo:12b"], [])
        self.assertEqual(pull.call_args[0][1], "mistral-nemo:12b")

    def test_no_model_installed_skip(self):
        lnc, ok, pull = self._install(["s"], [])
        self.assertFalse(ok)
        pull.assert_not_called()
        self.assertEqual(lnc.settings.model, "")

    def test_non_interactive_install(self):
        lnc, ok, pull = self._install([], ["z:1b", "a:1b"], interactive=False)
        self.assertEqual(lnc.settings.model, "a:1b")
        pull.assert_not_called()
        lnc, ok, pull = self._install([], [], interactive=False)
        self.assertEqual(pull.call_args[0][1], "a:1b")  # modèle enregistré re-téléchargé
        (Path(self.tmp.name) / "settings.json").unlink()
        lnc, ok, pull = self._install([], [], interactive=False)
        self.assertEqual(pull.call_args[0][1], launcher.RECOMMENDED_MODEL)  # rien d'enregistré

    def test_saved_model_removed_falls_back(self):
        path = Path(self.tmp.name) / "settings.json"
        launcher.Settings(model="gone:1b").save(path)
        lnc, ok, _ = self._install([], ["a:1b"], interactive=False)
        self.assertEqual(lnc.settings.model, "a:1b")
        self.assertIn("[--] Saved model not found in Ollama: gone:1b", self.out)

    def test_catalog_tags_are_valid(self):
        self.assertIn(launcher.RECOMMENDED_MODEL, [t for t, _, _ in launcher.SUGGESTED_MODELS])
        for tag, _, _ in launcher.SUGGESTED_MODELS:
            self.assertTrue(launcher.valid_model_name(tag), tag)

    def test_install_starts_local_server(self):
        lnc = self.make([])
        with mock.patch.object(launcher, "find_ollama", return_value="/usr/bin/ollama"), \
                mock.patch.object(launcher, "list_models", return_value=None), \
                mock.patch.object(launcher, "start_ollama_server") as start, \
                mock.patch.object(launcher, "wait_for_server", return_value=[launcher.RECOMMENDED_MODEL]):
            self.assertTrue(lnc.install(interactive=False))
        start.assert_called_once()

    def test_remote_ollama_host_not_started(self):
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": "http://192.0.2.10:11434"}):
            lnc = self.make([])
        with mock.patch.object(launcher, "list_models", return_value=None), \
                mock.patch.object(launcher, "start_ollama_server") as start:
            self.assertIsNone(lnc.ensure_server("/usr/bin/ollama"))
        start.assert_not_called()

    def test_check_against_fake_ollama_api(self):
        models = {"models": [{"name": launcher.RECOMMENDED_MODEL}]}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = json.dumps(models).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with mock.patch.dict(os.environ, {"OLLAMA_HOST": f"127.0.0.1:{srv.server_address[1]}"}):
                lnc = self.make([])
            self.assertEqual(lnc.check(), 0)
            models["models"] = []
            self.assertEqual(lnc.check(), 1)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
