"""FastAPI web app: convert a Word/text doc into a .pptx + HTML deck.

Stateless by design: each request generates both artifacts in memory and returns
them inline (HTML string + base64 PPTX). No server-side file persistence, so it
runs identically on a local machine and on serverless platforms like Vercel.
"""

from __future__ import annotations

import base64
import re
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .config import STATIC_DIR, load_settings
from .pipeline import SUPPORTED_EXTS, convert

settings = load_settings()
app = FastAPI(title="word2ppt", version="0.2.0")

_PPTX_MEDIA = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


@app.get("/")
def index():
    # Local dev serves the UI directly; on Vercel "/" is rewritten to the static
    # /index.html, but if the function is ever hit here, redirect rather than 500.
    path = STATIC_DIR / "index.html"
    if path.is_file():
        return HTMLResponse(path.read_text(encoding="utf-8"))
    return RedirectResponse(url="/index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "ai_enabled": settings.ai_enabled, "model": settings.groq_model}


@app.post("/api/convert")
async def convert_endpoint(
    file: UploadFile = File(...), review: bool = Form(False)
) -> JSONResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(SUPPORTED_EXTS)}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large.")

    return _convert_bytes(data, suffix, review)


@app.post("/api/convert-text")
async def convert_text_endpoint(
    text: str = Form(...), review: bool = Form(False)
) -> JSONResponse:
    content = text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="No text provided.")
    if len(content.encode("utf-8")) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Text too large.")
    # Treat pasted content as markdown so headings/tables/lists are understood.
    return _convert_bytes(content.encode("utf-8"), ".md", review)


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or "presentation"


def _convert_bytes(data: bytes, suffix: str, review: bool) -> JSONResponse:
    """Run the pipeline on the source bytes and return artifacts inline."""
    # Parsers take a path; use a short-lived temp file (works on serverless /tmp).
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        source_path = Path(tmp.name)

    try:
        result = convert(source_path, settings, review=review)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface a clean error to the client
        raise HTTPException(status_code=500, detail=f"Conversion failed: {exc}") from exc
    finally:
        source_path.unlink(missing_ok=True)

    return JSONResponse(
        {
            "title": result.deck.title,
            "filename": _slugify(result.deck.title),
            "slide_count": len(result.deck.slides),
            "strategy": result.strategy,
            "diagram_count": sum(1 for s in result.deck.slides if s.diagram),
            "table_count": sum(1 for s in result.deck.slides if s.table),
            "reviewed": result.reviewed,
            "review_notes": list(result.review_notes),
            "html": result.html,
            "pptx_base64": base64.b64encode(result.pptx_bytes).decode("ascii"),
            "pptx_media_type": _PPTX_MEDIA,
        }
    )
