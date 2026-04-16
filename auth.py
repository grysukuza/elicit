"""
Authentication & user management for the Clinical Decision Support tool.

Provides:
  - SQLite-backed user store (username, email, password hash, admin flag,
    auto_email_results preference).
  - Password hashing (werkzeug pbkdf2).
  - Session helpers with 30-day "remember me" persistence.
  - login_required / admin_required decorators.
  - Password reset tokens (single-use, time-limited).
"""

from __future__ import annotations

import os
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional

from urllib.parse import urlparse

from flask import session, redirect, url_for, request, jsonify, g, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash


DB_PATH = os.environ.get("AUTH_DB_PATH", "app.db")
RESET_TOKEN_TTL_HOURS = 24
SESSION_DAYS = 30


# ─────────────────────────────────────────────────────────────────────────────
# DB setup
# ─────────────────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                email TEXT COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                auto_email_results INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE TABLE IF NOT EXISTS password_resets (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────────
# User CRUD
# ─────────────────────────────────────────────────────────────────────────────

def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    if not email:
        return None
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()


def list_users() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM users ORDER BY created_at ASC"
        ).fetchall()


def user_count() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]


def create_user(
    username: str,
    password: str,
    email: Optional[str] = None,
    is_admin: bool = False,
) -> int:
    """Create a user. Returns the new user_id. Raises ValueError on conflict."""
    username = username.strip()
    email = (email or "").strip() or None
    if not username or not password:
        raise ValueError("Username and password are required.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    with _connect() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            raise ValueError("Username already taken.")

        cur = conn.execute(
            """
            INSERT INTO users (username, email, password_hash, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, email, generate_password_hash(password),
             1 if is_admin else 0, _now()),
        )
        return cur.lastrowid


def verify_credentials(username: str, password: str) -> Optional[sqlite3.Row]:
    user = get_user_by_username(username)
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def touch_last_login(user_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?", (_now(), user_id)
        )


def update_user(
    user_id: int,
    email: Optional[str] = None,
    auto_email_results: Optional[bool] = None,
) -> None:
    fields = []
    values: list = []
    if email is not None:
        fields.append("email = ?")
        values.append(email.strip() or None)
    if auto_email_results is not None:
        fields.append("auto_email_results = ?")
        values.append(1 if auto_email_results else 0)
    if not fields:
        return
    values.append(user_id)
    with _connect() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)


def change_password(user_id: int, new_password: str) -> None:
    """Change a user's password and invalidate all outstanding reset tokens."""
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), user_id),
        )
        _invalidate_user_reset_tokens(conn, user_id)


def set_admin(user_id: int, is_admin: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET is_admin = ? WHERE id = ?",
            (1 if is_admin else 0, user_id),
        )


def delete_user(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# ─────────────────────────────────────────────────────────────────────────────
# Password reset tokens
# ─────────────────────────────────────────────────────────────────────────────

def _invalidate_user_reset_tokens(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute(
        "UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0",
        (user_id,),
    )


def create_reset_token(user_id: int) -> str:
    """Issue a fresh reset token, invalidating any prior outstanding ones."""
    token = secrets.token_urlsafe(32)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_TTL_HOURS)
    ).isoformat(timespec="seconds")
    with _connect() as conn:
        _invalidate_user_reset_tokens(conn, user_id)
        conn.execute(
            """
            INSERT INTO password_resets (token, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, user_id, expires_at, _now()),
        )
    return token


def get_reset_record(token: str) -> Optional[sqlite3.Row]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM password_resets WHERE token = ?", (token,)
        ).fetchone()
    if not row:
        return None
    if row["used"]:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        return None
    return row


def consume_reset_token(token: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE password_resets SET used = 1 WHERE token = ?", (token,)
        )


def list_pending_resets() -> list[sqlite3.Row]:
    """For admin panel — pending, unexpired reset tokens with usernames."""
    now_iso = _now()
    with _connect() as conn:
        return conn.execute(
            """
            SELECT pr.token, pr.created_at, pr.expires_at,
                   u.id AS user_id, u.username, u.email
            FROM password_resets pr
            JOIN users u ON u.id = pr.user_id
            WHERE pr.used = 0 AND pr.expires_at > ?
            ORDER BY pr.created_at DESC
            """,
            (now_iso,),
        ).fetchall()


# ─────────────────────────────────────────────────────────────────────────────
# Session helpers
# ─────────────────────────────────────────────────────────────────────────────

def login_user(user_id: int, remember: bool = True) -> None:
    session["user_id"] = user_id
    session.permanent = remember  # 30-day lifetime configured on app


def logout_user() -> None:
    session.pop("user_id", None)
    session.pop("result_id", None)


def current_user() -> Optional[sqlite3.Row]:
    if hasattr(g, "_current_user"):
        return g._current_user
    uid = session.get("user_id")
    user = get_user_by_id(uid) if uid else None
    g._current_user = user
    return user


# ─────────────────────────────────────────────────────────────────────────────
# Decorators
# ─────────────────────────────────────────────────────────────────────────────

def _wants_json() -> bool:
    accept = request.headers.get("Accept", "")
    return (
        request.path.startswith("/api/")
        or request.is_json
        or "application/json" in accept
    )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            if _wants_json():
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def safe_next_url(target: Optional[str], default: str = "/") -> str:
    """Validate a `next` redirect target — only allow same-origin relative paths."""
    if not target:
        return default
    # Reject anything containing a scheme or protocol-relative '//'
    if target.startswith("//") or target.startswith("\\"):
        return default
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return default
    if not target.startswith("/"):
        return default
    return target


# ─────────────────────────────────────────────────────────────────────────────
# CSRF protection
# ─────────────────────────────────────────────────────────────────────────────

CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def get_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _csrf_safe_method() -> bool:
    return request.method in ("GET", "HEAD", "OPTIONS")


def _check_csrf() -> bool:
    expected = session.get("_csrf_token")
    if not expected:
        return False
    submitted = (
        request.headers.get(CSRF_HEADER)
        or (request.form.get(CSRF_FIELD) if request.form else None)
        or (request.get_json(silent=True) or {}).get(CSRF_FIELD)
    )
    if not submitted:
        return False
    return secrets.compare_digest(str(expected), str(submitted))


def csrf_protect(view):
    """Decorator that enforces CSRF on state-changing methods."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _csrf_safe_method() and not _check_csrf():
            if _wants_json():
                return jsonify({"error": "Invalid or missing CSRF token."}), 400
            abort(400)
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        u = current_user()
        if not u:
            if _wants_json():
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("login", next=request.path))
        if not u["is_admin"]:
            if _wants_json():
                return jsonify({"error": "Admin privileges required."}), 403
            flash("Admin privileges required.", "error")
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped
