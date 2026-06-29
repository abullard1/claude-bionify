"""Tests for the claude-bionify modules: core (pure), overrides, hook, and control."""

import io
import json
import pathlib
import sys

import pytest

_SCRIPTS = pathlib.Path(__file__).parent.parent / "plugins" / "claude-bionify" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import core  # noqa: E402
import overrides  # noqa: E402
import bionify  # noqa: E402
import control  # noqa: E402
import settings  # noqa: E402

Style = settings.Style
FRACTION = Style(fixation=0.5, min_length=4, boundary="fraction")
SYLLABLE = Style(fixation=0.5, min_length=4, boundary="syllable")


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Point the override file at an isolated, initially-absent tmp path."""
    monkeypatch.setenv("CLAUDE_BIONIFY_STATE_FILE", str(tmp_path / "runtime.json"))


class TestBionifyWord:
    def test_bolds_leading_half(self):
        assert core.bionify_word("reading", FRACTION) == "**read**ing"

    def test_short_words_untouched(self):
        assert core.bionify_word("is", FRACTION) == "is"
        assert core.bionify_word("the", FRACTION) == "the"

    def test_at_least_one_letter_bolded(self):
        assert core.bionify_word("a", Style(min_length=1)) == "**a**"

    def test_fixation_changes_cut(self):
        assert core.bionify_word("readable", Style(fixation=0.25)) == "**re**adable"


class TestSyllableBoundary:
    def test_ends_at_first_syllable(self):
        assert core.bionify_word("string", SYLLABLE) == "**stri**ng"
        assert core.bionify_word("reading", SYLLABLE) == "**rea**ding"

    def test_vowel_initial_word_is_floored(self):
        # "apple"'s syllable boundary is tiny; the floor keeps it readable.
        assert core.bionify_word("apple", SYLLABLE) == "**ap**ple"

    def test_handles_other_languages(self):
        assert core.bionify_word("über", SYLLABLE) == "**üb**er"
        assert core.bionify_word("schön", SYLLABLE) == "**sch**ön"

    def test_long_boundary_is_capped(self):
        # "rhythm" has no plain vowel; the cap stops it bolding the whole word.
        assert core.bionify_word("rhythm", SYLLABLE) == "**rhyt**hm"


class TestLogBoundary:
    LOG = Style(boundary="log")

    def test_grows_logarithmically(self):
        assert core.bionify_word("reading", self.LOG) == "**rea**ding"
        assert core.bionify_word("documentation", self.LOG) == "**docu**mentation"

    def test_long_word_is_bolded_proportionally_less(self):
        # 20 letters -> ceil(log2(20)) == 5, far short of a half (10).
        assert core.bionify_word("internationalization", self.LOG) == \
            "**inter**nationalization"


class TestAcronyms:
    def test_acronyms_are_left_whole_by_default(self):
        assert core.bionify_text("JSON output", Style()) == "JSON **out**put"

    def test_acronyms_are_bolded_when_disabled(self):
        assert core.bionify_text("JSON output", Style(skip_acronyms=False)) == \
            "**JS**ON **out**put"


class TestUrlProtection:
    def test_bare_url_is_protected_by_default(self):
        assert core.bionify_text("visit https://example.com today", Style()) == \
            "**vis**it https://example.com **tod**ay"

    def test_email_is_protected(self):
        assert core.bionify_text("mail user@example.com please", Style()) == \
            "**ma**il user@example.com **ple**ase"

    def test_url_is_bolded_when_disabled(self):
        out = core.bionify_text("visit https://example.com", Style(protect_urls=False))
        assert "**htt**ps" in out  # the URL is treated as prose


class TestBionifyText:
    def test_keeps_punctuation_and_spacing(self):
        assert core.bionify_text("Read this now.", FRACTION) == \
            "**Re**ad **th**is now."

    def test_bolds_words_in_any_language(self):
        assert core.bionify_text("Schöne Grüße", FRACTION) == \
            "**Sch**öne **Grü**ße"

    def test_numbers_and_identifiers_are_not_prose(self):
        assert core.bionify_text("value3 = 42", FRACTION) == "**val**ue3 = 42"

    def test_inline_code_is_preserved(self):
        assert core.bionify_text("call `function` here", FRACTION) == \
            "**ca**ll `function` **he**re"

    def test_existing_bold_is_preserved(self):
        assert core.bionify_text("**keep** this", FRACTION) == "**keep** **th**is"

    def test_link_label_bolded_but_url_left_alone(self):
        assert core.bionify_text(
            "See [the docs](https://example.com/guide) now.", FRACTION) == \
            "See [the **do**cs](https://example.com/guide) now."


class TestTransform:
    def test_prose_line(self):
        text, inside = core.transform("hello world", False, FRACTION)
        assert text == "**hel**lo **wor**ld"
        assert inside is False

    def test_fenced_block_within_one_delta_is_untouched(self):
        delta = "before\n```\ncode_here()\n```\nafter"
        text, inside = core.transform(delta, False, FRACTION)
        assert "code_here()" in text  # code unchanged
        assert text.startswith("**bef**ore")
        assert text.endswith("**aft**er")
        assert inside is False

    def test_fence_state_carries_across_deltas(self):
        d1, inside = core.transform("intro\n```python", False, FRACTION)
        assert inside is True
        assert d1.startswith("**int**ro")

        d2, inside = core.transform("secret_code()", inside, FRACTION)
        assert d2 == "secret_code()"  # untouched while inside the fence
        assert inside is True

        d3, inside = core.transform("```\noutro", inside, FRACTION)
        assert inside is False
        assert d3.endswith("**out**ro")

    def test_newlines_are_preserved_exactly(self):
        text, _ = core.transform("ones\ntwos\n", False, FRACTION)
        assert text == "**on**es\n**tw**os\n"


class TestFenceState:
    @pytest.fixture
    def data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
        return tmp_path

    def test_roundtrip(self, data_dir):
        bionify.write_fence_state("msg-1", True, final=False)
        assert bionify.read_fence_state("msg-1", index=1) is True
        bionify.write_fence_state("msg-1", False, final=False)
        assert bionify.read_fence_state("msg-1", index=1) is False

    def test_first_delta_starts_fresh(self, data_dir):
        bionify.write_fence_state("msg-1", True, final=False)
        assert bionify.read_fence_state("msg-1", index=0) is False

    def test_final_clears_state(self, data_dir):
        bionify.write_fence_state("msg-1", True, final=False)
        bionify.write_fence_state("msg-1", True, final=True)
        assert bionify.read_fence_state("msg-1", index=1) is False
        assert list(data_dir.iterdir()) == []

    def test_sweep_removes_orphans_but_keeps_current(self, data_dir):
        bionify.write_fence_state("old-1", True, final=False)
        bionify.write_fence_state("old-2", True, final=False)
        bionify.write_fence_state("current", True, final=False)
        bionify.sweep_stale_state("current")
        assert sorted(p.name for p in data_dir.iterdir()) == ["fence-current.state"]

    def test_operations_are_safe_without_data_dir(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        bionify.write_fence_state("msg", True, final=False)
        assert bionify.read_fence_state("msg", index=1) is False
        bionify.sweep_stale_state("msg")  # must not raise


class TestConfig:
    OPTION_KEYS = ("FIXATION", "MIN_WORD_LENGTH", "BOUNDARY",
                   "SKIP_ACRONYMS", "PROTECT_URLS", "SKIP_HEADINGS")

    def _clear(self, monkeypatch):
        for key in self.OPTION_KEYS:
            monkeypatch.delenv(f"CLAUDE_PLUGIN_OPTION_{key}", raising=False)

    def test_defaults_when_unset(self, monkeypatch):
        self._clear(monkeypatch)
        assert bionify.load_config() == Style()

    def test_reads_and_clamps_options(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FIXATION", "1.5")  # over max
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_MIN_WORD_LENGTH", "3")
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_BOUNDARY", "Syllable")  # any case
        assert bionify.load_config() == Style(0.9, 3, "syllable")

    def test_log_boundary_is_recognized(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_BOUNDARY", "log")
        assert bionify.load_config().boundary == "log"

    def test_unknown_boundary_falls_back_to_fraction(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_BOUNDARY", "nonsense")
        assert bionify.load_config().boundary == "fraction"

    def test_parses_boolean_options(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_SKIP_ACRONYMS", "false")
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_PROTECT_URLS", "0")
        style = bionify.load_config()
        assert style.skip_acronyms is False
        assert style.protect_urls is False

    def test_garbage_numbers_fall_back(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FIXATION", "not-a-number")
        assert bionify.load_config().fixation == 0.5


class TestMain:
    def _run(self, monkeypatch, capsys, payload):
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        bionify.main()
        return capsys.readouterr().out

    def test_emits_display_content(self, monkeypatch, capsys):
        out = self._run(monkeypatch, capsys,
                        json.dumps({"delta": "hello world", "final": True}))
        result = json.loads(out)["hookSpecificOutput"]
        assert result["hookEventName"] == "MessageDisplay"
        assert result["displayContent"] == "**hel**lo **wor**ld"

    def test_respects_boundary_option(self, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_BOUNDARY", "syllable")
        out = self._run(monkeypatch, capsys, json.dumps({"delta": "string"}))
        assert json.loads(out)["hookSpecificOutput"]["displayContent"] == "**stri**ng"

    def test_malformed_stdin_is_silent(self, monkeypatch, capsys):
        assert self._run(monkeypatch, capsys, "not json at all") == ""

    def test_empty_delta_is_silent(self, monkeypatch, capsys):
        assert self._run(monkeypatch, capsys, json.dumps({"delta": ""})) == ""

    def test_debug_env_reraises(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_BIONIFY_DEBUG", "1")
        monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
        with pytest.raises(Exception):
            bionify.main()


class TestControlApply:
    def test_on_off_toggle(self):
        assert control.apply({}, ["off"])[0] == {"enabled": False}
        assert control.apply({}, ["on"])[0] == {"enabled": True}
        assert control.apply({}, ["toggle"])[0] == {"enabled": False}  # default ON
        assert control.apply({"enabled": False}, ["toggle"])[0] == {"enabled": True}

    def test_set_fixation_is_clamped(self):
        assert control.apply({}, ["set", "fixation", "0.7"])[0]["fixation"] == 0.7
        assert control.apply({}, ["set", "fixation", "2"])[0]["fixation"] == 0.9

    def test_set_boundary_validates(self):
        assert control.apply({}, ["set", "boundary", "syllable"])[0]["boundary"] == "syllable"
        state, msg = control.apply({}, ["set", "boundary", "nonsense"])
        assert "boundary" not in state and "must be one of" in msg

    def test_set_minlen_and_bad_value(self):
        assert control.apply({}, ["set", "minlen", "6"])[0]["min_length"] == 6
        state, msg = control.apply({}, ["set", "fixation", "abc"])
        assert "fixation" not in state and "not a number" in msg

    def test_reset_signals_clear(self):
        new_state, msg = control.apply({"fixation": 0.7}, ["reset"])
        assert new_state is None
        assert "cleared" in msg

    def test_status_does_not_mutate(self):
        state, _ = control.apply({"enabled": False}, ["status"])
        assert state == {"enabled": False}


class TestControlIntegration:
    def _run(self, capsys, argv):
        control.main(argv)
        return capsys.readouterr().out.strip()

    def test_off_disables_hook(self, capsys):
        self._run(capsys, ["off"])
        assert bionify.load_config() is None

    def test_set_overrides_hook_style(self, capsys):
        self._run(capsys, ["set", "boundary", "syllable"])
        self._run(capsys, ["set", "fixation", "0.8"])
        style = bionify.load_config()
        assert style.boundary == "syllable"
        assert style.fixation == 0.8

    def test_reset_restores_defaults(self, capsys):
        self._run(capsys, ["off"])
        assert bionify.load_config() is None
        self._run(capsys, ["reset"])
        assert bionify.load_config() == Style()

    def test_corrupt_override_is_ignored(self, monkeypatch):
        with open(overrides.path(), "w", encoding="utf-8") as f:
            f.write("{ not json")
        assert bionify.load_config() == Style()


class TestFenceDetection:
    def test_real_fences_toggle(self):
        for marker in ("```", "```python", "```python {.line-numbers}", "````", "~~~", "   ```js"):
            assert core._is_fence(marker), marker

    def test_prose_starting_with_backticks_is_not_a_fence(self):
        for line in ("``` is the marker", "``` and then you write", "Use ``` to open"):
            assert not core._is_fence(line), line


class TestSkipHeadings:
    def test_headings_are_not_bolded_by_default(self):
        text, _ = core.transform("# Hello World", False, FRACTION)
        assert text == "# Hello World"

    def test_h2_through_h6(self):
        for level in range(2, 7):
            prefix = "#" * level
            text, _ = core.transform(f"{prefix} Heading", False, FRACTION)
            assert text == f"{prefix} Heading"

    def test_heading_with_leading_spaces(self):
        text, _ = core.transform("   ## Hello", False, FRACTION)
        assert text == "   ## Hello"

    def test_heading_is_bolded_when_disabled(self):
        style = Style(skip_headings=False)
        text, _ = core.transform("# Hello World", False, style)
        assert "**Hel**lo" in text

    def test_hash_in_prose_is_not_a_heading(self):
        text, _ = core.transform("Issue #42 is fixed", False, FRACTION)
        assert "**Iss**ue" in text

    def test_hashtag_is_not_a_heading(self):
        text, _ = core.transform("#hashtag here", False, FRACTION)
        assert "**hasht**ag" in text or "**hash**tag" in text

    def test_empty_heading_passes_through(self):
        text, _ = core.transform("##", False, FRACTION)
        assert text == "##"

    def test_four_leading_spaces_is_not_a_heading(self):
        text, _ = core.transform("    # indented code", False, FRACTION)
        assert "**inde**nted" in text

    def test_prose_line_with_backticks_does_not_suppress_bolding(self):
        delta = "``` is the marker\nThis sentence should be bolded."
        text, inside = core.transform(delta, False, FRACTION)
        assert inside is False  # not flipped into code mode
        assert "**Th**is" in text  # the following line is still bolded

    def test_info_string_fence_still_protects_code(self):
        delta = "```python {.line-numbers}\nsecret_code = 42\n```"
        text, inside = core.transform(delta, False, FRACTION)
        assert "secret_code = 42" in text  # code left untouched
        assert inside is False


class TestPathProtection:
    PATHS = ["src/components/Button.tsx", "/home/samuel/main.py", "./build/out",
             "../lib/util.js", "~/.config/app", "config.json", "example.com",
             "Node.js", "www.example.com", "docs/api/v2/spec.md"]

    def test_paths_files_and_domains_are_protected(self):
        for token in self.PATHS:
            out = core.bionify_text(f"see {token} here", Style())
            assert token in out, f"{token!r} was mangled: {out!r}"

    def test_prose_with_slashes_stays_prose(self):
        # one slash and no extension is prose, so the words still get bolded
        assert "**re**ad" in core.bionify_text("read/write access", Style())
        assert "**cli**ent" in core.bionify_text("client/server model", Style())
        assert "**inp**ut" in core.bionify_text("input/output stream", Style())

    def test_periods_in_prose_are_not_protected(self):
        # e.g. / i.e. / decimals must not be mistaken for filenames
        assert "**exam**ple" in core.bionify_text("for example e.g. this", Style())
        assert "**num**ber" in core.bionify_text("the number 3.14 here", Style())

    def test_paths_bold_when_protection_disabled(self):
        out = core.bionify_text("edit src/components/Button.tsx", Style(protect_urls=False))
        assert "**compo**nents" in out


class TestControlSet:
    def test_set_minlen(self):
        assert control.apply({}, ["set", "minlen", "6"])[0]["min_length"] == 6

    def test_set_minlen_is_clamped(self):
        assert control.apply({}, ["set", "minlen", "0"])[0]["min_length"] == 1

    def test_set_minlen_rejects_non_integer(self):
        state, msg = control.apply({}, ["set", "minlen", "x"])
        assert "min_length" not in state and "whole number" in msg

    def test_set_acronyms_and_urls_toggle(self):
        assert control.apply({}, ["set", "acronyms", "off"])[0]["skip_acronyms"] is False
        assert control.apply({}, ["set", "acronyms", "on"])[0]["skip_acronyms"] is True
        assert control.apply({}, ["set", "urls", "off"])[0]["protect_urls"] is False

    def test_set_headings_toggle(self):
        assert control.apply({}, ["set", "headings", "off"])[0]["skip_headings"] is False
        assert control.apply({}, ["set", "headings", "on"])[0]["skip_headings"] is True

    def test_set_unknown_option(self):
        _, msg = control.apply({}, ["set", "nonsense", "1"])
        assert "unknown option" in msg

    def test_format_shows_every_active_override(self):
        msg = settings.render_state({"enabled": False, "boundary": "log", "fixation": 0.7,
                                     "min_length": 5, "skip_acronyms": False,
                                     "protect_urls": False, "skip_headings": False})
        assert msg.startswith("claude-bionify: OFF")
        for part in ("boundary=log", "strength=0.7", "minlen=5",
                     "acronyms=off", "urls=off", "headings=off"):
            assert part in msg


class TestManifestConsistency:
    """The Python settings table and plugin.json userConfig must not drift."""

    def test_settings_match_the_plugin_manifest(self):
        manifest = json.loads(
            (_SCRIPTS.parent / ".claude-plugin" / "plugin.json").read_text())
        user_config = manifest["userConfig"]
        by_manifest = {s.manifest_key: s for s in settings.SETTINGS}

        # Every option is declared in both, keyed identically.
        assert set(by_manifest) == set(user_config)
        # Defaults agree across the two declarations.
        for key, spec in user_config.items():
            assert by_manifest[key].default == spec["default"], key
        # Numeric bounds in the manifest match what the parsers clamp to.
        assert user_config["fixation"]["min"] == settings.clamp_fixation(0.0)
        assert user_config["fixation"]["max"] == settings.clamp_fixation(1.0)
        assert user_config["min_word_length"]["min"] == settings.clamp_min_length(0)


class TestHookFencingIntegration:
    """Drive main() across streamed deltas the way Claude Code does, to prove a
    code block that spans deltas stays verbatim. Claude Code sends the message id
    as `messageId`, so the fence-state key must be derived from that.
    """

    def _emit(self, monkeypatch, capsys, event):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        bionify.main()
        return capsys.readouterr().out

    def test_code_fence_carries_across_deltas(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
        self._emit(monkeypatch, capsys,
                   {"messageId": "m1", "index": 0, "final": False,
                    "delta": "before\n```"})
        out = self._emit(monkeypatch, capsys,
                         {"messageId": "m1", "index": 1, "final": True,
                          "delta": "code_here()\n```\nafter"})
        content = json.loads(out)["hookSpecificOutput"]["displayContent"]
        assert "code_here()" in content      # code body left verbatim
        assert "**code**" not in content     # not bolded as if it were prose
        assert "**aft**er" in content        # prose after the closed fence is bolded
