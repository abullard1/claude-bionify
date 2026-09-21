"""Exercise the hook in separate processes for each streamed delta."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
script = root / "plugins/claude-bionify/scripts/bionify.py"
mode = sys.argv[1]
assert mode in {"broken", "fixed"}
deltas = ["Here is the report:\n```", "Total revenue collected today", "```\nDone."]
correct = ["**He**re is the **rep**ort:\n```", deltas[1], "```\n**Do**ne."]
broken = [correct[0], "**Tot**al **reve**nue **colle**cted **tod**ay", deltas[2]]
for data_dir_mode in ("missing", "empty", "provided"):
    with tempfile.TemporaryDirectory() as temp:
        state = Path(temp) / "state"
        state.mkdir()
        runtime = state / "runtime.json"
        runtime.write_text('{"fixation": 0.5}', encoding="utf-8")
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("CLAUDE_PLUGIN_OPTION_")}
        env["CLAUDE_BIONIFY_STATE_FILE"] = str(runtime)
        env["CLAUDE_BIONIFY_DEBUG"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("CLAUDE_PLUGIN_DATA", None)
        if data_dir_mode == "empty":
            env["CLAUDE_PLUGIN_DATA"] = ""
        elif data_dir_mode == "provided":
            env["CLAUDE_PLUGIN_DATA"] = str(state)
        outputs = []
        for index, delta in enumerate(deltas):
            payload = {"delta": delta, "message_id": "reproduction",
                       "index": index, "final": index == 2}
            result = subprocess.run(
                [sys.executable, str(script)],
                input=json.dumps(payload).encode("utf-8"),
                capture_output=True, env=env, check=True, timeout=20,
            )
            outputs.append(json.loads(result.stdout)["hookSpecificOutput"]["displayContent"])
        expected = broken if mode == "broken" and data_dir_mode != "provided" else correct
        assert outputs == expected, (mode, data_dir_mode, outputs, expected)
        assert runtime.read_text(encoding="utf-8") == '{"fixation": 0.5}'
        assert not list(state.glob("fence-*")), "Final delta left fence state behind"
        print(json.dumps({"platform": sys.platform, "python": sys.version.split()[0],
                          "mode": mode, "data_dir": data_dir_mode,
                          "outputs": outputs, "passed": True}))
