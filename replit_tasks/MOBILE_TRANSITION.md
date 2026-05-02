# Web App → Mobile App Transition Checklist

Goals:
1. Convert the web app into a mobile-first product, not just a smaller web page.
2. Preserve core user workflows while improving speed, convenience, and retention.
3. Build secure API access between the mobile app and backend.
4. Support mobile-specific behavior: offline use, push notifications, permissions, app-store release, and device testing.
5. Ship a minimum viable mobile app first, then expand features.

Reference baselines:
- Apple App Store Review Guidelines
- Apple Human Interface Guidelines
- Google Play Developer Policy Center
- Android Core App Quality Guidelines
- OWASP Mobile Application Security Verification Standard
- OWASP API Security Top 10

Useful references:
- https://developer.apple.com/app-store/review/guidelines/
- https://developer.apple.com/design/human-interface-guidelines/
- https://play.google.com/about/developer-content-policy/
- https://developer.android.com/docs/quality-guidelines/core-app-quality
- https://owasp.org/www-project-mobile-top-10/
- https://owasp.org/API-Security/

---

## 1. Product Strategy

- [ ] Define why the app should exist as mobile instead of web-only.
- [ ] Identify the top 3–5 mobile use cases.
- [ ] Remove nonessential web features from the first mobile version.
- [ ] Define the minimum viable mobile app.
- [ ] Define what must work offline.
- [ ] Define what requires real-time updates.
- [ ] Define what requires push notifications.
- [ ] Define what requires native device access.
- [ ] Define success metrics before building.

Suggested mobile success metrics:

```txt
Activation rate
Daily active users
Weekly active users
Retention D1 / D7 / D30
Push notification opt-in rate
Crash-free sessions
App open latency
Task completion rate
Conversion rate
Churn rate
Support tickets per 1,000 users