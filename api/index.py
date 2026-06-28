"""Vercel serverless entry point.

Vercel's Python runtime serves the ASGI ``app`` exported here. All routes are
rewritten to this function via vercel.json.
"""

import os
import sys

# Make the project root importable so `app` package resolves on Vercel.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402  (path setup must run first)

__all__ = ["app"]
