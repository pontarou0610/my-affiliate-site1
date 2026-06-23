from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from record_kpi_snapshot import build_snapshot, upsert_snapshot


class KpiSnapshotTests(unittest.TestCase):
    def test_builds_aggregate_snapshot_for_commercial_pages(self) -> None:
        ga4 = {
            "generated_on": "2026-06-23",
            "range_28d": {"start": "2026-05-26", "end": "2026-06-22"},
            "totals_28d": {"pageviews": 180},
            "affiliate_clicks_28d": 2,
            "commercial_metrics_28d": {
                "complete": True,
                "pageviews": 61,
                "affiliate_clicks": 1,
                "pages": [{"path": "/recommend/"}],
            },
            "inferred_commercial_program_clicks_28d": {
                "complete": True,
                "values": {"amazon": 1},
                "unattributed_clicks": 0,
            },
        }
        gsc = {
            "meta": {
                "start": "2026-05-25",
                "end": "2026-06-21",
                "page_rows_truncated": False,
            },
            "pages": [
                {"page": "/recommend/", "impressions": 100, "clicks": 5},
                {"page": "/posts/news/", "impressions": 900, "clicks": 90},
            ],
        }

        snapshot = build_snapshot(
            ga4,
            gsc,
            [{"path": "/recommend/", "match_type": "exact", "reason": ""}],
        )

        self.assertEqual(snapshot["commercial_search_impressions"], "100")
        self.assertEqual(snapshot["commercial_search_clicks"], "5")
        self.assertEqual(snapshot["commercial_affiliate_ctr"], "0.016393")
        self.assertEqual(snapshot["amazon_clicks_inferred"], "1")

    def test_upsert_replaces_same_date_and_sorts_dates(self) -> None:
        rows = [
            {"snapshot_date": "2026-06-24", "all_pageviews": "2"},
            {"snapshot_date": "2026-06-23", "all_pageviews": "1"},
        ]
        updated = upsert_snapshot(
            rows,
            {"snapshot_date": "2026-06-23", "all_pageviews": "3"},
        )

        self.assertEqual(
            [row["snapshot_date"] for row in updated],
            ["2026-06-23", "2026-06-24"],
        )
        self.assertEqual(updated[0]["all_pageviews"], "3")


if __name__ == "__main__":
    unittest.main()
