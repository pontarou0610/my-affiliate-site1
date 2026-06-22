#!/usr/bin/env python3
"""Report Google Search Console query and page SEO opportunities."""

from __future__ import annotations

import argparse
import csv
import json
import os
import posixpath
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build


REPO_ROOT = Path(__file__).resolve().parents[1]
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
EXPERIMENTS_PATH = REPO_ROOT / "data" / "optimization-experiments.csv"


def env_path(name: str) -> Path:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        raise SystemExit(f"{name} is not set in .env")
    path = Path(raw)
    return path if path.is_absolute() else REPO_ROOT / path


def normalize_page(value: str) -> str:
    path = urlparse(value).path or "/"
    prefix = "/my-affiliate-site1"
    if path == prefix:
        path = "/"
    elif path.startswith(f"{prefix}/"):
        path = path[len(prefix) :]
    normalized = posixpath.normpath(f"/{path.lstrip('/')}")
    if normalized != "/" and path.endswith("/"):
        normalized += "/"
    return normalized


def active_experiment_pages(path: Path = EXPERIMENTS_PATH) -> set[str]:
    if not path.exists():
        return set()
    pages: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("status") or "").strip().lower() == "active":
                pages.add(normalize_page(row.get("page") or ""))
    return pages


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


def is_noise_query(query: str) -> bool:
    normalized = query.strip().lower()
    return (
        normalized.startswith("site:")
        or " -site:" in normalized
        or normalized.count('"') >= 2
    )


def fetch_rows(days: int, max_rows: int) -> tuple[list[dict], dict]:
    load_dotenv(REPO_ROOT / ".env")
    site_url = (os.getenv("GSC_SITE_URL") or "").strip()
    if not site_url:
        raise SystemExit("GSC_SITE_URL is not set in .env")
    credentials_path = env_path("GSC_SERVICE_ACCOUNT_FILE")
    if not credentials_path.exists():
        raise SystemExit(f"GSC credential file not found: {credentials_path}")

    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=max(1, days) - 1)
    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path),
        scopes=SCOPES,
    )
    service = build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
    rows: list[dict] = []
    start_row = 0
    truncated = False
    while len(rows) < max_rows:
        row_limit = min(25_000, max_rows - len(rows))
        response = (
            service.searchanalytics()
            .query(
                siteUrl=site_url,
                body={
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "dimensions": ["date", "query", "page"],
                    "rowLimit": row_limit,
                    "startRow": start_row,
                    "dataState": "final",
                },
            )
            .execute()
        )
        batch = response.get("rows") or []
        if not batch:
            break
        for row in batch:
            keys = row.get("keys") or []
            if len(keys) < 3:
                continue
            query = " ".join(str(keys[1]).split())
            if is_noise_query(query):
                continue
            rows.append(
                {
                    "query": query,
                    "page": normalize_page(str(keys[2])),
                    "date": str(keys[0]),
                    "clicks": float(row.get("clicks") or 0),
                    "impressions": float(row.get("impressions") or 0),
                    "ctr": float(row.get("ctr") or 0),
                    "position": float(row.get("position") or 0),
                }
            )
        if len(batch) < row_limit:
            break
        start_row += len(batch)
    if len(rows) >= max_rows:
        truncated = True
    return rows, {
        "site_url": site_url,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "daily_rows_truncated": truncated,
    }


def aggregate_pages(rows: list[dict], active_pages: set[str]) -> list[dict]:
    totals: dict[str, dict] = defaultdict(
        lambda: {"clicks": 0.0, "impressions": 0.0, "position_sum": 0.0}
    )
    for row in rows:
        impressions = row["impressions"]
        item = totals[row["page"]]
        item["clicks"] += row["clicks"]
        item["impressions"] += impressions
        item["position_sum"] += row["position"] * impressions

    pages = []
    for page, item in totals.items():
        impressions = item["impressions"]
        clicks = item["clicks"]
        position = item["position_sum"] / impressions if impressions else 0
        ctr = clicks / impressions if impressions else 0
        potential_clicks = max(expected_ctr(position) * impressions - clicks, 0)
        pages.append(
            {
                "page": page,
                "clicks": clicks,
                "impressions": impressions,
                "ctr": ctr,
                "position": position,
                "potential_clicks": potential_clicks,
                "active_experiment": page in active_pages,
            }
        )
    pages.sort(
        key=lambda item: (
            item["active_experiment"],
            -item["potential_clicks"],
            -item["impressions"],
        )
    )
    return pages


