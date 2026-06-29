#!/usr/bin/env python3
"""Generate ``assets/themes.svg``, the palette gallery shown in the README.

One card per plugin theme: the name in its accent color and a strip of its
palette swatches. A final "fork your own" cell completes the grid.

Cards are built from ``plugins/claude-bionify/themes/*.json`` so the image stays in
sync with the themes. Regenerate after editing any theme:

    python assets/generate_themes.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Paths, resolved from this file so the script runs from any directory.
ROOT = Path(__file__).resolve().parent.parent
THEMES_DIR = ROOT / "plugins" / "claude-bionify" / "themes"
OUTPUT = ROOT / "assets" / "themes.svg"

# Theme order in the grid, top-left to bottom-right.
ORDER = ("nord", "dracula", "gruvbox", "solarized-dark",
         "solarized-light", "sepia", "focus-dark")

# Canonical upstream background per theme. Themes inherit Claude Code's base
# background at runtime; the authentic value makes each card read as its theme.
BACKGROUNDS = {
    "nord": "#2E3440", "dracula": "#282A36", "gruvbox": "#282828",
    "solarized-dark": "#002B36", "solarized-light": "#FDF6E3",
    "sepia": "#F4ECD8", "focus-dark": "#282C34",
}

# Palette keys shown in the swatch strip, left to right.
SWATCH_KEYS = ("claude", "text", "success", "warning", "error", "subtle")

MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

# Layout geometry, in px.
CARD_W, CARD_H = 392, 88
COLS, GAP, PAD = 2, 16, 22
SWATCH_W, SWATCH_H, SWATCH_STEP = 34, 16, 42


@dataclass(frozen=True)
class Theme:
    """Display data for one theme, loaded from its JSON file."""

    slug: str
    name: str
    base: str               # "dark" or "light"
    background: str
    palette: dict[str, str]  # keys: text, claude, subtle, promptBorder, error, success, warning


def load_themes() -> list[Theme]:
    """Load the themes named in ORDER, in that order."""
    themes = []
    for slug in ORDER:
        data = json.loads((THEMES_DIR / f"{slug}.json").read_text())
        themes.append(Theme(
            slug=slug,
            name=data["name"],
            base=data["base"],
            background=BACKGROUNDS[slug],
            palette=data["overrides"],
        ))
    return themes


def grid_xy(index: int) -> tuple[int, int]:
    """Top-left corner of the cell at ``index`` in the column grid."""
    col, row = index % COLS, index // COLS
    return col * (CARD_W + GAP), row * (CARD_H + GAP)


# Builders below take data and return SVG strings, with no side effects.
def _text(x: int, y: int, body: str, *, size: int, fill: str,
          weight: int = 400, spacing: float = 0) -> str:
    letter = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x}" y="{y}" font-family="{MONO}" font-size="{size}"'
            f' font-weight="{weight}"{letter} fill="{fill}">{body}</text>')


def _swatches(palette: dict[str, str], y: int) -> str:
    return "".join(
        f'<rect x="{PAD + i * SWATCH_STEP}" y="{y}" width="{SWATCH_W}"'
        f' height="{SWATCH_H}" rx="4" fill="{palette[key]}"'
        f' stroke="#000" stroke-opacity="0.18"/>'
        for i, key in enumerate(SWATCH_KEYS)
    )


def theme_card(theme: Theme, x: int, y: int) -> str:
    p = theme.palette
    clip = f"clip-{theme.slug}"
    return f'''  <g transform="translate({x},{y})">
    <clipPath id="{clip}"><rect width="{CARD_W}" height="{CARD_H}" rx="14"/></clipPath>
    <rect x="0.5" y="0.5" width="{CARD_W - 1}" height="{CARD_H - 1}" rx="14"
          fill="{theme.background}" stroke="{p['promptBorder']}" stroke-width="1"/>
    <g clip-path="url(#{clip})">
      {_text(PAD, 36, theme.name, size=14, weight=700, spacing=0.3, fill=p['claude'])}
      {_swatches(p, CARD_H - 32)}
    </g>
  </g>'''


def fork_card(x: int, y: int) -> str:
    """Final cell: folds the 'fork your own' instruction into the grid."""
    return f'''  <g transform="translate({x},{y})">
    <rect x="1" y="1" width="{CARD_W - 2}" height="{CARD_H - 2}" rx="14" fill="none"
          stroke="#8B949E" stroke-width="1.4" stroke-dasharray="5 5" stroke-opacity="0.5"/>
    {_text(PAD, 34, "Fork your own", size=14, weight=700, spacing=0.3, fill="#8B949E")}
    {_text(PAD, 58, 'Highlight in <tspan fill="#ADBAC7" font-weight="700">/theme</tspan>, press <tspan fill="#ADBAC7" font-weight="700">Ctrl+E</tspan>', size=13, fill="#6E7681")}
    {_text(PAD, 75, 'to copy &amp; tweak.', size=13, fill="#6E7681")}
  </g>'''


def build_svg(themes: list[Theme]) -> str:
    cells = [theme_card(t, *grid_xy(i)) for i, t in enumerate(themes)]
    cells.append(fork_card(*grid_xy(len(themes))))

    rows = (len(cells) + COLS - 1) // COLS
    width = COLS * CARD_W + (COLS - 1) * GAP
    height = rows * CARD_H + (rows - 1) * GAP

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"'
        f' width="{width}" height="{height}" role="img"'
        f' aria-label="The seven claude-bionify palettes">\n'
        f'  <title>claude-bionify themes</title>\n'
        + "\n".join(cells)
        + "\n</svg>\n"
    )


def main() -> None:
    OUTPUT.write_text(build_svg(load_themes()))
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()