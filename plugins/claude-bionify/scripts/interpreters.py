"""Which Python the MessageDisplay hook can actually start.

hooks.json declares its interpreters in exec form, which Claude Code spawns
directly with no shell, so the name has to resolve to a real executable. Windows
ships a Microsoft Store placeholder named python3.exe that resolves and spawns
but exits without running Python, so a candidate is judged by running it, never
by looking it up on PATH.
"""

import json
import os
import subprocess
from typing import NamedTuple

MINIMUM = (3, 10)
PROBE_TIMEOUT = 10
_PROBE = "import sys; print(sys.version_info[0], sys.version_info[1], sys.executable)"

# Tried by the doctor but deliberately not declared in hooks.json: on Arch and
# inside an activated venv `python` is the same interpreter as `python3`, so
# declaring it would run the transform twice per flush for many POSIX users.
UNDECLARED = ("python",)


class Candidate(NamedTuple):
    """An interpreter the hook could be launched with."""

    command: str
    args: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return " ".join((self.command, *self.args))


class Result(NamedTuple):
    """What running a candidate showed."""

    candidate: Candidate
    version: tuple[int, int] | None
    executable: str
    detail: str

    @property
    def usable(self) -> bool:
        return self.version is not None and self.version >= MINIMUM


def candidate_of(hook: dict) -> Candidate | None:
    """The interpreter a single hooks.json entry launches.

    Everything ahead of the script path is an interpreter flag, which is how
    `py -3` keeps its version selector.
    """
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


def parse_probe(raw: bytes) -> tuple[tuple[int, int] | None, str]:
    """Read `(major, minor), executable` back out of a probe's stdout."""
    parts = raw.decode("utf-8", "replace").split(maxsplit=2)
    try:
        return (int(parts[0]), int(parts[1])), parts[2].strip()
    except (IndexError, ValueError):
        return None, ""


def explain_failure(returncode: int, output: bytes) -> str:
    """Why a candidate that started did not turn out to be a usable Python."""
    text = output.decode("utf-8", "replace")
    if "Microsoft Store" in text or "was not found" in text:
        return "Microsoft Store placeholder, not a real Python"
    return f"exited {returncode}"


def describe(result: Result) -> str:
    """One line about a candidate, for the doctor and status reports."""
    if result.usable:
        return f"{result.candidate.label}: Python {result.version[0]}.{result.version[1]}"
    if result.version is not None:
        return (f"{result.candidate.label}: Python {result.version[0]}.{result.version[1]}"
                f", below the {MINIMUM[0]}.{MINIMUM[1]} minimum")
    return f"{result.candidate.label}: {result.detail}"


def probe(candidate: Candidate, timeout: int = PROBE_TIMEOUT) -> Result:
    """Run `candidate` and report the Python it started, if any."""
    argv = [candidate.command, *candidate.args, "-c", _PROBE]
    try:
        done = subprocess.run(argv, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        return Result(candidate, None, "", "not found on PATH")
    except subprocess.SubprocessError:
        return Result(candidate, None, "", "timed out")
    except OSError as exc:
        return Result(candidate, None, "", f"could not start ({exc.strerror or exc})")
    if done.returncode != 0:
        return Result(candidate, None, "",
                      explain_failure(done.returncode, done.stdout + done.stderr))
    version, executable = parse_probe(done.stdout)
    if version is None:
        return Result(candidate, None, "", "started but reported no version")
    return Result(candidate, version, executable, "")


def hooks_path(plugin_root: str) -> str:
    return os.path.join(plugin_root, "hooks", "hooks.json")


def load_hooks(plugin_root: str) -> dict:
    with open(hooks_path(plugin_root), encoding="utf-8") as f:
        return json.load(f)


def survey(plugin_root: str, extra: tuple[str, ...] = UNDECLARED) -> list[Result]:
    """Probe every declared interpreter, then the undeclared fallbacks."""
    candidates = list(declared(load_hooks(plugin_root)))
    candidates += [Candidate(name) for name in extra
                   if all(c.command != name for c in candidates)]
    return [probe(c) for c in candidates]


def first_usable(results: list[Result]) -> Result | None:
    return next((r for r in results if r.usable), None)
