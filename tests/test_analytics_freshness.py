from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_analytics_freshness import evaluate_freshness, format_result


class AnalyticsFreshnessTests(unittest.TestCase):
    def test_accepts_recent_ga4_and_gsc_reports(self) -> None:
        result = evaluate_freshness(
            {
                "generated_on": "2026-06-23",
                "range_28d": {"end": "2026-06-22"},
            },
            {"meta": {"end": "2026-06-21"}},
            today=date(2026, 6, 24),
        )

        self.assertTrue(result["fresh"])
        self.assertEqual(result["stale"], [])

    def test_rejects_stale_report_dates(self) -> None:
        result = evaluate_freshness(
            {
                "generated_on": "2026-06-01",
                "range_28d": {"end": "2026-06-01"},
            },
            {"meta": {"end": "2026-06-01"}},
            today=date(2026, 6, 24),
        )

        self.assertFalse(result["fresh"])
        self.assertGreaterEqual(len(result["stale"]), 1)
        self.assertIn("refresh GA4/GSC", format_result(result))


if __name__ == "__main__":
    unittest.main()
