from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from report_experiments import build_payload, evaluate_experiment, parse_date


def snapshots() -> tuple[dict, dict]:
    ga4 = {
        "range_28d": {"start": "2026-05-25", "end": "2026-06-21"},
        "top_pages_28d": [
            {"path": "/posts/tablet/", "views": 13, "affiliate_clicks": 0},
        ],
        "affiliate_click_pages_28d": {},
        "affiliate_click_breakdowns_28d": {
            "customEvent:affiliate_slot": {"tablet-slot": 0},
        },
        "daily_page_metrics_28d": [],
        "daily_affiliate_page_slots_28d": [],
        "experiment_data_status": {"page_views": True, "page_slot_clicks": True},
    }
    gsc = {
        "meta": {"start": "2026-05-24", "end": "2026-06-20"},
        "pages": [
            {
                "page": "/posts/search/",
                "impressions": 6,
                "clicks": 2,
                "ctr": 2 / 6,
            }
        ],
        "queries": [
            {
                "query": "notebooklm pc",
                "page": "/posts/search/",
                "impressions": 6,
                "clicks": 0,
                "ctr": 0,
            }
        ],
        "daily_rows": [],
    }
    return ga4, gsc


class ExperimentReportTests(unittest.TestCase):
    def test_parses_ga4_compact_date(self) -> None:
        self.assertEqual(parse_date("20260622"), date(2026, 6, 22))

    def test_does_not_treat_pre_change_snapshot_as_result(self) -> None:
        ga4, gsc = snapshots()
        experiment = {
            "experiment_id": "tablet",
            "start_date": "2026-06-22",
            "page": "/posts/tablet/",
            "primary_metric": "affiliate_slot:tablet-slot",
            "baseline_views": "13",
            "baseline_clicks": "0",
            "change": "test",
        }
        result = evaluate_experiment(experiment, ga4, gsc, date(2026, 6, 22))

        self.assertEqual(result["status"], "collecting")
        self.assertEqual(result["source_period"]["post_change_days"], 0)
        self.assertEqual(result["review_date"], "2026-07-20")

    def test_marks_full_post_change_window_for_review(self) -> None:
        ga4, gsc = snapshots()
        ga4["range_28d"] = {"start": "2026-06-22", "end": "2026-07-19"}
        ga4["top_pages_28d"][0]["views"] = 120
        ga4["affiliate_click_breakdowns_28d"]["customEvent:affiliate_slot"]["tablet-slot"] = 6
        ga4["daily_page_metrics_28d"] = [
            {"date": "2026-07-01", "path": "/posts/tablet/", "views": 120}
        ]
        ga4["daily_affiliate_page_slots_28d"] = [
            {
                "date": "2026-07-01",
                "path": "/posts/tablet/",
                "slot": "tablet-slot",
                "clicks": 6,
            }
        ]
        experiment = {
            "experiment_id": "tablet",
            "start_date": "2026-06-22",
            "page": "/posts/tablet/",
            "primary_metric": "affiliate_slot:tablet-slot",
            "baseline_views": "13",
            "baseline_clicks": "0",
            "change": "test",
        }
        result = evaluate_experiment(experiment, ga4, gsc, date(2026, 7, 20))

        self.assertEqual(result["status"], "review_due")
        self.assertEqual(result["current"]["volume"], 120)
        self.assertAlmostEqual(result["current"]["rate"], 0.05)

    def test_early_review_uses_post_change_observations(self) -> None:
        ga4, gsc = snapshots()
        ga4["range_28d"] = {"start": "2026-06-01", "end": "2026-06-28"}
        ga4["daily_page_metrics_28d"] = [
            {"date": "2026-06-25", "path": "/posts/tablet/", "views": 100}
        ]
        experiment = {
            "experiment_id": "tablet",
            "start_date": "2026-06-22",
            "page": "/posts/tablet/",
            "primary_metric": "affiliate_slot:tablet-slot",
            "baseline_views": "13",
            "baseline_clicks": "0",
            "change": "test",
        }
        result = evaluate_experiment(experiment, ga4, gsc, date(2026, 6, 29))

        self.assertEqual(result["status"], "review_due")
        self.assertEqual(result["current"]["volume"], 100)

    def test_mixed_window_without_enough_post_change_data_is_collecting(self) -> None:
        ga4, gsc = snapshots()
        ga4["range_28d"] = {"start": "2026-06-01", "end": "2026-07-18"}
        ga4["daily_page_metrics_28d"] = [
            {"date": "2026-07-01", "path": "/posts/tablet/", "views": 20}
        ]
        experiment = {
            "experiment_id": "tablet",
            "start_date": "2026-06-22",
            "page": "/posts/tablet/",
            "primary_metric": "affiliate_slot:tablet-slot",
            "baseline_views": "13",
            "baseline_clicks": "0",
            "change": "test",
        }
        result = evaluate_experiment(experiment, ga4, gsc, date(2026, 7, 19))

        self.assertEqual(result["status"], "collecting")

    def test_matches_query_and_page(self) -> None:
        ga4, gsc = snapshots()
        experiment = {
            "experiment_id": "search",
            "start_date": "2026-06-22",
            "page": "/posts/search/",
            "primary_metric": "gsc_query_ctr:notebooklm pc",
            "baseline_views": "6",
            "baseline_clicks": "0",
            "change": "test",
        }
        payload = build_payload([experiment], ga4, gsc, date(2026, 6, 22))

        self.assertEqual(payload["summary"]["active"], 1)
        self.assertEqual(payload["experiments"][0]["current"]["volume"], 0)
        self.assertEqual(payload["experiments"][0]["status"], "collecting")

    def test_truncated_gsc_data_is_not_treated_as_zero(self) -> None:
        ga4, gsc = snapshots()
        gsc["meta"]["daily_rows_truncated"] = True
        experiment = {
            "experiment_id": "search",
            "start_date": "2026-06-01",
            "page": "/posts/search/",
            "primary_metric": "gsc_query_ctr:notebooklm pc",
            "baseline_views": "6",
            "baseline_clicks": "0",
            "change": "test",
        }
        result = evaluate_experiment(experiment, ga4, gsc, date(2026, 6, 22))

        self.assertEqual(result["status"], "data_missing")


if __name__ == "__main__":
    unittest.main()
