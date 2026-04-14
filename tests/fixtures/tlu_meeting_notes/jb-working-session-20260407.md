# JailBreak Working Session - 2026-04-07

**Attendees:** Bruno, Luis, João Pedro

## Topics

- Webhook fixes: both supplier and buyer webhooks now merged
- Buyer webhook now listening to platform account events (option A implemented)
- Supplier onboarding URL bug: storing `requirements` on webhook fire, FE generates fresh URL
- Full e2e transactional test planned for Apr 10 on staging

## Action items

- [ ] Luis: run e2e test on staging (buyer purchases, transporter arrives, payment fires)
- [ ] João Pedro: confirm CloudSort payout account configured in Stripe
- [ ] Bruno: follow up with Derek on cost report format
