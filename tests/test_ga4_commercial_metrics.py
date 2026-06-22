from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from report_ga4 import (
    commercial_metrics,
    is_commercial_page,
    load_commercial_page_rules,
    normalize_page_path,
    response_complete,
)


class Ga4CommercialMetricsTests(unittest.TestCase):
    def test_matches_exact_and_prefix_rules(self) -> None:
        rules = [
            {"path": "/recommend/", "match_type": "exact", "reason": ""},
            {"path": "/lp/", "match_type": "prefix", "reason": ""},
        ]

        self.assertTrue(is_commercial_page("/recommend/", rules))
        self.assertTrue(is_commercial_page("/lp/kindle/", rules))
        self.assertFalse(is_commercial_page("/posts/news/", rules))
        self.assertEqual(normalize_page_path("/recommend"), "/recommend/")

    def test_aggregates_only_commercial_pages(self) -> None:
        rules = [{"path": "/lp/", "match_type": "prefix", "reason": ""}]
        daily_pages = [
            {"date": "20260620", "path": "/lp/kindle/", "views": 4},
            {"date": "20260621", "path": "/lp/kindle/", "views": 6},
            {"date": "20260621", "path": "/posts/news/", "views": 90},
        ]
        clicks = {"/lp/kindle/": 2, "/posts/news/": 9}

        result = commercial_metrics(daily_pages, clicks, rules)

        self.assertEqual(result["pageviews"], 10)
        self.assertEqual(result["affiliate_clicks"], 2)
        self.assertAlmostEqual(result["affiliate_ctr"], 0.2)
        self.assertEqual(result["pages"][0]["path"], "/lp/kindle/")
        self.assertTrue(result["complete"])

    def test_loads_only_explicit_commercial_experiments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.csv"
            experiments_path = root / "experiments.csv"
            rules_path.write_text(
                "path,match_type,reason\n/recommend/,exact,guide\n",
                encoding="utf-8",
            )
            experiments_path.write_text(
                "experiment_id,page,status,commercial_intent\n"
                "cta,/posts/cta/,active,true\n"
                "seo,/posts/seo/,active,false\n",
                encoding="utf-8",
            )

            rules = load_commercial_page_rules(rules_path, experiments_path)

        paths = {rule["path"] for rule in rules}
        self.assertIn("/posts/cta/", paths)
        self.assertNotIn("/posts/seo/", paths)

    def test_rejects_empty_commercial_rule_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_path = root / "rules.csv"
            rules_path.write_text(
                "path,match_type,reason\n,prefix,bad\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SystemExit, "non-empty absolute path"):
                load_commercial_page_rules(rules_path, root / "missing.csv")

    def test_detects_truncated_ga4_response(self) -> None:
        self.assertFalse(response_complete({"rowCount": 2, "rows": [{}]}))
        self.assertTrue(response_complete({"rowCount": 1, "rows": [{}]}))


if __name__ == "__main__":
    unittest.main()
