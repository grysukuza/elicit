"""
Flask web application for the Clinical Decision Support Tool.

Routes:
  GET  /                    — Main UI (text input form)  [auth required]
  POST /analyze             — Run pipeline, return JSON  [auth required]
  GET  /download            — Download PDF of last result  [auth required]
  POST /send-email          — Email result to provided address  [auth required]
  POST /evaluate-paper      — Critical appraisal of one paper  [auth required]
  GET  /download-references — BibTeX/RIS export  [auth required]

  GET  /login               — Login page
  POST /login               — Authenticate
  GET  /register            — Registration page
  POST /register            — Create account
  GET  /logout              — Log out
  GET  /forgot              — Forgot password page
  POST /forgot              — Issue reset token
  GET  /reset/<token>       — Reset password page
  POST /reset/<token>       — Set new password
  GET  /settings            — User settings  [auth required]
  POST /settings            — Update profile/preferences  [auth required]
  POST /settings/password   — Change password  [auth required]
  GET  /admin               — Admin panel  [admin required]
  POST /admin/users/<id>/admin   — Toggle admin flag  [admin required]
  POST /admin/users/<id>/delete  — Delete user  [admin required]
"""

import io
import os
import secrets as _secrets
import smtplib
import threading
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    session,
    redirect,
    url_for,
    flash,
    abort,
    g,
)
from dotenv import load_dotenv

from pipeline import run_pipeline
from pdf_generator import generate_pdf
from paper_evaluator import evaluate_paper, papers_to_bibtex, papers_to_ris
import auth
import email_inbox
from scheduler import BackgroundScheduler, should_start_scheduler

load_dotenv()

app = Flask(__name__)


def _load_or_create_secret_key() -> str:
    """Use FLASK_SECRET_KEY if set; otherwise persist a generated key to a
    local file so it survives Werkzeug debug-reloader restarts. Without
    persistence, the secret rotates on every reload and invalidates every
    user's session — breaking login (CSRF token can't be read back)."""
    env_key = os.environ.get("FLASK_SECRET_KEY")
    if env_key:
        return env_key
    key_path = os.path.join(os.path.dirname(__file__), ".flask_secret")
    try:
        with open(key_path, "r") as fh:
            existing = fh.read().strip()
            if existing:
                return existing
    except FileNotFoundError:
        pass
    new_key = _secrets.token_hex(32)
    try:
        with open(key_path, "w") as fh:
            fh.write(new_key)
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return new_key


app.secret_key = _load_or_create_secret_key()
# Cookies must be SameSite=None + Secure so they work inside Replit's preview iframe
# (the workspace hosts the app in a cross-site <iframe>).
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
)


class _PartitionedCookieMiddleware:
    """WSGI middleware that adds `Partitioned` to every Set-Cookie using
    SameSite=None. Modern browsers (Chrome 114+, etc.) require the CHIPS
    `Partitioned` attribute for cookies set inside cross-site iframes (like
    Replit's preview pane). Without it, the cookie is silently dropped and
    login state is lost on every navigation.

    This must run as WSGI middleware (not Flask after_request) because
    Flask's session cookie is added by `SecureCookieSessionInterface` in
    `app.process_response`, which runs *after* every after_request handler.
    """

    def __init__(self, wrapped):
        self.wrapped = wrapped

    def __call__(self, environ, start_response):
        def _start(status, headers, exc_info=None):
            new_headers = []
            for name, value in headers:
                if (
                    name.lower() == "set-cookie"
                    and "samesite=none" in value.lower()
                    and "partitioned" not in value.lower()
                ):
                    value = value + "; Partitioned"
                new_headers.append((name, value))
            return start_response(status, new_headers, exc_info)
        return self.wrapped(environ, _start)


app.wsgi_app = _PartitionedCookieMiddleware(app.wsgi_app)
app.permanent_session_lifetime = timedelta(days=auth.SESSION_DAYS)

# Initialize auth DB at startup
auth.init_db()

# In-memory result store keyed by result_id; each entry includes user_id ownership
_result_store: dict[str, dict] = {}


