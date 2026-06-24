from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from report_business_kpis import (
    RevenueRow,
    build_report,
    commercial_program_clicks,
    commercial_page_funnel,
    commercial_search_metrics,
    delta_rate,
    experiment_gate,
    next_unmet_milestone,
    normalize_program,
    planning_milestones,
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
                    {"path": "/fiction/", "views": 50, "affiliate_clicks": 0},
                ],
            },
            "previous_commercial_metrics_28d": {
                "pageviews": 100,
                "affiliate_clicks": 5,
                "affiliate_ctr": 0.05,
                "complete": True,
            },
            "affiliate_click_breakdowns_28d": {
                "customEvent:affiliate_store": {
                    "Amazon": 40,
                    "Rakuten": 10,
                }
            },
            "commercial_program_clicks_28d": {
                "complete": True,
                "reason": "",
                "values": {"amazon": 10, "rakuten": 10},
            },
            "top_pages_28d": [
                {"path": "/recommend/", "views": 200, "affiliate_clicks": 0},
            ],
        }
        rows = [
            RevenueRow("2026-06", "amazon", 4, 4_000, ""),
            RevenueRow("2026-06", "rakuten", 0, 0, ""),
        ]
        gsc = {
            "meta": {
                "start": "2026-05-24",
                "end": "2026-06-20",
                "page_rows_truncated": False,
            },
            "pages": [
                {
                    "page": "/recommend/",
                    "clicks": 10,
                    "impressions": 200,
                    "active_experiment": True,
                },
                {"page": "/posts/news/", "clicks": 90, "impressions": 900},
            ],
            "previous_pages": [
                {"page": "/recommend/", "clicks": 5, "impressions": 100},
            ],
        }

        self.assertEqual(store_clicks(ga4), {"amazon": 40, "rakuten": 10})
        report = build_report(ga4, rows, "2026-06", 100_000, gsc=gsc)

        self.assertIn("| Confirmed revenue | 4,000 yen | 100,000 yen |", report)
        self.assertIn("| Commercial-intent pageviews (28d) | 200 |", report)
        self.assertIn("| Commercial-intent affiliate CTR (28d) | 10.00% |", report)
        self.assertIn("| Confirmed commercial EPC | 200 yen | 40 yen planning baseline |", report)
        self.assertIn("`rakuten` has 10 clicks but no confirmed revenue", report)
        self.assertIn("current highest-EPC program (400 yen/click)", report)
        self.assertIn("`/fiction/` (50 views, zero clicks)", report)
        self.assertNotIn("`/recommend/` (200 views, zero clicks)", report)
        self.assertIn("| Search impressions | 200 |", report)
        self.assertIn("| Search clicks | 10 | 5.00% search CTR |", report)
        self.assertIn("| Commercial search impressions | 200 | 100 | +100.0% |", report)
        self.assertIn("| Commercial pageviews | 200 | 100 | +100.0% |", report)
        self.assertIn("## Growth Milestones", report)
        self.assertIn("| Stage 2 | 1,000 | 3.00% | 30 |", report)
        self.assertIn("## Next Milestone", report)
        self.assertIn("Next target: Stage 2", report)
        self.assertIn("| Commercial PV | 800 |", report)
        self.assertIn("| 200 | 10 | 200 | 0 | active | `/recommend/` |", report)

    def test_reports_experiment_gate_and_next_review_date(self) -> None:
        ga4 = {
            "range_28d": {"start": "2026-05-25", "end": "2026-06-21"},
            "totals_28d": {"pageviews": 100},
            "affiliate_clicks_28d": 1,
            "commercial_metrics_28d": {
                "pageviews": 20,
                "affiliate_clicks": 1,
                "affiliate_ctr": 0.05,
                "complete": True,
                "pages": [
                    {"path": "/recommend/", "views": 20, "affiliate_clicks": 0},
                ],
            },
            "commercial_program_clicks_28d": {
                "complete": False,
                "reason": "Register affiliate_program.",
                "values": {},
            },
        }
        gsc = {
            "meta": {"page_rows_truncated": False},
            "pages": [
                {
                    "page": "/recommend/",
                    "clicks": 1,
                    "impressions": 20,
                    "active_experiment": True,
                }
            ],
            "previous_pages": [],
        }
        experiment_status = {
            "summary": {
                "active": 1,
                "collecting": 1,
                "review_due": 0,
                "data_missing": 0,
            },
            "experiments": [
                {
                    "experiment_id": "recommend-scale",
                    "status": "collecting",
                    "review_date": "2026-07-20",
                }
            ],
        }

        report = build_report(
            ga4,
            [],
            "2026-06",
            100_000,
            revenue_available=False,
            gsc=gsc,
            experiment_status=experiment_status,
        )

        self.assertIn("## Experiment Gate", report)
        self.assertIn("| Active experiments | 1 |", report)
        self.assertIn("| Next review date | 2026-07-20 |", report)
        self.assertIn("unchanged until 2026-07-20", report)

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
            "commercial_program_clicks_28d": {
                "complete": True,
                "reason": "",
                "values": {"amazon": 2},
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

    def test_skips_low_volume_zero_click_pages_as_cta_actions(self) -> None:
        ga4 = {
            "range_28d": {"start": "2026-05-25", "end": "2026-06-21"},
            "totals_28d": {"pageviews": 10},
            "affiliate_clicks_28d": 0,
            "commercial_metrics_28d": {
                "pageviews": 5,
                "affiliate_clicks": 0,
                "affiliate_ctr": 0,
                "complete": True,
                "pages": [
                    {"path": "/fiction/", "views": 5, "affiliate_clicks": 0},
                ],
            },
            "commercial_program_clicks_28d": {
                "complete": True,
                "reason": "",
                "values": {},
            },
        }

        report = build_report(ga4, [], "2026-06", 100_000, revenue_available=False)

        self.assertNotIn("Improve the CTA and search-intent match on `/fiction/`", report)
        self.assertIn("low-volume zero-click pages", report)
        self.assertIn("at least 10 views", report)

    def test_allows_missing_revenue_file(self) -> None:
        rows = read_revenue(REPO_ROOT / "data" / "revenue" / "missing.csv", allow_missing=True)
        self.assertEqual(rows, [])

    def test_program_attribution_can_be_unavailable(self) -> None:
        clicks, reason = commercial_program_clicks(
            {
                "commercial_program_clicks_28d": {
                    "complete": False,
                    "reason": "Register affiliate_program.",
                    "values": {},
                }
            }
        )
        self.assertEqual(clicks, {})
        self.assertIn("Register", reason)

    def test_uses_store_clicks_when_program_dimension_is_unavailable(self) -> None:
        ga4 = {
            "range_28d": {"start": "2026-05-26", "end": "2026-06-22"},
            "totals_28d": {"pageviews": 180},
            "affiliate_clicks_28d": 1,
            "commercial_metrics_28d": {
                "pageviews": 61,
                "affiliate_clicks": 1,
                "affiliate_ctr": 1 / 61,
                "pages": [],
                "complete": True,
            },
            "affiliate_click_breakdowns_28d": {
                "customEvent:affiliate_store": {"Amazon": 1}
            },
            "commercial_program_clicks_28d": {
                "complete": False,
                "reason": "Register affiliate_program.",
                "values": {},
            },
            "inferred_commercial_program_clicks_28d": {
                "complete": True,
                "values": {"amazon": 1},
                "unattributed_clicks": 0,
            },
        }

        report = build_report(
            ga4,
            [],
            "2026-06",
            100_000,
            revenue_available=False,
        )

        self.assertIn("## Store Click Fallback", report)
        self.assertIn("## Inferred Program Clicks", report)
        self.assertIn("| amazon | 1 |", report)
        self.assertIn("Amazon clicks cannot be split", report)
        self.assertIn("Register `affiliate_program`", report)

    def test_commercial_search_metrics_exclude_noncommercial_pages(self) -> None:
        metrics, reason = commercial_search_metrics(
            {
                "meta": {"page_rows_truncated": False},
                "pages": [
                    {"page": "/lp/kindle/", "clicks": 2, "impressions": 20},
                    {"page": "/posts/news/", "clicks": 8, "impressions": 80},
                ],
            }
        )
        self.assertEqual(reason, "")
        self.assertEqual(metrics["impressions"], 20)
        self.assertEqual(metrics["clicks"], 2)

    def test_commercial_search_metrics_reject_truncated_pages(self) -> None:
        metrics, reason = commercial_search_metrics(
            {"meta": {"page_rows_truncated": True}, "pages": []}
        )
        self.assertIsNone(metrics)
        self.assertIn("truncated", reason)

    def test_commercial_page_funnel_joins_gsc_and_ga4(self) -> None:
        rows = commercial_page_funnel(
            {
                "pages": [
                    {
                        "page": "/recommend/",
                        "impressions": 20,
                        "clicks": 2,
                        "active_experiment": True,
                    }
                ]
            },
            {
                "pages": [
                    {
                        "path": "/recommend/",
                        "views": 5,
                        "affiliate_clicks": 1,
                    }
                ]
            },
        )
        self.assertEqual(rows[0]["impressions"], 20)
        self.assertEqual(rows[0]["pageviews"], 5)
        self.assertEqual(rows[0]["affiliate_clicks"], 1)
        self.assertTrue(rows[0]["active_experiment"])

    def test_experiment_gate_handles_missing_report(self) -> None:
        status = experiment_gate(None)

        self.assertFalse(status["available"])
        self.assertIn("report_experiments.py", status["reason"])

    def test_delta_rate_handles_zero_baseline(self) -> None:
        self.assertEqual(delta_rate(1, 0), "new")
        self.assertEqual(delta_rate(0, 0), "0.0%")

    def test_planning_milestones_show_next_stage_gap(self) -> None:
        rows = planning_milestones(61, 1, target_yen=100_000)

        self.assertEqual(rows[0]["target_pageviews"], 1_000)
        self.assertEqual(rows[0]["target_clicks"], 30)
        self.assertEqual(rows[0]["pageview_gap"], 939)
        self.assertEqual(rows[0]["click_gap"], 29)
        self.assertAlmostEqual(rows[0]["ctr_gap"], 0.03 - (1 / 61))
        self.assertEqual(rows[-1]["target_pageviews"], 31_250)
        self.assertEqual(rows[-1]["modeled_revenue"], 100_000)
        self.assertEqual(next_unmet_milestone(rows)["stage"], "Stage 2")

    def test_next_unmet_milestone_returns_none_when_all_reached(self) -> None:
        rows = planning_milestones(40_000, 4_000, target_yen=100_000)

        self.assertIsNone(next_unmet_milestone(rows))

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
