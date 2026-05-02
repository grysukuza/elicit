# Billing & Payments Checklist

Goals:
1. Charge correctly and predictably.
2. Minimize revenue leakage and fraud.
3. Provide clear, auditable records.
4. Handle failures and edge cases safely.
5. Stay compliant (PCI, tax, regional rules).

Reference baselines:
- PCI DSS (payment data handling)
- Revenue recognition standards (ASC 606 / IFRS 15)
- Provider best practices (e.g., :contentReference[oaicite:0]{index=0})

---

## 1. Pricing Model

- [ ] Define pricing clearly: free, tiered, per-seat, usage-based, hybrid.
- [ ] Map features → entitlements per plan.
- [ ] Define billing interval: monthly, annual.
- [ ] Define proration rules (upgrade/downgrade mid-cycle).
- [ ] Define overage pricing (usage beyond quota).
- [ ] Define discounts/coupons (fixed, percentage, duration).
- [ ] Version pricing (do not retroactively change existing contracts).

---

## 2. Customer & Accounts

- [ ] Customer record (user/tenant, billing email).
- [ ] Company/organization support (multi-seat).
- [ ] Billing contact vs product users.
- [ ] Tax IDs (VAT/GST) and exemption status.
- [ ] Address normalization (for tax calculation).
- [ ] Link customers to subscriptions and invoices.

---

## 3. Payment Methods

- [ ] Use a PCI-compliant processor (do not store raw card data).
- [ ] Support cards, ACH/bank debit, wallets (Apple Pay/Google Pay).
- [ ] Tokenize payment methods (store provider tokens only).
- [ ] Allow multiple payment methods per customer.
- [ ] Set default payment method.
- [ ] Handle card updates and expirations.
- [ ] Verify webhooks from provider.

---

## 4. Subscriptions

- [ ] Create/cancel/pause/resume subscriptions.
- [ ] Trial periods (start/end, conversion rules).
- [ ] Grace periods after failed payments.
- [ ] Seat-based quantity changes (add/remove seats).
- [ ] Plan changes with proration.
- [ ] Scheduled changes (next billing cycle).
- [ ] Auto-renew toggles.

---

## 5. Usage Metering (if applicable)

- [ ] Define billable metrics (API calls, storage, seats).
- [ ] Collect usage events (idempotent).
- [ ] Aggregate by billing period.
- [ ] Real-time vs delayed metering strategy.
- [ ] Handle late-arriving events.
- [ ] Reconciliation jobs (detect drift).
- [ ] Cap or throttle on quota exceedance.

---

## 6. Invoicing

- [ ] Generate invoices for each billing cycle.
- [ ] Line items: base fee, usage, discounts, taxes.
- [ ] Unique invoice numbers.
- [ ] Currency handling.
- [ ] Invoice PDFs and hosted pages.
- [ ] Status: draft, open, paid, void, uncollectible.
- [ ] Credit notes and adjustments.

---

## 7. Payments & Collections

- [ ] Automatic charge on invoice finalization.
- [ ] Retry logic (smart retries on failure).
- [ ] Dunning emails (payment failed, card expiring).
- [ ] Manual payment option (bank transfer).
- [ ] Partial payments (if supported).
- [ ] Mark invoices as paid externally when needed.
- [ ] Reconcile payments to invoices.

---

## 8. Taxes

- [ ] Calculate sales tax/VAT/GST based on location.
- [ ] Support tax-inclusive and tax-exclusive pricing.
- [ ] Store tax rates used per invoice.
- [ ] Reverse charge for valid VAT IDs (EU).
- [ ] Maintain jurisdiction rules (or use provider automation).
- [ ] Export tax reports for filing.

---

## 9. Discounts & Credits

- [ ] Coupons (percentage/fixed, duration).
- [ ] Promotion codes (user-entered).
- [ ] Account credits (goodwill, refunds).
- [ ] Apply credits before charging payment method.
- [ ] Track remaining credit balance.
- [ ] Audit trail for all discounts/credits.

---

## 10. Refunds

- [ ] Full and partial refunds.
- [ ] Link refunds to original payment/invoice.
- [ ] Automatic vs manual approval workflows.
- [ ] Update revenue/ledger after refund.
- [ ] Notify customer with receipt.
- [ ] Prevent duplicate refunds (idempotency).

---

## 11. Chargebacks & Fraud

- [ ] Track disputes/chargebacks.
- [ ] Provide evidence (receipts, logs, usage).
- [ ] Flag high-risk accounts.
- [ ] Velocity checks (many cards, many attempts).
- [ ] 3D Secure / step-up authentication (where applicable).
- [ ] Blacklist abusive payment sources.

---

