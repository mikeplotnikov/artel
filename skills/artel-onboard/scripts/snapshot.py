#!/usr/bin/env python3
"""Artel Route O, stage O1: a read-only, repeatable snapshot of a project (no model calls).

Writes JSON with: as_of, git (branches, worktrees, uncommitted, divergence), github (open PRs, recent
CI, release-branch rules, environments, secret NAMES only), workflows (triggers, environments, secret
references, owner guard), agent config (permission counts, hooks, rules, skills, pinned models,
instruction files), docs, tests, stack and risk signals with a proposed profile.

Reads only version-controlled files outside the exclusions, plus the local agent-permission files
(.claude/settings*.json) for counts and key names — never their values. Never reads secret values.
Every section fails soft into {"error": ...} so one missing tool never hides the rest.

Usage: snapshot.py [--repo PATH] [--release main] [--exclude PATH ...] [--out FILE]
--out must be outside the repository or under work/onboarding/ (onboarding's own folder).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

RISK_PATTERNS = {
    "money": r"payment|billing|invoice|stripe|yookassa|cloudpayments|refund|tariff|subscription",
    "auth": r"\bauth\b|jwt|password|totp|oauth|session_token|login",
    "personal_data": r"personal.?data|\bpii\b|152-?фз|passport|phone_number|\bphone\b|birth.?date",
    "migrations": r"alembic|migration|migrate\b|flyway|liquibase",
    "deploy": r"deploy|docker-compose|kubernetes|helm|terraform|systemd",
}
TEST_PATTERNS = [r"(^|/)tests?/", r"_test\.(py|go|dart)$", r"(^|/)test_[^/]+\.py$", r"\.(spec|test)\.[jt]sx?$"]
STACK_FILES = ["pyproject.toml", "requirements.txt", "package.json", "pubspec.yaml", "go.mod", "Cargo.toml",
               "Dockerfile", "docker-compose.yml", "docker-compose.prod.yml", "Makefile"]
TRIGGER_NAMES = (r"(push|pull_request|pull_request_target|workflow_dispatch|schedule|workflow_run|workflow_call|"
                 r"release|repository_dispatch)")
OWN_FILES = ("work/onboarding/", ".artel/")  # artel's own output is not project activity


def run(args: list[str], cwd: Path, timeout: int = 60) -> str:
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"{args[0]}: {e}") from e
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return r.stdout


def soft(fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — a snapshot section must never abort the snapshot
        return {"error": str(e)[:300]}


def norm_excludes(raw: list[str]) -> list[str]:
    out = []
    for e in raw:
        e = e.strip().replace("\\", "/")
        while e.startswith("./"):
            e = e[2:]
        e = e.strip("/")
        if e:
            out.append(e)
    return out


def is_excluded(rel: str, excludes: list[str]) -> bool:
    return any(rel == e or rel.startswith(e + "/") for e in excludes)


def read_allowed(repo: Path, rel: str, excludes: list[str]) -> str | None:
    """File text unless the path or its symlink target is excluded or outside the repository."""
    p = repo / rel
    if is_excluded(rel, excludes) or not p.is_file():
        return None
    real = p.resolve()
    if repo not in real.parents or is_excluded(real.relative_to(repo).as_posix(), excludes):
        return None
    return p.read_text(encoding="utf-8", errors="ignore")


def github_slug(url: str) -> str | None:
    m = re.match(r"^(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^@/\s]+@)?github\.com/)"
                 r"([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def tracked(repo: Path, excludes: list[str]) -> list[str]:
    files = run(["git", "ls-files", "-z"], repo).split("\0")
    return [f for f in files if f and not is_excluded(f, excludes)]


def git_section(repo: Path, release: str) -> dict:
    head = run(["git", "rev-parse", "HEAD"], repo).strip()
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo).strip()
    status = [l for l in run(["git", "status", "--porcelain"], repo).splitlines()
              if l and not l[3:].strip('"').startswith(OWN_FILES)]
    wts = [l.split(" ", 1)[1] for l in run(["git", "worktree", "list", "--porcelain"], repo).splitlines()
           if l.startswith("worktree ")]
    refs = run(["git", "for-each-ref", "--format=%(refname:short)|%(committerdate:iso8601)",
                "refs/heads", "refs/remotes"], repo).splitlines()
    div = soft(lambda: run(["git", "rev-list", "--left-right", "--count", f"origin/{release}...HEAD"], repo).split())
    return {"head": head, "branch": branch, "uncommitted_count": len(status), "uncommitted": status[:60],
            "worktrees": wts, "branches": [dict(zip(("ref", "date"), r.split("|", 1))) for r in refs][:80],
            f"vs_origin_{release}": {"behind": div[0], "ahead": div[1]} if isinstance(div, list) else div}


def gh_json(args: list[str], repo: Path):
    return json.loads(run(["gh", *args], repo) or "null")


def github_section(repo: Path, release: str) -> dict:
    url = run(["git", "remote", "get-url", "origin"], repo).strip()
    slug = github_slug(url)
    if not slug:
        raise RuntimeError("origin is not a GitHub repository")
    out: dict = {"repo": slug}
    out["open_prs"] = soft(lambda: gh_json(["pr", "list", "-R", slug, "--state", "open", "--limit", "50", "--json",
                                            "number,title,baseRefName,headRefName,author,isDraft,updatedAt"], repo))
    out["recent_runs"] = soft(lambda: gh_json(["run", "list", "-R", slug, "--limit", "30", "--json",
                                               "workflowName,event,headBranch,conclusion,status,createdAt"], repo))
    out["release_branch_rules"] = soft(lambda: gh_json(["api", f"repos/{slug}/rules/branches/{release}"], repo))
    out["environments"] = soft(lambda: [
        {"name": e["name"], "protection": [p.get("type") for p in e.get("protection_rules", [])]}
        for e in (gh_json(["api", f"repos/{slug}/environments"], repo) or {}).get("environments", [])])
    out["repo_secret_names"] = soft(lambda: [s["name"] for s in gh_json(
        ["secret", "list", "-R", slug, "--json", "name"], repo)])
    out["default_branch"] = soft(lambda: gh_json(["api", f"repos/{slug}", "--jq", "{d:.default_branch}"], repo)["d"])
    return out


def workflow_triggers(text: str) -> list[str]:
    """Event names under the top-level `on:` key (block or inline form)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(?:on|\"on\"|'on'):[ \t]*(.*)$", line)
        if not m:
            continue
        inline = m.group(1).split("#", 1)[0].strip()
        if inline:
            return sorted(set(re.findall(TRIGGER_NAMES, inline)))
        child_indent = None
        found = set()
        for nxt in lines[i + 1:]:
            if not nxt.strip() or nxt.lstrip().startswith("#"):
                continue
            indent = len(nxt) - len(nxt.lstrip())
            if indent == 0:
                break
            if child_indent is None:
                child_indent = indent
            if indent == child_indent:
                km = re.match(TRIGGER_NAMES + r"\s*:", nxt.lstrip())
                if km:
                    found.add(km.group(1))
        return sorted(found)
    return []


