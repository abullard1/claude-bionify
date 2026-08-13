#!/usr/bin/env python3
"""claude-bionify:doctor: report whether the hook can start, and why not.

Prints a plain-text report and changes nothing. It deliberately does not write a
repaired hook into settings.json: the plugin cache path carries the version, so a
path written today breaks silently at the next update, which is the failure mode
this command exists to expose.
"""

import json
import os
import platform
import sys

import interpreters
import overrides
import settings

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def plugin_version(plugin_root: str) -> str:
    try:
        manifest = os.path.join(plugin_root, ".claude-plugin", "plugin.json")
        with open(manifest, encoding="utf-8") as f:
            return json.load(f).get("version", "unknown")
    except (OSError, ValueError):
        return "unknown"


def manual_hook(executable: str, plugin_root: str) -> str:
    """A settings.json hook pinned to an interpreter the declared ones missed."""
    entry = {
        "hooks": {
            "MessageDisplay": [{
                "hooks": [{
                    "type": "command",
                    "command": executable,
                    "args": [os.path.join(plugin_root, "scripts", "bionify.py")],
                    "timeout": 10,
                }]
            }]
        }
    }
    return json.dumps(entry, indent=2)


def verdict(results: list[interpreters.Result], plugin_root: str) -> list[str]:
    """The closing section: what works, or what to do about it."""
    working = interpreters.first_usable(results)
    declared = interpreters.declared(interpreters.load_hooks(plugin_root))
    names = {c.command for c in declared}
    if working and working.candidate.command in names:
        return [f"verdict     OK, the hook starts via `{working.candidate.label}`."]
    if working:
        return [
            "verdict     BROKEN. No interpreter the plugin declares can start, so",
            "            Claude Code shows the original text and reports no error.",
            "",
            f"            `{working.candidate.label}` does work, at:",
            f"              {working.executable}",
            "",
            "            Add this to ~/.claude/settings.json to point the hook at it,",
            "            then restart Claude Code:",
            "",
            *(f"              {line}" for line in
              manual_hook(working.executable, plugin_root).splitlines()),
            "",
            "            Both paths are specific to this install. A marketplace install",
            "            keeps the plugin under a version-numbered directory, so recheck",
            "            them after an upgrade or the hook goes quiet again.",
        ]
    return [
        "verdict     BROKEN. No Python 3.10+ could be started at all.",
        "            Install Python from https://www.python.org/downloads/ and,",
        "            on Windows, keep the py launcher option enabled.",
    ]


def report(plugin_root: str = PLUGIN_ROOT) -> str:
    results = interpreters.survey(plugin_root)
    state = overrides.load()
    lines = [
        "claude-bionify doctor",
        "",
        f"plugin      {plugin_version(plugin_root)} at {plugin_root}",
        f"platform    {platform.system() or os.name} ({sys.platform})",
        f"settings    {settings.render_state(state)}",
        "",
        "interpreters (the hook tries each in order; the first that works bolds)",
    ]
    lines += [f"  {interpreters.describe(r)}" for r in results]
    lines += ["", *verdict(results, plugin_root)]
    return "\n".join(lines)


def main() -> None:
    # Output is read as UTF-8; print() would apply the locale encoding.
    sys.stdout.buffer.write(report().encode("utf-8") + b"\n")


if __name__ == "__main__":
    main()