@app.context_processor
def inject_user():
    return {
        "current_user": auth.current_user(),
        "csrf_token": auth.get_csrf_token,
    }


@app.before_request
def _enforce_csrf():
    """CSRF protection for all state-changing requests."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    # /api/ routes authenticate via bearer key or X-Cron-Secret header — these
    # are not sent automatically by browsers, so they're CSRF-immune. We only
    # exempt the request from CSRF when one of those auth headers is present;
    # otherwise (e.g. a future cookie-authed /api/ route) CSRF still applies.
    if request.path.startswith("/api/") and (
        request.headers.get("Authorization", "").lower().startswith("bearer ")
        or request.headers.get("X-API-Key")
        or request.headers.get("X-Cron-Secret")
    ):
        return None
    # Stateless HMAC-signed CSRF token — validated without needing the
    # session cookie (which may be blocked by third-party cookie policies
    # when the app is embedded in a cross-site iframe like Replit's preview).
    submitted = (
        request.headers.get(auth.CSRF_HEADER)
        or (request.form.get(auth.CSRF_FIELD) if request.form else None)
    )
    if submitted is None and request.is_json:
        body = request.get_json(silent=True) or {}
        submitted = body.get(auth.CSRF_FIELD)

    if not submitted or not auth._verify_csrf_token(submitted):
        app.logger.warning(
            "CSRF reject path=%s submitted_present=%s",
            request.path, bool(submitted),
        )
        if request.is_json or "application/json" in request.headers.get("Accept", ""):
            return jsonify({"error": "Invalid or missing CSRF token."}), 400
        return ("Invalid or missing CSRF token. Please refresh and try again.", 400)
    return None


def _own_result(result_id: str | None) -> dict | None:
    """Fetch a stored result if it belongs to the current user."""
    if not result_id or result_id not in _result_store:
        return None
    entry = _result_store[result_id]
    user = auth.current_user()
    if not user or entry.get("user_id") != user["id"]:
        return None
    return entry


# ─────────────────────────────────────────────────────────────────────────────
# Main app routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
@auth.login_required
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
@auth.login_required
def analyze():
    data = request.get_json(silent=True) or {}
    free_text = (data.get("text") or "").strip()

    if not free_text:
        return jsonify({"error": "No text provided."}), 400

    try:
        output = run_pipeline(free_text)
    except Exception as exc:
        app.logger.exception("Pipeline error")
        return jsonify({"error": str(exc)}), 500

    user = auth.current_user()
    result_id = uuid.uuid4().hex
    _result_store[result_id] = {
        "user_id": user["id"],
        "output": output,
        "appraisals": {},
    }
    session["result_id"] = result_id

    # Record in query history (used by daily digest)
    try:
        auth.record_query(
            user["id"],
            free_text,
            output.get("result", {}).get("clinical_bottom_line", ""),
            source="web",
        )
    except Exception:
        app.logger.exception("Failed to record query history")

    auto_emailed_to = None
    if user["auto_email_results"] and user["email"]:
        try:
            _send_result_email(user["email"], output["result"])
            auto_emailed_to = user["email"]
        except Exception as exc:
            app.logger.warning("Auto-email failed: %s", exc)

    response = {"result_id": result_id, **output}
    if auto_emailed_to:
        response["auto_emailed_to"] = auto_emailed_to
    return jsonify(response)


@app.route("/download")
@auth.login_required
def download():
    result_id = request.args.get("result_id") or session.get("result_id")
    entry = _own_result(result_id)
    if not entry:
        return "No result available. Run an analysis first.", 404

    pdf_bytes = generate_pdf(entry["output"]["result"])

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="clinical_report.pdf",
    )


@app.route("/evaluate-paper", methods=["POST"])
@auth.login_required
def evaluate_paper_route():
    data = request.get_json(silent=True) or {}
    result_id = data.get("result_id") or session.get("result_id")
    paper_index = data.get("paper_index")

    entry = _own_result(result_id)
    if not entry:
        return jsonify({"error": "No result available. Run an analysis first."}), 404
    if paper_index is None:
        return jsonify({"error": "paper_index required."}), 400

    papers = entry["output"].get("result", {}).get("papers_used", [])
    try:
        idx = int(paper_index)
    except (TypeError, ValueError):
        return jsonify({"error": "paper_index must be an integer."}), 400
    if idx < 0 or idx >= len(papers):
        return jsonify({"error": "paper_index out of range."}), 400

    cache = entry["appraisals"]
    cache_key = str(idx)
    if cache_key in cache:
        return jsonify({"appraisal": cache[cache_key], "cached": True})

    try:
        appraisal = evaluate_paper(papers[idx])
    except Exception:
        app.logger.exception("Appraisal error")
        return jsonify({"error": "Failed to perform appraisal. Please try again."}), 500

    cache[cache_key] = appraisal
    return jsonify({"appraisal": appraisal, "cached": False})


@app.route("/download-references")
@auth.login_required
def download_references():
    fmt = (request.args.get("format") or "bibtex").lower()
    result_id = request.args.get("result_id") or session.get("result_id")
    entry = _own_result(result_id)
    if not entry:
        return "No result available. Run an analysis first.", 404

    papers = entry["output"].get("result", {}).get("papers_used", [])
    if not papers:
        return "No references available.", 404

    if fmt == "ris":
        body = papers_to_ris(papers)
        mimetype = "application/x-research-info-systems"
        filename = "references.ris"
    else:
        body = papers_to_bibtex(papers)
        mimetype = "application/x-bibtex"
        filename = "references.bib"

    return send_file(
        io.BytesIO(body.encode("utf-8")),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


@app.route("/send-email", methods=["POST"])
@auth.login_required
def send_email():
    data = request.get_json(silent=True) or {}
    recipient = (data.get("email") or "").strip()
    result_id = data.get("result_id") or session.get("result_id")

    if not recipient:
        return jsonify({"error": "No email address provided."}), 400

    entry = _own_result(result_id)
    if not entry:
        return jsonify({"error": "No result available. Run an analysis first."}), 404

    try:
        _send_result_email(recipient, entry["output"]["result"])
        return jsonify({"message": f"Report emailed to {recipient}."})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        app.logger.exception("Email error")
        return jsonify({"error": "Failed to send email."}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Email helpers
# ─────────────────────────────────────────────────────────────────────────────

def _smtp_settings() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASS", "").replace(" ", ""),
        "from_addr": os.environ.get("SMTP_FROM", "") or os.environ.get("SMTP_USER", ""),
    }


def _send_smtp(recipient: str, subject: str, body_text: str,
               attachment: tuple[str, bytes, str] | None = None) -> None:
    s = _smtp_settings()
    if not s["host"]:
        raise RuntimeError(
            "Email is not configured. An admin must set SMTP_HOST/SMTP_USER/"
            "SMTP_PASS in environment variables."
        )

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = s["from_addr"] or s["user"]
    msg["To"] = recipient
    msg.attach(MIMEText(body_text, "plain"))

    if attachment:
        filename, blob, mimetype = attachment
        maintype, subtype = mimetype.split("/", 1)
        part = MIMEBase(maintype, subtype)
        part.set_payload(blob)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    with smtplib.SMTP(s["host"], s["port"]) as server:
        server.ehlo()
        server.starttls()
        if s["user"]:
            server.login(s["user"], s["password"])
        server.sendmail(msg["From"], [recipient], msg.as_string())


def _send_result_email(recipient: str, result: dict) -> None:
    pdf_bytes = generate_pdf(result)
    body = _result_to_plain_text(result)
    _send_smtp(
        recipient=recipient,
        subject="Clinical Decision Support Report",
        body_text=body,
        attachment=("clinical_report.pdf", pdf_bytes, "application/pdf"),
    )


def _result_to_plain_text(result: dict) -> str:
    from meta_analysis import format_probability_table, ProbabilityEstimates
    est_dict = result.get("probability_estimates", {})
    est = ProbabilityEstimates(**{k: est_dict.get(k) for k in ProbabilityEstimates.__dataclass_fields__})

    lines = [
        "CLINICAL DECISION SUPPORT REPORT",
        "=" * 60,
        "",
        "CLINICAL QUESTION",
        result.get("pico_statement", ""),
        "",
        "CLINICAL BOTTOM LINE",
        result.get("clinical_bottom_line", ""),
        "",
        "EVIDENCE SUMMARY",
        f"Quality: {result.get('evidence_quality', '')}",
        "",
        result.get("summary", ""),
        "",
        format_probability_table(est),
        "",
        "LIMITATIONS",
        result.get("limitations", ""),
        "",
        "REFERENCES",
    ]
    for i, p in enumerate(result.get("papers_used", []), 1):
        authors = ", ".join((p.get("authors") or [])[:3])
        urls = p.get("urls") or []
        url_str = f"  {urls[0]}" if urls else ""
        lines.append(f"[{i}] {p.get('title', '')} ({authors}, {p.get('year', '')}){url_str}")

    lines += [
        "",
        "─" * 60,
        "DISCLAIMER: AI-assisted tool. Not a substitute for professional medical advice.",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Auth routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if auth.current_user():
        return redirect(url_for("index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        user = auth.verify_credentials(username, password)
        if not user:
            flash("Invalid username or password.", "error")
            return render_template("login.html", username=username), 401

        auth.login_user(user["id"], remember=remember)
        auth.touch_last_login(user["id"])
        nxt = auth.safe_next_url(request.args.get("next"), default=url_for("index"))
        return redirect(nxt)

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if auth.current_user():
        return redirect(url_for("index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""

        if password != password2:
            flash("Passwords do not match.", "error")
            return render_template("register.html", username=username, email=email), 400

        # First user automatically becomes admin
        is_first = auth.user_count() == 0

        try:
            user_id = auth.create_user(
                username=username, password=password, email=email, is_admin=is_first
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("register.html", username=username, email=email), 400

        auth.login_user(user_id, remember=True)
        auth.touch_last_login(user_id)
        if is_first:
            flash("Account created. You are the first user and have admin privileges.", "info")
        else:
            flash("Account created.", "info")
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    auth.logout_user()
    return redirect(url_for("login"))


@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        user = auth.get_user_by_username(identifier) or auth.get_user_by_email(identifier)

        # Always show success-like message to avoid account enumeration
        smtp_configured = bool(_smtp_settings()["host"])
        msg_emailed = "If an account matches, a password-reset link has been emailed."
        msg_admin = (
            "If an account matches, a password-reset link has been generated. "
            "Email is not configured on this server, so please contact your "
            "administrator to obtain it."
        )

        if user:
            token = auth.create_reset_token(user["id"])
            reset_url = url_for("reset", token=token, _external=True)
            if smtp_configured and user["email"]:
                try:
                    _send_smtp(
                        recipient=user["email"],
                        subject="Password Reset — Clinical Decision Support",
                        body_text=(
                            f"Hello {user['username']},\n\n"
                            f"Use the link below to reset your password. "
                            f"It expires in {auth.RESET_TOKEN_TTL_HOURS} hours:\n\n"
                            f"{reset_url}\n\n"
                            "If you did not request this, you can ignore this email.\n"
                        ),
                    )
                except Exception:
                    app.logger.exception("Reset email failed")

        flash(msg_emailed if smtp_configured else msg_admin, "info")
        return redirect(url_for("login"))

    return render_template("forgot.html")


@app.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    record = auth.get_reset_record(token)
    if not record:
        flash("This reset link is invalid or has expired.", "error")
        return redirect(url_for("forgot"))

    if request.method == "POST":
        pw1 = request.form.get("password") or ""
        pw2 = request.form.get("password2") or ""
        if pw1 != pw2:
            flash("Passwords do not match.", "error")
            return render_template("reset.html", token=token), 400
        try:
            auth.change_password(record["user_id"], pw1)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("reset.html", token=token), 400
        auth.consume_reset_token(token)
        flash("Password updated. You can now log in.", "info")
        return redirect(url_for("login"))

    return render_template("reset.html", token=token)


# ─────────────────────────────────────────────────────────────────────────────
# Settings & admin
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
@auth.login_required
def settings():
    user = auth.current_user()

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        auto_email = bool(request.form.get("auto_email_results"))
        daily_digest = bool(request.form.get("daily_digest"))
        auth.update_user(
            user["id"],
            email=email,
            auto_email_results=auto_email,
            daily_digest=daily_digest,
        )
        flash("Settings saved.", "info")
        return redirect(url_for("settings"))

    return render_template(
        "settings.html",
        user=user,
        smtp_configured=bool(_smtp_settings()["host"]),
        imap_configured=email_inbox.imap_configured(),
        api_base_url=request.url_root.rstrip("/"),
        inbox_address=os.environ.get("IMAP_USER", ""),
    )


@app.route("/settings/api-key", methods=["POST"])
@auth.login_required
def regenerate_api_key():
    user = auth.current_user()
    new_key = auth.regenerate_api_key(user["id"])
    flash(
        "A new API key has been generated. Copy it now — it won't be shown again "
        "unless you regenerate.",
        "info",
    )
    session["_just_issued_api_key"] = new_key
    return redirect(url_for("settings"))


@app.route("/settings/api-key/revoke", methods=["POST"])
@auth.login_required
def revoke_api_key():
    user = auth.current_user()
    auth.revoke_api_key(user["id"])
    flash("API key revoked.", "info")
    return redirect(url_for("settings"))


@app.route("/settings/password", methods=["POST"])
@auth.login_required
def change_password():
    user = auth.current_user()
    current = request.form.get("current_password") or ""
    new1 = request.form.get("new_password") or ""
    new2 = request.form.get("new_password2") or ""

    if not auth.verify_credentials(user["username"], current):
        flash("Current password is incorrect.", "error")
        return redirect(url_for("settings"))
    if new1 != new2:
        flash("New passwords do not match.", "error")
        return redirect(url_for("settings"))
    try:
        auth.change_password(user["id"], new1)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("settings"))
    flash("Password changed successfully.", "info")
    return redirect(url_for("settings"))


@app.route("/admin")
@auth.admin_required
def admin_panel():
    users = auth.list_users()
    pending = auth.list_pending_resets()
    # Build full reset URLs for admin to share when email isn't configured
    pending_with_urls = [
        {**dict(p), "reset_url": url_for("reset", token=p["token"], _external=True)}
        for p in pending
    ]
    total_users = len(users)
    admin_count = sum(1 for u in users if u["is_admin"])
    smtp_configured = bool(_smtp_settings()["host"])
    return render_template(
        "admin.html",
        users=users,
        pending=pending_with_urls,
        smtp_configured=smtp_configured,
        stats={
            "total_users": total_users,
            "standard_users": total_users - admin_count,
            "admin_users": admin_count,
            "pending_resets": len(pending_with_urls),
            "smtp_status": "Configured" if smtp_configured else "Not configured",
        },
    )


@app.route("/admin/users/<int:user_id>/admin", methods=["POST"])
@auth.admin_required
def admin_toggle_admin(user_id):
    me = auth.current_user()
    target = auth.get_user_by_id(user_id)
    if not target:
        abort(404)
    if target["id"] == me["id"]:
        flash("You cannot change your own admin status.", "error")
        return redirect(url_for("admin_panel"))
    auth.set_admin(user_id, not target["is_admin"])
    flash(
        f"{target['username']} is now {'an admin' if not target['is_admin'] else 'a regular user'}.",
        "info",
    )
    return redirect(url_for("admin_panel"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@auth.admin_required
def admin_delete_user(user_id):
    me = auth.current_user()
    target = auth.get_user_by_id(user_id)
    if not target:
        abort(404)
    if target["id"] == me["id"]:
        flash("You cannot delete your own account from the admin panel.", "error")
        return redirect(url_for("admin_panel"))
    auth.delete_user(user_id)
    flash(f"User {target['username']} deleted.", "info")
    return redirect(url_for("admin_panel"))


# ─────────────────────────────────────────────────────────────────────────────
# REST API (key-authenticated)
# ─────────────────────────────────────────────────────────────────────────────

API_VERSION = "1"


def _extract_api_key() -> str:
    """Extract an API key from Authorization: Bearer ... or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return (request.headers.get("X-API-Key") or "").strip()


