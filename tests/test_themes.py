"""Tests for the plugin themes: valid colors and readable contrast.

Claude Code silently ignores a color value it cannot parse and falls back to the
base preset, so a typo would ship unnoticed. Contrast is WCAG 2 relative
luminance, measured against each theme's canonical background: Claude Code does
not paint the terminal background, so these colors assume a matching terminal.
"""

import json
import pathlib
import re
import sys

import pytest

_ROOT = pathlib.Path(__file__).parent.parent
THEMES_DIR = _ROOT / "plugins" / "claude-bionify" / "themes"
sys.path.insert(0, str(_ROOT / "assets"))

from generate_themes import BACKGROUNDS  # noqa: E402

# Backgrounds the theme's text sits on. The word highlights mark a few changed
# words inside an already tinted diff line, so they get the lower WCAG floor for
# emphasis; Claude Code's own dark preset is about 3.1:1 there.
BODY_TOKENS = ("diffAdded", "diffRemoved", "diffAddedDimmed", "diffRemovedDimmed",
               "userMessageBackground", "userMessageBackgroundHover", "selectionBg")
WORD_TOKENS = ("diffAddedWord", "diffRemovedWord")
BODY_MIN, WORD_MIN = 4.5, 3.0

HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
               for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_matches_known_values():
    assert contrast("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert contrast("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)


def _slugs() -> list[str]:
    return sorted(p.stem for p in THEMES_DIR.glob("*.json"))


def test_every_theme_has_a_background():
    assert set(_slugs()) == set(BACKGROUNDS)


@pytest.mark.parametrize("slug", _slugs())
def test_theme_colors_are_valid_and_readable(slug):
    overrides = json.loads((THEMES_DIR / f"{slug}.json").read_text(encoding="utf-8"))["overrides"]
    text, background = overrides["text"], BACKGROUNDS[slug]

    bad = {k: v for k, v in overrides.items() if not HEX.fullmatch(v)}
    assert not bad, f"not #rrggbb, Claude Code would ignore: {bad}"

    missing = set(BODY_TOKENS + WORD_TOKENS) - set(overrides)
    assert not missing, f"missing tokens: {sorted(missing)}"

    assert contrast(text, background) >= BODY_MIN, "text on the theme background"
    for token in BODY_TOKENS:
        ratio = contrast(text, overrides[token])
        assert ratio >= BODY_MIN, f"{token} {overrides[token]}: {ratio:.2f}:1"
    for token in WORD_TOKENS:
        ratio = contrast(text, overrides[token])
        assert ratio >= WORD_MIN, f"{token} {overrides[token]}: {ratio:.2f}:1"
