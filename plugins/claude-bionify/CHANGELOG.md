# Changelog

All notable changes to claude-bionify are documented here. This project follows
[semantic versioning](https://semver.org) and [Keep a Changelog](https://keepachangelog.com).

## [1.0.5] - 2026-08-13

### Fixed
- The hook now starts on native Windows. It was declared to run as `python3`, which the
  python.org installer never creates, while Windows ships a Microsoft Store placeholder of
  that name that starts and exits without running Python. Claude Code spawns exec-form hooks
  with no shell, so neither case could fall back, and a failed `MessageDisplay` hook shows the
  original text without reporting an error: the plugin was silently inert. It is now declared
  twice, as `python3` and as `py -3`, and the first one that starts does the bolding.
  Reported by @aermak.
- `/claude-bionify:status` no longer reports ON while nothing is being bolded. The slash
  commands reach Python through a shell, which resolves names the hook's own spawn cannot, so
  status could describe a hook that was never running. It now appends a warning when no
  declared interpreter can start.
- The slash commands fall back through `py -3` and `python`, so they keep working where only
  one of the three names resolves.

### Added
- `/claude-bionify:doctor` reports whether the hook can start and why not. It tests each
  interpreter by running it, rather than looking it up on `PATH`, because the Store placeholder
  passes a PATH check. When it finds a working interpreter the plugin does not declare, such as
  a conda or uv install, it prints a ready-made settings snippet, with the caveat that the path
  is version-scoped and needs updating after an upgrade. It never edits configuration itself.

### Notes
- Where both `python3` and `py` resolve, both run the transform on every flush. That is safe
  because 1.0.4 made the fence-state write atomic; reverting that change would corrupt state on
  those machines only. A test pins the two interpreters to identical output.

## [1.0.4] - 2026-08-13

### Fixed
- Code blocks are less likely to be bolded as prose when Claude streams quickly.
  Claude Code runs up to three flushes of one message at once, and the file that
  remembers whether a code fence is open was truncated before being rewritten, so
  an overlapping flush could read it as empty. It is now written to a temporary
  file and moved into place, which no reader can observe half-finished.
- The hook reads the message identifier from `message_id`, the field Claude Code
  actually sends. It looked for `messageId`, never found it, and fell back to the
  session id, which keyed fence state per session rather than per message.
- Fence state is cleared when a message ends on a newline. That final flush
  carries no text, and the hook returned before reaching its own cleanup, leaving
  a stale file behind for the rest of the session.
- Stale temporary files from an interrupted flush are collected alongside stale
  fence state at the start of the next message.

## [1.0.3] - 2026-07-26

### Fixed
- Non-ASCII characters no longer garble on Windows. Python decodes a pipe with
  the system ANSI codepage rather than UTF-8, so em dashes and curly quotes in
  Claude's replies arrived corrupted before being bolded. The hook now reads its
  event as bytes and lets JSON decode it. Thanks to @aermak for the report.
- `/claude-bionify:status` and the other control commands no longer emit an
  undecodable separator on Windows. The status line is now written as UTF-8
  bytes instead of being encoded with the platform codepage, which produced a
  broken glyph on Western systems and failed outright on Japanese ones.
- `assets/generate_themes.py` reads and writes UTF-8 explicitly, so regenerating
  `themes.svg` produces the same file on any platform.

## [1.0.2] - 2026-07-12

### Changed
- The claude-bionify skill now confirms the plugin is installed before giving
  settings or command guidance. Skill marketplaces can surface the skill on its
  own, so when the plugin is missing the skill now says so and points to the
  install commands instead of walking through controls that are not there.

## [1.0.1] - 2026-07-04

### Fixed
- Preserve fenced code blocks that use spaced info strings such as
  ```` ``` python ````.
- Stop URL protection before surrounding quotes and brackets.
- Reject invalid boolean and minimum-word-length live override values instead
  of silently applying surprising settings.
- Save live overrides correctly when `CLAUDE_BIONIFY_STATE_FILE` is set to a
  filename in the current working directory.
- Use fully-qualified `/claude-bionify:set ...` examples in the plugin README.

## [1.0.0] - 2026-06-28

Initial release.

### Added
- `MessageDisplay` hook that bolds the leading part of each word in Claude's
  streamed replies as they render. The change is display-only: the saved
  transcript and what Claude reads are never altered.
- Unicode-aware bolding that works in any language, while leaving numbers and
  identifiers like `value3` or `api_key` alone.
- Three bolding strategies via the `boundary` option: `fraction` (default),
  `syllable` (ends at the first syllable), and `log` (long words bolded less).
- Configurable `fixation` strength and `min_word_length`.
- `skip_acronyms` (default on) leaves ALL-CAPS acronyms like `API` whole.
- `protect_urls` (default on) keeps URLs, emails, and file paths unbolded, while
  still bolding prose like `and/or` or `e.g.`.
- `skip_headings` (default on) leaves markdown headings unbolded.
- Inline `` `code` ``, fenced code blocks, markdown links, and existing
  `**bold**` always render verbatim.
- Live control commands (`/claude-bionify:on`, `:off`, `:toggle`,
  `:set <option> <value>`, `:status`, `:reset`) that change settings mid-session
  with no reload.
- Seven color themes (Nord, Dracula, Gruvbox, Solarized Dark, Solarized Light,
  Sepia, Focus Dark) in Claude Code's `/theme` picker as `custom:claude-bionify:<name>`.
- Crash-safe by design: on any error the original text is shown unchanged.
