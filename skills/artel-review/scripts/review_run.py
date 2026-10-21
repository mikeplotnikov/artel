#!/usr/bin/env python3
"""Run a resumable review wave, switching families only on usage-limit output."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MATRIX = HERE / "../../artel/scripts/matrix.py"
CONTRACT = HERE.parent / "references/lane-prompt.md"
LIMIT = re.compile(r"\busage limit\b|\bspend cap\b", re.IGNORECASE)
CLAUDE_LIMIT = re.compile(r"^You['’]ve hit your (?:session|weekly|usage) limit\b")
RESET = re.compile(r"\bresets\b|\btry again at\b", re.IGNORECASE)
CHECKLIST = "<lane-specific checklist: code / tests (mutation checklist) / security / infrastructure / layout / docs>"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def limit_details(output: str, harness: str) -> tuple[str | None, list[str]]:
    # omp has no verified limit signature: without ## Done it fails, with no handover.
    lines = output.splitlines()
    matched = next((line for line in lines if
                    (harness == "codex" and line.startswith("ERROR:") and LIMIT.search(line)) or
                    (harness == "claude-code" and CLAUDE_LIMIT.match(line))), None)
    # reset text only from the limit line and the line right after it — other lines may quote documentation
    if matched is None:
        return None, []
    i = lines.index(matched)
    return matched, [line for line in lines[i:i + 2] if RESET.search(line)]


def confirm_limit(args: argparse.Namespace, reviewer: dict) -> bool | str:
    # Reuse the matrix's Orca/file parsing and family-specific window selection.
    spec = importlib.util.spec_from_file_location("artel_matrix", MATRIX)
    matrix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(matrix)
    limits = matrix.load_limits(argparse.Namespace(limits=args.limits, no_limits=False))
    if limits is None:
        return "unknown"
    windows = matrix.family_windows(limits, reviewer["family"], reviewer["model"])
    return any(used >= 100 for used in windows.values())


class RunnerInterrupted(Exception):
    def __init__(self, signum: int):
        self.signum = signum
        super().__init__(f"runner interrupted by signal {signum}")


def name(value: str) -> str:
    if value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise argparse.ArgumentTypeError("must be a single name using letters, digits, '.', '_' or '-'")
    return value


def nonnegative(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def positive(value: str) -> float:
    number = float(value)
    if not 0 < number < float("inf"):
        raise argparse.ArgumentTypeError("must be positive and finite")
    return number


def pick(args: argparse.Namespace, excluded: list[str]) -> tuple[int, dict]:
    command = [sys.executable, str(MATRIX), "pick", "--role", args.role,
               "--tier", args.tier, "--author", args.author, "--json"]
    if args.limits:
        command += ["--limits", args.limits]
    for family in excluded:
        command += ["--exclude-family", family]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, encoding="utf-8")
    if result.returncode not in {0, 3}:
        raise RuntimeError(f"matrix pick exited {result.returncode}: {result.stderr.strip()}")
    return result.returncode, json.loads(result.stdout)


def prompt(args: argparse.Namespace, reviewer: dict, started: str,
           wave_file: Path, handover: dict | None) -> str:
    contract, replacement = re.findall(r"```text\n(.*?)\n```", CONTRACT.read_text(encoding="utf-8"), re.S)
    values = {"<lane>": args.lane, "<K>": str(args.wave), "<slice>": args.feature,
              "<feature>": args.feature, "<tier>": args.tier, "<base>": args.base,
              "<head>": args.head, "<model id>": reviewer["model"],
              "<effort>": reviewer["effort"], "<ISO time>": started,
              CHECKLIST: args.checklist}
    if handover:
        values.update({"<model>": handover["from"], "<old model>": handover["from"],
                       "<your model>": reviewer["model"],
                       "<reason, e.g. provider limit, resets at …>": handover["reason"],
                       "<reason>": handover["reason"]})
        if wave_file.exists():
            instruction = ("For this handover, read the existing wave file first; insert findings under "
                           "## Findings, coverage under ## Coverage, and confirmations or rejections "
                           "under the old findings. Keep every existing line in its original order; "
                           "do not recreate or truncate it. The header-creation instruction above "
                           "applies only to the first reviewer.")
        else:
            replacement = re.sub(r"^Its partial work is in .*$",
                                 "The previous reviewer did not create a wave file.", replacement, flags=re.M)
            instruction = ("There are no findings or coverage to resume. Follow step 1 of the contract "
                           "above to create the header, then review the whole diff and finish this wave.")
        contract += "\n\n" + replacement + "\n\n" + instruction
    # One pass prevents placeholder-like text in user values from being re-expanded.
    filled = re.sub("|".join(re.escape(key) for key in values),
                    lambda match: values[match.group()], contract)
    if reviewer["harness"] == "omp":
        filled += (f"\n\nYou cannot run shell commands. The diff under review is in "
                   f"{wave_file.with_suffix('.diff')}; read it and any repository file you need.")
    return filled + f"\n\nWave file: {wave_file}\n"


def command(args: argparse.Namespace, reviewer: dict, text: str) -> list[str]:
    model, effort = reviewer["model"], reviewer["effort"]
    if reviewer["harness"] == "codex":
        return ["codex", "exec", "-C", str(args.repo), "-m", model,
                "-c", f"model_reasoning_effort={effort}", "--sandbox", "workspace-write", text]
    if reviewer["harness"] == "claude-code":
        tools = ("Read,Grep,Glob,Bash(git diff:*),Bash(git log:*),Bash(git show:*),"
                 f"Write(work/{args.feature}/reviews/**),Edit(work/{args.feature}/reviews/**)")
        return ["claude", "-p", text, "--model", model, "--effort", effort, "--allowedTools", tools]
    if reviewer["harness"] == "omp":
        return ["omp", "-p", text, "--model", model, "--thinking", effort,
                "--approval-mode", "write", "--mode", "text"]
    raise RuntimeError(f"unsupported harness: {reviewer['harness']}")


def launch(args: argparse.Namespace, reviewer: dict, text: str,
           log: Path) -> tuple[int | None, bool, str, int | None]:
    timed_out = False
    interrupted = None
    with tempfile.TemporaryDirectory(prefix="artel-review-") as temp:
        if fake := os.environ.get("ARTEL_REVIEW_FAKE"):
            prompt_file = Path(temp) / "prompt.txt"
            prompt_file.write_text(text, encoding="utf-8")
            cmd = [fake, reviewer["harness"], reviewer["model"], str(prompt_file)]
        else:
            cmd = command(args, reviewer, text)
        with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", errors="replace", dir=log.parent,
                                         prefix=".review-log-", delete=False) as output:
            temporary = Path(output.name)
            try:
                os.replace(temporary, log)
            finally:
                temporary.unlink(missing_ok=True)
            exit_code = None
            process = None
            group_killed = False

            def kill_group():
                nonlocal group_killed
                if process is not None and not group_killed:
                    group_killed = True
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

            def interrupt_reviewer(signum, frame):
                nonlocal interrupted
                if interrupted is None:
                    interrupted = signum
                # Do not raise inside process creation or cleanup. Killing the
                # group releases wait(); the normal path always reaps the leader.
                kill_group()

            handlers = {sig: signal.signal(sig, interrupt_reviewer) for sig in
                        (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
            try:
                try:
                    try:
                        process = subprocess.Popen(cmd, cwd=args.repo, stdin=subprocess.DEVNULL,
                                                   stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                    except OSError as error:
                        output.write(str(error) + "\n")
                    if interrupted is not None:
                        # The signal may have arrived before Popen returned its handle.
                        kill_group()
                    if process is not None:
                        process.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                finally:
                    # Also remove grandchildren that outlive a normally exiting leader.
                    kill_group()
                    if process is not None:
                        process.wait()
                        exit_code = process.returncode
                output.flush()
                output.seek(0)
                captured = output.read()
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
    return exit_code, timed_out, captured, interrupted


def scope_baseline(repo: Path) -> dict:
    def git(*arguments: str) -> bytes:
        return subprocess.run(["git", "-C", str(repo), *arguments], stdin=subprocess.DEVNULL,
                              capture_output=True, check=True).stdout

    head = git("rev-parse", "HEAD").strip()
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    raw = git("status", "--porcelain", "-z", "--ignored=matching", "--untracked-files=all")
    entries = iter(os.fsdecode(raw).split("\0"))
    paths = {}
    for entry in entries:
        if not entry:
            continue
        entry_paths = [entry[3:]]
        if "R" in entry[:2] or "C" in entry[:2]:
            entry_paths.append(next(entries))
        for path in entry_paths:
            full_path = repo / path
            # Metadata detects repeated edits with identical porcelain codes without
            # opening ignored files (which may contain secrets).
            candidates = [full_path]
            if full_path.is_dir() and not full_path.is_symlink():
                # Git collapses ignored directories into one entry. Expand to
                # files so lane-output exclusions still apply inside them.
                candidates = [item for item in full_path.rglob("*")
                              if not item.is_dir() or item.is_symlink()]
            for candidate in candidates:
                relative = candidate.relative_to(repo)
                if entry[:2] == "!!" and (candidate.name == ".DS_Store" or candidate.suffix == ".pyc" or
                                          "__pycache__" in relative.parts[:-1]):
                    continue
                metadata = None
                try:
                    stat = candidate.lstat()
                    metadata = (stat.st_mode, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
                except FileNotFoundError:
                    pass
                paths[relative.as_posix()] = (entry[:2], metadata, tuple(entry_paths))
    return {"head": head, "branch": branch, "paths": paths}


def lane_output(path: str, wave_file: Path, repo: Path) -> bool:
    relative = wave_file.relative_to(repo).as_posix()
    if path in {relative, wave_file.with_suffix(".status.json").relative_to(repo).as_posix(),
                wave_file.with_suffix(".diff").relative_to(repo).as_posix()}:
        return True
    if re.fullmatch(re.escape(relative) + r"(?:\.\d+\.log|\.before-\d+\.md)", path):
        return True
    # Other lanes of the same wave run concurrently: their outputs cannot be attributed
    # to this reviewer. Arbitrary files under reviews/ remain in scope.
    prefix = re.escape(wave_file.parent.relative_to(repo).as_posix() + "/")
    wave = re.escape(wave_file.name.split("-", 2)[1])
    archive = rf"(?:wave-{wave}-[A-Za-z0-9_.-]+\.md\.old-[0-9TZ]+/)?"
    return bool(re.fullmatch(prefix + archive + rf"wave-{wave}-[A-Za-z0-9_.-]+(?:\.md|\.diff|\.md\.\d+\.log|"
                            r"\.status(?:\.\d+)?\.json|\.md\.before-\d+\.md)", path))


def scope_paths(repo: Path, wave_file: Path, before: dict) -> list[str]:
    after = scope_baseline(repo)
    paths = {path for path, entry in after["paths"].items()
             if before["paths"].get(path) != entry and not lane_output(path, wave_file, repo)}
    # A dirty/untracked entry disappearing can also mean an out-of-scope deletion
    # or restoration of someone else's work.
    paths.update(path for path in before["paths"] if path not in after["paths"]
                 and not lane_output(path, wave_file, repo))
    if before["head"] != after["head"]:
        paths.add("HEAD")
    if before["branch"] != after["branch"]:
        paths.add("branch")
    return sorted(paths)


def next_number(wave_file: Path, suffix: str) -> int:
    numbers = [int(match[1]) for path in wave_file.parent.iterdir()
               if (match := re.fullmatch(re.escape(wave_file.name) + suffix, path.name))]
    return max(numbers, default=0) + 1


def has_done(wave_file: Path) -> bool:
    return wave_file.exists() and any(re.match(r"^## Done(?:\s|$)", line) for line in
                                     wave_file.read_text(encoding="utf-8", errors="replace").splitlines())


def preserves_lines(original: bytes, updated: bytes) -> bool:
    """Allow insertions while preserving every original line in order."""
    remaining = iter(updated.splitlines())
    return all(line in remaining for line in original.splitlines())


def archive_status(wave_file: Path) -> None:
    path = wave_file.with_suffix(".status.json")
    if path.exists():
        number = 1
        while wave_file.with_suffix(f".status.{number}.json").exists():
            number += 1
        path.rename(wave_file.with_suffix(f".status.{number}.json"))


def archive_wave(wave_file: Path) -> None:
    archive = Path(f"{wave_file}.old-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}")
    archive.mkdir()
    for path in wave_file.parent.iterdir():
        if (path == wave_file or path == wave_file.with_suffix(".diff") or
            re.fullmatch(re.escape(wave_file.name) + r"(?:\.\d+\.log|\.before-\d+\.md)", path.name) or
            re.fullmatch(re.escape(wave_file.stem) + r"\.status(?:\.\d+)?\.json", path.name)):
            path.rename(archive / path.name)


def run(args: argparse.Namespace, wave_file: Path) -> dict:
    status = {"reviewers": [], "outcome": "failed", "independence_weakened": False,
              "handover_chain": []}
    excluded = []
    handover = None
    handover_count = 0
    try:
        if wave_file.exists() and args.force_new:  # finished or not: start the wave from scratch
            archive_wave(wave_file)
        archive_status(wave_file)
        if has_done(wave_file):
            status["outcome"] = "already_done"
            return status
        if wave_file.exists():
            handover = {"from": "previous invocation", "family": None,
                        "reason": "resumed by a new runner invocation", "wave_file": str(wave_file)}
    except RunnerInterrupted as error:
        status.update(outcome="interrupted_runner", signal=error.signum)
        return status
    except (OSError, ValueError, RuntimeError) as error:
        status.update(error=str(error))
        return status
    while True:
        try:
            code, reviewer = pick(args, excluded)
            if code == 3:
                status.update(outcome="no_candidate", pick=reviewer)
                break
            status["independence_weakened"] = reviewer["independence_weakened"]
            started = now()
            if reviewer["harness"] == "omp":
                diff = subprocess.run(["git", "-C", str(args.repo), "diff", f"{args.base}..{args.head}"],
                                      stdin=subprocess.DEVNULL, capture_output=True, check=True).stdout
                # Replace the lane's diff without following pre-existing symlinks or hardlinks.
                temporary = None
                if wave_file.parent.resolve() != wave_file.parent:
                    raise RuntimeError("review directory became a symlink before the diff write")
                try:
                    with tempfile.NamedTemporaryFile(dir=wave_file.parent, prefix=".review-diff-",
                                                     delete=False) as output:
                        temporary = Path(output.name)
                        output.write(diff)
                    os.replace(temporary, wave_file.with_suffix(".diff"))
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
            text = prompt(args, reviewer, started, wave_file, handover)
            if handover:
                status["handover_chain"].append({**handover, "to": reviewer["model"]})
            original = None
            backup = None
            if handover and wave_file.exists():
                original = wave_file.read_bytes()
                number = next_number(wave_file, r"\.before-(\d+)\.md")
                backup = Path(f"{wave_file}.before-{number}.md")
                with backup.open("xb") as file:
                    file.write(original)
            log_number = next_number(wave_file, r"\.(\d+)\.log")
            log = Path(f"{wave_file}.{log_number}.log")
            if log.is_symlink():
                raise RuntimeError(f"log path is a symlink: {log}")
            baseline = scope_baseline(args.repo)
            exit_code, timed_out, captured, interrupted = launch(args, reviewer, text, log)
            finished = now()
            matched, resets = limit_details(captured, reviewer["harness"])
            attempt = {"model": reviewer["model"], "family": reviewer["family"],
                       "harness": reviewer["harness"], "effort": reviewer["effort"],
                       "started": started, "finished": finished, "exit_code": exit_code,
                       "outcome": "failed", "matched_limit_line": matched, "reset_text": resets,
                       "timed_out": timed_out, "notes": reviewer["notes"], "log": str(log)}
            status["reviewers"].append(attempt)
            if backup:
                attempt["backup"] = str(backup)
            if interrupted is not None:
                attempt["outcome"] = "interrupted_runner"
                status.update(outcome="interrupted_runner", signal=interrupted)
                break
            if wave_file.parent.resolve() != wave_file.parent or wave_file.is_symlink() or log.is_symlink():
                raise RuntimeError("review output paths became symlinks during the run")
            if original is not None and (not wave_file.exists() or
                                         not preserves_lines(original, wave_file.read_bytes())):
                attempt["outcome"] = "handover_overwrote"
                status["outcome"] = "handover_overwrote"
                break
            violations = scope_paths(args.repo, wave_file, baseline)
            if violations:
                attempt["outcome"] = "scope_violation"
                status.update(outcome="scope_violation", scope_violations=violations)
                break
            confirmed = confirm_limit(args, reviewer) if matched else False
            attempt["limit_confirmed"] = confirmed
            outcome = "done" if has_done(wave_file) else "interrupted_limit" if matched and confirmed else "failed"
            attempt.update(outcome=outcome, matched_limit_line=matched, reset_text=resets)
            if outcome != "interrupted_limit":
                status["outcome"] = outcome
                break
            if handover_count >= args.max_handovers:
                status["outcome"] = "handovers_exhausted"
                break
            excluded.append(reviewer["family"])
            handover_count += 1
            reason = "\n".join(dict.fromkeys([matched, *resets]))
            handover = {"from": reviewer["model"], "family": reviewer["family"], "reason": reason,
                        "wave_file": str(wave_file)}
        except RunnerInterrupted as error:
            status.update(outcome="interrupted_runner", signal=error.signum)
            break
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            status.update(outcome="failed", error=str(error))
            break
    return status


def write_status(path: Path, status: dict) -> str:
    """Replace the runner-owned status file without following a reviewer-created link."""
    temporary = None
    try:
        if path.parent.resolve() != path.parent:
            raise RuntimeError("review directory became a symlink during the run")
        output = json.dumps(status, ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".review-status-", delete=False) as file:
            temporary = Path(file.name)
            file.write(output + "\n")
        os.replace(temporary, path)
    except (OSError, RuntimeError) as error:
        if status["outcome"] == "done":
            status["outcome"] = "failed"
        status["status_write_error"] = str(error)
        output = json.dumps(status, ensure_ascii=False, indent=2)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--feature", required=True, type=name)
    ap.add_argument("--lane", required=True, type=name)
    ap.add_argument("--wave", required=True, type=nonnegative)
    ap.add_argument("--role", required=True)
    ap.add_argument("--tier", required=True, choices=("t01", "t23"))
    ap.add_argument("--author", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--checklist", required=True)
    ap.add_argument("--limits")
    ap.add_argument("--force-new", action="store_true")
    ap.add_argument("--max-handovers", type=nonnegative, default=2)
    ap.add_argument("--timeout", type=positive, default=3600)
    args = ap.parse_args()
    args.repo = args.repo.resolve()
    reviews = args.repo / "work" / args.feature / "reviews"
    wave_file = reviews / f"wave-{args.wave}-{args.lane}.md"
    status_file = wave_file.with_suffix(".status.json")
    if reviews.resolve() != reviews or wave_file.is_symlink() or status_file.is_symlink():
        ap.error("review output paths must not be symlinks")
    reviews.mkdir(parents=True, exist_ok=True)
    received_signal = None

    def interrupt(signum, frame):
        nonlocal received_signal
        if received_signal is None:
            received_signal = signum
            raise RunnerInterrupted(signum)

    handlers = {sig: signal.signal(sig, interrupt) for sig in
                (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        status = run(args, wave_file)
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    output = write_status(status_file, status)
    print(output)
    return 0 if status["outcome"] == "done" else 5 if status["outcome"] == "handovers_exhausted" else 4


if __name__ == "__main__":
    raise SystemExit(main())
