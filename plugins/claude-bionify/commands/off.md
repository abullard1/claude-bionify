---
description: Turn claude-bionify off so Claude's replies render normally.
allowed-tools: Bash(python3 *), Bash(py *), Bash(python *)
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" off || py -3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" off || python "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" off`

The command above applied the change and printed claude-bionify's new state. Relay that single line to the user and take no further action.
