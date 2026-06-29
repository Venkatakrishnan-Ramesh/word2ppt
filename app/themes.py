"""Named visual themes for the generated deck.

A theme is a flat bag of hex colours (plus a ``dark`` flag) consumed by both the
PPTX renderer and the HTML renderer, so a deck looks consistent across formats.
Themes are selected by naming them in the user instructions (see
``resolve_theme``); when nothing matches we fall back to the default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """Palette for one deck style. Colours are hex strings without the ``#``."""

    name: str
    label: str
    aliases: tuple[str, ...]

    accent: str          # bright accent: side bar, connectors, node borders
    accent_dark: str     # deep tone: title band, table header, slide titles
    page_bg: str         # content/title slide background
    title_text: str      # text on the title band
    subtitle_text: str   # subtitle on the title band
    heading_text: str    # content slide title colour
    body_text: str       # bullet / body text colour
    node_fill: str       # diagram node fill
    node_text: str       # diagram node label colour
    table_header_text: str   # header-row text
    table_cell_bg: str       # body cell background
    table_stripe: str        # even body-row background (HTML only)
    table_border: str        # cell borders (HTML only)
    dark: bool = False       # dark deck -> dark reveal/mermaid base


# Order matters: the first theme whose alias is found in the instructions wins,
# so more specific names should come before generic ones.
THEMES: tuple[Theme, ...] = (
    Theme(
        name="tamilnadu-highways",
        label="Tamil Nadu Highways",
        # Listed first so "tamil nadu highways" wins before the generic
        # "government" alias of the navy theme below.
        aliases=(
            "tamil nadu highways", "tamilnadu highways", "tn highways",
            "highways department", "highways", "highway",
            "tamil nadu government", "tamilnadu government", "tamil nadu",
            "tamilnadu", "tn government", "tn govt", "tn",
        ),
        # Tamil Nadu Highways Dept: road-signage green with amber marking accents.
        accent="E0A400",          # highway amber / road-marking accent
        accent_dark="005A2B",     # deep signboard green band / headers
        page_bg="FFFFFF",
        title_text="FFFFFF",
        subtitle_text="E9DCA8",
        heading_text="005A2B",
        body_text="1A1A1A",
        node_fill="EAF4EC",
        node_text="005A2B",
        table_header_text="FFFFFF",
        table_cell_bg="FFFFFF",
        table_stripe="EEF6EF",
        table_border="C9E2CE",
    ),
    Theme(
        name="government-navy",
        label="Government Navy",
        aliases=("government navy", "government", "govt", "navy", "gold", "official"),
        accent="C8A24B",
        accent_dark="0B2545",
        page_bg="FFFFFF",
        title_text="FFFFFF",
        subtitle_text="E7D6A6",
        heading_text="0B2545",
        body_text="1A1A1A",
        node_fill="EAF0FA",
        node_text="0B2545",
        table_header_text="FFFFFF",
        table_cell_bg="FFFFFF",
        table_stripe="F4F1E6",
        table_border="D6C9A0",
    ),
    Theme(
        name="emerald",
        label="Emerald",
        aliases=("emerald", "green", "eco"),
        accent="1F8A5B",
        accent_dark="0B3B2E",
        page_bg="FFFFFF",
        title_text="FFFFFF",
        subtitle_text="BFE3CE",
        heading_text="0B3B2E",
        body_text="1A1A1A",
        node_fill="E6F4EC",
        node_text="0B3B2E",
        table_header_text="FFFFFF",
        table_cell_bg="FFFFFF",
        table_stripe="EEF7F1",
        table_border="C7E3D3",
    ),
    Theme(
        name="maroon",
        label="Maroon",
        aliases=("maroon", "burgundy", "crimson", "academic"),
        accent="9B2D3A",
        accent_dark="5A1420",
        page_bg="FFFFFF",
        title_text="FFFFFF",
        subtitle_text="E6C9CF",
        heading_text="5A1420",
        body_text="1A1A1A",
        node_fill="F6E9EC",
        node_text="5A1420",
        table_header_text="FFFFFF",
        table_cell_bg="FFFFFF",
        table_stripe="FBF1F3",
        table_border="E3CBD0",
    ),
    Theme(
        name="slate-dark",
        label="Slate Dark",
        aliases=("slate dark", "dark", "slate", "night", "black"),
        accent="4FB6C6",
        accent_dark="1E2530",
        page_bg="14181F",
        title_text="FFFFFF",
        subtitle_text="9FB3C8",
        heading_text="E6EDF3",
        body_text="D5DEE7",
        node_fill="222B36",
        node_text="E6EDF3",
        table_header_text="FFFFFF",
        table_cell_bg="1A2029",
        table_stripe="1C232C",
        table_border="39434F",
        dark=True,
    ),
    Theme(
        name="corporate-blue",
        label="Corporate Blue",
        aliases=("corporate blue", "corporate", "blue", "default"),
        accent="2D5BFF",
        accent_dark="1B2A4A",
        page_bg="FFFFFF",
        title_text="FFFFFF",
        subtitle_text="C8D4F0",
        heading_text="1B2A4A",
        body_text="1A1A1A",
        node_fill="ECF1FF",
        node_text="1B2A4A",
        table_header_text="FFFFFF",
        table_cell_bg="FFFFFF",
        table_stripe="F4F7FF",
        table_border="D3DCF0",
    ),
)

# Current look stays the default so decks without a named theme are unchanged.
DEFAULT_THEME = next(t for t in THEMES if t.name == "corporate-blue")

_BY_NAME = {t.name: t for t in THEMES}


def resolve_theme(instructions: str) -> Theme:
    """Pick a theme by scanning user instructions for a theme name/alias.

    Matches whole words/phrases (so ``darker`` doesn't select the dark theme).
    Returns ``DEFAULT_THEME`` when nothing matches.
    """
    text = (instructions or "").lower()
    if not text.strip():
        return DEFAULT_THEME
    for theme in THEMES:
        for alias in theme.aliases:
            if re.search(rf"\b{re.escape(alias)}\b", text):
                return theme
    return DEFAULT_THEME


def get_theme(name: str) -> Theme:
    """Look up a theme by its canonical name, falling back to the default."""
    return _BY_NAME.get(name, DEFAULT_THEME)
