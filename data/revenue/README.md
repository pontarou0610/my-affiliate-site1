# Revenue Data

Copy `partner-revenue.example.csv` to `partner-revenue.csv` and replace the
example values with confirmed monthly results from each partner dashboard.

The KPI report can run before this file exists. In that state, revenue,
conversions, and EPC are shown as not entered; they are never assumed to be
zero.

Before using conversion or EPC conclusions, run:

```powershell
python scripts/revenue_status.py --month 2026-06
```

`missing_file`, `missing_month`, and `placeholder_zero` block conversion and
EPC decisions. `placeholder_zero` means the month has rows but every order and
revenue value is zero; keep it blocked unless the partner dashboards have been
checked and the zero result is confirmed in `notes`.

`partner-revenue.csv` is ignored by Git because it may contain private business
data. Keep one row per month and program. Multiple rows for the same program are
allowed and are summed by the KPI report.

Required columns:

- `month`: `YYYY-MM`
- `program`: `amazon`, `rakuten`, `yahoo`, `kdp`, `kindle_unlimited`, or `audible`
- `orders`: confirmed orders or eligible registrations
- `revenue_yen`: confirmed commission or royalty in yen
- `notes`: optional source or reconciliation note
