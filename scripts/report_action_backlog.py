#!/usr/bin/env python3
"""Build a prioritized weekly action backlog from GA4, GSC, and KPI gates."""

from __future__ import annotations

import argparse
import csv
import json
import posixpath
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GA4 = REPO_ROOT / "reports" / "analytics" / "ga4-latest.json"
DEFAULT_GSC = REPO_ROOT / "reports" / "analytics" / "gsc-latest.json"
DEFAULT_SUMMARY = REPO_ROOT / "reports" / "analytics" / "business-kpi-summary.json"
DEFAULT_EXPERIMENTS = REPO_ROOT / "data" / "optimization-experiments.csv"
DEFAULT_MARKDOWN = REPO_ROOT / "reports" / "analytics" / "action-backlog.md"
DEFAULT_JSON = REPO_ROOT / "reports" / "analytics" / "action-backlog.json"


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def normalize_page(value: str) -> str:
    path = urlparse(value or "/").path or "/"
    prefix = "/my-affiliate-site1"
    if path == prefix:
        path = "/"
    elif path.startswith(f"{prefix}/"):
        path = path[len(prefix) :]
    normalized = posixpath.normpath(f"/{path.lstrip('/')}")
    if normalized != "/":
        normalized += "/"
    return normalized


def read_json(path: Path, label: str) -> dict:
    if not path.exists():
        raise SystemExit(f"{label} not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} is invalid JSON: {path}") from exc


def active_experiment_pages(path: Path, gsc: dict) -> set[str]:
    pages = {
        normalize_page(row.get("page") or "")
        for row in gsc.get("pages", [])
        if row.get("active_experiment")
    }
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if (row.get("status") or "").strip().lower() == "active":
                    pages.add(normalize_page(row.get("page") or ""))
    return {page for page in pages if page}


def expected_ctr(position: float) -> float:
    if position <= 3:
        return 0.12
    if position <= 5:
        return 0.07
    if position <= 10:
        return 0.03
    if position <= 20:
        return 0.015
    if position <= 30:
        return 0.01
    return 0.005


def add_candidate(candidates: list[dict], candidate: dict) -> None:
    key = (candidate["page"], candidate["type"])
    if any((item["page"], item["type"]) == key for item in candidates):
        return
    candidates.append(candidate)


def build_candidates(
    ga4: dict,
    gsc: dict,
    summary: dict,
    active_pages: set[str],
    *,
    min_impressions: int = 5,
    min_views: int = 5,
) -> list[dict]:
    candidates: list[dict] = []
    milestone = summary.get("next_milestone") or {}
    click_gap = float(milestone.get("click_gap") or 0)
    ctr_gap = float(milestone.get("ctr_gap") or 0)

    for row in gsc.get("scale_candidates", []):
        page = normalize_page(row.get("page") or "")
        if page in active_pages:
            continue
        clicks = float(row.get("clicks") or 0)
        impressions = float(row.get("impressions") or 0)
        if clicks <= 0 or impressions < min_impressions:
            continue
        add_candidate(
            candidates,
            {
                "type": "scale_proven_search_page",
                "page": page,
                "score": round(50 + clicks * 10 + impressions / 10, 2),
                "reason": (
                    f"Search already produced {clicks:.0f} clicks from "
                    f"{impressions:.0f} impressions; add internal links or a supporting article."
                ),
            },
        )

    for row in gsc.get("pages", []):
        page = normalize_page(row.get("page") or "")
        if page in active_pages:
            continue
        impressions = float(row.get("impressions") or 0)
        clicks = float(row.get("clicks") or 0)
        position = float(row.get("position") or 0)
        ctr = float(row.get("ctr") or 0)
        benchmark = expected_ctr(position)
        if impressions < min_impressions or clicks > 0 or ctr >= benchmark * 0.5:
            continue
        potential = float(row.get("potential_clicks") or 0)
        add_candidate(
            candidates,
            {
                "type": "lift_search_ctr",
                "page": page,
                "score": round(40 + impressions / 3 + potential * 25 + max(ctr_gap, 0) * 100, 2),
                "reason": (
                    f"{impressions:.0f} search impressions and 0 clicks at position "
                    f"{position:.1f}; rewrite title/description for query intent."
                ),
            },
        )

    commercial = ga4.get("commercial_metrics_28d") or {}
    for row in commercial.get("pages", []):
        page = normalize_page(row.get("path") or "")
        if page in active_pages:
            continue
        views = float(row.get("views") or 0)
        clicks = float(row.get("affiliate_clicks") or 0)
        if views < min_views or clicks > 0:
            continue
        add_candidate(
            candidates,
            {
                "type": "improve_zero_click_cta",
                "page": page,
                "score": round(35 + views * 2 + min(click_gap, 10), 2),
                "reason": (
                    f"{views:.0f} commercial pageviews but no affiliate clicks; "
                    "tighten the first CTA and match it to the page intent."
                ),
            },
        )

    candidates.sort(key=lambda item: (-item["score"], item["page"], item["type"]))
    return candidates


