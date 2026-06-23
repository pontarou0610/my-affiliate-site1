#!/usr/bin/env python3
"""Record one aggregate analytics snapshot in a versioned CSV history."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from report_ga4 import is_commercial_page, load_commercial_page_rules


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GA4 = REPO_ROOT / "reports" / "analytics" / "ga4-latest.json"
DEFAULT_GSC = REPO_ROOT / "reports" / "analytics" / "gsc-latest.json"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "analytics-kpi-history.csv"
FIELDS = [
    "snapshot_date",
    "ga4_start",
    "ga4_end",
    "all_pageviews",
    "commercial_pageviews",
    "affiliate_clicks",
    "commercial_affiliate_clicks",
    "commercial_affiliate_ctr",
    "gsc_start",
    "gsc_end",
    "commercial_search_impressions",
    "commercial_search_clicks",
    "commercial_search_ctr",
    "amazon_clicks_inferred",
    "kindle_unlimited_clicks_inferred",
    "audible_clicks_inferred",
    "rakuten_clicks_inferred",
    "yahoo_clicks_inferred",
    "kdp_clicks_inferred",
    "unattributed_clicks",
]


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Analytics JSON not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Analytics JSON is invalid: {path}") from exc


def normalize_page(path: str) -> str:
    cleaned = "/" + str(path or "").strip().lstrip("/")
    return cleaned if cleaned.endswith("/") else cleaned + "/"


def validate_commercial_metrics(ga4: dict) -> dict:
    commercial = ga4.get("commercial_metrics_28d")
    if not isinstance(commercial, dict) or not commercial.get("complete"):
        raise SystemExit("GA4 commercial_metrics_28d is missing or incomplete.")
    return commercial


def build_snapshot(
    ga4: dict,
    gsc: dict,
    rules: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    commercial = validate_commercial_metrics(ga4)
    commercial_rules = rules if rules is not None else load_commercial_page_rules()
    if gsc.get("meta", {}).get("page_rows_truncated"):
        raise SystemExit("GSC page totals are truncated.")
    selected_pages = [
        row
        for row in gsc.get("pages", [])
        if is_commercial_page(normalize_page(row.get("page") or ""), commercial_rules)
    ]
    impressions = int(sum(float(row.get("impressions") or 0) for row in selected_pages))
    search_clicks = int(sum(float(row.get("clicks") or 0) for row in selected_pages))
    inferred = ga4.get("inferred_commercial_program_clicks_28d") or {}
    inferred_values = inferred.get("values", {}) if inferred.get("complete") else {}
    generated_on = str(ga4.get("generated_on") or "").strip()
    if not generated_on:
        raise SystemExit("GA4 generated_on is missing.")
    affiliate_clicks = int(ga4.get("affiliate_clicks_28d") or 0)
    commercial_clicks = int(commercial.get("affiliate_clicks") or 0)
    commercial_views = int(commercial.get("pageviews") or 0)
    return {
        "snapshot_date": generated_on,
        "ga4_start": str(ga4.get("range_28d", {}).get("start") or ""),
        "ga4_end": str(ga4.get("range_28d", {}).get("end") or ""),
        "all_pageviews": str(int(ga4.get("totals_28d", {}).get("pageviews") or 0)),
        "commercial_pageviews": str(commercial_views),
        "affiliate_clicks": str(affiliate_clicks),
        "commercial_affiliate_clicks": str(commercial_clicks),
        "commercial_affiliate_ctr": f"{(commercial_clicks / commercial_views) if commercial_views else 0:.6f}",
        "gsc_start": str(gsc.get("meta", {}).get("start") or ""),
        "gsc_end": str(gsc.get("meta", {}).get("end") or ""),
        "commercial_search_impressions": str(impressions),
        "commercial_search_clicks": str(search_clicks),
        "commercial_search_ctr": f"{(search_clicks / impressions) if impressions else 0:.6f}",
        "amazon_clicks_inferred": str(int(inferred_values.get("amazon") or 0)),
        "kindle_unlimited_clicks_inferred": str(
            int(inferred_values.get("kindle_unlimited") or 0)
        ),
        "audible_clicks_inferred": str(int(inferred_values.get("audible") or 0)),
        "rakuten_clicks_inferred": str(int(inferred_values.get("rakuten") or 0)),
        "yahoo_clicks_inferred": str(int(inferred_values.get("yahoo") or 0)),
        "kdp_clicks_inferred": str(int(inferred_values.get("kdp") or 0)),
        "unattributed_clicks": str(int(inferred.get("unattributed_clicks") or 0)),
    }


def read_history(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise SystemExit(f"KPI history has unexpected columns: {path}")
        return list(reader)


def upsert_snapshot(rows: list[dict[str, str]], snapshot: dict[str, str]) -> list[dict[str, str]]:
    by_date = {row["snapshot_date"]: row for row in rows}
    by_date[snapshot["snapshot_date"]] = snapshot
    return [by_date[key] for key in sorted(by_date)]


def write_history(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ga4", type=Path, default=DEFAULT_GA4)
    parser.add_argument("--gsc", type=Path, default=DEFAULT_GSC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    snapshot = build_snapshot(read_json(args.ga4), read_json(args.gsc))
    rows = upsert_snapshot(read_history(args.output), snapshot)
    write_history(args.output, rows)
    print(
        f"Recorded KPI snapshot {snapshot['snapshot_date']}: "
        f"{snapshot['commercial_pageviews']} commercial PV, "
        f"{snapshot['commercial_affiliate_clicks']} affiliate clicks, "
        f"{snapshot['commercial_search_clicks']} search clicks."
    )
    print(f"History: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
