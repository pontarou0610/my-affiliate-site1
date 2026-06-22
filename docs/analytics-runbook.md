# Analytics Runbook

## Current Sources

- GA4 traffic and affiliate-click report: `python scripts/report_ga4.py --top 20`
- Production click verification: `python scripts/report_ga4.py --realtime-check --top 20`
- Search Console SEO opportunities: `python scripts/report_gsc.py --top 20`
- Active experiment progress: `python scripts/report_experiments.py`
- GA4 auth/config check without opening a browser: `python scripts/report_ga4.py --auth-status`
- OAuth refresh when the token is missing or revoked: `python scripts/report_ga4.py --force-auth`
- Monthly revenue target model: `python scripts/report_revenue_target.py --commercial-pageviews 173`
- Expired campaign audit: `python scripts/check_expired_campaigns.py --report-only`
- Combined traffic, click, conversion, and revenue report:
  `python scripts/report_business_kpis.py --month 2026-06`

The business target and milestone definitions are in `docs/monthly-100k-roadmap.md`.

The GA4 report reads `.env` values:

- `GA4_PROPERTY_ID`
- `GA4_OAUTH_CLIENT_FILE`
- `GA4_OAUTH_TOKEN_FILE`

If `--auth-status` reports `oauth_token_file: missing`, run `--force-auth` and approve the Google browser prompt. A successful run creates the token file locally.

## Weekly KPI Report

1. Export confirmed monthly results from Amazon Associates, Rakuten Affiliate,
   Yahoo/ValueCommerce, and KDP.
2. Copy `data/revenue/partner-revenue.example.csv` to
   `data/revenue/partner-revenue.csv` and enter the confirmed totals.
3. Save the latest GA4 data:

   ```powershell
   python scripts/report_ga4.py --top 40 `
     --json-output reports/analytics/ga4-latest.json
   ```

4. Build the action report:

   ```powershell
   python scripts/report_business_kpis.py --month 2026-06
   ```

5. Build the Search Console opportunity report:

   ```powershell
   python scripts/report_gsc.py --days 28 --top 20
   ```

6. Build the experiment status report:

   ```powershell
   python scripts/report_experiments.py
   ```

The generated files under `reports/analytics/` and the real revenue CSV are
ignored by Git. The report identifies zero-click traffic pages, clicked
programs with no confirmed revenue, and the highest-EPC program to scale.
The Search Console report ranks query and page opportunities while excluding
pages with active CTA experiments. The experiment report identifies the review
date and prevents rolling windows that still include baseline data from being
treated as post-change results.

## CTA Experiment Discipline

Record revenue-page changes in `data/optimization-experiments.csv`.

- Keep one primary CTA metric per experiment.
- Do not rewrite the same active experiment page for at least 28 days unless
  the link or page is broken.
- If the page reaches 100 views earlier, it can be reviewed at that point.
- Compare the new slot's clicks and CTR with the recorded baseline before
  marking the experiment `won`, `lost`, or `inconclusive`.
- Run `report_experiments.py` before changing an active experiment page. Only
  decide an outcome when it reports `review_due`; the ledger is never updated
  automatically.

## GA4 Custom Definitions

Register these event-scoped custom dimensions in GA4 so affiliate clicks can be analyzed by CTA placement:

| Custom dimension name | Event parameter | Use |
| --- | --- | --- |
| affiliate_store | `affiliate_store` | Amazon, Rakuten, Yahoo, or other store grouping |
| affiliate_slot | `affiliate_slot` | CTA placement such as hero, bottom, offerbox, related products |
| link_domain | `link_domain` | Destination domain sanity check |
| link_id | `link_id` | Stable low-cardinality link identifier for repeated CTA analysis |

Avoid reporting directly on `link_url` and `link_text` unless needed for debugging. They can produce too many unique values.

## Interpreting The Report

- Top pages with high views and zero affiliate clicks are CTA-improvement candidates.
- Pages with clicks but low traffic are SEO/internal-link candidates.
- `affiliate_slot` shows which CTA positions actually get clicked.
- Shared CTA components use button-specific slot names such as
  `lp-hero-unlimited` and `article-top-amazon-1`; do not reuse one slot name
  for different offers in the same CTA block.
- `affiliate_store` shows whether Amazon, Rakuten, or Yahoo links are getting traction.

The report's opportunity list is based on the selected `--top` page count, not every page on the site. Increase `--top` when doing a broader audit.
