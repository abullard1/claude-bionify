---
description: Change a claude-bionify setting, e.g. "fixation 0.7" or "boundary syllable".
allowed-tools: Bash(python3 *), Bash(py *), Bash(python *)
argument-hint: <fixation|boundary|minlen|acronyms|urls|headings> <value>
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" set $ARGUMENTS || py -3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" set $ARGUMENTS || python "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" set $ARGUMENTS`

The command above applied the change and printed claude-bionify's new state. Relay that single line to the user and take no further action.
