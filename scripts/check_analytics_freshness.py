#!/usr/bin/env python3
"""Check that analytics JSON files are fresh enough for KPI decisions."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GA4 = REPO_ROOT / "reports" / "analytics" / "ga4-latest.json"
DEFAULT_GSC = REPO_ROOT / "reports" / "analytics" / "gsc-latest.json"


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def read_json(path: Path, label: str) -> dict:
    if not path.exists():
        raise SystemExit(f"{label} not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} is invalid JSON: {path}") from exc


def parse_date(value: str, label: str) -> date:
    raw = str(value or "").strip()
    for date_format in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"{label} has invalid date: {value!r}")


def age_days(today: date, value: date) -> int:
    return (today - value).days


def evaluate_freshness(
    ga4: dict,
    gsc: dict,
    *,
    today: date,
    max_generated_age_days: int = 7,
    max_period_lag_days: int = 7,
) -> dict:
    ga4_generated = parse_date(ga4.get("generated_on"), "GA4 generated_on")
    ga4_end = parse_date((ga4.get("range_28d") or {}).get("end"), "GA4 range_28d.end")
    gsc_end = parse_date((gsc.get("meta") or {}).get("end"), "GSC meta.end")
    checks = [
        {
            "name": "ga4_generated_on",
            "date": ga4_generated.isoformat(),
            "age_days": age_days(today, ga4_generated),
            "max_age_days": max_generated_age_days,
        },
        {
            "name": "ga4_range_end",
            "date": ga4_end.isoformat(),
            "age_days": age_days(today, ga4_end),
            "max_age_days": max_period_lag_days,
        },
        {
            "name": "gsc_range_end",
            "date": gsc_end.isoformat(),
            "age_days": age_days(today, gsc_end),
            "max_age_days": max_period_lag_days,
        },
    ]
    stale = [
        check for check in checks if check["age_days"] < 0 or check["age_days"] > check["max_age_days"]
    ]
    return {
        "today": today.isoformat(),
        "fresh": not stale,
        "checks": checks,
        "stale": stale,
    }


def format_result(result: dict) -> str:
    lines = [
        f"Analytics freshness: {'fresh' if result['fresh'] else 'stale'}",
        f"- today: {result['today']}",
    ]
    for check in result["checks"]:
        lines.append(
            f"- {check['name']}: {check['date']} "
            f"({check['age_days']} days old, max {check['max_age_days']})"
        )
    if result["stale"]:
        lines.append("- action: refresh GA4/GSC JSON before running KPI decisions")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ga4-json", type=Path, default=DEFAULT_GA4)
    parser.add_argument("--gsc-json", type=Path, default=DEFAULT_GSC)
    parser.add_argument("--today", type=lambda value: parse_date(value, "today"), default=date.today())
    parser.add_argument("--max-generated-age-days", type=int, default=7)
    parser.add_argument("--max-period-lag-days", type=int, default=7)
    args = parser.parse_args()

    result = evaluate_freshness(
        read_json(resolve_path(args.ga4_json), "GA4 JSON"),
        read_json(resolve_path(args.gsc_json), "GSC JSON"),
        today=args.today,
        max_generated_age_days=args.max_generated_age_days,
        max_period_lag_days=args.max_period_lag_days,
    )
    print(format_result(result))
    return 0 if result["fresh"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
