from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from report_gsc import (
    aggregate_pages,
    expected_ctr,
    is_noise_query,
    normalize_page,
    query_opportunities,
)


class GscReportTests(unittest.TestCase):
    def test_normalizes_project_page_url(self) -> None:
        self.assertEqual(
            normalize_page(
                "https://pontarou0610.github.io/my-affiliate-site1/posts/test/"
            ),
            "/posts/test/",
        )

    def test_ranks_non_experiment_pages_first(self) -> None:
        rows = [
            {
                "query": "active query",
                "page": "/active/",
                "clicks": 0.0,
                "impressions": 100.0,
                "ctr": 0.0,
                "position": 5.0,
            },
            {
                "query": "available query",
                "page": "/available/",
                "clicks": 0.0,
                "impressions": 20.0,
                "ctr": 0.0,
                "position": 5.0,
            },
        ]
        pages = aggregate_pages(rows, {"/active/"})
        queries = query_opportunities(rows, {"/active/"})
        self.assertEqual(pages[0]["page"], "/available/")
        self.assertEqual(queries[0]["query"], "available query")
        self.assertTrue(pages[-1]["active_experiment"])

    def test_expected_ctr_is_monotonic(self) -> None:
        self.assertGreater(expected_ctr(1), expected_ctr(5))
        self.assertGreater(expected_ctr(5), expected_ctr(15))
        self.assertGreater(expected_ctr(15), expected_ctr(35))

    def test_filters_search_audit_queries(self) -> None:
        self.assertTrue(is_noise_query('site:github.io "coupon" -site:amazon.com'))
        self.assertFalse(is_noise_query("notebooklm epub"))


if __name__ == "__main__":
    unittest.main()
