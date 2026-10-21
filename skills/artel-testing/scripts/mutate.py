#!/usr/bin/env python3
"""Execute proposed mutants against a test command and report which survive (artel testing policy §4).

Input: a JSON file with a list of mutants:
  [{"id": "M1", "file": "app/x.py", "find": "a >= b", "replace": "a > b", "why": "boundary"}, ...]
Each mutant must match exactly once in its file. For each mutant: apply, run the test command, record
killed (tests failed) or survived (tests passed), restore the original bytes and verify restoration by
sha256 — the run aborts if a file cannot be restored. A control run first checks the suite is green on
the unmutated code (otherwise every mutant would look "killed").

Usage: mutate.py --mutants mutants.json --test "pytest -q tests/test_x.py" [--repo .] [--timeout 600]
Output: JSON report on stdout; exit 1 = some survived (findings; invalid mutants are listed too),
2 = harness problem only (red control run, invalid mutants, interruption), 0 = all killed.
Interruption (SIGTERM/SIGINT/SIGHUP) restores the mutated file before exiting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
CURRENT: subprocess.Popen | None = None  # the running test command, so an interruption can stop it
PENDING: list[str] = []  # signals that arrived while a file was being restored


def kill_group() -> None:
    p = CURRENT
    if p is not None and p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()


def run_tests(cmd: str, repo: Path, timeout: int) -> tuple[bool, str]:
    """Run the test command in its own process group; on timeout kill the whole group."""
    global CURRENT
    proc = subprocess.Popen(cmd, shell=True, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, start_new_session=True)
    CURRENT = proc
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group()
        return False, "timeout (counted as killed; process group terminated)"
    finally:
        if proc.poll() is not None:
            CURRENT = None
    tail = (out or "").strip().splitlines()[-3:]
    return proc.returncode == 0, " | ".join(tail)


class Interrupted(Exception):
    pass


def _raise_interrupt(signum, _frame):
    raise Interrupted(signal.Signals(signum).name)


def _defer(signum, _frame):
    PENDING.append(signal.Signals(signum).name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutants", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    repo = Path(a.repo).resolve()
    mutants = json.loads(Path(a.mutants).read_text(encoding="utf-8"))
    for s in SIGNALS:
        signal.signal(s, _raise_interrupt)  # restore the file before dying (finally below)

    green, tail = run_tests(a.test, repo, a.timeout)
    if not green:
        print(json.dumps({"error": "control run failed: the suite is not green on unmutated code",
                          "tail": tail, "test": a.test}, ensure_ascii=False, indent=2))
        return 2

    results = []
    for m in mutants:
        path = (repo / m["file"]).resolve()
        if repo not in path.parents:
            results.append({**m, "status": "error", "detail": "file outside repo"})
            continue
        try:
            original = path.read_bytes()
        except OSError as e:
            results.append({**m, "status": "error", "detail": f"cannot read: {e.strerror}"})
            continue
        before = hashlib.sha256(original).hexdigest()
        try:
            text = original.decode("utf-8")
        except UnicodeDecodeError:
            results.append({**m, "status": "error", "detail": "not UTF-8 text"})
            continue
        count = text.count(m["find"])
        if count != 1:
            results.append({**m, "status": "error", "detail": f"'find' matches {count} times (must be 1)"})
            continue
        interrupted = None
        try:
            path.write_text(text.replace(m["find"], m["replace"], 1), encoding="utf-8")
            passed, tail = run_tests(a.test, repo, a.timeout)
        except Interrupted as e:
            interrupted = str(e)
        finally:
            for s in SIGNALS:  # nothing may interrupt stopping the tests and restoring the file
                signal.signal(s, _defer)
            kill_group()
            path.write_bytes(original)
            for s in SIGNALS:
                signal.signal(s, _raise_interrupt)
        interrupted = interrupted or (PENDING[0] if PENDING else None)
        if interrupted:
            ok = sha(path) == before
            print(json.dumps({"error": f"interrupted by {interrupted}; {m['file']} restored: {ok}"}), file=sys.stderr)
            return 2
        if sha(path) != before:
            print(json.dumps({"error": f"restoration failed for {m['file']} — stop and restore from git"}),
                  file=sys.stderr)
            return 2
        results.append({**m, "status": "survived" if passed else "killed", "tail": tail})

    survived = [r for r in results if r["status"] == "survived"]
    errors = [r for r in results if r["status"] == "error"]
    print(json.dumps({"test": a.test, "control": "green", "total": len(results), "killed":
                      sum(r["status"] == "killed" for r in results), "survived": len(survived),
                      "errors": len(errors), "results": results}, ensure_ascii=False, indent=2))
    return 1 if survived else (2 if errors else 0)


if __name__ == "__main__":
    raise SystemExit(main())
