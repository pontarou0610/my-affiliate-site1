#!/usr/bin/env python3
"""Build a progress report for active SEO and affiliate experiments."""

from __future__ import annotations

import argparse
import csv
import json
import posixpath
from datetime import date, datetime, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPERIMENTS = REPO_ROOT / "data" / "optimization-experiments.csv"
DEFAULT_GA4 = REPO_ROOT / "reports" / "analytics" / "ga4-latest.json"
DEFAULT_GSC = REPO_ROOT / "reports" / "analytics" / "gsc-latest.json"
DEFAULT_JSON = REPO_ROOT / "reports" / "analytics" / "experiment-status.json"
DEFAULT_MARKDOWN = REPO_ROOT / "reports" / "analytics" / "experiment-status.md"
REVIEW_DAYS = 28
EARLY_REVIEW_VOLUME = 100


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def parse_date(value: str) -> date:
    for date_format in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {value}")


def normalize_page(value: str) -> str:
    raw = (value or "/").split("?", 1)[0].strip() or "/"
    prefix = "/my-affiliate-site1"
    if raw == prefix:
        raw = "/"
    elif raw.startswith(f"{prefix}/"):
        raw = raw[len(prefix) :]
    normalized = posixpath.normpath(f"/{raw.lstrip('/')}")
    if normalized != "/" and raw.endswith("/"):
        normalized += "/"
    return normalized


def load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Required report not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_experiments(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Experiment ledger not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            row
            for row in csv.DictReader(handle)
            if (row.get("status") or "").strip().lower() == "active"
        ]


