"""Shared data models for the slide pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Diagram(BaseModel):
    """A simple flow/process diagram rendered natively in PPTX and via Mermaid in HTML."""

    type: Literal["flow"] = "flow"
    direction: Literal["down", "right"] = Field(
        default="down", description="Layout direction of the flow"
    )
    steps: list[str] = Field(
        default_factory=list, description="Ordered nodes, connected sequentially by arrows"
    )


class Table(BaseModel):
    """A tabular block rendered as a native table in PPTX and an HTML table."""

    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class Slide(BaseModel):
    """A single slide: title, bullets, optional flow diagram/table, and notes."""

    title: str = Field(..., description="Short slide headline")
    bullets: list[str] = Field(default_factory=list, description="Body bullet points")
    diagram: Diagram | None = Field(
        default=None, description="Optional flow diagram instead of / alongside bullets"
    )
    table: Table | None = Field(
        default=None, description="Optional tabular content for this slide"
    )
    notes: str = Field(default="", description="Speaker notes for this slide")


class Deck(BaseModel):
    """A full presentation produced from a Word document."""

    title: str = Field(..., description="Presentation title")
    subtitle: str = Field(default="", description="Optional subtitle / source name")
    slides: list[Slide] = Field(default_factory=list)