## 12. Revenue Recognition (high-level)

- [ ] Separate booking (invoice) vs revenue recognition.
- [ ] Recognize subscription revenue over time.
- [ ] Recognize usage revenue when incurred.
- [ ] Handle refunds/credits adjustments.
- [ ] Export data for accounting system.

---

## 13. Reporting & Analytics

- [ ] MRR (monthly recurring revenue).
- [ ] ARR (annual recurring revenue).
- [ ] New MRR, expansion, contraction, churn.
- [ ] ARPU (average revenue per user).
- [ ] LTV (lifetime value) estimates.
- [ ] Cohort retention by plan.
- [ ] Failed payment rates and recovery rate.
- [ ] Aging report (outstanding invoices).

---

## 14. Customer Portal

- [ ] View/update payment methods.
- [ ] View invoices and receipts.
- [ ] Download PDFs.
- [ ] Change plan / seats.
- [ ] Cancel or pause subscription.
- [ ] Apply promo codes.
- [ ] Update billing address and tax info.

---

## 15. Webhooks & Idempotency

- [ ] Verify webhook signatures.
- [ ] Handle events idempotently (dedupe by event ID).
- [ ] Process key events:
  - invoice.created
  - invoice.paid
  - invoice.payment_failed
  - customer.subscription.updated
  - payment_method.updated
- [ ] Retry failed webhook processing safely.
- [ ] Dead-letter queue for failures.

---

## 16. Security & Compliance

- [ ] Do not store raw card data (PCI scope reduction).
- [ ] Encrypt sensitive billing data at rest.
- [ ] Mask PII in logs (no full card numbers).
- [ ] Role-based access to billing/admin tools.
- [ ] Audit logs for all billing changes.
- [ ] Data retention policy for invoices and payments.

---

## 17. Edge Cases & Lifecycle

- [ ] Mid-cycle upgrades/downgrades (proration).
- [ ] Trial → paid conversion failures.
- [ ] Expired cards at renewal.
- [ ] Currency changes (if supported).
- [ ] Timezone consistency for billing cycles.
- [ ] Backdated subscriptions (careful handling).
- [ ] Account deletion with outstanding balance.

---

## 18. Minimum Billing Baseline (MVP)

Before launch:

- [ ] Use a payment provider (e.g., Stripe).
- [ ] Create subscriptions (monthly/annual).
- [ ] Store customer + provider IDs.
- [ ] Handle webhook: invoice.paid.
- [ ] Grant/revoke access based on subscription status.
- [ ] Retry failed payments.
- [ ] Basic invoices accessible to users.
- [ ] Do not store raw card data.
- [ ] Log billing events.

---

## 19. Data Model (suggested)

- customers(id, email, provider_customer_id, created_at)
- payment_methods(id, customer_id, provider_pm_id, last4, brand, exp_month, exp_year)
- subscriptions(id, customer_id, plan_id, status, quantity, current_period_start, current_period_end)
- prices(id, plan_id, amount, currency, interval, usage_type)
- usage_events(id, customer_id, metric, quantity, timestamp, idempotency_key)
- invoices(id, customer_id, provider_invoice_id, amount_due, status, currency, period_start, period_end)
- invoice_items(id, invoice_id, description, amount, quantity)
- payments(id, invoice_id, provider_payment_id, amount, status, created_at)
- credits(id, customer_id, amount, remaining, reason, created_at)
- refunds(id, payment_id, amount, reason, created_at)
- webhooks(id, provider_event_id, type, processed, created_at)

---

## 20. Implementation Notes (Replit)

- [ ] Keep provider secret keys in Replit Secrets.
- [ ] Never expose secret keys to frontend.
- [ ] Use server endpoints to create checkout sessions.
- [ ] Verify all webhooks server-side.
- [ ] Queue webhook processing for reliability.
- [ ] Use idempotency keys on create/charge endpoints.
- [ ] Cache plan/price data to reduce API calls.
- [ ] Index by provider IDs for reconciliation.

---

## 21. Failure Modes

- Double charging (missing idempotency).
- Missed webhook → access not updated.
- Over/under billing (metering drift).
- Leaked API keys for payment provider.
- Incorrect tax calculation.
- Proration bugs on plan changes.
- Race conditions on subscription updates.
- Silent payment failures (no alerts).

---

## 22. Review Checklist Before Release

- Can a user be charged twice for the same event?
- Are webhooks verified and idempotent?
- Is access correctly tied to subscription status?
- Are failed payments retried and communicated?
- Are invoices accurate and reproducible?
- Are taxes applied correctly for key regions?
- Are secrets secured and not logged?
- Can admins audit all billing changes?
- Are refunds and credits correctly reflected?