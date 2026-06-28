"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
# UI lives in /public so Vercel serves it as a static asset at "/".
STATIC_DIR = BASE_DIR / "public"

# Slide content limits keep decks readable instead of dumping whole paragraphs.
MAX_BULLETS_PER_SLIDE = 6
MAX_BULLET_CHARS = 160
# Default slide ceiling; callers can override per request up to MAX_SLIDES_LIMIT.
MAX_SLIDES = 80
MAX_SLIDES_LIMIT = 200
MIN_SLIDES_LIMIT = 5
# Tables larger than this many body rows are split across multiple slides.
MAX_TABLE_ROWS_PER_SLIDE = 5


def clamp_max_slides(value: int | None) -> int:
    """Clamp a requested slide ceiling into the allowed range."""
    if not value:
        return MAX_SLIDES
    return max(MIN_SLIDES_LIMIT, min(MAX_SLIDES_LIMIT, int(value)))


@dataclass(frozen=True)
class Settings:
    """Immutable view of the app's configuration."""

    groq_api_key: str | None
    groq_model: str
    max_upload_bytes: int
    groq_max_tokens: int
    groq_source_chars: int
    feedback_webhook_url: str | None

    @property
    def ai_enabled(self) -> bool:
        return bool(self.groq_api_key)


def load_settings() -> Settings:
    """Read settings from the environment. Missing Groq key => heuristic fallback.

    GROQ_MAX_TOKENS / GROQ_SOURCE_CHARS default to values that keep input+output
    under the Groq free tier's ~12k tokens-per-minute limit. Raise them after
    upgrading the Groq plan to allow larger AI-generated decks.
    """
    return Settings(
        groq_api_key=os.environ.get("GROQ_API_KEY") or None,
        # Free, fast Groq model with JSON mode support.
        groq_model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", 20 * 1024 * 1024)),
        groq_max_tokens=int(os.environ.get("GROQ_MAX_TOKENS", 4000)),
        groq_source_chars=int(os.environ.get("GROQ_SOURCE_CHARS", 9000)),
        # Optional: POST each feedback submission here (Slack/Discord/Sheets webhook).
        feedback_webhook_url=os.environ.get("FEEDBACK_WEBHOOK_URL") or None,
    )


def ensure_dirs() -> None:
    for directory in (UPLOAD_DIR, OUTPUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
