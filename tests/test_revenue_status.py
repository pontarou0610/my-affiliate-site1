from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from revenue_status import evaluate_revenue_status, format_status


class RevenueStatusTests(unittest.TestCase):
    def test_missing_revenue_csv_blocks_epc_decisions(self) -> None:
        status = evaluate_revenue_status(Path("missing.csv"), "2026-06")

        self.assertEqual(status.status, "missing_file")
        self.assertTrue(status.blocks_epc_decisions)
        self.assertIn("partner-revenue.example.csv", status.message)

    def test_all_zero_rows_are_treated_as_unconfirmed_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "partner-revenue.csv"
            path.write_text(
                "\n".join(
                    [
                        "month,program,orders,revenue_yen,notes",
                        "2026-06,amazon,0,0,Amazon dashboard",
                        "2026-06,rakuten,0,0,Rakuten dashboard",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            status = evaluate_revenue_status(path, "2026-06")

        self.assertEqual(status.status, "placeholder_zero")
        self.assertTrue(status.blocks_epc_decisions)
        self.assertEqual(status.rows, 2)
        self.assertIn("unconfirmed", status.message)

    def test_partial_rows_remain_usable_but_list_missing_programs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "partner-revenue.csv"
            path.write_text(
                "\n".join(
                    [
                        "month,program,orders,revenue_yen,notes",
                        "2026-06,amazon,2,1200,Amazon dashboard",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            status = evaluate_revenue_status(path, "2026-06")

        self.assertEqual(status.status, "partial")
        self.assertFalse(status.blocks_epc_decisions)
        self.assertEqual(status.orders, 2)
        self.assertEqual(status.revenue_yen, 1200)
        self.assertIn("rakuten", status.missing_programs)

    def test_format_status_is_cli_readable(self) -> None:
        status = evaluate_revenue_status(Path("missing.csv"), "2026-06")
        output = format_status(status)

        self.assertIn("Revenue status: missing_file", output)
        self.assertIn("EPC decisions blocked: yes", output)


if __name__ == "__main__":
    unittest.main()