def query_opportunities(rows: list[dict], active_pages: set[str]) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"clicks": 0.0, "impressions": 0.0, "position_sum": 0.0}
    )
    for row in rows:
        key = (row["query"], row["page"])
        item = grouped[key]
        item["clicks"] += row["clicks"]
        item["impressions"] += row["impressions"]
        item["position_sum"] += row["position"] * row["impressions"]

    opportunities = []
    for (query, page), item in grouped.items():
        impressions = item["impressions"]
        clicks = item["clicks"]
        position = item["position_sum"] / impressions if impressions else 0
        ctr = clicks / impressions if impressions else 0
        potential_clicks = max(expected_ctr(position) * impressions - clicks, 0)
        opportunities.append(
            {
                "query": query,
                "page": page,
                "clicks": clicks,
                "impressions": impressions,
                "ctr": ctr,
                "position": position,
                "potential_clicks": potential_clicks,
                "active_experiment": page in active_pages,
            }
        )
    opportunities.sort(
        key=lambda item: (
            item["active_experiment"],
            -item["potential_clicks"],
            -item["impressions"],
        )
    )
    return opportunities


def scale_candidates(pages: list[dict]) -> list[dict]:
    candidates = [
        row
        for row in pages
        if not row["active_experiment"]
        and row["clicks"] > 0
        and row["ctr"] >= expected_ctr(row["position"])
    ]
    candidates.sort(
        key=lambda item: (
            -item["clicks"],
            -item["ctr"],
            -item["impressions"],
        )
    )
    return candidates


def format_report(payload: dict, limit: int) -> str:
    meta = payload["meta"]
    lines = [
        "# Search Console Opportunity Report",
        "",
        f"Period: {meta['start']} to {meta['end']}",
        f"Rows: {meta['row_count']:,}",
        "",
        "## Page Opportunities",
        "",
        "| Impressions | Clicks | CTR | Position | Est. click gap | Page |",
        "| ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    available_pages = [
        row
        for row in payload["pages"]
        if not row["active_experiment"] and row["potential_clicks"] > 0.01
    ][:limit]
    if not available_pages:
        lines.append("| 0 | 0 | 0.00% | 0.0 | 0.0 | No available pages |")
    for row in available_pages:
        lines.append(
            f"| {row['impressions']:.0f} | {row['clicks']:.0f} | "
            f"{row['ctr']:.2%} | {row['position']:.1f} | "
            f"{row['potential_clicks']:.1f} | `{row['page']}` |"
        )

    lines.extend(
        [
            "",
            "## Query Opportunities",
            "",
            "| Impressions | Clicks | CTR | Position | Query | Page |",
            "| ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    available_queries = [
        row
        for row in payload["queries"]
        if not row["active_experiment"]
        and row["impressions"] >= 2
        and row["potential_clicks"] > 0.01
    ][:limit]
    if not available_queries:
        lines.append("| 0 | 0 | 0.00% | 0.0 | No available queries | - |")
    for row in available_queries:
        lines.append(
            f"| {row['impressions']:.0f} | {row['clicks']:.0f} | "
            f"{row['ctr']:.2%} | {row['position']:.1f} | "
            f"{row['query']} | `{row['page']}` |"
        )

    lines.extend(
        [
            "",
            "## Scale Candidates",
            "",
            "| Impressions | Clicks | CTR | Position | Page |",
            "| ---: | ---: | ---: | ---: | --- |",
        ]
    )
    candidates = payload["scale_candidates"][:limit]
    if not candidates:
        lines.append("| 0 | 0 | 0.00% | 0.0 | No proven pages yet |")
    for row in candidates:
        lines.append(
            f"| {row['impressions']:.0f} | {row['clicks']:.0f} | "
            f"{row['ctr']:.2%} | {row['position']:.1f} | `{row['page']}` |"
        )

    active_count = sum(1 for row in payload["pages"] if row["active_experiment"])
    lines.extend(
        [
            "",
            f"Active experiment pages excluded from priority ranking: {active_count}",
            "",
            "The estimated click gap uses a conservative position-based CTR benchmark. "
            "Use it for prioritization, not as a revenue forecast.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--max-rows", type=int, default=2_000)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("reports/analytics/gsc-latest.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("reports/analytics/gsc-opportunities.md"),
    )
    args = parser.parse_args()
    if args.days <= 0 or args.max_rows <= 0 or args.top <= 0:
        raise SystemExit("--days, --max-rows, and --top must be greater than 0")

    rows, meta = fetch_rows(args.days, args.max_rows)
    active_pages = active_experiment_pages()
    payload = {
        "meta": {**meta, "row_count": len(rows)},
        "pages": aggregate_pages(rows, active_pages),
        "queries": query_opportunities(rows, active_pages),
        "daily_rows": rows,
    }
    payload["scale_candidates"] = scale_candidates(payload["pages"])
    json_output = args.json_output if args.json_output.is_absolute() else REPO_ROOT / args.json_output
    markdown_output = (
        args.markdown_output
        if args.markdown_output.is_absolute()
        else REPO_ROOT / args.markdown_output
    )
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = format_report(payload, args.top)
    markdown_output.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"\nJSON report: {json_output}")
    print(f"Markdown report: {markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
