# Admin Capabilities Checklist

Goals:
1. Observe system health and user behavior.
2. Detect abuse and anomalies early.
3. Intervene safely (support, moderation, recovery).
4. Measure product usage and outcomes.
5. Preserve auditability and least-privilege access.

## 1. Admin Access Control

- [ ] Dedicated admin login (separate from user auth flow).
- [ ] Role-based access control (RBAC): viewer, analyst, moderator, admin, superadmin.
- [ ] Principle of least privilege (default deny).
- [ ] Multi-factor authentication required for admins.
- [ ] IP allowlist or VPN for admin panel (optional/high-risk apps).
- [ ] Session timeout + re-authentication for sensitive actions.
- [ ] Break-glass account with strict monitoring.

## 2. User Directory & Profiles

- [ ] Search users by email, username, ID, phone.
- [ ] Filter by status (active, suspended, deleted).
- [ ] View profile: signup date, last login, roles, flags.
- [ ] View linked identities (OAuth providers).
- [ ] View verification status (email/phone).
- [ ] View consent flags (terms, marketing).
- [ ] View tenant/organization membership.

## 3. Account Actions (Support + Moderation)

- [ ] Suspend / unsuspend account.
- [ ] Soft delete / hard delete (with safeguards).
- [ ] Reset password (force reset on next login).
- [ ] Invalidate sessions (logout everywhere).
- [ ] Revoke API keys / tokens.
- [ ] Change roles (with approval workflow).
- [ ] Impersonation (“login as user”) with banner + audit.
- [ ] Notes/annotations on user accounts (internal only).

## 4. Activity & Audit Logs

- [ ] Login events (success/failure, IP, device).
- [ ] Sensitive actions (password change, role change).
- [ ] API usage (endpoint, status, latency).
- [ ] Admin actions (who did what, when, before/after).
- [ ] Exportable logs (CSV/JSON).
- [ ] Immutable append-only audit trail.
- [ ] Retention policy (e.g., 90–365 days).
- [ ] Correlation/request IDs for tracing.

## 5. Metrics & Analytics (Product)

- [ ] DAU/WAU/MAU (daily/weekly/monthly active users).
- [ ] New signups, activations, retention cohorts.
- [ ] Funnel metrics (signup → activation → key action).
- [ ] Feature usage (per endpoint/feature flag).
- [ ] Session length, frequency.
- [ ] Conversion rates (trial → paid, etc.).
- [ ] Segmentation (plan, geography, device).
- [ ] Time-series dashboards (hour/day/week).

## 6. System Health & Performance

- [ ] Uptime status and health checks.
- [ ] Error rates (4xx/5xx).
- [ ] Latency percentiles (p50/p95/p99).
- [ ] Throughput (requests per second).
- [ ] Queue/backlog depth (if async jobs).
- [ ] Database metrics (connections, slow queries).
- [ ] External dependency status.
- [ ] Alerting on SLO breaches.

## 7. Abuse Detection & Risk Scoring

- [ ] Rate-limit dashboards (per IP/user/key).
- [ ] Failed login spikes (credential stuffing signals).
- [ ] Geo anomalies (impossible travel).
- [ ] Device anomalies (new/rare fingerprints).
- [ ] API misuse (sudden volume or pattern change).
- [ ] Content/report queues (if UGC).
- [ ] Risk score per account (heuristic or model-based).
- [ ] Auto-actions (temporary lock, step-up auth).

## 8. Billing & Entitlements (if applicable)

- [ ] View plan/subscription status.
- [ ] View invoices and payment history.
- [ ] Apply credits/adjustments (with audit).
- [ ] Manage entitlements (features/limits).
- [ ] Usage-based metrics (API calls, storage).
- [ ] Quota enforcement and overage alerts.

## 9. API Key & Integration Management

- [ ] List API keys per user/tenant.
- [ ] Create/revoke/rotate keys.
- [ ] Scope keys (read/write/admin).
- [ ] Last used timestamp and IP.
- [ ] Per-key rate limits and quotas.
- [ ] Webhook endpoints + signature status.
- [ ] Replay protection status (timestamps/nonces).

## 10. Content Moderation (if applicable)

- [ ] Queue for reported content.
- [ ] Bulk actions (approve/remove).
- [ ] Reason codes and policy mapping.
- [ ] User strike system / escalation ladder.
- [ ] Appeal workflow and resolution tracking.

## 11. Feature Flags & Configuration

- [ ] Toggle features per environment/user segment.
- [ ] Gradual rollout (percentage-based).
- [ ] Kill switch for critical features.
- [ ] Config audit trail (who changed what).
- [ ] Safe defaults and rollback capability.

## 12. Data Export & Compliance

