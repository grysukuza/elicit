# Elicit Clinical Decision Support Tool

## Overview
A Clinical Decision Support System designed for physicians in hospital settings. It automates the process of answering clinical questions by:
1. Parsing raw text into a structured PICO framework using LLMs.
2. Retrieving academic literature via the Elicit API.
3. Synthesizing a meta-analysis with a "Clinical Bottom Line" and probability estimates (ARR, RRR, NNT, Sens/Spec).
4. Per-paper critical appraisal (Oxford CEBM, GRADE, Jadad, QUADAS-2, NOS, AMSTAR-2).
5. PDF reports + BibTeX/RIS citation export.

The system can be used three ways:
- **Web UI** (PICO form, results page) — full authentication, settings, admin panel.
- **REST API** with per-user API keys.
- **Email-to-answer** — send a question by email, get an analysis back.

## Tech Stack
- **Backend:** Python 3.12 + Flask
- **AI/LLM:** Anthropic Claude
- **External:** Elicit API (literature), SMTP (outbound email), IMAP (inbound email)
- **Storage:** SQLite (`app.db`) for users / sessions / query history
- **PDF:** ReportLab

## Project Structure
- `app.py` — Flask app, all routes (web + REST API), scheduler bootstrap
- `auth.py` — SQLite-backed users, sessions, password resets, API keys, query history
- `email_inbox.py` — IMAP poller and email parsing
- `scheduler.py` — Background daemon thread that polls IMAP and triggers daily digests
- `pipeline.py` — Question parser → Elicit → meta-analysis orchestrator
- `question_parser.py`, `elicit_client.py`, `meta_analysis.py` — pipeline pieces
- `paper_evaluator.py` — Critical appraisal + BibTeX/RIS export
- `pdf_generator.py` — PDF report generation
- `templates/` — Jinja2 templates (extends `_base.html`)
- `static/style.css` — UI styles

## REST API
All API endpoints live under `/api/v1/`. JSON in/out. CSRF is bypassed for API
routes; auth uses bearer tokens or shared secrets.

| Endpoint                     | Auth                      | Purpose                                    |
|-----------------------------|---------------------------|--------------------------------------------|
| `GET /api/v1/health`        | Public                    | Liveness ping (status, time, capabilities) |
| `GET /api/v1/me`            | Bearer key                | Current user info                          |
| `POST /api/v1/analyze`      | Bearer key                | Run pipeline; returns full result JSON     |
| `POST /api/v1/digest/run`   | `X-Cron-Secret` header    | Send pending daily digests                 |
| `POST /api/v1/inbox/poll`   | `X-Cron-Secret` header    | Poll IMAP inbox once                       |

Auth headers accepted: `Authorization: Bearer <key>` **or** `X-API-Key: <key>`.
Users mint and revoke their own keys at `/settings`.

### Example
```bash
# Health
curl https://your-host/api/v1/health

# Run an analysis
curl -X POST https://your-host/api/v1/analyze \
     -H "Authorization: Bearer cds_..." \
     -H "Content-Type: application/json" \
     -d '{"question": "65yo with afib, DOAC vs warfarin?"}'
```

## Daily Digest
- Per-user toggle in `/settings`.
- Sent at most once every 24 hours per user (idempotent).
- Triggered two ways:
  - **Internal scheduler** (background thread, default on).
  - **External cron** hitting `POST /api/v1/digest/run` with `X-Cron-Secret`.

## Email-to-Answer
- When IMAP is configured, a background thread polls the inbox every
  `IMAP_POLL_SECONDS` (default 60s).
- Inbound email body/subject becomes the clinical question.
- Sender is matched by email to a registered user; the analysis is replied with
  PDF attachment.
- Unknown senders get a polite "register first" reply.
- Can also be triggered on demand via `POST /api/v1/inbox/poll` with the cron
  secret.

## Environment Variables
| Variable                   | Required for           | Notes                                |
|---------------------------|------------------------|--------------------------------------|
| `ANTHROPIC_API_KEY`       | Core pipeline          | Anthropic Claude                     |
| `ELICIT_API_KEY`          | Literature search      | Elicit API                           |
| `FLASK_SECRET_KEY`        | Recommended            | Persists sessions across restarts    |
| `SMTP_HOST/PORT/USER/PASS/FROM` | Email features    | Outbound email (reports, digest)     |
| `IMAP_HOST/PORT/USER/PASS/FOLDER` | Email-to-answer  | Inbound email polling                |
| `IMAP_POLL_SECONDS`       | Optional               | Default 60                            |
| `CRON_SECRET`             | External cron triggers | Required for `/api/v1/*/run` & `/poll` |
| `DISABLE_SCHEDULER`       | Optional               | `1` to disable background scheduler   |
| `FLASK_DEBUG`             | Dev only               | `1` enables debug; `0` disables       |

## Authentication
- SQLite-backed user store; passwords hashed with werkzeug pbkdf2.
- 30-day "remember me" sessions (`SameSite=None; Secure` for Replit's iframe).
- CSRF protection on all state-changing form/JSON endpoints.
- First registered user automatically gets admin privileges.
- Forgot/reset password flow with 24h tokens; admin panel exposes pending links
  if SMTP isn't configured.

## Workflow
- **Start application**: `python app.py` on port `5000` (webview).
