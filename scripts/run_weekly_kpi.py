#!/usr/bin/env python3
"""Run the weekly KPI report sequence in the required order."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GA4 = Path("reports/analytics/ga4-latest.json")
DEFAULT_GSC = Path("reports/analytics/gsc-latest.json")


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def existing_required_report(path: Path, label: str) -> None:
    resolved = resolve_path(path)
    if not resolved.exists():
        raise SystemExit(
            f"{label} not found: {resolved}\n"
            "Refresh analytics first, then rerun this weekly KPI sequence."
        )


def build_commands(args: argparse.Namespace) -> list[list[str]]:
    py = sys.executable
    commands: list[list[str]] = []
    if not args.skip_freshness:
        commands.append(
            [
                py,
                "scripts/check_analytics_freshness.py",
                "--ga4-json",
                args.ga4_json.as_posix(),
                "--gsc-json",
                args.gsc_json.as_posix(),
            ]
        )
    if not args.skip_experiments:
        commands.append(
            [
                py,
                "scripts/report_experiments.py",
                "--ga4",
                args.ga4_json.as_posix(),
                "--gsc",
                args.gsc_json.as_posix(),
            ]
        )
    commands.append(
        [
            py,
            "scripts/report_business_kpis.py",
            "--month",
            args.month,
            "--ga4-json",
            args.ga4_json.as_posix(),
            "--gsc-json",
            args.gsc_json.as_posix(),
        ]
    )
    commands.append([py, "scripts/report_weekly_decision.py"])
    return commands


def run_command(command: list[str]) -> None:
    print(f"\n$ {' '.join(command)}", flush=True)
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="Revenue month in YYYY-MM")
    parser.add_argument("--ga4-json", type=Path, default=DEFAULT_GA4)
    parser.add_argument("--gsc-json", type=Path, default=DEFAULT_GSC)
    parser.add_argument(
        "--skip-experiments",
        action="store_true",
        help="Skip report_experiments.py when experiment-status.json is already fresh.",
    )
    parser.add_argument(
        "--skip-freshness",
        action="store_true",
        help="Skip analytics freshness checks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    existing_required_report(args.ga4_json, "GA4 JSON")
    existing_required_report(args.gsc_json, "GSC JSON")
    for command in build_commands(args):
        run_command(command)
    print("\n[done] Weekly KPI reports generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