def workflows_section(repo: Path, files: list[str], excludes: list[str]) -> list[dict]:
    res = []
    for f in sorted(x for x in files if re.match(r"^\.github/workflows/[^/]+\.ya?ml$", x)):
        t = read_allowed(repo, f, excludes)
        if t is None:
            continue
        res.append({
            "file": f.rsplit("/", 1)[1],
            "triggers": workflow_triggers(t),
            "environments": sorted(set(re.findall(r"^\s+environment:\s*(.+)$", t, re.M))),
            "secret_refs": sorted(set(re.findall(r"secrets\.([A-Z0-9_]+)", t))),
            "self_hosted": "self-hosted" in t,
            "mentions_triggering_actor": bool(re.search(r"triggering_actor", t)),
        })
    return res


def frontmatter_model(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    m = re.search(r"(?m)^model:\s*(\S+)", text.split("---", 2)[1])
    return m.group(1) if m else None


def agent_config_section(repo: Path, files: list[str], excludes: list[str]) -> dict:
    out: dict = {}
    for name in ("settings.json", "settings.local.json"):
        rel = f".claude/{name}"
        text = read_allowed(repo, rel, excludes)
        if text is not None:
            d = soft(lambda text=text: json.loads(text))
            if not isinstance(d, dict) or "error" in d:
                out[rel] = d
                continue
            perm = d.get("permissions", {}) or {}
            allow = perm.get("allow", [])
            risky = sum(bool(re.search(r"(^Bash\(|&& |; )(ssh|scp|rsync|sshpass) |git push \S+ (\S+:)?main\b|"
                                       r"environment=prod", a)) for a in allow)
            out[rel] = {"allow": len(allow), "deny": len(perm.get("deny", [])), "risky_allow_count": risky,
                        "env_keys": sorted((d.get("env") or {}).keys()),
                        "hooks": {ev: len(v) for ev, v in (d.get("hooks") or {}).items()}}
    out["codex_rules"] = sorted(f for f in files if f.startswith(".codex/rules/")) or \
        sorted(p.name for p in (repo / ".codex" / "rules").glob("*.rules"))
    out["codex_project_config"] = (repo / ".codex" / "config.toml").exists()
    out["instruction_files"] = {n: (repo / n).stat().st_size for n in ("CLAUDE.md", "AGENTS.md")
                                if n in files or (repo / n).exists()}
    out["project_skills"] = sorted({f.split("/")[2] for f in files if f.startswith(".claude/skills/")})
    out["project_agents"] = {f.rsplit("/", 1)[1]: frontmatter_model(read_allowed(repo, f, excludes) or "")
                             for f in files if re.match(r"^\.claude/agents/[^/]+\.md$", f)}
    out["git_hooks_path"] = soft(lambda: run(["git", "config", "--get", "core.hooksPath"], repo).strip())
    out["artel_project"] = (repo / ".artel" / "project.toml").exists()
    return out


def docs_section(repo: Path, files: list[str]) -> dict:
    md = [(f, (repo / f).stat().st_size) for f in files if f.endswith(".md") and (repo / f).exists()]
    status_like = [f for f in files if re.search(r"(^|/)(status|STATE|HANDOFF|backlog|decisions|Бэклог)[^/]*\.md$",
                                                 f, re.I) and not f.startswith(OWN_FILES)]
    last = {}
    for f in status_like[:20]:
        last[f] = soft(lambda f=f: run(["git", "log", "-1", "--format=%cI %h %s", "--", f], repo).strip())
    return {"largest_md": sorted(md, key=lambda x: -x[1])[:15], "status_files_last_commit": last,
            "md_total_bytes": sum(s for _, s in md), "md_count": len(md)}


def tests_section(files: list[str]) -> dict:
    hits = [f for f in files if any(re.search(p, f) for p in TEST_PATTERNS)]
    by_top: dict[str, int] = {}
    for f in hits:
        top = f.split("/", 1)[0]
        by_top[top] = by_top.get(top, 0) + 1
    return {"test_files": len(hits), "by_top_dir": by_top}


def signals_section(repo: Path, files: list[str], excludes: list[str]) -> dict:
    stack = [s for s in STACK_FILES if s in files or any(f.endswith("/" + s) for f in files)]
    code = [f for f in files if re.search(r"\.(py|ts|tsx|js|dart|go|sql|ya?ml|toml)$", f)][:6000]
    counts = {k: 0 for k in RISK_PATTERNS}
    for f in code:
        try:
            t = (read_allowed(repo, f, excludes) or "")[:200_000].lower()
        except OSError:
            continue
        for k, pat in RISK_PATTERNS.items():
            if re.search(pat, t):
                counts[k] += 1
    proposed = "critical" if counts["money"] or counts["personal_data"] else (
        "standard" if counts["auth"] or counts["migrations"] else "light")
    return {"stack_files": stack, "risk_signal_files": counts, "proposed_profile": proposed,
            "note": "proposal from code/config signals only; the owner confirms at the onboarding gate"}


def check_out_path(out: Path, repo: Path) -> None:
    out = out.resolve()
    allowed = (repo / "work" / "onboarding").resolve()
    if (out == repo or repo in out.parents) and allowed not in out.parents:
        raise SystemExit(f"--out must be outside the repository or under work/onboarding/: {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--release", default=None)
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    repo = Path(a.repo).resolve()
    if a.out:
        check_out_path(Path(a.out) if Path(a.out).is_absolute() else Path.cwd() / a.out, repo)
    cfg = repo / ".artel" / "project.toml"
    pcfg = tomllib.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
    release = a.release or pcfg.get("release_branch", "main")
    excludes = sorted(set(norm_excludes(a.exclude + pcfg.get("discovery_exclusions", []))))
    files = tracked(repo, excludes)
    snap = {
        "artel_snapshot": "0.2",
        "as_of": {"utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                  "commit": soft(lambda: run(["git", "rev-parse", "HEAD"], repo).strip())},
        "repo": str(repo), "release_branch": release, "excluded": excludes, "tracked_files": len(files),
        "git": soft(lambda: git_section(repo, release)),
        "github": soft(lambda: github_section(repo, release)),
        "workflows": soft(lambda: workflows_section(repo, files, excludes)),
        "agent_config": soft(lambda: agent_config_section(repo, files, excludes)),
        "docs": soft(lambda: docs_section(repo, files)),
        "tests": soft(lambda: tests_section(files)),
        "signals": soft(lambda: signals_section(repo, files, excludes)),
    }
    text = json.dumps(snap, ensure_ascii=False, indent=2)
    if a.out:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"snapshot written: {out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
