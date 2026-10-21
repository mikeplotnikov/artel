#!/usr/bin/env python3
"""Offline reviewer fixture; each model's behavior is selected by ARTEL_REVIEW_BEHAVIORS."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

harness, model, prompt_file = sys.argv[1:]
prompt = Path(prompt_file).read_text(encoding="utf-8")
wave_file = Path(next(line.removeprefix("Wave file: ") for line in prompt.splitlines()
                      if line.startswith("Wave file: ")))
capture = Path(os.environ["ARTEL_REVIEW_CAPTURE_DIR"])
capture.mkdir(parents=True, exist_ok=True)
assert sys.stdin.read() == "", "reviewer stdin must be closed"
behavior = json.loads(os.environ["ARTEL_REVIEW_BEHAVIORS"])[model]
(capture / f"{model}.prompt.txt").parent.mkdir(parents=True, exist_ok=True)
(capture / f"{model}.prompt.txt").write_text(prompt, encoding="utf-8")
(capture / f"{model}.harness.txt").write_text(harness, encoding="utf-8")
if "check_diff" in behavior:
    diff_file = wave_file.with_suffix(".diff")
    assert diff_file.read_text(encoding="utf-8") == behavior["check_diff"]
    assert f"The diff under review is in {diff_file}; read it" in prompt
if behavior.get("exhaust_family") and os.environ.get("ARTEL_REVIEW_LIMITS"):
    limits_file = Path(os.environ["ARTEL_REVIEW_LIMITS"])
    limits = json.loads(limits_file.read_text())
    provider = "codex" if harness == "codex" else "claude"
    limits["result"]["rateLimits"][provider]["weekly"]["usedPercent"] = 100
    limits_file.write_text(json.dumps(limits))
if behavior.get("mode") in {"early_limit", "no_write"}:
    print("fake reviewer stdout", flush=True)
    print(behavior.get("message", "network failure"), file=sys.stderr, flush=True)
    raise SystemExit(1)
if behavior.get("old_model"):
    assert behavior["old_model"] in prompt
    assert str(wave_file) in prompt
    assert "re-check every finding" in prompt.lower()
    if behavior.get("no_partial"):
        assert not wave_file.exists()
        assert "create the header" in prompt
        assert "did not create a wave file" in prompt
        assert "Its partial work is in" not in prompt
    else:
        assert "do not recreate or truncate" in prompt
        assert "### F1" in wave_file.read_text(encoding="utf-8")
if behavior.get("resume"):
    assert "resumed by a new runner invocation" in prompt
    assert "do not recreate or truncate" in prompt
if (behavior.get("old_model") and not behavior.get("no_partial")) or behavior.get("resume"):
    handover = f"\n## Handover · from {behavior.get('old_model', 'previous invocation')} to {model}\n"
    if behavior.get("insert_sections"):
        text = wave_file.read_text(encoding="utf-8")
        text = text.replace("- evidence: first finding\n",
                            "- evidence: first finding\n" + handover +
                            f"- {behavior.get('annotation', 'confirmed by')} {model}\n")
        text = text.replace("## Coverage\n", "### F2 · minor · project.txt:1\n"
                            "- evidence: second finding\n## Coverage\n"
                            "- project.txt — checked: remaining code — result: F2\n")
        wave_file.write_text(text, encoding="utf-8")
    else:
        with wave_file.open("a", encoding="utf-8") as output:
            output.write(handover)
            output.write(f"- confirmed by {model}\n### F2 · minor · project.txt:1\n")
else:
    wave_file.write_text(f"# Wave · reviewer {model}\n## Findings\n"
                         "### F1 · minor · project.txt:1\n- evidence: first finding\n## Coverage\n",
                         encoding="utf-8")
mode = behavior.get("mode", "done")
if mode == "overwrite":
    wave_file.write_text("# Replaced findings\n## Done · replacement\n")
if behavior.get("replace_same_length"):
    wave_file.write_text(wave_file.read_text().replace("first finding", "other finding"))
if behavior.get("delete_finding_line"):
    wave_file.write_text(wave_file.read_text().replace("- evidence: first finding\n", ""))
if behavior.get("reorder_finding_lines"):
    wave_file.write_text(wave_file.read_text().replace(
        "### F1 · minor · project.txt:1\n- evidence: first finding\n",
        "- evidence: first finding\n### F1 · minor · project.txt:1\n"))
for path in behavior.get("rewrite_paths", []):
    Path(path).write_text("rewritten during review\n", encoding="utf-8")
if mode == "status_symlink":
    wave_file.with_suffix(".status.json").symlink_to(Path.cwd() / "project.txt")
elif mode == "status_hardlink":
    os.link("project.txt", wave_file.with_suffix(".status.json"))
elif mode == "next_log_hardlink":
    os.link("project.txt", Path(f"{wave_file}.2.log"))
if mode == "scope":
    Path(behavior.get("path", "project.txt")).write_text("outside review scope\n", encoding="utf-8")
elif mode == "rename":
    Path("project.txt").rename(wave_file.parent / "moved-project.txt")
    subprocess.run(["git", "add", "-A"], check=True)
elif mode == "commit":
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "reviewer"], check=True)
elif mode == "branch":
    subprocess.run(["git", "checkout", "-qb", "reviewer-branch"], check=True)
elif mode == "archive_other_lane":
    spec = importlib.util.spec_from_file_location("review_runner", os.environ["ARTEL_REVIEW_RUNNER"])
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.archive_wave(wave_file.with_name("wave-1-security.md"))
elif mode in {"timeout", "background"}:
    heartbeat = capture / "child-heartbeat.txt"
    subprocess.Popen([sys.executable, "-c", "import sys,time; from pathlib import Path; "
                      "p=Path(sys.argv[1]);\nwhile True: p.write_text(str(time.monotonic_ns())); time.sleep(.02)",
                      str(heartbeat)])
    (capture / "child-group.txt").write_text(str(os.getpgrp()))
    print("child started", flush=True)
    deadline = time.monotonic() + 5
    while not heartbeat.exists() and time.monotonic() < deadline:
        time.sleep(.01)
    assert heartbeat.exists(), "background child did not start"
    if mode == "timeout":
        time.sleep(30)
if mode in {"done", "scope", "rename", "status_symlink", "status_hardlink", "commit", "branch", "background",
            "archive_other_lane"}:
    with wave_file.open("a", encoding="utf-8") as output:
        if (not behavior.get("old_model") or behavior.get("no_partial")) and not behavior.get("insert_sections"):
            output.write("### F2 · minor · project.txt:1\n- evidence: second finding\n")
        output.write("## Done · 2026-10-06T00:00:00+00:00 · 2 findings\n")
print("fake reviewer stdout", flush=True)
if behavior.get("message"):
    print(behavior["message"], file=sys.stderr, flush=True)
raise SystemExit(behavior.get("exit", 1 if mode in {"limit", "error", "next_log_hardlink"} else 0))
