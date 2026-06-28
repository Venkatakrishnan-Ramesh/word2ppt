"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"

# Slide content limits keep decks readable instead of dumping whole paragraphs.
MAX_BULLETS_PER_SLIDE = 6
MAX_BULLET_CHARS = 160
MAX_SLIDES = 80
# Tables larger than this many body rows are split across multiple slides.
MAX_TABLE_ROWS_PER_SLIDE = 5


@dataclass(frozen=True)
class Settings:
    """Immutable view of the app's configuration."""

    groq_api_key: str | None
    groq_model: str
    max_upload_bytes: int

    @property
    def ai_enabled(self) -> bool:
        return bool(self.groq_api_key)


def load_settings() -> Settings:
    """Read settings from the environment. Missing Groq key => heuristic fallback."""
    return Settings(
        groq_api_key=os.environ.get("GROQ_API_KEY") or None,
        # Free, fast Groq model with JSON mode support.
        groq_model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", 20 * 1024 * 1024)),
    )


def ensure_dirs() -> None:
    for directory in (UPLOAD_DIR, OUTPUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
