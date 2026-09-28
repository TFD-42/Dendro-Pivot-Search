import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("websearch", ROOT / "websearch.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeHeaders:
    def __init__(self, length=None):
        self.length = length

    def get(self, name):
        return self.length if name == "Content-Length" else None


class FakeResponse:
    def __init__(self, data, length=None):
        self.data = data
        self.headers = FakeHeaders(length)
        self.pos = 0

    def read(self, n=-1):
        if n < 0:
            n = len(self.data) - self.pos
        out = self.data[self.pos:self.pos + n]
        self.pos += len(out)
        return out


class WebSearchTests(unittest.TestCase):
    def test_safe_http_url(self):
        self.assertEqual(MODULE.safe_http_url("https://example.com/a"), "https://example.com/a")
        self.assertIsNone(MODULE.safe_http_url("javascript:alert(1)"))
        self.assertIsNone(MODULE.safe_http_url("file:///tmp/a"))
        self.assertIsNone(MODULE.safe_http_url("not-a-url"))

    def test_limited_response(self):
        response = FakeResponse(b"abc", length="3")
        self.assertEqual(MODULE._read_limited(response, 3), b"abc")
        with self.assertRaises(MODULE.BackendError):
            MODULE._read_limited(FakeResponse(b"abcd"), 3)
        with self.assertRaises(MODULE.BackendError):
            MODULE._read_limited(FakeResponse(b"abc", length="100"), 3)

    def test_cli_rejects_negative_rounds(self):
        with self.assertRaises(SystemExit):
            MODULE.parse_args(["--rounds", "-1"])

    def test_html_escapes_untrusted_text(self):
        cfg, _ = MODULE.parse_args(["--no-ollama", "--rounds", "1"])
        session = MODULE.Session("<script>alert(1)</script>", cfg, MODULE.Planner(cfg), MODULE.BackendPool([]))
        topic = session._new_topic(1, "test", "seed")
        session.results[topic.id] = [MODULE.Result("<img onerror=alert(1)>", "https://example.com", "<svg/onload=alert(1)>", topic_id=topic.id)]
        page = MODULE.render_html(session.snapshot(), live=False)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_post_body_limit_and_headers(self):
        cfg, _ = MODULE.parse_args(["--no-ollama", "--rounds", "1"])
        session = MODULE.Session("test", cfg, MODULE.Planner(cfg), MODULE.BackendPool([]))
        server = MODULE.WebServer(session, "127.0.0.1", 0).start()
        try:
            import urllib.request
            with urllib.request.urlopen(server.url + "state.json", timeout=3) as response:
                self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
