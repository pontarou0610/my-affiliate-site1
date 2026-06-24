#!/usr/bin/env python3
"""Combine GA4 clicks and normalized partner revenue into an action report."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from report_ga4 import is_commercial_page, load_commercial_page_rules
from revenue_status import (
    RevenueRow,
    RevenueStatus,
    evaluate_revenue_status,
    normalize_program,
    read_revenue,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
STORE_DIMENSION = "customEvent:affiliate_store"
MIN_ZERO_CLICK_ACTION_VIEWS = 10


def resolve_path(raw: Path) -> Path:
    return raw if raw.is_absolute() else REPO_ROOT / raw


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


def read_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON is invalid: {path}") from exc


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


def inferred_commercial_program_clicks(ga4: dict) -> tuple[dict[str, int], int]:
    payload = ga4.get("inferred_commercial_program_clicks_28d")
    if not isinstance(payload, dict) or not payload.get("complete"):
        return {}, 0
    return (
        {
            normalize_program(program): int(count)
            for program, count in payload.get("values", {}).items()
        },
        int(payload.get("unattributed_clicks") or 0),
    )


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


def commercial_search_metrics(gsc: dict | None) -> tuple[dict | None, str]:
    if gsc is None:
        return None, "Run report_gsc.py before the business KPI report."
    meta = gsc.get("meta", {})
    if meta.get("page_rows_truncated"):
        return None, "Search Console page totals are truncated."
    pages = gsc.get("pages")
    if not isinstance(pages, list):
        return None, "Search Console page totals are unavailable."
    rules = load_commercial_page_rules()
    selected = [
        row for row in pages if is_commercial_page(row.get("page") or "", rules)
    ]
    impressions = int(sum(float(row.get("impressions") or 0) for row in selected))
    clicks = int(sum(float(row.get("clicks") or 0) for row in selected))
    return {
        "impressions": impressions,
        "clicks": clicks,
        "ctr": (clicks / impressions) if impressions else 0,
        "period": {
            "start": meta.get("start", "?"),
            "end": meta.get("end", "?"),
        },
        "pages": selected,
    }, ""


def previous_commercial_search_metrics(gsc: dict | None) -> tuple[dict | None, str]:
    if gsc is None:
        return None, "Run report_gsc.py before the business KPI report."
    meta = gsc.get("meta", {})
    if meta.get("previous_page_rows_truncated"):
        return None, "Previous Search Console page totals are truncated."
    pages = gsc.get("previous_pages")
    if not isinstance(pages, list):
        return None, "Previous Search Console page totals are unavailable."
    rules = load_commercial_page_rules()
    selected = [
        row for row in pages if is_commercial_page(row.get("page") or "", rules)
    ]
    impressions = int(sum(float(row.get("impressions") or 0) for row in selected))
    clicks = int(sum(float(row.get("clicks") or 0) for row in selected))
    return {
        "impressions": impressions,
        "clicks": clicks,
        "ctr": (clicks / impressions) if impressions else 0,
        "period": {
            "start": meta.get("previous_start", "?"),
            "end": meta.get("previous_end", "?"),
        },
    }, ""


def delta_rate(current: float, previous: float) -> str:
    if previous == 0:
        return "new" if current > 0 else "0.0%"
    return f"{((current - previous) / previous):+.1%}"


def planning_milestones(
    pageviews: int,
    clicks: int,
    *,
    target_yen: int,
    planning_epc: float = 40.0,
) -> list[dict]:
    stages = [
        ("Stage 2", 1_000, 0.03),
        ("Stage 3", 10_000, 0.05),
        (
            "Stage 4",
            math.ceil((target_yen / planning_epc) / 0.08),
            0.08,
        ),
    ]
    current_ctr = (clicks / pageviews) if pageviews else 0
    rows = []
    for name, target_views, target_ctr in stages:
        target_clicks = math.ceil(target_views * target_ctr)
        rows.append(
            {
                "stage": name,
                "target_pageviews": target_views,
                "target_ctr": target_ctr,
                "target_clicks": target_clicks,
                "modeled_revenue": target_clicks * planning_epc,
                "pageview_gap": max(target_views - pageviews, 0),
                "click_gap": max(target_clicks - clicks, 0),
                "ctr_gap": max(target_ctr - current_ctr, 0),
                "reached": pageviews >= target_views and current_ctr >= target_ctr,
            }
        )
    return rows


def next_unmet_milestone(rows: list[dict]) -> dict | None:
    for row in rows:
        if not row.get("reached"):
            return row
    return None


def commercial_page_funnel(search: dict | None, commercial: dict) -> list[dict]:
    search_pages = {
        row.get("page") or "/": row
        for row in ((search or {}).get("pages") or [])
    }
    ga4_pages = {
        row.get("path") or "/": row
        for row in commercial.get("pages", [])
    }
    paths = set(search_pages) | set(ga4_pages)
    rows = []
    for path in paths:
        search_row = search_pages.get(path, {})
        ga4_row = ga4_pages.get(path, {})
        rows.append(
            {
                "path": path,
                "impressions": int(float(search_row.get("impressions") or 0)),
                "search_clicks": int(float(search_row.get("clicks") or 0)),
                "pageviews": int(ga4_row.get("views") or 0),
                "affiliate_clicks": int(ga4_row.get("affiliate_clicks") or 0),
                "active_experiment": bool(search_row.get("active_experiment")),
            }
        )
    rows.sort(
        key=lambda row: (
            -row["impressions"],
            -row["pageviews"],
            row["path"],
        )
    )
    return rows


def experiment_gate(experiment_status: dict | None) -> dict:
    if not isinstance(experiment_status, dict):
        return {
            "available": False,
            "active": 0,
            "collecting": 0,
            "review_due": 0,
            "data_missing": 0,
            "next_review_date": "",
            "reason": "Run report_experiments.py before the business KPI report.",
        }
    summary = experiment_status.get("summary") or {}
    experiments = experiment_status.get("experiments") or []
    collecting_dates = sorted(
        str(row.get("review_date") or "")
        for row in experiments
        if row.get("status") == "collecting" and row.get("review_date")
    )
    due_dates = sorted(
        str(row.get("review_date") or "")
        for row in experiments
        if row.get("status") == "review_due" and row.get("review_date")
    )
    return {
        "available": True,
        "active": int(summary.get("active") or 0),
        "collecting": int(summary.get("collecting") or 0),
        "review_due": int(summary.get("review_due") or 0),
        "data_missing": int(summary.get("data_missing") or 0),
        "next_review_date": (due_dates or collecting_dates or [""])[0],
        "reason": "",
    }


def priority_actions(
    *,
    total_clicks: int,
    revenue_available: bool,
    program_attribution_available: bool,
    all_programs: list[str],
    clicks: dict[str, int],
    revenue_by_program: dict[str, dict[str, float]],
    next_milestone: dict | None,
    revenue_status: RevenueStatus | None,
    selected_revenue_rows: list[RevenueRow],
    page_funnel: list[dict],
    commercial_pages: list[dict],
    experiment_next_review_date: str = "",
) -> list[str]:
    actions: list[str] = []
    if total_clicks == 0:
        actions.append(
            "Verify a real production affiliate click in GA4 DebugView and inspect the highest-view CTA page."
        )
    if revenue_available and program_attribution_available:
        for program in all_programs:
            program_clicks = clicks.get(program, 0)
            program_revenue = revenue_by_program[program]["revenue"]
            if program_clicks > 0 and program_revenue == 0:
                actions.append(
                    f"`{program}` has {program_clicks} clicks but no confirmed revenue; "
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
                f"Scale pages and CTA slots for `{best_program}`, "
                f"the current highest-EPC program ({format_yen(best_epc)} yen/click)."
            )
    if total_clicks > 0 and not program_attribution_available:
        actions.append(
            "Register `affiliate_program` as an event-scoped GA4 custom "
            "dimension so the observed clicks can be separated by revenue program."
        )
    if next_milestone and not (
        revenue_status and revenue_status.blocks_epc_decisions
    ):
        actions.append(
            f"Push toward {next_milestone['stage']}: add search/internal-link lift before broad content production "
            f"({next_milestone['pageview_gap']:,} PV and {next_milestone['click_gap']:,} clicks still needed)."
        )
    if revenue_status and revenue_status.status == "placeholder_zero":
        actions.append(
            f"Replace the all-zero {revenue_status.month} revenue placeholder with confirmed partner/KDP results, or add a note that the dashboards were checked and revenue was truly zero."
        )
    elif revenue_status and revenue_status.status == "partial":
        actions.append(
            f"Complete missing {revenue_status.month} partner rows before treating EPC as final: "
            f"{', '.join(revenue_status.missing_programs)}."
        )
    elif not revenue_available or not selected_revenue_rows:
        month = revenue_status.month if revenue_status else "the selected month"
        actions.append(f"Enter confirmed {month} partner/KDP results in the revenue CSV.")

    active_experiment_paths = {
        row["path"] for row in page_funnel if row.get("active_experiment")
    }
    zero_click_pages = [
        page
        for page in commercial_pages
        if int(page.get("affiliate_clicks", 0)) == 0
        and (page.get("path") or "/") not in active_experiment_paths
        and int(page.get("views", 0)) >= MIN_ZERO_CLICK_ACTION_VIEWS
    ]
    if zero_click_pages:
        page = max(zero_click_pages, key=lambda item: int(item.get("views", 0)))
        actions.append(
            f"Improve the CTA and search-intent match on "
            f"`{page.get('path', '/')}` ({int(page.get('views', 0))} views, zero clicks)."
        )
    elif active_experiment_paths:
        review_hint = f" until {experiment_next_review_date}" if experiment_next_review_date else ""
        actions.append(
            f"Keep zero-click active experiment pages unchanged{review_hint}; use `report_experiments.py` before selecting another page."
        )
    elif commercial_pages:
        actions.append(
            f"Do not spend this cycle on low-volume zero-click pages; wait for at least {MIN_ZERO_CLICK_ACTION_VIEWS} views or improve search/internal links first."
        )
    if not actions:
        actions.append("Preserve the current winners and test one CTA or internal-link change this week.")
    return actions


def numbered_actions(actions: list[str]) -> list[str]:
    return [f"{index + 1}. {action}" for index, action in enumerate(actions)]


def build_report(
    ga4: dict,
    rows: list[RevenueRow],
    month: str,
    target_yen: int,
    *,
    revenue_available: bool = True,
    revenue_status: RevenueStatus | None = None,
    gsc: dict | None = None,
    experiment_status: dict | None = None,
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
    inferred_program_clicks, inferred_unattributed = inferred_commercial_program_clicks(ga4)
    store_click_breakdown = store_clicks(ga4)
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
    search, search_reason = commercial_search_metrics(gsc)
    previous_search, previous_search_reason = previous_commercial_search_metrics(gsc)
    previous_commercial = ga4.get("previous_commercial_metrics_28d")
    previous_commercial_available = (
        isinstance(previous_commercial, dict)
        and previous_commercial.get("complete")
    )
    page_funnel = commercial_page_funnel(search, commercial)
    milestones = planning_milestones(
        pageviews,
        commercial_clicks,
        target_yen=target_yen,
    )
    next_milestone = next_unmet_milestone(milestones)
    experiments = experiment_gate(experiment_status)

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
        "## Revenue Input Gate",
        "",
        "| Item | Status |",
        "| --- | --- |",
    ]
    if revenue_status:
        lines.extend(
            [
                f"| Revenue CSV state | {revenue_status.status} |",
                f"| EPC/conversion decisions | "
                f"{'blocked' if revenue_status.blocks_epc_decisions else 'usable'} |",
                f"| Revenue rows for {month} | {revenue_status.rows} |",
                f"| Partner/KDP input note | {revenue_status.message} |",
            ]
        )
        if revenue_status.missing_programs:
            lines.append(
                f"| Missing programs | {', '.join(revenue_status.missing_programs)} |"
            )
    else:
        lines.append(
            "| Revenue CSV state | not checked by this report invocation |"
        )
    lines.extend(
        [
        "",
        "## Commercial Search Funnel",
        "",
        "| Stage | 28-day value | Rate |",
        "| --- | ---: | ---: |",
        ]
    )
    if search:
        lines.extend(
            [
                f"| Search impressions | {search['impressions']:,} | - |",
                f"| Search clicks | {search['clicks']:,} | {search['ctr']:.2%} search CTR |",
                f"| GA4 pageviews | {pageviews:,} | - |",
                f"| Affiliate clicks | {commercial_clicks:,} | {ctr:.2%} pageview-to-affiliate CTR |",
            ]
        )
    else:
        lines.extend(
            [
                f"| Search Console unavailable | - | {search_reason} |",
                f"| GA4 pageviews | {pageviews:,} | - |",
                f"| Affiliate clicks | {commercial_clicks:,} | {ctr:.2%} pageview-to-affiliate CTR |",
            ]
        )
    lines.extend(
        [
        "",
        "## Previous 28-Day Trend",
        "",
        "| KPI | Current | Previous | Change |",
        "| --- | ---: | ---: | ---: |",
        ]
    )
    if search and previous_search:
        lines.extend(
            [
                f"| Commercial search impressions | {search['impressions']:,} | "
                f"{previous_search['impressions']:,} | "
                f"{delta_rate(search['impressions'], previous_search['impressions'])} |",
                f"| Commercial search clicks | {search['clicks']:,} | "
                f"{previous_search['clicks']:,} | "
                f"{delta_rate(search['clicks'], previous_search['clicks'])} |",
                f"| Commercial search CTR | {search['ctr']:.2%} | "
                f"{previous_search['ctr']:.2%} | "
                f"{(search['ctr'] - previous_search['ctr']):+.2%} pt |",
            ]
        )
    else:
        lines.append(
            f"| Search metrics | - | - | "
            f"{search_reason or previous_search_reason} |"
        )
    if previous_commercial_available:
        previous_views = int(previous_commercial.get("pageviews", 0))
        previous_clicks = int(previous_commercial.get("affiliate_clicks", 0))
        previous_ctr = float(previous_commercial.get("affiliate_ctr", 0))
        lines.extend(
            [
                f"| Commercial pageviews | {pageviews:,} | {previous_views:,} | "
                f"{delta_rate(pageviews, previous_views)} |",
                f"| Affiliate clicks | {commercial_clicks:,} | {previous_clicks:,} | "
                f"{delta_rate(commercial_clicks, previous_clicks)} |",
                f"| Pageview-to-affiliate CTR | {ctr:.2%} | {previous_ctr:.2%} | "
                f"{(ctr - previous_ctr):+.2%} pt |",
            ]
        )
    else:
        lines.append("| GA4 commercial metrics | - | - | Previous period unavailable |")
    lines.extend(
        [
            "",
            "## Growth Milestones",
            "",
            "| Stage | Target commercial PV | Target CTR | Target clicks | Current gap | Modeled revenue at 40 yen EPC |",
            "| --- | ---: | ---: | ---: | --- | ---: |",
        ]
    )
    for row in milestones:
        gap = (
            "reached"
            if row["reached"]
            else (
                f"{row['pageview_gap']:,} PV, {row['click_gap']:,} clicks, "
                f"{row['ctr_gap']:.2%} pt CTR"
            )
        )
        lines.append(
            f"| {row['stage']} | {row['target_pageviews']:,} | "
            f"{row['target_ctr']:.2%} | {row['target_clicks']:,} | "
            f"{gap} | {format_yen(row['modeled_revenue'])} yen |"
        )
    lines.extend(
        [
            "",
            "Milestone revenue is a planning model, not confirmed revenue. Replace the "
            "40 yen EPC assumption with partner-report results before using it for forecasts.",
        ]
    )
    lines.extend(["", "## Next Milestone", ""])
    if next_milestone:
        lines.extend(
            [
                f"Next target: {next_milestone['stage']} "
                f"({next_milestone['target_pageviews']:,} commercial PV, "
                f"{next_milestone['target_ctr']:.2%} CTR, "
                f"{next_milestone['target_clicks']:,} clicks).",
                "",
                "| Gap | Remaining |",
                "| --- | ---: |",
                f"| Commercial PV | {next_milestone['pageview_gap']:,} |",
                f"| Affiliate clicks | {next_milestone['click_gap']:,} |",
                f"| CTR points | {next_milestone['ctr_gap']:.2%} pt |",
            ]
        )
    else:
        lines.append("All configured planning milestones are currently reached.")
    lines.extend(
        [
            "",
            "## Experiment Gate",
            "",
            "| Item | Status |",
            "| --- | --- |",
        ]
    )
    if experiments["available"]:
        lines.extend(
            [
                f"| Active experiments | {experiments['active']} |",
                f"| Collecting | {experiments['collecting']} |",
                f"| Review due | {experiments['review_due']} |",
                f"| Data missing | {experiments['data_missing']} |",
                f"| Next review date | {experiments['next_review_date'] or '-'} |",
            ]
        )
    else:
        lines.append(f"| Experiment status | unavailable: {experiments['reason']} |")
    lines.extend(
        [
        "",
        "## Commercial Page Funnel",
        "",
        "| Search impressions | Search clicks | GA4 PV | Affiliate clicks | Experiment | Page |",
        "| ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    if page_funnel:
        for row in page_funnel[:12]:
            experiment = "active" if row["active_experiment"] else "-"
            lines.append(
                f"| {row['impressions']:,} | {row['search_clicks']:,} | "
                f"{row['pageviews']:,} | {row['affiliate_clicks']:,} | "
                f"{experiment} | `{row['path']}` |"
            )
    else:
        lines.append("| 0 | 0 | 0 | 0 | - | No commercial page rows |")
    lines.extend(
        [
        "",
        "## Program Performance",
        "",
        "| Program | Clicks (28d) | Orders | Revenue | EPC |",
        "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
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
        if inferred_program_clicks:
            lines.extend(
                [
                    "",
                    "## Inferred Program Clicks",
                    "",
                    "| Program | Inferred clicks (28d) |",
                    "| --- | ---: |",
                ]
            )
            for program, count in sorted(
                inferred_program_clicks.items(),
                key=lambda item: (-item[1], item[0]),
            ):
                lines.append(f"| {program} | {count:,} |")
            lines.extend(
                [
                    "",
                    "These values are inferred only when the registered store and CTA slot "
                    "identify one program unambiguously. They are not used for EPC decisions.",
                ]
            )
            if inferred_unattributed:
                lines.append(
                    f"Unattributed commercial clicks: {inferred_unattributed:,}."
                )
        if store_click_breakdown:
            lines.extend(
                [
                    "",
                    "## Store Click Fallback",
                    "",
                    "| Store | Clicks (28d) |",
                    "| --- | ---: |",
                ]
            )
            for store, count in sorted(
                store_click_breakdown.items(),
                key=lambda item: (-item[1], item[0]),
            ):
                lines.append(f"| {store} | {count:,} |")
            lines.extend(
                [
                    "",
                    "Store attribution remains usable, but Amazon clicks cannot be split into "
                    "standard products, Kindle Unlimited, and Audible until `affiliate_program` "
                    "is registered.",
                ]
            )

    lines.extend(["", "## Priority Actions", ""])
    actions = priority_actions(
        total_clicks=total_clicks,
        revenue_available=revenue_available,
        program_attribution_available=program_attribution_available,
        all_programs=all_programs,
        clicks=clicks,
        revenue_by_program=revenue_by_program,
        next_milestone=next_milestone,
        revenue_status=revenue_status,
        selected_revenue_rows=selected,
        page_funnel=page_funnel,
        commercial_pages=commercial["pages"],
        experiment_next_review_date=str(experiments.get("next_review_date") or ""),
    )
    lines.extend(numbered_actions(actions))
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
            (
                f"Search Console period: {search['period']['start']} to {search['period']['end']}. "
                "GA4 and Search Console periods differ by reporting delay, so compare stages directionally."
                if search
                else f"Search funnel status: {search_reason}"
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def build_summary(
    ga4: dict,
    rows: list[RevenueRow],
    month: str,
    target_yen: int,
    *,
    revenue_available: bool = True,
    revenue_status: RevenueStatus | None = None,
    gsc: dict | None = None,
    experiment_status: dict | None = None,
) -> dict:
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
    search, search_reason = commercial_search_metrics(gsc)
    page_funnel = commercial_page_funnel(search, commercial)
    milestones = planning_milestones(
        pageviews,
        commercial_clicks,
        target_yen=target_yen,
    )
    next_milestone = next_unmet_milestone(milestones)
    experiments = experiment_gate(experiment_status)
    actions = priority_actions(
        total_clicks=total_clicks,
        revenue_available=revenue_available,
        program_attribution_available=program_attribution_available,
        all_programs=all_programs,
        clicks=clicks,
        revenue_by_program=revenue_by_program,
        next_milestone=next_milestone,
        revenue_status=revenue_status,
        selected_revenue_rows=selected,
        page_funnel=page_funnel,
        commercial_pages=commercial["pages"],
        experiment_next_review_date=str(experiments.get("next_review_date") or ""),
    )
    return {
        "month": month,
        "ga4_period": ga4.get("range_28d", {}),
        "scorecard": {
            "target_yen": target_yen,
            "confirmed_revenue_yen": total_revenue if revenue_available else None,
            "revenue_progress": progress if revenue_available else None,
            "orders": total_orders if revenue_available else None,
            "all_pageviews_28d": total_pageviews,
            "commercial_pageviews_28d": pageviews,
            "affiliate_clicks_28d": total_clicks,
            "commercial_affiliate_clicks_28d": commercial_clicks,
            "commercial_affiliate_ctr_28d": ctr,
            "confirmed_commercial_epc_yen": epc if revenue_available else None,
        },
        "revenue_gate": {
            "status": revenue_status.status if revenue_status else "not_checked",
            "blocks_epc_decisions": (
                revenue_status.blocks_epc_decisions if revenue_status else None
            ),
            "rows": revenue_status.rows if revenue_status else None,
            "orders": revenue_status.orders if revenue_status else None,
            "revenue_yen": revenue_status.revenue_yen if revenue_status else None,
            "missing_programs": list(revenue_status.missing_programs)
            if revenue_status
            else [],
            "message": revenue_status.message if revenue_status else "",
        },
        "program_attribution": {
            "available": program_attribution_available,
            "reason": program_attribution_reason,
        },
        "search_funnel": {
            "available": bool(search),
            "reason": "" if search else search_reason,
            "impressions": search["impressions"] if search else None,
            "clicks": search["clicks"] if search else None,
            "ctr": search["ctr"] if search else None,
        },
        "next_milestone": next_milestone,
        "experiment_gate": experiments,
        "priority_actions": actions,
    }


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
    parser.add_argument(
        "--gsc-json",
        type=Path,
        default=Path("reports/analytics/gsc-latest.json"),
    )
    parser.add_argument(
        "--experiments-json",
        type=Path,
        default=Path("reports/analytics/experiment-status.json"),
    )
    parser.add_argument("--month", help="Revenue month in YYYY-MM; defaults to latest CSV month")
    parser.add_argument("--target-yen", type=int, default=100_000)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/analytics/business-kpi.md"),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("reports/analytics/business-kpi-summary.json"),
    )
    args = parser.parse_args()

    ga4 = read_ga4(resolve_path(args.ga4_json))
    gsc = read_optional_json(resolve_path(args.gsc_json))
    experiment_status = read_optional_json(resolve_path(args.experiments_json))
    revenue_path = resolve_path(args.revenue_csv)
    rows = read_revenue(revenue_path, allow_missing=True)
    generated_month = str(ga4.get("generated_on") or "")[:7]
    month = args.month or max((row.month for row in rows), default=generated_month)
    if not month:
        raise SystemExit("Provide --month when GA4 generated_on and revenue rows are unavailable.")
    if args.target_yen <= 0:
        raise SystemExit("--target-yen must be greater than 0")
    revenue_status = evaluate_revenue_status(revenue_path, month)
    revenue_available = not revenue_status.blocks_epc_decisions

    report = build_report(
        ga4,
        rows,
        month,
        args.target_yen,
        revenue_available=revenue_available,
        revenue_status=revenue_status,
        gsc=gsc,
        experiment_status=experiment_status,
    )
    summary = build_summary(
        ga4,
        rows,
        month,
        args.target_yen,
        revenue_available=revenue_available,
        revenue_status=revenue_status,
        gsc=gsc,
        experiment_status=experiment_status,
    )
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    json_output = resolve_path(args.json_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(report, end="")
    print(f"\nReport written to: {output}")
    print(f"JSON summary written to: {json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
