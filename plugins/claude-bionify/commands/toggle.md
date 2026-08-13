---
description: Flip claude-bionify on or off.
allowed-tools: Bash(python3 *), Bash(py *), Bash(python *)
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" toggle || py -3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" toggle || python "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" toggle`

The command above applied the change and printed claude-bionify's new state. Relay that single line to the user and take no further action.
