# Privacy Policy

**Effective date:** 2026-07-01

claude-bionify is a display-only Claude Code plugin. It bolds the leading part of
words in Claude's replies as they render in your terminal. This policy explains
what it does and does not do with data. The short version is that it collects
nothing and sends nothing anywhere.

## What we collect

Nothing. claude-bionify has no analytics, no telemetry, and no tracking of any
kind. It does not collect, store, or transmit personal data, usage data, message
content, or identifiers.

## Network access

None. The plugin makes no network requests. It runs entirely on your machine and
has no runtime dependencies and no external services.

## Your message content

claude-bionify only changes how text looks on screen. What gets saved to the
transcript and what Claude reads stays the original, unbolded text. Message
content is never copied, logged, or sent off your machine, and the bolding is
discarded once the text has rendered.

## Local files it writes

The plugin stores your own settings locally so they persist between sessions.
These files live under `CLAUDE_PLUGIN_DATA` and `~/.claude/claude-bionify/` and
hold only your configuration, such as whether the plugin is on, your fixation
strength, and your boundary mode. They contain no message content and no personal
data, they never leave your machine, and you can delete them at any time.

## Third parties

There are none. No data is shared with anyone because none is collected.

## Children's privacy

The plugin collects no data from anyone, including children.

## Changes to this policy

If this policy ever changes, the update will be committed to this repository with
a new effective date, so the history stays public and versioned alongside the code.

## Contact

Questions about privacy can go to samuel.ruairi.bullard@gmail.com or the
[issue tracker](https://github.com/abullard1/claude-bionify/issues). For security
reports, please follow [SECURITY.md](SECURITY.md) instead.
