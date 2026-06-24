from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from report_weekly_decision import gate_status, render_decision


class WeeklyDecisionTests(unittest.TestCase):
    def test_renders_blocked_weekly_decision_without_zeroing_revenue(self) -> None:
        summary = {
            "month": "2026-06",
            "scorecard": {
                "commercial_pageviews_28d": 61,
                "commercial_affiliate_clicks_28d": 1,
                "commercial_affiliate_ctr_28d": 1 / 61,
                "orders": None,
                "confirmed_revenue_yen": None,
                "confirmed_commercial_epc_yen": None,
            },
            "revenue_gate": {
                "status": "missing_file",
                "blocks_epc_decisions": True,
            },
            "program_attribution": {
                "available": False,
            },
            "experiment_gate": {
                "active": 10,
                "review_due": 0,
                "next_review_date": "2026-07-20",
            },
            "next_milestone": {
                "stage": "Stage 2",
                "pageview_gap": 939,
                "click_gap": 29,
                "ctr_gap": 0.0136,
            },
            "priority_actions": [
                "Register `affiliate_program` as an event-scoped GA4 custom dimension.",
            ],
        }

        report = render_decision(summary)

        self.assertIn("Gate: Blocked: revenue=missing_file, affiliate_program=missing", report)
        self.assertIn("| Confirmed revenue | Not entered |", report)
        self.assertIn("| Confirmed EPC | Not entered |", report)
        self.assertIn("Stage 2: 939 PV, 29 clicks, 1.36% pt CTR remaining.", report)
        self.assertIn("next review 2026-07-20", report)
        self.assertIn("Register `affiliate_program`", report)

    def test_gate_status_is_ok_when_core_gates_are_clear(self) -> None:
        self.assertEqual(
            gate_status(
                {
                    "revenue_gate": {"blocks_epc_decisions": False},
                    "program_attribution": {"available": True},
                    "experiment_gate": {"data_missing": 0},
                }
            ),
            "OK",
        )


if __name__ == "__main__":
    unittest.main()
