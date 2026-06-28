"""User feedback capture.

Stateless-friendly: feedback is logged (visible in Vercel runtime logs) and,
if FEEDBACK_WEBHOOK_URL is set, forwarded to that webhook (Slack/Discord/Google
Apps Script/etc.). No database required.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx

from .config import Settings

logger = logging.getLogger("word2ppt.feedback")

MAX_COMMENT_CHARS = 2000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_feedback(
    settings: Settings, rating: int, comment: str, context: str = ""
) -> None:
    """Log the feedback and best-effort forward it to a webhook if configured."""
    entry = {
        "ts": _now_iso(),
        "rating": rating,
        "comment": comment[:MAX_COMMENT_CHARS],
        "context": context[:200],
    }
    logger.info("FEEDBACK %s", json.dumps(entry, ensure_ascii=False))

    if not settings.feedback_webhook_url:
        return
    try:
        # Slack/Discord accept {"text": ...}; generic endpoints get the full entry.
        summary = (
            f"⭐ {rating}/5 — {entry['comment'] or '(no comment)'}"
            + (f"\n_context: {entry['context']}_" if entry["context"] else "")
        )
        httpx.post(
            settings.feedback_webhook_url,
            json={"text": summary, **entry},
            timeout=4.0,
        )
    except Exception:  # noqa: BLE001 — never let webhook issues fail the request
        logger.warning("Feedback webhook delivery failed", exc_info=True)
