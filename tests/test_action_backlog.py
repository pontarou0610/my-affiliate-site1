from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from report_action_backlog import build_candidates, format_backlog


class ActionBacklogTests(unittest.TestCase):
    def test_prioritizes_unlocked_revenue_actions(self) -> None:
        ga4 = {
            "commercial_metrics_28d": {
                "pages": [
                    {"path": "/recommend/", "views": 20, "affiliate_clicks": 0},
                    {"path": "/locked/", "views": 30, "affiliate_clicks": 0},
                ]
            }
        }
        gsc = {
            "pages": [
                {
                    "page": "/search-gap/",
                    "impressions": 30,
                    "clicks": 0,
                    "position": 8.0,
                    "ctr": 0.0,
                    "potential_clicks": 0.9,
                }
            ],
            "scale_candidates": [
                {
                    "page": "/proven/",
                    "impressions": 100,
                    "clicks": 3,
                    "position": 4.0,
                    "ctr": 0.03,
                },
                {
                    "page": "/locked/",
                    "impressions": 100,
                    "clicks": 4,
                    "position": 4.0,
                    "ctr": 0.04,
                },
            ],
        }
        summary = {
            "next_milestone": {"click_gap": 29, "ctr_gap": 0.01},
        }

        candidates = build_candidates(ga4, gsc, summary, {"/locked/"})

        pages = {item["page"] for item in candidates}
        self.assertIn("/proven/", pages)
        self.assertIn("/search-gap/", pages)
        self.assertIn("/recommend/", pages)
        self.assertNotIn("/locked/", pages)
        self.assertEqual(candidates[0]["type"], "scale_proven_search_page")

    def test_formats_gate_and_milestone_context(self) -> None:
        payload = {
            "summary": {
                "revenue_gate": {"blocks_epc_decisions": True, "status": "missing_file"},
                "program_attribution": {"available": False},
                "next_milestone": {
                    "stage": "Stage 2",
                    "pageview_gap": 939,
                    "click_gap": 29,
                    "ctr_gap": 0.0136,
                },
            },
            "candidates": [
                {
                    "type": "lift_search_ctr",
                    "score": 42.0,
                    "page": "/sample/",
                    "reason": "Improve the title.",
                }
            ],
        }

        report = format_backlog(payload, 10)

        self.assertIn("Gate: revenue=missing_file, affiliate_program=missing", report)
        self.assertIn("Stage 2: 939 PV, 29 clicks", report)
        self.assertIn("`lift_search_ctr`", report)


if __name__ == "__main__":
    unittest.main()