def api_key_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        key = _extract_api_key()
        user = auth.get_user_by_api_key(key) if key else None
        if not user:
            return jsonify({
                "error": "Invalid or missing API key.",
                "hint": "Send 'Authorization: Bearer <key>' or 'X-API-Key: <key>'.",
            }), 401
        g.api_user = user
        return view(*args, **kwargs)
    return wrapped


def cron_secret_required(view):
    """Routes called by an external cron need a shared secret in X-Cron-Secret."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        configured = os.environ.get("CRON_SECRET", "")
        if not configured:
            return jsonify({"error": "CRON_SECRET is not configured on this server."}), 503
        provided = request.headers.get("X-Cron-Secret", "")
        if not provided or not _secrets.compare_digest(provided, configured):
            return jsonify({"error": "Invalid cron secret."}), 401
        return view(*args, **kwargs)
    return wrapped


@app.route("/api/v1/health", methods=["GET"])
def api_health():
    """Public ping endpoint — no auth required."""
    return jsonify({
        "status": "ok",
        "service": "clinical-decision-support",
        "version": API_VERSION,
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "smtp_configured": bool(_smtp_settings()["host"]),
        "imap_configured": email_inbox.imap_configured(),
    })


@app.route("/api/v1/me", methods=["GET"])
@api_key_required
def api_me():
    u = g.api_user
    return jsonify({
        "id": u["id"],
        "username": u["username"],
        "email": u["email"],
        "is_admin": bool(u["is_admin"]),
        "auto_email_results": bool(u["auto_email_results"]),
        "daily_digest": bool(u["daily_digest"]),
    })


@app.route("/api/v1/analyze", methods=["POST"])
@api_key_required
def api_analyze():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or data.get("text") or "").strip()
    if not question:
        return jsonify({"error": "Field 'question' is required."}), 400

    try:
        max_papers = int(data.get("max_papers", 20))
    except (TypeError, ValueError):
        max_papers = 20
    max_papers = max(1, min(max_papers, 50))

    try:
        output = run_pipeline(question, max_papers=max_papers)
    except Exception as exc:
        app.logger.exception("API analyze pipeline error")
        return jsonify({"error": str(exc)}), 500

    user = g.api_user
    try:
        auth.record_query(
            user["id"],
            question,
            output.get("result", {}).get("clinical_bottom_line", ""),
            source="api",
        )
    except Exception:
        app.logger.exception("Failed to record API query history")

    # Optional: email the result if requested or if user opted in
    if (data.get("email") or user["auto_email_results"]) and user["email"]:
        try:
            _send_result_email(user["email"], output["result"])
            output["emailed_to"] = user["email"]
        except Exception as exc:
            app.logger.warning("API auto-email failed: %s", exc)
            output["email_error"] = str(exc)

    return jsonify(output)


@app.route("/api/v1/digest/run", methods=["POST"])
@cron_secret_required
def api_digest_run():
    """External-cron-triggered daily digest dispatch."""
    sent, skipped = run_daily_digest(force=False)
    return jsonify({"sent": sent, "skipped": skipped})


@app.route("/api/v1/inbox/poll", methods=["POST"])
@cron_secret_required
def api_inbox_poll():
    """External-cron-triggered IMAP poll (alternative to the internal scheduler)."""
    n = poll_inbox_now()
    return jsonify({"processed": n})


# ─────────────────────────────────────────────────────────────────────────────
# Daily digest
# ─────────────────────────────────────────────────────────────────────────────

DIGEST_INTERVAL_HOURS = 24

# Single-flight locks: prevent overlapping scheduler + cron-endpoint runs
# from doing duplicate work in the same process.
_digest_lock = threading.Lock()
_inbox_lock = threading.Lock()

# Public base URL used for outbound emails sent from background threads
# (where Flask's `request` object is not available).
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")


def _digest_body(user: dict, since_iso: str) -> str:
    rows = auth.queries_since(user["id"], since_iso)
    lines = [
        f"Hello {user['username']},",
        "",
        "Here is your daily Clinical Decision Support digest.",
        "",
        f"Service status: API healthy (v{API_VERSION}).",
        "",
    ]
    if rows:
        lines.append(f"Your activity in the last 24 hours ({len(rows)} question{'s' if len(rows) != 1 else ''}):")
        lines.append("")
        for r in rows:
            q = (r["question"] or "").replace("\n", " ").strip()
            if len(q) > 140:
                q = q[:137] + "…"
            bl = (r["bottom_line"] or "").replace("\n", " ").strip()
            if len(bl) > 220:
                bl = bl[:217] + "…"
            lines.append(f"• [{r['source']}] {q}")
            if bl:
                lines.append(f"    → {bl}")
            lines.append("")
    else:
        lines.append("No questions analyzed in the last 24 hours.")
        lines.append("")
        lines.append("Tip: you can email a question to the configured inbox or POST")
        lines.append("to /api/v1/analyze with your API key for an instant analysis.")
        lines.append("")

    lines += [
        "─" * 60,
        "You're receiving this because daily digest is enabled in your settings.",
        "Disable it any time at /settings.",
    ]
    return "\n".join(lines)


def run_daily_digest(force: bool = False) -> tuple[int, int]:
    """Send digest to every opted-in user whose 24h window has elapsed.

    Race-safe: each user's slot is claimed via an atomic conditional UPDATE
    (`auth.claim_digest_slot`) so concurrent scheduler + cron-endpoint runs
    cannot send duplicate digests. A process-level lock additionally
    serialises in-process callers.
    """
    if not _smtp_settings()["host"]:
        app.logger.info("Skipping digest: SMTP not configured")
        return (0, 0)

    if not _digest_lock.acquire(blocking=False):
        app.logger.info("Skipping digest: another digest run is already in progress")
        return (0, 0)

    try:
        sent = 0
        skipped = 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=DIGEST_INTERVAL_HOURS)
        since_iso = cutoff.isoformat(timespec="seconds")

        for user in auth.get_users_with_digest():
            previous_last = user["last_digest_at"]
            if force:
                # When forced, send unconditionally and just timestamp it
                claimed = True
                auth.mark_digest_sent(user["id"])
            else:
                claimed = auth.claim_digest_slot(user["id"], since_iso)
            if not claimed:
                skipped += 1
                continue
            try:
                body = _digest_body(dict(user), since_iso)
                _send_smtp(
                    recipient=user["email"],
                    subject="Daily Digest — Clinical Decision Support",
                    body_text=body,
                )
                sent += 1
            except Exception:
                app.logger.exception("Failed to send digest to user %s", user["id"])
                # Roll back the claim so the next run can retry this user
                auth.release_digest_slot(user["id"], previous_last)

        if sent or skipped:
            app.logger.info("Daily digest run: sent=%d skipped=%d", sent, skipped)
        return (sent, skipped)
    finally:
        _digest_lock.release()


# ─────────────────────────────────────────────────────────────────────────────
# Email-to-answer (IMAP inbound handler)
# ─────────────────────────────────────────────────────────────────────────────

def _user_lookup_by_email(addr: str):
    user = auth.get_user_by_email(addr)
    return dict(user) if user else None


def _handle_inbound_question(user: dict, subject: str, body: str) -> None:
    """Run the pipeline for an inbound email and reply with the analysis."""
    question = (body or subject or "").strip()
    if not question:
        try:
            _send_smtp(
                recipient=user["email"],
                subject="Re: " + (subject or "Your clinical question"),
                body_text=(
                    f"Hello {user['username']},\n\n"
                    "We received your email but couldn't find a clinical question "
                    "in the body. Please reply with your question in plain text.\n\n"
                    "— Clinical Decision Support"
                ),
            )
        except Exception:
            app.logger.exception("Failed to send empty-body reply")
        return

    try:
        output = run_pipeline(question)
    except Exception:
        app.logger.exception("Pipeline failed for inbound email from %s", user["email"])
        try:
            _send_smtp(
                recipient=user["email"],
                subject="Re: " + (subject or "Your clinical question"),
                body_text=(
                    "We were unable to analyze your question due to a server "
                    "error. Please try again later or use the web interface.\n\n"
                    "— Clinical Decision Support"
                ),
            )
        except Exception:
            app.logger.exception("Failed to send error reply")
        return

    try:
        auth.record_query(
            user["id"],
            question,
            output.get("result", {}).get("clinical_bottom_line", ""),
            source="email",
        )
    except Exception:
        app.logger.exception("Failed to record email query history")

    try:
        result = output["result"]
        body_text = (
            f"Hello {user['username']},\n\n"
            f"Below is the analysis for your question:\n\n"
            f"\"{question[:500]}{'…' if len(question) > 500 else ''}\"\n\n"
            "─" * 60 + "\n\n"
            + _result_to_plain_text(result)
        )
        pdf_bytes = generate_pdf(result)
        _send_smtp(
            recipient=user["email"],
            subject="Re: " + (subject or "Your clinical question"),
            body_text=body_text,
            attachment=("clinical_report.pdf", pdf_bytes, "application/pdf"),
        )
    except Exception:
        app.logger.exception("Failed to send analysis reply")


def _handle_unknown_sender(sender: str, subject: str, body: str) -> None:
    """Polite bounce-back for emails from non-registered addresses.

    This callback may run inside a background thread (no Flask request
    context), so we use the configured PUBLIC_BASE_URL env var for the link.
    """
    if not sender:
        return
    base = PUBLIC_BASE_URL or "your Clinical Decision Support server"
    register_link = f"{base}/register" if PUBLIC_BASE_URL else f"{base} (visit /register)"
    try:
        _send_smtp(
            recipient=sender,
            subject="Re: " + (subject or "Clinical Decision Support"),
            body_text=(
                "Hello,\n\n"
                "Thanks for writing in. To use the email-question service you "
                "must first register an account using this email address at:\n"
                f"  {register_link}\n\n"
                "Once registered, just reply to this address with your clinical "
                "question and you'll get an analysis back.\n\n"
                "— Clinical Decision Support"
            ),
        )
    except Exception:
        app.logger.exception("Failed to send unknown-sender bounce")


def poll_inbox_now(max_messages: int | None = None) -> int:
    """Run one IMAP poll cycle. Safe to call from anywhere.

    A process-level lock prevents the background scheduler and the
    `/api/v1/inbox/poll` endpoint from polling at the same time, which would
    risk fetching the same UNSEEN messages twice before flags are updated.
    """
    if not email_inbox.imap_configured() or not _smtp_settings()["host"]:
        return 0
    if max_messages is None:
        max_messages = int(os.environ.get("IMAP_MAX_PER_POLL", "10"))
    if not _inbox_lock.acquire(blocking=False):
        app.logger.info("Skipping inbox poll: another poll is already in progress")
        return 0
    try:
        return email_inbox.poll_inbox(
            user_lookup=_user_lookup_by_email,
            on_question=_handle_inbound_question,
            on_unknown=_handle_unknown_sender,
            max_messages=max_messages,
        )
    finally:
        _inbox_lock.release()


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler startup
# ─────────────────────────────────────────────────────────────────────────────

_scheduler: BackgroundScheduler | None = None


def _start_scheduler_once() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    if not should_start_scheduler():
        return
    _scheduler = BackgroundScheduler(
        poll_inbox_fn=poll_inbox_now if email_inbox.imap_configured() else None,
        run_digest_fn=lambda: run_daily_digest(force=False)[0],
        imap_poll_seconds=int(os.environ.get("IMAP_POLL_SECONDS", "60")),
        digest_check_seconds=300,  # check every 5 minutes
    )
    _scheduler.start()


_start_scheduler_once()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") not in ("0", "false", "False", "")
    app.run(debug=debug, host="0.0.0.0", port=port)