def format_backlog(payload: dict, limit: int) -> str:
    summary = payload.get("summary") or {}
    milestone = summary.get("next_milestone") or {}
    gates = []
    revenue_gate = summary.get("revenue_gate") or {}
    program_gate = summary.get("program_attribution") or {}
    if revenue_gate.get("blocks_epc_decisions"):
        gates.append(f"revenue={revenue_gate.get('status', 'blocked')}")
    if not program_gate.get("available", False):
        gates.append("affiliate_program=missing")
    gate_text = ", ".join(gates) if gates else "clear"

    lines = [
        "# Weekly Action Backlog",
        "",
        f"Gate: {gate_text}",
        "",
    ]
    if milestone:
        lines.extend(
            [
                "## Next Milestone",
                "",
                (
                    f"{milestone.get('stage', 'Next')}: "
                    f"{milestone.get('pageview_gap', 0):,} PV, "
                    f"{milestone.get('click_gap', 0):,} clicks, "
                    f"{float(milestone.get('ctr_gap') or 0):.2%} pt CTR remaining."
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## Prioritized Work",
            "",
            "| Rank | Type | Score | Page | Reason |",
            "| ---: | --- | ---: | --- | --- |",
        ]
    )
    candidates = payload.get("candidates", [])[:limit]
    if not candidates:
        lines.append("| 0 | - | 0 | - | No unlocked action candidate found. |")
    for index, item in enumerate(candidates, start=1):
        lines.append(
            f"| {index} | `{item['type']}` | {item['score']:.2f} | "
            f"`{item['page']}` | {item['reason']} |"
        )

    lines.extend(
        [
            "",
            "Use this backlog for the weekly edit only after the analytics freshness gate passes. "
            "Active experiment pages are excluded so their review windows stay clean.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_payload(args: argparse.Namespace) -> dict:
    ga4 = read_json(resolve_path(args.ga4_json), "GA4 JSON")
    gsc = read_json(resolve_path(args.gsc_json), "GSC JSON")
    summary = read_json(resolve_path(args.summary_json), "Business KPI summary")
    active_pages = active_experiment_pages(resolve_path(args.experiments_csv), gsc)
    candidates = build_candidates(
        ga4,
        gsc,
        summary,
        active_pages,
        min_impressions=args.min_impressions,
        min_views=args.min_views,
    )
    return {
        "ga4_period": ga4.get("range_28d") or {},
        "gsc_period": gsc.get("meta") or {},
        "summary": summary,
        "active_experiment_pages": sorted(active_pages),
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ga4-json", type=Path, default=DEFAULT_GA4)
    parser.add_argument("--gsc-json", type=Path, default=DEFAULT_GSC)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--experiments-csv", type=Path, default=DEFAULT_EXPERIMENTS)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--min-impressions", type=int, default=5)
    parser.add_argument("--min-views", type=int, default=5)
    args = parser.parse_args()
    if args.top <= 0 or args.min_impressions <= 0 or args.min_views <= 0:
        raise SystemExit("--top, --min-impressions, and --min-views must be greater than 0")

    payload = build_payload(args)
    markdown = format_backlog(payload, args.top)
    markdown_output = resolve_path(args.markdown_output)
    json_output = resolve_path(args.json_output)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(markdown, encoding="utf-8")
    json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(markdown, end="")
    print(f"\nJSON report: {json_output}")
    print(f"Markdown report: {markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
