from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_weekly_kpi import build_commands


class WeeklyKpiRunnerTests(unittest.TestCase):
    def test_builds_required_weekly_kpi_sequence(self) -> None:
        args = argparse.Namespace(
            month="2026-06",
            ga4_json=Path("reports/analytics/ga4-latest.json"),
            gsc_json=Path("reports/analytics/gsc-latest.json"),
            skip_experiments=False,
            skip_freshness=False,
        )

        commands = build_commands(args)

        self.assertEqual(commands[0][1], "scripts/check_analytics_freshness.py")
        self.assertEqual(commands[1][1], "scripts/report_experiments.py")
        self.assertEqual(commands[2][1], "scripts/report_business_kpis.py")
        self.assertIn("--month", commands[2])
        self.assertEqual(commands[3][1], "scripts/report_weekly_decision.py")

    def test_can_skip_experiment_report_when_fresh(self) -> None:
        args = argparse.Namespace(
            month="2026-06",
            ga4_json=Path("reports/analytics/ga4-latest.json"),
            gsc_json=Path("reports/analytics/gsc-latest.json"),
            skip_experiments=True,
            skip_freshness=False,
        )

        commands = build_commands(args)

        self.assertEqual(len(commands), 3)
        self.assertEqual(commands[0][1], "scripts/check_analytics_freshness.py")
        self.assertEqual(commands[1][1], "scripts/report_business_kpis.py")
        self.assertEqual(commands[2][1], "scripts/report_weekly_decision.py")

    def test_can_skip_freshness_check_explicitly(self) -> None:
        args = argparse.Namespace(
            month="2026-06",
            ga4_json=Path("reports/analytics/ga4-latest.json"),
            gsc_json=Path("reports/analytics/gsc-latest.json"),
            skip_experiments=False,
            skip_freshness=True,
        )

        commands = build_commands(args)

        self.assertEqual(commands[0][1], "scripts/report_experiments.py")


if __name__ == "__main__":
    unittest.main()
