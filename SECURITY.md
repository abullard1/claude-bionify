# Security Policy

## Reporting a vulnerability

Please report security issues privately, not in public issues.

- Preferred: use GitHub's private vulnerability reporting on this repository (the **Security** tab, then "Report a vulnerability").
- Alternatively, email samuel.ruairi.bullard@gmail.com.

Expect an initial response within a few days. Please include the plugin version, your Claude Code version, your OS and terminal, and steps to reproduce.

## Scope

claude-bionify runs locally as a Claude Code MessageDisplay hook and a small control CLI. It has no network access and no runtime dependencies. The formatting is display-only: it never changes the text Claude reads or what is saved to the transcript.

Relevant areas for a security report include the hook's handling of untrusted message text and the files it writes under `CLAUDE_PLUGIN_DATA` and `~/.claude/claude-bionify/`.

## Supported versions

The latest released version receives fixes. Please upgrade before reporting.
