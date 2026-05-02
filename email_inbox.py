"""
IMAP inbox poller — listens for inbound clinical questions sent by email and
replies with an analysis.

Configured by environment variables:
  IMAP_HOST          (e.g. imap.gmail.com)        — required to enable
  IMAP_PORT          (default 993)
  IMAP_USER          (login email)
  IMAP_PASS          (app password)
  IMAP_FOLDER        (default INBOX)
  IMAP_POLL_SECONDS  (default 60)

The poller matches the From: address to a registered user. Anonymous senders
get a polite "please register first" reply. Authorized senders get the full
analysis (plain-text email + PDF attachment).

Designed to be run on a daemon thread by `scheduler.py`.
"""

from __future__ import annotations

import email
import imaplib
import logging
import os
import re
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def imap_configured() -> bool:
    return bool(os.environ.get("IMAP_HOST")) and bool(os.environ.get("IMAP_USER"))


def _imap_settings() -> dict:
    return {
        "host": os.environ.get("IMAP_HOST", ""),
        "port": int(os.environ.get("IMAP_PORT", "993")),
        "user": os.environ.get("IMAP_USER", ""),
        "password": os.environ.get("IMAP_PASS", "").replace(" ", ""),
        "folder": os.environ.get("IMAP_FOLDER", "INBOX"),
    }


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for txt, charset in parts:
        if isinstance(txt, bytes):
            try:
                out.append(txt.decode(charset or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                out.append(txt.decode("utf-8", errors="replace"))
        else:
            out.append(txt)
    return "".join(out)


def _extract_text(msg: Message) -> str:
    """Return the plain-text body of an email, stripping quoted replies."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        body = payload.decode(charset, errors="replace")
                    except (LookupError, TypeError):
                        body = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                body = payload.decode(charset, errors="replace")
            except (LookupError, TypeError):
                body = payload.decode("utf-8", errors="replace")

    # Strip quoted replies — common patterns: "On … wrote:" and leading ">" lines.
    cleaned = []
    for line in body.splitlines():
        if re.match(r"^On .+ wrote:\s*$", line.strip()):
            break
        if line.startswith("-----Original Message-----"):
            break
        cleaned.append(line)
    text = "\n".join(cleaned).strip()
    # Drop quoted lines
    text = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(">"))
    return text.strip()


DEFAULT_MAX_PER_POLL = 10


def poll_inbox(
    user_lookup: Callable[[str], Optional[dict]],
    on_question: Callable[[dict, str, str], None],
    on_unknown: Optional[Callable[[str, str, str], None]] = None,
    max_messages: int = DEFAULT_MAX_PER_POLL,
) -> int:
    """
    Poll the configured IMAP inbox for UNSEEN messages and dispatch each.

    Args:
        user_lookup: function(email_address) -> user-dict-or-None.
        on_question: function(user_dict, subject, body) -> None.
            Called for messages whose sender matches a registered user.
            This callback is responsible for sending the reply.
        on_unknown: function(sender_email, subject, body) -> None.
            Called for messages from unknown senders. Optional.
        max_messages: cap the number of messages processed per call to bound
            CPU/LLM cost. Remaining messages stay UNSEEN for the next poll.

    Returns:
        Number of messages processed.
    """
    if not imap_configured():
        return 0

    s = _imap_settings()
    processed = 0
    try:
        with imaplib.IMAP4_SSL(s["host"], s["port"]) as imap:
            imap.login(s["user"], s["password"])
            imap.select(s["folder"])
            typ, data = imap.search(None, "UNSEEN")
            if typ != "OK":
                logger.warning("IMAP search failed: %s", typ)
                return 0
            ids = (data[0] or b"").split()
            if max_messages > 0:
                ids = ids[:max_messages]
            for msg_id in ids:
                try:
                    typ, msg_data = imap.fetch(msg_id, "(RFC822)")
                    if typ != "OK" or not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)
                    sender_name, sender_addr = parseaddr(msg.get("From", ""))
                    subject = _decode(msg.get("Subject"))
                    body = _extract_text(msg)
                    sender_addr = (sender_addr or "").strip().lower()

                    user = user_lookup(sender_addr) if sender_addr else None
                    if user:
                        on_question(user, subject, body)
                    elif on_unknown:
                        on_unknown(sender_addr, subject, body)

                    # Mark as Seen so we don't re-process
                    imap.store(msg_id, "+FLAGS", "\\Seen")
                    processed += 1
                except Exception:
                    logger.exception("Failed to handle inbound message %s", msg_id)
                    continue
    except Exception:
        logger.exception("IMAP poll failed")
    return processed
