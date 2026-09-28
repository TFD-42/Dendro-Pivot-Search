"""Regression tests for Marginalia and Yahoo HTML parsers using stored fixtures."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

SPEC = importlib.util.spec_from_file_location("websearch", ROOT / "websearch.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class MarginaliaParserTests(unittest.TestCase):
    def _call(self, html: str, limit: int = 10) -> list:
        with patch.object(MODULE, "_http_get_with_retry", return_value=html):
            return MODULE.backend_marginalia("test query", limit)

    def test_parses_three_results(self):
        results = self._call(_fixture("marginalia_results.html"))
        self.assertEqual(len(results), 3)

    def test_first_result_title_and_url(self):
        results = self._call(_fixture("marginalia_results.html"))
        self.assertEqual(results[0].title, "Example Result One")
        self.assertEqual(results[0].url, "https://example.com/page1")

    def test_snippet_text(self):
        results = self._call(_fixture("marginalia_results.html"))
        self.assertIn("Python programming", results[0].snippet)

    def test_html_entities_in_snippet(self):
        results = self._call(_fixture("marginalia_results.html"))
        self.assertIn("&", results[1].snippet)

    def test_result_without_snippet(self):
        results = self._call(_fixture("marginalia_results.html"))
        self.assertEqual(results[2].snippet, "")

    def test_limit_respected(self):
        results = self._call(_fixture("marginalia_results.html"), limit=2)
        self.assertEqual(len(results), 2)

    def test_no_results_page_returns_empty(self):
        results = self._call(_fixture("marginalia_noresults.html"))
        self.assertEqual(results, [])

    def test_rank_assigned(self):
        results = self._call(_fixture("marginalia_results.html"))
        for i, r in enumerate(results):
            self.assertEqual(r.rank, i + 1)

    def test_unknown_structure_raises(self):
        with self.assertRaises(MODULE.BackendError):
            self._call("<html><body><p>nothing here</p></body></html>")


class YahooParserTests(unittest.TestCase):
    def _call(self, html: str, limit: int = 10) -> list:
        with patch.object(MODULE, "_http_get_with_retry", return_value=html):
            return MODULE.backend_yahoo("test query", limit)

    def test_parses_three_results(self):
        results = self._call(_fixture("yahoo_results.html"))
        self.assertEqual(len(results), 3)

    def test_first_result_title(self):
        results = self._call(_fixture("yahoo_results.html"))
        self.assertEqual(results[0].title, "Yahoo Result One")

    def test_redirect_decoded(self):
        results = self._call(_fixture("yahoo_results.html"))
        # RU= redirect should be decoded to the actual URL
        self.assertEqual(results[0].url, "https://example.com/page1")

    def test_direct_link_kept(self):
        results = self._call(_fixture("yahoo_results.html"))
        self.assertEqual(results[1].url, "https://example.org/direct-link")

    def test_snippet_text(self):
        results = self._call(_fixture("yahoo_results.html"))
        self.assertIn("Yahoo search", results[0].snippet)

    def test_html_entities_in_snippet(self):
        results = self._call(_fixture("yahoo_results.html"))
        self.assertIn("&", results[1].snippet)

    def test_extra_class_on_span_parsed(self):
        results = self._call(_fixture("yahoo_results.html"))
        self.assertEqual(results[2].title, "Yahoo Result Three Extra Class")

    def test_limit_respected(self):
        results = self._call(_fixture("yahoo_results.html"), limit=1)
        self.assertEqual(len(results), 1)

    def test_rank_assigned(self):
        results = self._call(_fixture("yahoo_results.html"))
        for i, r in enumerate(results):
            self.assertEqual(r.rank, i + 1)


class DdgLiteParserTests(unittest.TestCase):
    def _call(self, html: str, limit: int = 10) -> list:
        with patch.object(MODULE, "http_post", return_value=html):
            return MODULE.backend_ddg_lite("test query", limit)

    def test_parses_three_results(self):
        results = self._call(_fixture("ddg_lite_results.html"))
        self.assertEqual(len(results), 3)

    def test_first_result_title_and_url(self):
        results = self._call(_fixture("ddg_lite_results.html"))
        self.assertEqual(results[0].title, "DDG Result One")
        self.assertEqual(results[0].url, "https://example.com/ddg-page1")

    def test_snippet_text(self):
        results = self._call(_fixture("ddg_lite_results.html"))
        self.assertIn("Python", results[0].snippet)

    def test_html_entities_in_snippet(self):
        results = self._call(_fixture("ddg_lite_results.html"))
        self.assertIn("&", results[0].snippet)

    def test_inline_markup_stripped(self):
        results = self._call(_fixture("ddg_lite_results.html"))
        self.assertNotIn("<b>", results[1].snippet)
        self.assertIn("bold", results[1].snippet)

    def test_empty_snippet_returns_empty_string(self):
        results = self._call(_fixture("ddg_lite_results.html"))
        self.assertEqual(results[2].snippet, "")

    def test_limit_respected(self):
        results = self._call(_fixture("ddg_lite_results.html"), limit=2)
        self.assertEqual(len(results), 2)

    def test_rank_assigned(self):
        results = self._call(_fixture("ddg_lite_results.html"))
        for i, r in enumerate(results):
            self.assertEqual(r.rank, i + 1)

    def test_anomalous_response_raises(self):
        with self.assertRaises(MODULE.BackendError):
            self._call("<html><body><p>blocked</p></body></html>")


if __name__ == "__main__":
    unittest.main()
