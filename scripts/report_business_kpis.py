#!/usr/bin/env python3
"""Combine GA4 clicks and normalized partner revenue into an action report."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STORE_DIMENSION = "customEvent:affiliate_store"
PROGRAM_ALIASES = {
    "amazon": "amazon",
    "amazon associates": "amazon",
    "audible": "audible",
    "kindle unlimited": "kindle_unlimited",
    "kdp": "kdp",
    "rakuten": "rakuten",
    "楽天": "rakuten",
    "yahoo": "yahoo",
    "yahoo shopping": "yahoo",
}


@dataclass
class RevenueRow:
    month: str
    program: str
    orders: int
    revenue_yen: float
    notes: str


def resolve_path(raw: Path) -> Path:
    return raw if raw.is_absolute() else REPO_ROOT / raw


def normalize_program(value: str) -> str:
    cleaned = " ".join(value.strip().lower().replace("_", " ").split())
    return PROGRAM_ALIASES.get(cleaned, cleaned.replace(" ", "_"))


def read_revenue(path: Path, *, allow_missing: bool = False) -> list[RevenueRow]:
    if not path.exists():
        if allow_missing:
            return []
        raise SystemExit(
            f"Revenue CSV not found: {path}\n"
            "Create it from data/revenue/partner-revenue.example.csv."
        )

    rows: list[RevenueRow] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"month", "program", "orders", "revenue_yen", "notes"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Revenue CSV is missing columns: {', '.join(sorted(missing))}")
        for line_number, raw in enumerate(reader, start=2):
            if not any((value or "").strip() for value in raw.values()):
                continue
            try:
                orders = int((raw["orders"] or "0").replace(",", ""))
                revenue = float((raw["revenue_yen"] or "0").replace(",", ""))
            except ValueError as exc:
                raise SystemExit(f"Invalid numeric value on revenue CSV line {line_number}") from exc
            if orders < 0 or revenue < 0:
                raise SystemExit(f"Negative values are not allowed on revenue CSV line {line_number}")
            month = (raw["month"] or "").strip()
            if len(month) != 7 or month[4] != "-":
                raise SystemExit(f"month must use YYYY-MM on revenue CSV line {line_number}")
            rows.append(
                RevenueRow(
                    month=month,
                    program=normalize_program(raw["program"] or ""),
                    orders=orders,
                    revenue_yen=revenue,
                    notes=(raw["notes"] or "").strip(),
                )
            )
    return rows


def read_ga4(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"GA4 JSON not found: {path}\n"
            "Run scripts/report_ga4.py with --json-output first."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"GA4 JSON is invalid: {path}") from exc


def store_clicks(ga4: dict) -> dict[str, int]:
    raw = ga4.get("affiliate_click_breakdowns_28d", {}).get(STORE_DIMENSION, {})
    clicks: dict[str, int] = defaultdict(int)
    for program, count in raw.items():
        clicks[normalize_program(program)] += int(count)
    return dict(clicks)


def commercial_program_clicks(ga4: dict) -> tuple[dict[str, int], str]:
    payload = ga4.get("commercial_program_clicks_28d")
    if not isinstance(payload, dict) or not payload.get("complete"):
        reason = (
            payload.get("reason", "")
            if isinstance(payload, dict)
            else "Run the latest GA4 report."
        )
        return {}, reason or "Program attribution is unavailable."
    return {
        normalize_program(program): int(count)
        for program, count in payload.get("values", {}).items()
    }, ""


def format_yen(value: float) -> str:
    return f"{value:,.0f}"


def validated_commercial_metrics(ga4: dict) -> dict:
    commercial = ga4.get("commercial_metrics_28d")
    required = {"pageviews", "affiliate_clicks", "affiliate_ctr", "pages", "complete"}
    if not isinstance(commercial, dict) or not required.issubset(commercial):
        raise ValueError(
            "GA4 JSON is missing complete commercial_metrics_28d data; rerun report_ga4.py."
        )
    if not commercial["complete"]:
        raise ValueError(
            "GA4 commercial_metrics_28d is truncated; increase report limits or paginate before KPI reporting."
        )
    return commercial


def build_report(
    ga4: dict,
    rows: list[RevenueRow],
    month: str,
    target_yen: int,
    *,
    revenue_available: bool = True,
) -> str:
    selected = [row for row in rows if row.month == month]
    revenue_by_program: dict[str, dict[str, float]] = defaultdict(
        lambda: {"orders": 0, "revenue": 0.0}
    )
    for row in selected:
        revenue_by_program[row.program]["orders"] += row.orders
        revenue_by_program[row.program]["revenue"] += row.revenue_yen

    clicks, program_attribution_reason = commercial_program_clicks(ga4)
    program_attribution_available = not program_attribution_reason
    all_programs = sorted(set(revenue_by_program) | set(clicks))
    total_revenue = sum(item["revenue"] for item in revenue_by_program.values())
    total_orders = int(sum(item["orders"] for item in revenue_by_program.values()))
    total_clicks = int(ga4.get("affiliate_clicks_28d", 0))
    total_pageviews = int(ga4.get("totals_28d", {}).get("pageviews", 0))
    commercial = validated_commercial_metrics(ga4)
    pageviews = int(commercial["pageviews"])
    commercial_clicks = int(commercial["affiliate_clicks"])
    ctr = float(commercial["affiliate_ctr"])
    click_attributable_revenue = sum(
        item["revenue"]
        for program, item in revenue_by_program.items()
        if program != "kdp"
    )
    epc = click_attributable_revenue / commercial_clicks if commercial_clicks else 0
    progress = total_revenue / target_yen if target_yen else 0
    revenue_actual = f"{format_yen(total_revenue)} yen" if revenue_available else "Not entered"
    progress_actual = f"{progress:.1%}" if revenue_available else "Not available"
    orders_actual = f"{total_orders:,}" if revenue_available else "Not entered"
    epc_actual = f"{format_yen(epc)} yen" if revenue_available else "Not available"

    lines = [
        f"# Business KPI Report: {month}",
        "",
        f"GA4 period: {ga4.get('range_28d', {}).get('start', '?')} to "
        f"{ga4.get('range_28d', {}).get('end', '?')}",
        "",
        "## Scorecard",
        "",
        "| KPI | Actual | Target |",
        "| --- | ---: | ---: |",
        f"| Confirmed revenue | {revenue_actual} | {target_yen:,} yen |",
        f"| Revenue progress | {progress_actual} | 100.0% |",
        f"| Orders/conversions | {orders_actual} | - |",
        f"| All pageviews (28d) | {total_pageviews:,} | - |",
        f"| Commercial-intent pageviews (28d) | {pageviews:,} | 31,250 planning baseline |",
        f"| Affiliate clicks (28d) | {total_clicks:,} | - |",
        f"| Commercial-intent affiliate clicks (28d) | {commercial_clicks:,} | 2,500 planning baseline |",
        f"| Commercial-intent affiliate CTR (28d) | {ctr:.2%} | 8.00% planning baseline |",
        f"| Confirmed commercial EPC | {epc_actual} | 40 yen planning baseline |",
        "",
        "## Program Performance",
        "",
        "| Program | Clicks (28d) | Orders | Revenue | EPC |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    if all_programs:
        for program in all_programs:
            program_clicks = clicks.get(program, 0)
            program_orders = int(revenue_by_program[program]["orders"])
            program_revenue = revenue_by_program[program]["revenue"]
            program_epc = program_revenue / program_clicks if program_clicks else 0
            orders_cell = f"{program_orders:,}" if revenue_available else "-"
            revenue_cell = (
                f"{format_yen(program_revenue)} yen" if revenue_available else "Not entered"
            )
            epc_cell = f"{format_yen(program_epc)} yen" if revenue_available else "-"
            lines.append(
                f"| {program} | {program_clicks:,} | {orders_cell} | "
                f"{revenue_cell} | {epc_cell} |"
            )
    else:
        lines.append(
            (
                f"| Program attribution unavailable | - | - | "
                f"{'Not entered' if not revenue_available else '-'} | - |"
            )
        )
    if not program_attribution_available:
        lines.extend(["", f"Program attribution: {program_attribution_reason}"])

    lines.extend(["", "## Priority Actions", ""])
    actions: list[str] = []
    if total_clicks == 0:
        actions.append(
            "1. Verify a real production affiliate click in GA4 DebugView and inspect the highest-view CTA page."
        )
    if revenue_available and program_attribution_available:
        for program in all_programs:
            program_clicks = clicks.get(program, 0)
            program_revenue = revenue_by_program[program]["revenue"]
            if program_clicks > 0 and program_revenue == 0:
                actions.append(
                    f"{len(actions) + 1}. `{program}` has {program_clicks} clicks but no confirmed revenue; "
                    "verify partner-report attribution and landing-page offer fit."
                )
        profitable = [
            (revenue_by_program[program]["revenue"] / clicks[program], program)
            for program in all_programs
            if clicks.get(program, 0) > 0 and revenue_by_program[program]["revenue"] > 0
        ]
        if profitable:
            best_epc, best_program = max(profitable)
            actions.append(
                f"{len(actions) + 1}. Scale pages and CTA slots for `{best_program}`, "
                f"the current highest-EPC program ({format_yen(best_epc)} yen/click)."
            )

    commercial_pages = commercial["pages"]
    zero_click_pages = [
        page
        for page in commercial_pages
        if int(page.get("affiliate_clicks", 0)) == 0
    ]
    if zero_click_pages:
        page = max(zero_click_pages, key=lambda item: int(item.get("views", 0)))
        actions.append(
            f"{len(actions) + 1}. Improve the CTA and search-intent match on "
            f"`{page.get('path', '/')}` ({int(page.get('views', 0))} views, zero clicks)."
        )
    if not revenue_available or not selected:
        actions.append(
            f"{len(actions) + 1}. Enter confirmed {month} partner/KDP results in the revenue CSV."
        )
    if not actions:
        actions.append("1. Preserve the current winners and test one CTA or internal-link change this week.")
    lines.extend(actions)
    lines.extend(
        [
            "",
            (
                "Revenue status: not entered. Traffic and click KPIs remain usable, but conversion, "
                "revenue, and EPC conclusions are intentionally withheld."
                if not revenue_available
                else "Revenue is controlled by partner and KDP reports. GA4 click counts are directional "
                "and may use a different date window."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ga4-json",
        type=Path,
        default=Path("reports/analytics/ga4-latest.json"),
    )
    parser.add_argument(
        "--revenue-csv",
        type=Path,
        default=Path("data/revenue/partner-revenue.csv"),
    )
    parser.add_argument("--month", help="Revenue month in YYYY-MM; defaults to latest CSV month")
    parser.add_argument("--target-yen", type=int, default=100_000)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/analytics/business-kpi.md"),
    )
    args = parser.parse_args()

    ga4 = read_ga4(resolve_path(args.ga4_json))
    revenue_path = resolve_path(args.revenue_csv)
    revenue_available = revenue_path.exists()
    rows = read_revenue(revenue_path, allow_missing=True)
    generated_month = str(ga4.get("generated_on") or "")[:7]
    month = args.month or max((row.month for row in rows), default=generated_month)
    if not month:
        raise SystemExit("Provide --month when GA4 generated_on and revenue rows are unavailable.")
    if args.target_yen <= 0:
        raise SystemExit("--target-yen must be greater than 0")

    report = build_report(
        ga4,
        rows,
        month,
        args.target_yen,
        revenue_available=revenue_available,
    )
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"\nReport written to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
