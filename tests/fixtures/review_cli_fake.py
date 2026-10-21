#!/usr/bin/env python3
"""Offline native CLI adapter: record argv and pass the prompt to review_fake.py."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

args = sys.argv[1:]
if Path(sys.argv[0]).name == "orca":
    assert args == ["account", "list", "--json"]
    print(Path(os.environ["ARTEL_REVIEW_LIMITS"]).read_text())
    raise SystemExit(0)
if Path(sys.argv[0]).name == "codex":
    harness = "codex"
    model = args[args.index("-m") + 1]
    prompt = args[-1]
elif Path(sys.argv[0]).name == "omp":
    harness = "omp"
    model = args[args.index("--model") + 1]
    prompt = args[args.index("-p") + 1]
else:
    harness = "claude-code"
    model = args[args.index("--model") + 1]
    prompt = args[args.index("-p") + 1]
wave_file = Path(next(line.removeprefix("Wave file: ") for line in prompt.splitlines()
                      if line.startswith("Wave file: ")))
capture = Path(os.environ["ARTEL_REVIEW_CAPTURE_DIR"])
capture.mkdir(parents=True, exist_ok=True)
(capture / f"{model}.argv.json").parent.mkdir(parents=True, exist_ok=True)
(capture / f"{model}.argv.json").write_text(json.dumps(args), encoding="utf-8")
with tempfile.TemporaryDirectory(prefix="artel-native-fake-") as temp:
    prompt_file = Path(temp) / "prompt.txt"
    prompt_file.write_text(prompt, encoding="utf-8")
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().with_name("review_fake.py")),
                             harness, model, str(prompt_file)])
raise SystemExit(result.returncode)
