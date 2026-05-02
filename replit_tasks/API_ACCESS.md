# API Access Checklist

Goals:
1. Authenticate every caller reliably.
2. Authorize every action with least privilege.
3. Limit blast radius if a token or key leaks.
4. Prevent abuse, scraping, replay, and denial-of-service.
5. Make API access auditable, observable, revocable, and easy to manage.

Reference baselines:
- OWASP API Security Top 10 2023
- OWASP Application Security Verification Standard
- IETF RFC 9700: Best Current Practice for OAuth 2.0 Security
- NIST SP 800-63B: Digital Identity Guidelines
- OpenAPI Specification

Useful references:
- https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- https://datatracker.ietf.org/doc/rfc9700/
- https://csrc.nist.gov/pubs/sp/800/63/b/upd2/final
- https://owasp.org/www-project-application-security-verification-standard/

---

## 1. API Access Modes

Support only the access modes your product actually needs.

- [ ] Public unauthenticated API access for non-sensitive data only.
- [ ] API key access for simple server-to-server integrations.
- [ ] OAuth 2.0 access for user-delegated access.
- [ ] OAuth 2.0 client credentials flow for machine-to-machine access.
- [ ] JSON Web Token (JWT) validation for signed tokens.
- [ ] HMAC request signing for high-integrity requests.
- [ ] Mutual TLS (mTLS) for high-trust enterprise/internal services.
- [ ] Webhooks with signature verification.
- [ ] Admin-generated service tokens for internal jobs only.
- [ ] Separate sandbox/test API access from production API access.

---

## 2. Authentication

- [ ] Require authentication for all private API endpoints.
- [ ] Never rely only on client-side checks.
- [ ] Accept tokens only in headers, not URLs.
- [ ] Use `Authorization: Bearer <token>` for OAuth/JWT tokens.
- [ ] Use a separate header for API keys, e.g. `X-API-Key`.
- [ ] Reject missing, malformed, expired, or revoked credentials.
- [ ] Validate token signature, issuer, audience, expiration, and not-before claims.
- [ ] Use strong signing algorithms: RS256, ES256, or EdDSA.
- [ ] Avoid weak JWT algorithms such as `none` or unexpected symmetric algorithms.
- [ ] Require HTTPS for every API request.
- [ ] Deny API access over plain HTTP.

---

## 3. Authorization

- [ ] Check authorization on every protected endpoint.
- [ ] Enforce permissions server-side.
- [ ] Use least privilege by default.
- [ ] Use scopes for API actions.
- [ ] Use role-based access control (RBAC) where appropriate.
- [ ] Use attribute-based access control (ABAC) where needed.
- [ ] Check object-level permissions on every resource by ID.
- [ ] Prevent user A from reading, editing, or deleting user B’s data.
- [ ] Prevent normal users from calling admin endpoints.
- [ ] Default deny unless explicitly allowed.
- [ ] Test horizontal authorization failures.
- [ ] Test vertical authorization failures.

Example scopes:

```txt
read:profile
write:profile
read:users
write:users
read:billing
write:billing
read:analytics
write:analytics
admin:users
admin:billing
admin:system