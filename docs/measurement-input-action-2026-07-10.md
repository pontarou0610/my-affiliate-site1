# Hugo Measurement Input Action 2026-07-10

## Conclusion

Do not edit active experiment pages yet.

The next Hugo monetization work is measurement input, not content rewriting.

## Current Verified State

- `reports/analytics/business-kpi.md` reports 66 commercial-intent pageviews and 1 affiliate click for the latest 28-day window.
- `reports/analytics/action-backlog.md` reports `No unlocked action candidate found.`
- Active experiments are still collecting data.
- Next experiment review date is 2026-07-20.
- Revenue CSV is missing, so EPC and confirmed revenue decisions are blocked.
- GA4 `affiliate_program` is not registered as an event-scoped custom dimension, so program-level attribution remains limited.

## Required CEO / Admin Actions

### 1. Register GA4 Custom Dimension

Create a GA4 event-scoped custom dimension:

| Field | Value |
| --- | --- |
| Dimension name | `affiliate_program` |
| Scope | Event |
| Event parameter | `affiliate_program` |

Purpose:

- Separate Amazon, Kindle Unlimited, Audible, Kobo, and other affiliate clicks.
- Stop treating all store clicks as one undifferentiated bucket.
- Make EPC and program-level decisions possible after revenue data is entered.

### 2. Enter Confirmed Revenue CSV

Create the revenue file from the example if it does not exist:

```powershell
Copy-Item data\revenue\partner-revenue.example.csv data\revenue\partner-revenue.csv
```

Then enter only confirmed partner/KDP revenue.

Rules:

- Do not enter unconfirmed revenue.
- Do not treat unknown as zero.
- Keep Amazon, KDP, Kobo, and other partner results separate when possible.

## Five-Expert Review

### 1. SEO

Traffic is still low, and active experiments are collecting. Editing pages now would blur test results.

Verdict: hold content edits.

### 2. Analytics

The main blocker is attribution and revenue input. `affiliate_program` and partner revenue must be available before EPC-based decisions.

Verdict: S priority.

### 3. Affiliate

One click exists, but program attribution is incomplete. Registering `affiliate_program` is more valuable than rewriting copy today.

Verdict: A priority.

### 4. Operations

This is a CEO/admin task, not an automated content task. Codex should not infer revenue or access admin screens without confirmed data.

Verdict: CEO input required.

### 5. Governance

No public site changes should be made until the 2026-07-20 experiment review unless a critical issue appears.

Verdict: safe hold.

## Next Codex Action After CEO Input

After GA4 custom dimension registration and revenue CSV input:

1. Run the weekly KPI scripts again.
2. Rebuild `business-kpi.md`.
3. Rebuild `action-backlog.md`.
4. Select the first unlocked commercial page only if the gate opens.

## Status

Blocked on CEO/admin input.
