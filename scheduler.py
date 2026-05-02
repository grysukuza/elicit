"""
Lightweight background scheduler.

Runs two periodic tasks on a single daemon thread:

  1. IMAP inbox polling (if IMAP is configured)       — every IMAP_POLL_SECONDS
  2. Daily digest dispatch (if SMTP is configured)    — checked every minute,
     sends to each opted-in user once per 24h.

Both task callbacks are injected by `app.py` so this module stays
framework-agnostic and easy to test.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class BackgroundScheduler:
    def __init__(
        self,
        poll_inbox_fn: Optional[Callable[[], int]] = None,
        run_digest_fn: Optional[Callable[[], int]] = None,
        imap_poll_seconds: int = 60,
        digest_check_seconds: int = 60,
    ) -> None:
        self.poll_inbox_fn = poll_inbox_fn
        self.run_digest_fn = run_digest_fn
        self.imap_poll_seconds = imap_poll_seconds
        self.digest_check_seconds = digest_check_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_inbox_poll = 0.0
        self._last_digest_check = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="cds-scheduler", daemon=True
        )
        self._thread.start()
        logger.info("BackgroundScheduler started")

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            now = time.time()
            try:
                if (
                    self.poll_inbox_fn
                    and now - self._last_inbox_poll >= self.imap_poll_seconds
                ):
                    self._last_inbox_poll = now
                    n = self.poll_inbox_fn() or 0
                    if n:
                        logger.info("Processed %d inbound email(s)", n)
            except Exception:
                logger.exception("Inbox poll failed")

            try:
                if (
                    self.run_digest_fn
                    and now - self._last_digest_check >= self.digest_check_seconds
                ):
                    self._last_digest_check = now
                    self.run_digest_fn()
            except Exception:
                logger.exception("Digest check failed")

            # Sleep in short increments so .stop() responds quickly
            self._stop.wait(timeout=5)


def should_start_scheduler() -> bool:
    """
    Avoid starting the scheduler twice when Flask's reloader spawns a child
    process. The reloader sets WERKZEUG_RUN_MAIN=true in the child only.
    """
    if os.environ.get("DISABLE_SCHEDULER", "").lower() in ("1", "true", "yes"):
        return False
    debug = os.environ.get("FLASK_DEBUG", "1") not in ("0", "false", "False", "")
    if debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
