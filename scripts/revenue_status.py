#!/usr/bin/env python3
"""Report whether confirmed partner revenue is ready for KPI decisions."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVENUE_CSV = REPO_ROOT / "data" / "revenue" / "partner-revenue.csv"
EXPECTED_PROGRAMS = (
    "amazon",
    "rakuten",
    "yahoo",
    "kdp",
    "kindle_unlimited",
    "audible",
)
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


@dataclass(frozen=True)
class RevenueRow:
    month: str
    program: str
    orders: int
    revenue_yen: float
    notes: str


@dataclass(frozen=True)
class RevenueStatus:
    status: str
    message: str
    month: str
    rows: int = 0
    orders: int = 0
    revenue_yen: float = 0.0
    missing_programs: tuple[str, ...] = ()

    @property
    def blocks_epc_decisions(self) -> bool:
        return self.status in {"missing_file", "missing_month", "placeholder_zero"}


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


def evaluate_revenue_status(
    path: Path,
    month: str,
    expected_programs: tuple[str, ...] = EXPECTED_PROGRAMS,
) -> RevenueStatus:
    if not month:
        raise ValueError("month is required")
    if not path.exists():
        return RevenueStatus(
            status="missing_file",
            month=month,
            message=(
                "Confirmed partner revenue CSV is missing. Copy "
                "data/revenue/partner-revenue.example.csv to "
                "data/revenue/partner-revenue.csv and enter partner/KDP totals."
            ),
        )

    rows = read_revenue(path, allow_missing=False)
    selected = [row for row in rows if row.month == month]
    if not selected:
        months = sorted({row.month for row in rows})
        month_hint = f" Available months: {', '.join(months)}." if months else ""
        return RevenueStatus(
            status="missing_month",
            month=month,
            rows=0,
            message=f"No confirmed revenue rows found for {month}.{month_hint}",
        )

    programs = {row.program for row in selected}
    missing_programs = tuple(program for program in expected_programs if program not in programs)
    orders = sum(row.orders for row in selected)
    revenue_yen = sum(row.revenue_yen for row in selected)
    if orders == 0 and revenue_yen == 0:
        return RevenueStatus(
            status="placeholder_zero",
            month=month,
            rows=len(selected),
            orders=orders,
            revenue_yen=revenue_yen,
            missing_programs=missing_programs,
            message=(
                f"{month} revenue rows are present but all orders and revenue are zero. "
                "Treat this as unconfirmed unless partner dashboards have been checked."
            ),
        )
    if missing_programs:
        return RevenueStatus(
            status="partial",
            month=month,
            rows=len(selected),
            orders=orders,
            revenue_yen=revenue_yen,
            missing_programs=missing_programs,
            message=(
                f"{month} revenue is partially entered. Missing programs: "
                f"{', '.join(missing_programs)}."
            ),
        )
    return RevenueStatus(
        status="ready",
        month=month,
        rows=len(selected),
        orders=orders,
        revenue_yen=revenue_yen,
        message=f"{month} confirmed revenue is ready for conversion and EPC decisions.",
    )


def format_status(status: RevenueStatus) -> str:
    lines = [
        f"Revenue status: {status.status}",
        f"- month: {status.month}",
        f"- rows: {status.rows}",
        f"- orders: {status.orders:,}",
        f"- revenue: {status.revenue_yen:,.0f} yen",
        f"- EPC decisions blocked: {'yes' if status.blocks_epc_decisions else 'no'}",
        f"- message: {status.message}",
    ]
    if status.missing_programs:
        lines.append(f"- missing programs: {', '.join(status.missing_programs)}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="Revenue month in YYYY-MM")
    parser.add_argument(
        "--revenue-csv",
        type=Path,
        default=DEFAULT_REVENUE_CSV,
    )
    args = parser.parse_args()

    path = args.revenue_csv if args.revenue_csv.is_absolute() else REPO_ROOT / args.revenue_csv
    status = evaluate_revenue_status(path, args.month)
    print(format_status(status))
    return 1 if status.blocks_epc_decisions else 0


if __name__ == "__main__":
    raise SystemExit(main())