- [ ] Export user data (subject access requests).
- [ ] Delete/anonymize user data.
- [ ] View data retention status.
- [ ] Consent history.
- [ ] Redaction tools for sensitive fields.
- [ ] Audit trail for compliance actions.

## 13. Notifications & Alerting

- [ ] Real-time alerts (email/Slack/webhook).
- [ ] Threshold-based alerts (errors, latency, abuse).
- [ ] Scheduled reports (daily/weekly).
- [ ] On-call routing and escalation.
- [ ] Alert deduplication and silencing windows.

## 14. Search & Filtering UX

- [ ] Global search across users, logs, keys.
- [ ] Advanced filters (time range, status, region).
- [ ] Saved views and queries.
- [ ] Pagination and fast queries (indexes).
- [ ] Export filtered results.

## 15. Impersonation Safety

- [ ] Explicit “impersonating” banner.
- [ ] Read-only mode by default (write requires elevation).
- [ ] Time-limited sessions.
- [ ] Full audit of impersonation actions.
- [ ] User notification (optional, policy-driven).

## 16. Privacy & Least Exposure

- [ ] Mask sensitive fields (email partial, tokens hidden).
- [ ] Click-to-reveal with audit for secrets.
- [ ] Role-based field visibility.
- [ ] No plaintext secrets in UI.
- [ ] Data minimization in dashboards.

## 17. Rate Limits & Quotas (Admin Controls)

- [ ] Set per-user/per-key limits.
- [ ] Temporary overrides.
- [ ] Burst vs sustained limits.
- [ ] Visualize consumption vs quota.
- [ ] Automatic throttling policies.

## 18. Experimentation (A/B)

- [ ] Define experiments and variants.
- [ ] Assign users/segments.
- [ ] Track outcomes and guardrails.
- [ ] Stop/rollback experiments.
- [ ] Export results.

## 19. Backoffice Workflows

- [ ] Ticket linking (support cases to users).
- [ ] Internal notes and attachments.
- [ ] Approval flows for high-risk actions.
- [ ] Bulk operations with confirmation and dry-run.
- [ ] Undo/rollback where feasible.

## 20. Minimum Admin Baseline

Before launch, ensure:

- [ ] RBAC with least privilege.
- [ ] Admin MFA enforced.
- [ ] User search + profile view.
- [ ] Suspend/reactivate users.
- [ ] Revoke sessions and API keys.
- [ ] Basic audit log (logins + admin actions).
- [ ] Error/latency dashboard.
- [ ] Rate-limit visibility.
- [ ] Alerting on critical failures.
- [ ] No secrets exposed in admin UI.

## 21. KPIs & Thresholds (define upfront)

- [ ] Error rate threshold (e.g., >1% 5xx triggers alert).
- [ ] Latency SLO (e.g., p95 < 300 ms).
- [ ] Abuse threshold (failed logins per IP/time).
- [ ] Retention targets (D7/D30).
- [ ] Quota breach alerts (≥80% usage).
- [ ] Uptime SLO (e.g., 99.9%).

## 22. Data Model (suggested)

- users(id, email, role, status, created_at, last_login_at, tenant_id)
- sessions(id, user_id, device, ip, created_at, expires_at, revoked)
- api_keys(id, user_id, scope, last_used_at, revoked)
- audit_logs(id, actor_id, action, target_id, before, after, created_at)
- events(id, user_id, type, metadata, created_at)
- metrics(time_bucket, name, value, dimensions_json)

## 23. Implementation Notes (Replit)

- [ ] Protect `/admin` routes with middleware (auth + RBAC).
- [ ] Store logs in append-only table or external log service.
- [ ] Use background jobs for aggregation (cron/worker).
- [ ] Cache hot dashboards (e.g., Redis) to reduce load.
- [ ] Index fields used in filters (email, user_id, created_at).
- [ ] Paginate all large queries.
- [ ] Sanitize any user-generated content shown in admin.

## 24. Common Failure Modes

- Over-broad admin access (no RBAC).
- Missing audit logs (no accountability).
- Impersonation without visibility.
- Secrets exposed in UI/logs.
- Metrics without segmentation (can’t localize issues).
- No alerts (issues discovered by users).
- Slow admin queries (no indexes/pagination).

## 25. Review Checklist Before Release

- Can a non-admin access `/admin` endpoints?
- Are all admin actions logged with actor + timestamp?
- Can admins revoke sessions and keys immediately?
- Are sensitive fields masked by default?
- Do alerts fire for error spikes?
- Are dashboards performant under load?
- Is impersonation clearly labeled and audited?
- Are bulk actions safe (confirmations/dry-run)?
- Are quotas and rate limits visible and adjustable?