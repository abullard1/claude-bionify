"""Tests for the claude-bionify modules: core (pure), overrides, hook, and control."""

import io
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

_SCRIPTS = pathlib.Path(__file__).parent.parent / "plugins" / "claude-bionify" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import bionify  # noqa: E402
import control  # noqa: E402
import core  # noqa: E402
import interpreters  # noqa: E402
import overrides  # noqa: E402
import settings  # noqa: E402

Style = settings.Style
FRACTION = Style(fixation=0.5, min_length=4, boundary="fraction")
SYLLABLE = Style(fixation=0.5, min_length=4, boundary="syllable")


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Point the override file at an isolated, initially-absent tmp path."""
    monkeypatch.setenv("CLAUDE_BIONIFY_STATE_FILE", str(tmp_path / "runtime.json"))


def hook_stdout(encoding="utf-8"):
    """A stdout with a text layer in `encoding`, plus the raw bytes behind it."""
    raw = io.BytesIO()
    return io.TextIOWrapper(raw, encoding=encoding, errors="replace"), raw


def hook_stdin(payload, encoding="utf-8"):
    """stdin as the hook receives it: UTF-8 bytes under a text layer in `encoding`."""
    return io.TextIOWrapper(io.BytesIO(payload.encode("utf-8")),
                            encoding=encoding, errors="surrogateescape")


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

    def test_url_protection_stops_before_quotes_and_brackets(self):
        assert core.bionify_text('visit "https://example.com/docs" now', Style()) == \
            '**vis**it "https://example.com/docs" now'
        assert core.bionify_text("open (https://example.com/docs) now", Style()) == \
            "**op**en (https://example.com/docs) now"

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
        bionify.write_fence_state("msg-1", True)
        assert bionify.read_fence_state("msg-1", index=1) is True
        bionify.write_fence_state("msg-1", False)
        assert bionify.read_fence_state("msg-1", index=1) is False

    def test_first_delta_starts_fresh(self, data_dir):
        bionify.write_fence_state("msg-1", True)
        assert bionify.read_fence_state("msg-1", index=0) is False

    def test_clear_removes_state(self, data_dir):
        bionify.write_fence_state("msg-1", True)
        bionify.clear_fence_state("msg-1")
        assert bionify.read_fence_state("msg-1", index=1) is False
        assert list(data_dir.iterdir()) == []

    def test_write_leaves_no_temporary_file(self, data_dir):
        bionify.write_fence_state("msg-1", True)
        assert sorted(p.name for p in data_dir.iterdir()) == ["fence-msg-1.state"]

    def test_sweep_removes_orphans_but_keeps_current(self, data_dir):
        bionify.write_fence_state("old-1", True)
        bionify.write_fence_state("old-2", True)
        bionify.write_fence_state("current", True)
        bionify.sweep_stale_state("current")
        assert sorted(p.name for p in data_dir.iterdir()) == ["fence-current.state"]

    def test_sweep_collects_orphaned_temporary_files(self, data_dir):
        """A killed process can leave the tmp half of an atomic write behind."""
        (data_dir / "fence-old.state.tmp-999").write_text("1", encoding="utf-8")
        bionify.write_fence_state("current", True)
        bionify.sweep_stale_state("current")
        assert sorted(p.name for p in data_dir.iterdir()) == ["fence-current.state"]

    def test_sweep_spares_the_current_messages_temporary_file(self, data_dir):
        """A concurrent flush of the same message may be mid-write during the sweep."""
        (data_dir / "fence-current.state.tmp-999").write_text("1", encoding="utf-8")
        bionify.sweep_stale_state("current")
        assert [p.name for p in data_dir.iterdir()] == ["fence-current.state.tmp-999"]

    def test_operations_are_safe_without_data_dir(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        bionify.write_fence_state("msg", True)
        bionify.clear_fence_state("msg")
        assert bionify.read_fence_state("msg", index=1) is False
        bionify.sweep_stale_state("msg")  # must not raise


class TestFenceStateWithoutPluginDataDir:
    """When CLAUDE_PLUGIN_DATA is absent, fence state falls back to the plugin's
    own per-user directory rather than vanishing, so a fenced block still spans
    deltas instead of being bolded as prose. The autouse _isolate_state fixture
    points that per-user store at tmp_path, so these run against an isolated dir.
    """

    def test_fence_dir_prefers_the_plugin_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "pd"))
        assert bionify._fence_dir() == str(tmp_path / "pd")

    def test_fence_dir_falls_back_to_the_per_user_state_dir(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        assert bionify._fence_dir() == os.path.dirname(overrides.path())

    def test_state_persists_across_deltas_without_the_plugin_data_dir(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
        bionify.write_fence_state("msg", True)
        assert bionify.read_fence_state("msg", index=1) is True

    def test_interior_delta_is_not_bionified_without_the_plugin_data_dir(
            self, monkeypatch, capsys):
        """The regression: a fenced block whose interior arrives in a later delta,
        one that carries no opening ```, must stay verbatim even with no data dir.
        """
        monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)

        def run(delta, index, final=False):
            payload = json.dumps({"delta": delta, "message_id": "m",
                                  "index": index, "final": final})
            monkeypatch.setattr("sys.stdin", hook_stdin(payload))
            bionify.main()
            out = capsys.readouterr().out
            return json.loads(out)["hookSpecificOutput"]["displayContent"] if out else delta

        opening = run("Here is the report:\n```", 0)
        interior = run("Total revenue collected today", 1)
        closing = run("```\nDone.", 2, final=True)

        assert opening == "**He**re is the **rep**ort:\n```"
        assert interior == "Total revenue collected today"  # inside the fence, untouched
        assert closing == "```\n**Do**ne."


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
    def _run(self, monkeypatch, capsys, payload, encoding="utf-8"):
        monkeypatch.setattr("sys.stdin", hook_stdin(payload, encoding))
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

    @pytest.mark.parametrize("encoding", ["utf-8", "cp1252"])
    def test_non_ascii_survives_the_platform_stdio_encoding(
            self, monkeypatch, capsys, encoding):
        """ensure_ascii=False is required; ASCII escapes would skip the decode."""
        payload = json.dumps({"delta": "dashes \u2014 and quotes \u201d here"},
                             ensure_ascii=False)
        out = self._run(monkeypatch, capsys, payload, encoding)
        assert (json.loads(out)["hookSpecificOutput"]["displayContent"]
                == "**das**hes \u2014 and **quo**tes \u201d **he**re")

    def test_debug_env_reraises(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_BIONIFY_DEBUG", "1")
        monkeypatch.setattr("sys.stdin", hook_stdin("not json at all"))
        with pytest.raises(json.JSONDecodeError):
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


class TestControlStreamEncoding:
    def test_status_line_is_utf8_regardless_of_platform_codepage(self, monkeypatch):
        """The status separator is non-ASCII, so the bytes must be UTF-8."""
        stdout, raw = hook_stdout("cp1252")
        monkeypatch.setattr("sys.stdout", stdout)
        control.main(["status"])
        stdout.flush()
        assert "\u00b7" in raw.getvalue().decode("utf-8")


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

    def test_state_file_without_directory_component_is_saved(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_BIONIFY_STATE_FILE", "runtime.json")
        self._run(capsys, ["set", "fixation", "0.8"])
        saved = (tmp_path / "runtime.json").read_text(encoding="utf-8")
        assert json.loads(saved) == {"fixation": 0.8}
        assert bionify.load_config().fixation == 0.8

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
        for marker in ("```", "```python", "``` python", "```python {.line-numbers}",
                       "````", "~~~", "   ```js"):
            assert core._is_fence(marker), marker

    def test_prose_starting_with_backticks_is_not_a_fence(self):
        for line in ("Use ``` to open", "Use ~~~ to open"):
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
        delta = "Use ``` as the marker\nThis sentence should be bolded."
        text, inside = core.transform(delta, False, FRACTION)
        assert inside is False  # not flipped into code mode
        assert "**Th**is" in text  # the following line is still bolded

    def test_info_string_fence_still_protects_code(self):
        delta = "``` python {.line-numbers}\nsecret_code = 42\n```"
        text, inside = core.transform(delta, False, FRACTION)
        assert "secret_code = 42" in text  # code left untouched
        assert inside is False


class TestPathProtection:
    PATHS = ("src/components/Button.tsx", "/home/samuel/main.py", "./build/out",
             "../lib/util.js", "~/.config/app", "config.json", "example.com",
             "Node.js", "www.example.com", "docs/api/v2/spec.md")

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

        state, msg = control.apply({}, ["set", "minlen", "4.9"])
        assert "min_length" not in state and "whole number" in msg

    def test_set_min_length_alias_is_not_accepted(self):
        state, msg = control.apply({}, ["set", "min_length", "5"])
        assert "min_length" not in state and "unknown option" in msg

    def test_set_acronyms_and_urls_toggle(self):
        assert control.apply({}, ["set", "acronyms", "off"])[0]["skip_acronyms"] is False
        assert control.apply({}, ["set", "acronyms", "on"])[0]["skip_acronyms"] is True
        assert control.apply({}, ["set", "urls", "off"])[0]["protect_urls"] is False

    def test_set_boolean_rejects_typos(self):
        state, msg = control.apply({}, ["set", "acronyms", "maybe"])
        assert "skip_acronyms" not in state and "not on or off" in msg

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
            (_SCRIPTS.parent / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
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

    @pytest.mark.parametrize("readme", [
        _SCRIPTS.parent / "README.md",           # plugin README
        _SCRIPTS.parent.parent.parent / "README.md",   # repo README
    ])
    def test_readme_version_badges_match_the_manifest(self, readme):
        """Both badges drifted behind the manifest before this test existed."""
        manifest = json.loads(
            (_SCRIPTS.parent / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        badges = re.findall(r"badge/version-([\d.]+?)-",
                            readme.read_text(encoding="utf-8"))
        assert badges, f"no version badge found in {readme}"
        assert set(badges) == {manifest["version"]}


class TestSubprocessStdio:
    """Drive the scripts as Claude Code does: child processes reading a pipe.

    The in-process tests substitute their own streams, so only these exercise the
    encoding the platform actually applies to a pipe.
    """

    @staticmethod
    def _run(script, argv=(), stdin=b""):
        env = dict(os.environ)
        for var in ("PYTHONUTF8", "PYTHONIOENCODING"):
            env.pop(var, None)          # let the platform default stand
        return subprocess.run([sys.executable, str(script), *argv], input=stdin,
                              capture_output=True, env=env, check=True).stdout

    def test_pipe_is_not_utf8_on_windows(self):
        """Guard: on a UTF-8 runner the two tests below would prove nothing."""
        if sys.platform != "win32":
            pytest.skip("only Windows defaults a pipe to a non-UTF-8 codepage")
        enc = subprocess.run(
            [sys.executable, "-c", "import sys; print(sys.stdin.encoding)"],
            input=b"", capture_output=True, check=True).stdout.decode().strip()
        assert enc.lower().replace("-", "") not in ("utf8", "cp65001"), \
            f"runner pipes are already {enc}; these tests are vacuous"

    def test_hook_roundtrips_non_ascii(self):
        payload = json.dumps({"delta": "dash \u2014 quote \u201d here", "final": True},
                             ensure_ascii=False).encode("utf-8")
        out = self._run(_SCRIPTS / "bionify.py", stdin=payload)
        assert (json.loads(out)["hookSpecificOutput"]["displayContent"]
                == "**da**sh \u2014 **quo**te \u201d **he**re")

    def test_control_status_line_is_utf8(self):
        out = self._run(_SCRIPTS / "control.py", ["status"])
        assert "\u00b7" in out.decode("utf-8")


def display_event(**overrides):
    """A MessageDisplay payload shaped like the one Claude Code puts on the wire.

    The base fields accompany every hook event, so tests that omit them can pass
    while the real payload takes a different path through `parse_event`.
    """
    return {
        "session_id": "sess-1",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "MessageDisplay",
        "turn_id": "turn-1",
        "message_id": "m1",
        "index": 0,
        "final": False,
        "delta": "",
        **overrides,
    }


class TestParseEvent:
    """The message id keys the fence state, so the wire field must be read exactly."""

    def test_reads_message_id(self):
        event = bionify.parse_event(display_event(message_id="m1"))
        assert event.message_id == "m1"

    def test_falls_back_to_camel_case_for_older_builds(self):
        raw = display_event(messageId="m-camel")
        del raw["message_id"]
        assert bionify.parse_event(raw).message_id == "m-camel"

    def test_falls_back_to_session_id(self):
        raw = display_event()
        del raw["message_id"]
        assert bionify.parse_event(raw).message_id == "sess-1"

    def test_message_id_wins_over_the_fallbacks(self):
        raw = display_event(message_id="m1", messageId="m-camel")
        assert bionify.parse_event(raw).message_id == "m1"

    def test_key_is_empty_when_nothing_identifies_the_message(self):
        assert bionify.parse_event({}).message_id == ""


class TestHookFencingIntegration:
    """Drive main() across streamed deltas the way Claude Code does, to prove a
    code block that spans deltas stays verbatim and leaves no state behind.
    """

    def _emit(self, monkeypatch, capsys, **overrides):
        payload = json.dumps(display_event(**overrides))
        monkeypatch.setattr("sys.stdin", hook_stdin(payload))
        bionify.main()
        return capsys.readouterr().out

    def test_code_fence_carries_across_deltas(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
        self._emit(monkeypatch, capsys, index=0, delta="before\n```")
        out = self._emit(monkeypatch, capsys, index=1, final=True,
                         delta="code_here()\n```\nafter")
        content = json.loads(out)["hookSpecificOutput"]["displayContent"]
        assert "code_here()" in content      # code body left verbatim
        assert "**code**" not in content     # not bolded as if it were prose
        assert "**aft**er" in content        # prose after the closed fence is bolded

    def test_state_is_keyed_by_message_not_session(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
        self._emit(monkeypatch, capsys, message_id="m1", index=0, delta="before\n```")
        assert [p.name for p in tmp_path.iterdir()] == ["fence-m1.state"]

    def test_empty_final_delta_clears_state(self, tmp_path, monkeypatch, capsys):
        """A message ending on a newline flushes one last time with no text."""
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
        self._emit(monkeypatch, capsys, index=0, delta="before\n```\n")
        assert list(tmp_path.iterdir())          # state exists mid-message
        out = self._emit(monkeypatch, capsys, index=1, final=True, delta="")
        assert out == ""                         # nothing to display
        assert list(tmp_path.iterdir()) == []    # and nothing left behind

    def test_final_delta_with_text_clears_state(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
        self._emit(monkeypatch, capsys, index=0, delta="before\n```")
        self._emit(monkeypatch, capsys, index=1, final=True, delta="code()\n```\nafter")
        assert list(tmp_path.iterdir()) == []


_PLUGIN = _SCRIPTS.parent
_HOOKS = _PLUGIN / "hooks" / "hooks.json"


class TestHookManifest:
    """`claude plugin validate --strict` checks none of this, so these do."""

    @pytest.fixture
    def hooks(self):
        return json.loads(_HOOKS.read_text(encoding="utf-8"))

    def test_declares_the_interpreters_windows_and_posix_need(self, hooks):
        """python3 covers POSIX and Store Python; py covers python.org on Windows."""
        declared = interpreters.declared(hooks)
        assert [c.command for c in declared] == ["python3", "py"]
        assert declared[1].args == ("-3",)

    def test_every_entry_is_exec_form_running_the_hook_script(self, hooks):
        entries = hooks["hooks"]["MessageDisplay"][0]["hooks"]
        assert entries, "no MessageDisplay hook declared"
        for entry in entries:
            assert entry["type"] == "command"
            assert isinstance(entry.get("args"), list), "shell form loses exec-form quoting"
            assert entry["args"][-1] == "${CLAUDE_PLUGIN_ROOT}/scripts/bionify.py"
            assert entry["timeout"] > 0

    def test_no_entry_carries_an_if_condition(self, hooks):
        """`if` is a tool-event matcher; on MessageDisplay it silently skips the hook."""
        for entry in hooks["hooks"]["MessageDisplay"][0]["hooks"]:
            assert "if" not in entry

    def test_commands_use_no_shell_operators(self):
        """Shell form falls back to PowerShell 5.1, where `||` is a parse error."""
        for path in sorted((_PLUGIN / "commands").glob("*.md")):
            body = path.read_text(encoding="utf-8")
            assert "||" not in body, f"{path.name} uses a shell operator PowerShell 5.1 rejects"
            assert "&&" not in body, f"{path.name} uses a shell operator PowerShell 5.1 rejects"


class TestInterpreterProbe:
    """Availability is decided by running a candidate, never by locating it."""

    def test_reads_a_candidate_out_of_a_hook_entry(self):
        entry = {"command": "py", "args": ["-3", "/x/scripts/bionify.py"]}
        assert interpreters.candidate_of(entry) == interpreters.Candidate("py", ("-3",))

    def test_shell_form_entries_have_no_candidate(self):
        assert interpreters.candidate_of({"command": "python3 /x/bionify.py"}) is None

    def test_the_running_interpreter_starts(self):
        assert interpreters.starts(interpreters.Candidate(sys.executable))

    def test_a_missing_interpreter_is_reported_not_raised(self):
        assert not interpreters.starts(interpreters.Candidate("definitely-not-a-python-xyz"))

    def test_an_interpreter_that_exits_nonzero_does_not_count(self):
        """The Windows Store placeholder spawns fine and exits 9009 without running Python."""
        assert not interpreters.starts(
            interpreters.Candidate(sys.executable, ("-c", "import sys; sys.exit(9009)")))

    def test_a_version_below_the_floor_does_not_count(self):
        assert interpreters.parse_version(b"3 9") < interpreters.MINIMUM
        assert interpreters.parse_version(b"3 12") >= interpreters.MINIMUM

    def test_a_banner_before_the_version_does_not_hide_it(self):
        """A sitecustomize or conda banner prints ahead of the probe's own line."""
        assert interpreters.parse_version(b"conda banner\n3 13") == (3, 13)
        assert interpreters.parse_version(b"warning: locale failed\n3 12") == (3, 12)
        assert interpreters.parse_version(b"a\nb\n3 10") == (3, 10)

    def test_a_chatty_but_healthy_interpreter_counts_as_working(self):
        chatty = interpreters.Candidate(
            sys.executable,
            ("-c", "import sys; print('banner'); print(*sys.version_info[:2])", "--"))
        assert interpreters.starts(chatty)

    def test_unreadable_probe_output_is_not_a_version(self):
        assert interpreters.parse_version(b"") is None
        assert interpreters.parse_version(b"Python was not found") is None

    def test_the_beside_prober_check_is_windows_only(self):
        """Windows searches the caller's own directory before PATH; POSIX does not."""
        if os.name == "nt":
            pytest.skip("POSIX execvp searches PATH only; this guard is for Windows")
        assert interpreters.found_only_beside_prober("python") is False



class TestMalformedHookConfig:
    """A bad hooks.json must yield no candidates, never an exception."""

    @pytest.mark.parametrize("shape", [
        [],                                              # top level is a list
        {"hooks": []},                                   # hooks is not a mapping
        {"hooks": {"MessageDisplay": "nope"}},           # groups is not a list
        {"hooks": {"MessageDisplay": ["nope"]}},         # group is not a mapping
        {"hooks": {"MessageDisplay": [{"hooks": "no"}]}},        # entries not a list
        {"hooks": {"MessageDisplay": [{"hooks": ["no"]}]}},      # entry not a mapping
        {"hooks": {"MessageDisplay": [{"hooks": [{"command": ["x"], "args": []}]}]}},
        {},
    ])
    def test_odd_shapes_yield_no_candidates(self, shape):
        assert interpreters.declared(shape) == ()

    def test_a_well_formed_file_still_parses(self):
        hooks = json.loads(_HOOKS.read_text(encoding="utf-8"))
        assert [c.command for c in interpreters.declared(hooks)] == ["python3", "py"]


class TestHookSpawnsUnderADeclaredInterpreter:
    """Spawn by name in exec form, as Claude Code does, not via sys.executable."""

    @staticmethod
    def _spawn(command, args):
        payload = json.dumps({"delta": "alpha bravo", "message_id": "m1",
                              "index": 0, "final": True}).encode("utf-8")
        script = str(_SCRIPTS / "bionify.py")
        argv = [command, *args, script]
        try:
            return subprocess.run(argv, input=payload, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None

    def test_at_least_one_declared_interpreter_carries_the_hook(self):
        hooks = json.loads(_HOOKS.read_text(encoding="utf-8"))
        outputs = []
        for candidate in interpreters.declared(hooks):
            done = self._spawn(candidate.command, candidate.args)
            if done is None or done.returncode != 0 or not done.stdout:
                continue
            outputs.append(json.loads(done.stdout)["hookSpecificOutput"]["displayContent"])
        assert outputs, "no interpreter this plugin declares could run the hook"
        assert all("**alp**ha" in text for text in outputs)

    def test_declared_interpreters_agree(self):
        """Where both exist, both transform each delta; disagreement would flicker."""
        hooks = json.loads(_HOOKS.read_text(encoding="utf-8"))
        results = [self._spawn(c.command, c.args) for c in interpreters.declared(hooks)]
        ran = [d.stdout for d in results if d is not None and d.returncode == 0 and d.stdout]
        if len(ran) < 2:
            pytest.skip("only one declared interpreter is present on this machine")
        assert len(set(ran)) == 1


class TestStatusHealthWarning:
    def test_status_warns_when_no_declared_interpreter_can_start(self, monkeypatch, capsys):
        monkeypatch.setattr(interpreters, "any_usable", lambda root, timeout=None: False)
        control.main(["status"])
        out = capsys.readouterr().out
        assert "WARNING" in out
        assert "nothing is being bolded" in out

    def test_status_stays_a_single_line_when_the_hook_is_healthy(self, monkeypatch, capsys):
        monkeypatch.setattr(interpreters, "any_usable", lambda root, timeout=None: True)
        control.main(["status"])
        assert capsys.readouterr().out.strip().count("\n") == 0

    def test_other_verbs_do_not_pay_for_the_probe(self, monkeypatch, capsys):
        def fail(*a, **k):
            raise AssertionError("probe must not run for a plain toggle")
        monkeypatch.setattr(interpreters, "any_usable", fail)
        control.main(["on"])
        assert "WARNING" not in capsys.readouterr().out

    def test_an_unreadable_config_warns_instead_of_staying_silent(self, monkeypatch, capsys):
        def missing(*a, **k):
            raise FileNotFoundError("hooks.json")
        monkeypatch.setattr(interpreters, "any_usable", missing)
        control.main(["status"])
        out = capsys.readouterr().out
        assert "WARNING" in out
        assert "could not be read" in out

    def test_a_broken_probe_never_breaks_the_command(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise OSError("no /proc")
        monkeypatch.setattr(interpreters, "any_usable", boom)
        control.main(["status"])
        assert "claude-bionify:" in capsys.readouterr().out
