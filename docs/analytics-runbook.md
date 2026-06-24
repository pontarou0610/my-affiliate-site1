# Analytics Runbook

## Current Sources

- GA4 traffic and affiliate-click report: `python scripts/report_ga4.py --top 20`
- Production click verification: `python scripts/report_ga4.py --realtime-check --top 20`
- Search Console SEO opportunities: `python scripts/report_gsc.py --top 20`
- Active experiment progress: `python scripts/report_experiments.py`
- Versioned aggregate KPI history: `python scripts/record_kpi_snapshot.py`
- Confirmed partner revenue input gate:
  `python scripts/revenue_status.py --month 2026-06`
- GA4 auth/config check without opening a browser: `python scripts/report_ga4.py --auth-status`
- OAuth refresh when the token is missing or revoked: `python scripts/report_ga4.py --force-auth`
- Monthly revenue target model: `python scripts/report_revenue_target.py --commercial-pageviews 173`
- Expired campaign audit: `python scripts/check_expired_campaigns.py --report-only`
- Search indexing consistency: `python scripts/check_search_indexing.py public`
- Combined traffic, click, conversion, and revenue report:
  `python scripts/report_business_kpis.py --month 2026-06`

The business target and milestone definitions are in `docs/monthly-100k-roadmap.md`.

The GA4 report reads `.env` values:

- `GA4_PROPERTY_ID`
- `GA4_OAUTH_CLIENT_FILE`
- `GA4_OAUTH_TOKEN_FILE`

If `--auth-status` reports `oauth_token_file: missing`, run `--force-auth` and approve the Google browser prompt. A successful run creates the token file locally.

## Weekly KPI Report

1. Save the latest GA4 data:

   ```powershell
   python scripts/report_ga4.py --top 40 `
     --json-output reports/analytics/ga4-latest.json
   ```

2. Build the Search Console report:

   ```powershell
   python scripts/report_gsc.py --days 28 --top 20
   ```

3. Record the aggregate KPI snapshot:

   ```powershell
   python scripts/record_kpi_snapshot.py
   ```

   This updates the current report date in
   `data/analytics-kpi-history.csv`. The file contains aggregate counts only
   and is committed so weekly decisions remain auditable.

4. Build the experiment status report so the business KPI report can show
   active experiment locks and the next review date:

   ```powershell
   python scripts/report_experiments.py
   ```

5. Build the action report. This works even before revenue has been entered
   and combines commercial Search Console stages with GA4:

   ```powershell
   python scripts/report_business_kpis.py --month 2026-06
   ```

6. Export confirmed monthly results from Amazon Associates, Rakuten Affiliate,
   Yahoo/ValueCommerce, and KDP when available.
7. Copy `data/revenue/partner-revenue.example.csv` to
   `data/revenue/partner-revenue.csv` and enter the confirmed totals. Re-run the
   action report to unlock conversion, revenue, and EPC conclusions.
   Then run `python scripts/revenue_status.py --month 2026-06`; if it reports
   `missing_file`, `missing_month`, or `placeholder_zero`, do not use EPC or
   conversion conclusions yet.

The generated files under `reports/analytics/` and the real revenue CSV are
ignored by Git. The report identifies zero-click traffic pages, clicked
programs with no confirmed revenue, and the highest-EPC program to scale.
`data/analytics-kpi-history.csv` is intentionally tracked. Weekly runs append
one aggregate row per report date; rerunning on the same date replaces that
date's row instead of creating a duplicate.
When the revenue CSV is absent, it reports revenue as `Not entered` rather than
zero and continues producing the traffic and click sections.
When the revenue CSV exists but every selected-month row is zero, it is treated
as `placeholder_zero` until the partner dashboards have been checked and noted.
The Search Console report ranks query and page opportunities while excluding
pages with active CTA experiments. The experiment report identifies the review
date and prevents rolling windows that still include baseline data from being
treated as post-change results.
The business KPI report adds a commercial search funnel: page-level Search
Console impressions and clicks, GA4 commercial pageviews, affiliate clicks,
then confirmed orders and revenue when supplied.
It also compares the latest 28 days with the immediately preceding 28 days for
commercial search impressions, search clicks, pageviews, affiliate clicks, and
both CTR stages.
Use the `Next Milestone` section as the weekly operating target. It identifies
the first unreached Stage 2/3/4 threshold and shows the remaining commercial PV,
affiliate clicks, and CTR-point gap before broad content production is justified.

Commercial-intent traffic is defined by `data/commercial-pages.csv` plus active
experiment rows whose `commercial_intent` value is `true`. Add an `exact`
or `prefix` rule only for pages whose primary purpose includes a product,
subscription, store, or owned-book decision. The business KPI report uses this
traffic, rather than all site pageviews, for the 31,250-PV and 8%-CTR model.
SEO and internal-link experiments must remain `commercial_intent=false` unless
the page's primary purpose is a product, subscription, store, or owned-book
decision.

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
| affiliate_program | `affiliate_program` | Amazon, Kindle Unlimited, Audible, Rakuten, Yahoo, or owned KDP grouping |
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
- `affiliate_program` separates Amazon store clicks from Kindle Unlimited,
  Audible, and owned Kindle book clicks. Until this custom definition is
  registered, the KPI report keeps overall traffic/click reporting active but
  shows a store-level fallback and withholds program-level EPC conclusions.
  The fallback cannot split Amazon clicks into standard products, Kindle
  Unlimited, and Audible.
- When the store and CTA slot identify one program unambiguously, the report
  also shows an explicitly labeled inferred-program table. Inferred values are
  diagnostic only and are never used for EPC or winner decisions.
- Every generated link carrying `data-affiliate` must also carry an explicit
  `data-affiliate-program`. `check_affiliate_html.py` enforces this during
  deployment so program attribution cannot silently regress.

The report's opportunity list is based on the selected `--top` page count, not every page on the site. Increase `--top` when doing a broader audit.
