#!/usr/bin/env python3
"""Render a concise weekly operating decision from the business KPI JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = REPO_ROOT / "reports" / "analytics" / "business-kpi-summary.json"
DEFAULT_OUTPUT = REPO_ROOT / "reports" / "analytics" / "weekly-decision.md"


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def read_summary(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"Business KPI summary not found: {path}\n"
            "Run scripts/report_business_kpis.py first."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Business KPI summary is invalid JSON: {path}") from exc


def format_yen(value: float | int | None) -> str:
    return "Not entered" if value is None else f"{value:,.0f} yen"


def format_percent(value: float | None) -> str:
    return "Not available" if value is None else f"{value:.2%}"


def format_count(value: float | int | None) -> str:
    return "Not entered" if value is None else f"{int(value):,}"


def gate_status(summary: dict) -> str:
    revenue_gate = summary.get("revenue_gate") or {}
    program_gate = summary.get("program_attribution") or {}
    experiment_gate = summary.get("experiment_gate") or {}
    blockers: list[str] = []
    if revenue_gate.get("blocks_epc_decisions"):
        blockers.append(f"revenue={revenue_gate.get('status', 'unknown')}")
    if not program_gate.get("available", False):
        blockers.append("affiliate_program=missing")
    if experiment_gate.get("data_missing"):
        blockers.append("experiment_data=missing")
    return "OK" if not blockers else "Blocked: " + ", ".join(blockers)


def render_decision(summary: dict) -> str:
    scorecard = summary.get("scorecard") or {}
    milestone = summary.get("next_milestone") or {}
    actions = summary.get("priority_actions") or []
    experiment_gate = summary.get("experiment_gate") or {}
    primary_action = actions[0] if actions else "No priority action generated."

    lines = [
        f"# Weekly Affiliate Decision: {summary.get('month', 'unknown')}",
        "",
        f"Gate: {gate_status(summary)}",
        "",
        "| KPI | Value |",
        "| --- | ---: |",
        f"| Commercial PV | {format_count(scorecard.get('commercial_pageviews_28d'))} |",
        f"| Affiliate clicks | {format_count(scorecard.get('commercial_affiliate_clicks_28d'))} |",
        f"| Affiliate CTR | {format_percent(scorecard.get('commercial_affiliate_ctr_28d'))} |",
        f"| Orders/conversions | {format_count(scorecard.get('orders'))} |",
        f"| Confirmed revenue | {format_yen(scorecard.get('confirmed_revenue_yen'))} |",
        f"| Confirmed EPC | {format_yen(scorecard.get('confirmed_commercial_epc_yen'))} |",
        "",
        "## Next Milestone",
        "",
    ]
    if milestone:
        lines.extend(
            [
                (
                    f"{milestone.get('stage')}: "
                    f"{format_count(milestone.get('pageview_gap'))} PV, "
                    f"{format_count(milestone.get('click_gap'))} clicks, "
                    f"{format_percent(milestone.get('ctr_gap'))} pt CTR remaining."
                ),
                "",
            ]
        )
    else:
        lines.extend(["All configured planning milestones are reached.", ""])
    lines.extend(
        [
            "## Experiment Lock",
            "",
            (
                f"Active {experiment_gate.get('active', 0)}, review due "
                f"{experiment_gate.get('review_due', 0)}, next review "
                f"{experiment_gate.get('next_review_date') or '-'}."
            ),
            "",
            "## Next Action",
            "",
            f"1. {primary_action}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summary = read_summary(resolve_path(args.summary_json))
    report = render_decision(summary)
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"\nWeekly decision written to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
