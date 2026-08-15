"""Whether the MessageDisplay hook can start.

hooks.json launches its interpreters in exec form, which Claude Code spawns with
no shell, so the name must resolve to a real executable. Windows ships a
Microsoft Store placeholder named python3.exe that spawns and exits without
running Python, so a candidate is judged by running it, not by finding it.
"""

import json
import os
import shutil
import subprocess
import sys
from typing import NamedTuple

MINIMUM = (3, 10)
PROBE_TIMEOUT = 10
_PROBE = "import sys; print(sys.version_info[0], sys.version_info[1])"


class Candidate(NamedTuple):
    """An interpreter the hook could be launched with."""

    command: str
    args: tuple[str, ...] = ()


def candidate_of(hook: dict) -> Candidate | None:
    """The interpreter one hooks.json entry launches, flags included."""
    command = hook.get("command")
    if not command or not isinstance(hook.get("args"), list):
        return None
    flags = tuple(str(a) for a in hook["args"] if not str(a).endswith(".py"))
    return Candidate(str(command), flags)


def declared(hooks_json: dict) -> tuple[Candidate, ...]:
    """Every interpreter the MessageDisplay hook declares, in order."""
    found = []
    for group in hooks_json.get("hooks", {}).get("MessageDisplay", []):
        for hook in group.get("hooks", []):
            candidate = candidate_of(hook)
            if candidate is not None and candidate not in found:
                found.append(candidate)
    return tuple(found)


def parse_version(raw: bytes) -> tuple[int, int] | None:
    parts = raw.decode("utf-8", "replace").split()
    try:
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return None


def found_only_beside_prober(command: str) -> bool:
    """Whether Windows resolved this name from our own directory rather than PATH.

    CreateProcess searches the calling process's directory first, so a Python
    probing for `python` finds its own sibling, which the hook cannot reach.
    """
    if os.name != "nt":
        return False
    beside = os.path.join(os.path.dirname(sys.executable), f"{command}.exe")
    if not os.path.exists(beside):
        return False
    on_path = shutil.which(command)
    return on_path is None or not os.path.samefile(on_path, beside)


def starts(candidate: Candidate, timeout: int = PROBE_TIMEOUT) -> bool:
    """Whether running `candidate` yields a Python the hook could use."""
    argv = [candidate.command, *candidate.args, "-c", _PROBE]
    try:
        done = subprocess.run(argv, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return False
    if done.returncode != 0:          # the Store placeholder lands here, exiting 9009
        return False
    if found_only_beside_prober(candidate.command):
        return False
    version = parse_version(done.stdout)
    return version is not None and version >= MINIMUM


def load_hooks(plugin_root: str) -> dict:
    with open(os.path.join(plugin_root, "hooks", "hooks.json"), encoding="utf-8") as f:
        return json.load(f)


def any_usable(plugin_root: str, timeout: int = PROBE_TIMEOUT) -> bool:
    """Whether the hook can start, stopping at the first interpreter that works."""
    return any(starts(c, timeout) for c in declared(load_hooks(plugin_root)))
