"""Semantic flow-diagram node styles shared by PPTX and HTML renderers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

DiagramNodeKind = Literal[
    "start",
    "end",
    "decision",
    "input",
    "output",
    "data",
    "document",
    "process",
]


@dataclass(frozen=True)
class DiagramNodeStyle:
    kind: DiagramNodeKind
    label: str


_START_HINTS = ("start", "begin", "init", "input", "intake", "source", "receive")
_END_HINTS = ("end", "final", "finish", "complete", "summary", "result", "capture", "publish", "deliver")
_DECISION_HINTS = ("decision", "decide", "if", "check", "validate", "branch", "approve", "reject", "whether")
_INPUT_HINTS = ("input", "import", "upload", "submit", "ingest", "enter", "capture")
_OUTPUT_HINTS = ("output", "export", "download", "generate", "publish", "produce", "send")
_DATA_HINTS = ("data", "database", "db", "store", "storage", "archive", "persistence")
_DOCUMENT_HINTS = ("document", "report", "memo", "notice", "form", "sheet", "file")


def _normalise(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().lower())


def classify_node(label: str, index: int, total: int) -> DiagramNodeKind:
    text = _normalise(label)
    if index == 0 and any(h in text for h in _START_HINTS):
        return "start"
    if index == total - 1 and any(h in text for h in _END_HINTS):
        return "end"
    if "?" in text or any(h in text for h in _DECISION_HINTS):
        return "decision"
    if any(h in text for h in _INPUT_HINTS):
        return "input"
    if any(h in text for h in _OUTPUT_HINTS):
        return "output"
    if any(h in text for h in _DATA_HINTS):
        return "data"
    if any(h in text for h in _DOCUMENT_HINTS):
        return "document"
    return "process"


def diagram_node_style(label: str, index: int, total: int) -> DiagramNodeStyle:
    kind = classify_node(label, index, total)
    return DiagramNodeStyle(kind=kind, label=label)