def period_for_metric(metric: str, ga4: dict, gsc: dict) -> tuple[date, date]:
    source = gsc.get("meta", {}) if metric.startswith("gsc_") else ga4.get("range_28d", {})
    try:
        return parse_date(source["start"]), parse_date(source["end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"Missing or invalid report period for metric {metric}") from exc


def find_ga4_page(ga4: dict, page: str) -> dict | None:
    target = normalize_page(page)
    for row in ga4.get("top_pages_28d", []):
        if normalize_page(row.get("path") or "") == target:
            return row
    return None


def find_gsc_page(gsc: dict, page: str) -> dict | None:
    target = normalize_page(page)
    for row in gsc.get("pages", []):
        if normalize_page(row.get("page") or "") == target:
            return row
    return None


def find_gsc_query(gsc: dict, page: str, query: str) -> dict | None:
    target_page = normalize_page(page)
    target_query = " ".join(query.lower().split())
    for row in gsc.get("queries", []):
        row_query = " ".join(str(row.get("query") or "").lower().split())
        if normalize_page(row.get("page") or "") == target_page and row_query == target_query:
            return row
    return None


def current_measurement(experiment: dict, ga4: dict, gsc: dict) -> dict:
    metric = (experiment.get("primary_metric") or "").strip()
    page = experiment.get("page") or ""

    if metric.startswith("affiliate_slot:"):
        slot = metric.split(":", 1)[1]
        page_row = find_ga4_page(ga4, page)
        clicks = (
            ga4.get("affiliate_click_breakdowns_28d", {})
            .get("customEvent:affiliate_slot", {})
            .get(slot, 0)
        )
        if page_row is None:
            return {"available": False, "unit": "views", "reason": "page absent from GA4 top pages"}
        views = int(page_row.get("views") or 0)
        return {
            "available": True,
            "unit": "views",
            "volume": views,
            "clicks": int(clicks),
            "rate": (int(clicks) / views) if views else 0,
        }

    if metric == "page_affiliate_ctr":
        page_row = find_ga4_page(ga4, page)
        if page_row is None:
            return {"available": False, "unit": "views", "reason": "page absent from GA4 top pages"}
        views = int(page_row.get("views") or 0)
        clicks = int(
            ga4.get("affiliate_click_pages_28d", {}).get(normalize_page(page), 0)
        )
        return {
            "available": True,
            "unit": "views",
            "volume": views,
            "clicks": clicks,
            "rate": (clicks / views) if views else 0,
        }

    if metric.startswith("gsc_query_ctr:"):
        query = metric.split(":", 1)[1]
        row = find_gsc_query(gsc, page, query)
        if row is None:
            return {"available": False, "unit": "impressions", "reason": "query absent from GSC report"}
        impressions = int(float(row.get("impressions") or 0))
        clicks = int(float(row.get("clicks") or 0))
        return {
            "available": True,
            "unit": "impressions",
            "volume": impressions,
            "clicks": clicks,
            "rate": (clicks / impressions) if impressions else 0,
        }

    if metric == "gsc_page_impressions":
        row = find_gsc_page(gsc, page)
        if row is None:
            return {"available": False, "unit": "impressions", "reason": "page absent from GSC report"}
        impressions = int(float(row.get("impressions") or 0))
        clicks = int(float(row.get("clicks") or 0))
        return {
            "available": True,
            "unit": "impressions",
            "volume": impressions,
            "clicks": clicks,
            "rate": (clicks / impressions) if impressions else 0,
        }

    return {"available": False, "unit": "observations", "reason": f"unsupported metric: {metric}"}


def post_change_measurement(
    experiment: dict,
    ga4: dict,
    gsc: dict,
    start: date,
    period_end: date,
) -> dict:
    metric = experiment["primary_metric"]
    page = normalize_page(experiment["page"])

    if metric.startswith("affiliate_slot:"):
        status = ga4.get("experiment_data_status", {})
        if not status.get("page_views") or not status.get("page_slot_clicks"):
            return {"available": False, "unit": "views", "reason": "GA4 daily page/slot data unavailable"}
        slot = metric.split(":", 1)[1]
        views = sum(
            int(row.get("views") or 0)
            for row in ga4.get("daily_page_metrics_28d", [])
            if normalize_page(row.get("path") or "") == page
            and start <= parse_date(row["date"]) <= period_end
        )
        clicks = sum(
            int(row.get("clicks") or 0)
            for row in ga4.get("daily_affiliate_page_slots_28d", [])
            if normalize_page(row.get("path") or "") == page
            and row.get("slot") == slot
            and start <= parse_date(row["date"]) <= period_end
        )
        return {
            "available": True,
            "unit": "views",
            "volume": views,
            "clicks": clicks,
            "rate": (clicks / views) if views else 0,
        }

    if metric == "page_affiliate_ctr":
        status = ga4.get("experiment_data_status", {})
        if not status.get("page_views") or not status.get("page_slot_clicks"):
            return {"available": False, "unit": "views", "reason": "GA4 daily page/click data unavailable"}
        views = sum(
            int(row.get("views") or 0)
            for row in ga4.get("daily_page_metrics_28d", [])
            if normalize_page(row.get("path") or "") == page
            and start <= parse_date(row["date"]) <= period_end
        )
        clicks = sum(
            int(row.get("clicks") or 0)
            for row in ga4.get("daily_affiliate_page_slots_28d", [])
            if normalize_page(row.get("path") or "") == page
            and start <= parse_date(row["date"]) <= period_end
        )
        return {
            "available": True,
            "unit": "views",
            "volume": views,
            "clicks": clicks,
            "rate": (clicks / views) if views else 0,
        }

    daily_rows = gsc.get("daily_rows")
    if not isinstance(daily_rows, list):
        return {"available": False, "unit": "impressions", "reason": "GSC daily data unavailable"}
    if gsc.get("meta", {}).get("daily_rows_truncated"):
        return {"available": False, "unit": "impressions", "reason": "GSC daily data is truncated"}
    if metric.startswith("gsc_query_ctr:"):
        query = " ".join(metric.split(":", 1)[1].lower().split())
        rows = [
            row
            for row in daily_rows
            if normalize_page(row.get("page") or "") == page
            and " ".join(str(row.get("query") or "").lower().split()) == query
            and start <= parse_date(row["date"]) <= period_end
        ]
    elif metric == "gsc_page_impressions":
        rows = [
            row
            for row in daily_rows
            if normalize_page(row.get("page") or "") == page
            and start <= parse_date(row["date"]) <= period_end
        ]
    else:
        return current_measurement(experiment, ga4, gsc)
    impressions = int(sum(float(row.get("impressions") or 0) for row in rows))
    clicks = int(sum(float(row.get("clicks") or 0) for row in rows))
    return {
        "available": True,
        "unit": "impressions",
        "volume": impressions,
        "clicks": clicks,
        "rate": (clicks / impressions) if impressions else 0,
    }


def evaluate_experiment(experiment: dict, ga4: dict, gsc: dict, today: date) -> dict:
    start = parse_date(experiment["start_date"])
    review_date = start + timedelta(days=REVIEW_DAYS)
    metric = experiment["primary_metric"]
    period_start, period_end = period_for_metric(metric, ga4, gsc)
    if period_start > period_end:
        raise SystemExit(f"Invalid source period for {experiment['experiment_id']}")
    if period_end >= today:
        raise SystemExit(f"Source period must end before today for {experiment['experiment_id']}")
    measurement = post_change_measurement(experiment, ga4, gsc, start, period_end)
    elapsed_days = max((today - start).days, 0)
    post_change_days = max(
        0,
        (period_end - max(period_start, start) + timedelta(days=1)).days,
    )
    full_post_change_window = period_start >= start
    time_ready = (
        post_change_days >= REVIEW_DAYS
        and today >= review_date
    )
    volume_ready = (
        measurement.get("available", False)
        and measurement.get("volume", 0) >= EARLY_REVIEW_VOLUME
    )

    if not measurement.get("available", False):
        status = "data_missing"
        recommendation = measurement["reason"]
    elif time_ready or volume_ready:
        status = "review_due"
        recommendation = "compare the full post-change result with baseline; mark won, lost, or inconclusive manually"
    elif post_change_days == 0:
        status = "collecting"
        recommendation = "latest source period ends before the experiment; wait for post-change data"
    elif not full_post_change_window:
        status = "collecting"
        recommendation = "rolling source window overlaps baseline; post-change daily rows are still collecting"
    else:
        status = "collecting"
        recommendation = "continue collecting data until 28 days or 100 observations"

    return {
        "experiment_id": experiment["experiment_id"],
        "page": normalize_page(experiment["page"]),
        "metric": metric,
        "start_date": start.isoformat(),
        "review_date": review_date.isoformat(),
        "elapsed_days": elapsed_days,
        "source_period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "post_change_days": post_change_days,
            "full_post_change_window": full_post_change_window,
        },
        "baseline": {
            "volume": int(float(experiment.get("baseline_views") or 0)),
            "clicks": int(float(experiment.get("baseline_clicks") or 0)),
        },
        "current": measurement,
        "status": status,
        "recommendation": recommendation,
        "change": experiment.get("change") or "",
    }


def build_payload(experiments: list[dict], ga4: dict, gsc: dict, today: date) -> dict:
    rows = [evaluate_experiment(row, ga4, gsc, today) for row in experiments]
    return {
        "generated_on": today.isoformat(),
        "review_rules": {
            "minimum_days": REVIEW_DAYS,
            "early_review_observations": EARLY_REVIEW_VOLUME,
            "automatic_outcome_updates": False,
        },
        "summary": {
            "active": len(rows),
            "collecting": sum(row["status"] == "collecting" for row in rows),
            "review_due": sum(row["status"] == "review_due" for row in rows),
            "data_missing": sum(row["status"] == "data_missing" for row in rows),
        },
        "experiments": rows,
    }


def format_measurement(row: dict) -> str:
    current = row["current"]
    if not current.get("available", False):
        return "data missing"
    if row["metric"] == "gsc_page_impressions":
        return f"{current['volume']} impressions / {current['clicks']} clicks"
    return (
        f"{current['volume']} {current['unit']} / {current['clicks']} clicks / "
        f"{current['rate']:.2%}"
    )


def format_baseline(row: dict) -> str:
    baseline = row["baseline"]
    rate = baseline["clicks"] / baseline["volume"] if baseline["volume"] else 0
    if row["metric"] == "gsc_page_impressions":
        return f"{baseline['volume']} impressions / {baseline['clicks']} clicks"
    return f"{baseline['volume']} / {baseline['clicks']} / {rate:.2%}"


def format_report(payload: dict) -> str:
    summary = payload["summary"]
    lines = [
        "# Experiment Status Report",
        "",
        f"Generated: {payload['generated_on']}",
        (
            f"Active: {summary['active']} | Collecting: {summary['collecting']} | "
            f"Review due: {summary['review_due']} | Data missing: {summary['data_missing']}"
        ),
        "",
        "| Experiment | Metric | Baseline | Current source window | Current | Review date | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    if not payload["experiments"]:
        lines.append("| No active experiments | - | - | - | - | - | - |")
    for row in payload["experiments"]:
        source = row["source_period"]
        window = (
            f"{source['start']}..{source['end']} "
            f"({source['post_change_days']} post-change days)"
        )
        lines.append(
            f"| `{row['experiment_id']}` | `{row['metric']}` | "
            f"{format_baseline(row)} | {window} | {format_measurement(row)} | "
            f"{row['review_date']} | {row['status']} |"
        )
    lines.extend(
        [
            "",
            "## Actions",
            "",
        ]
    )
    due = [row for row in payload["experiments"] if row["status"] == "review_due"]
    missing = [row for row in payload["experiments"] if row["status"] == "data_missing"]
    if due:
        for row in due:
            lines.append(f"- Review `{row['experiment_id']}`: {row['recommendation']}.")
    if missing:
        for row in missing:
            lines.append(f"- Fix data for `{row['experiment_id']}`: {row['recommendation']}.")
    if not due and not missing:
        lines.append("- No experiment is ready for a result decision. Keep active pages unchanged.")
    lines.extend(
        [
            "",
            "A rolling source window that overlaps the baseline is shown for monitoring only. "
            "Do not compare it with the baseline until the report marks the experiment review_due.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiments", type=Path, default=DEFAULT_EXPERIMENTS)
    parser.add_argument("--ga4", type=Path, default=DEFAULT_GA4)
    parser.add_argument("--gsc", type=Path, default=DEFAULT_GSC)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--today", type=parse_date, default=date.today())
    args = parser.parse_args()

    experiments = load_experiments(resolve_path(args.experiments))
    ga4 = load_json(resolve_path(args.ga4))
    gsc = load_json(resolve_path(args.gsc))
    payload = build_payload(experiments, ga4, gsc, args.today)
    report = format_report(payload)

    json_output = resolve_path(args.json_output)
    markdown_output = resolve_path(args.markdown_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_output.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"\nJSON report: {json_output}")
    print(f"Markdown report: {markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
