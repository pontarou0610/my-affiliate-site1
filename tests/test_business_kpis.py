from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from report_business_kpis import (
    RevenueRow,
    build_report,
    normalize_program,
    read_revenue,
    store_clicks,
)
from report_ga4 import normalize_page_path, realtime_affiliate_clicks


class BusinessKpiReportTests(unittest.TestCase):
    def test_normalizes_program_and_site_paths(self) -> None:
        self.assertEqual(normalize_program("Amazon Associates"), "amazon")
        self.assertEqual(normalize_program("Kindle_Unlimited"), "kindle_unlimited")
        self.assertEqual(
            normalize_page_path("/my-affiliate-site1/recommend/"),
            "/recommend/",
        )

    def test_builds_revenue_and_priority_report(self) -> None:
        ga4 = {
            "range_28d": {"start": "2026-05-25", "end": "2026-06-21"},
            "totals_28d": {"pageviews": 1_000},
            "affiliate_clicks_28d": 50,
            "affiliate_ctr_28d": 0.05,
            "commercial_metrics_28d": {
                "pageviews": 200,
                "affiliate_clicks": 20,
                "affiliate_ctr": 0.10,
                "complete": True,
                "pages": [
                    {"path": "/recommend/", "views": 200, "affiliate_clicks": 0},
                ],
            },
            "affiliate_click_breakdowns_28d": {
                "customEvent:affiliate_store": {
                    "Amazon": 40,
                    "Rakuten": 10,
                }
            },
            "top_pages_28d": [
                {"path": "/recommend/", "views": 200, "affiliate_clicks": 0},
            ],
        }
        rows = [
            RevenueRow("2026-06", "amazon", 4, 4_000, ""),
            RevenueRow("2026-06", "rakuten", 0, 0, ""),
        ]

        self.assertEqual(store_clicks(ga4), {"amazon": 40, "rakuten": 10})
        report = build_report(ga4, rows, "2026-06", 100_000)

        self.assertIn("| Confirmed revenue | 4,000 yen | 100,000 yen |", report)
        self.assertIn("| Commercial-intent pageviews (28d) | 200 |", report)
        self.assertIn("| Commercial-intent affiliate CTR (28d) | 10.00% |", report)
        self.assertIn("| Confirmed commercial EPC | 200 yen | 40 yen planning baseline |", report)
        self.assertIn("`rakuten` has 10 clicks but no confirmed revenue", report)
        self.assertIn("current highest-EPC program (100 yen/click)", report)
        self.assertIn("`/recommend/` (200 views, zero clicks)", report)

    def test_requires_complete_commercial_metrics(self) -> None:
        ga4 = {
            "totals_28d": {"pageviews": 1_000},
            "affiliate_clicks_28d": 50,
            "commercial_metrics_28d": {"pageviews": 200},
        }

        with self.assertRaisesRegex(ValueError, "commercial_metrics_28d"):
            build_report(ga4, [], "2026-06", 100_000)

    def test_rejects_truncated_commercial_metrics(self) -> None:
        ga4 = {
            "totals_28d": {"pageviews": 1_000},
            "affiliate_clicks_28d": 50,
            "commercial_metrics_28d": {
                "pageviews": 200,
                "affiliate_clicks": 20,
                "affiliate_ctr": 0.10,
                "pages": [],
                "complete": False,
            },
        }

        with self.assertRaisesRegex(ValueError, "truncated"):
            build_report(ga4, [], "2026-06", 100_000)

    def test_reports_unknown_revenue_without_treating_it_as_zero(self) -> None:
        ga4 = {
            "range_28d": {"start": "2026-05-25", "end": "2026-06-21"},
            "totals_28d": {"pageviews": 100},
            "affiliate_clicks_28d": 2,
            "commercial_metrics_28d": {
                "pageviews": 50,
                "affiliate_clicks": 2,
                "affiliate_ctr": 0.04,
                "pages": [],
                "complete": True,
            },
            "affiliate_click_breakdowns_28d": {
                "customEvent:affiliate_store": {"Amazon": 2}
            },
        }

        report = build_report(
            ga4,
            [],
            "2026-06",
            100_000,
            revenue_available=False,
        )

        self.assertIn("| Confirmed revenue | Not entered |", report)
        self.assertIn("| amazon | 2 | - | Not entered | - |", report)
        self.assertNotIn("has 2 clicks but no confirmed revenue", report)
        self.assertIn("conclusions are intentionally withheld", report)

    def test_allows_missing_revenue_file(self) -> None:
        rows = read_revenue(REPO_ROOT / "data" / "revenue" / "missing.csv", allow_missing=True)
        self.assertEqual(rows, [])

    def test_realtime_click_count(self) -> None:
        class Request:
            def execute(self) -> dict:
                return {
                    "rows": [
                        {"metricValues": [{"value": "1"}]},
                        {"metricValues": [{"value": "2"}]},
                    ]
                }

        class Properties:
            def runRealtimeReport(self, **_kwargs) -> Request:
                return Request()

        class Service:
            def properties(self) -> Properties:
                return Properties()

        self.assertEqual(realtime_affiliate_clicks(Service(), "123"), 3)


if __name__ == "__main__":
    unittest.main()
