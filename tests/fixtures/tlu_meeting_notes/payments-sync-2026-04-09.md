# Payments Sync - 2026-04-09

**Attendees:** Bruno, Luis

## Update

- E2e test ran on staging: buyer purchased a lane, transporter marked arrived, payment fired
- Supplier received payout in Stripe test account — confirmed
- CloudSort fee received — confirmed
- Address redaction PR merged to main, WEB integration in review

## Risks resolved

- Risk #1 (payment flow not validated) — RESOLVED. Money moved end-to-end in staging.
- Risk #3 (address redaction) — FE integration in progress, expected Apr 11

## Open

- Risk #4 (cancel lanes bug) — fix merged, QA pending
- Risk #5 (buyer payment prompt) — in progress
