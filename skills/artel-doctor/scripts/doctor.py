#!/usr/bin/env python3
"""artel doctor — conformance checks for one project (contract: `artel doctor` checks 1–10).

Read-only. Live reads of the VCS host and the working copy; it never pushes, merges, dispatches or
deploys, and never reads paths in the exclusion list (declared exclusions plus agent Read-deny rules).
A verdict states only what the data shows: anything it could not read or cannot judge is MANUAL, never
PASS. Checks 1–2 verify the configuration that makes the agent's push/merge fail; the live probe is a
manual procedure (a probe against broken protection would itself change production).

Usage: doctor.py [--repo .] [--json]
Exit: 0 = no FAIL, 1 = at least one FAIL (WARN and MANUAL do not fail).
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

SECRET_PATTERNS = {
    # split literal: skill sync tools scan sources for this header and would reject the file
    "private key": (r"-----BEGIN (RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE"
                    r" KEY-----"),
    "GitHub token": r"\b(ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}",
    "AWS-style key": r"\bAKIA[0-9A-Z]{16}\b",
    "Yandex IAM/API key": r"\bAQVN[A-Za-z0-9_\-]{30,}",
    "OpenAI/Anthropic key": r"\bsk-(ant-)?[A-Za-z0-9_\-]{30,}",
}
SECRET_NAME = re.compile(r"TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|_KEY$|_KEY_|^KEY_|API_?KEY", re.I)
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".dart_tool", "build", "dist", "Pods",
             ".gradle", ".next", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "coverage"}
MAX_SCAN = 2_000_000
REVIEWERS = ["code-reviewer", "test-reviewer", "security-auditor", "infrastructure-reviewer", "codex-reviewer"]


class Report:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, check: str, status: str, detail: str):
        self.rows.append({"check": check, "status": status, "detail": detail})


def run(args, cwd, env=None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    except OSError as e:
        return subprocess.CompletedProcess(args, 127, "", f"{args[0]}: {e}")


def gh_json(args, cwd, env=None):
    r = run(["gh", *args], cwd, env)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:200] or f"gh exit {r.returncode}")
    return json.loads(r.stdout or "null")


def load_toml(p: Path) -> dict:
    return tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def github_slug(url: str) -> str | None:
    m = re.match(r"^(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^@/\s]+@)?github\.com/)"
                 r"([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def norm_path(e: str) -> str:
    e = e.strip().replace("\\", "/")
    while e.startswith("./"):
        e = e[2:]
    return e.strip("/")


def excluded(rel: str, excl: list[str]) -> bool:
    return any(rel == e or rel.startswith(e + "/") for e in excl)


def readable(repo: Path, rel: str, excl: list[str]) -> str | None:
    """Text of a repo file unless it is excluded or resolves outside the repo/into an exclusion."""
    p = repo / rel
    if excluded(rel, excl) or not p.is_file():
        return None
    real = p.resolve()
    if repo not in real.parents:
        return None
    if excluded(real.relative_to(repo).as_posix(), excl):
        return None
    return p.read_text(encoding="utf-8", errors="ignore")


def exclusions(repo: Path, pc: dict) -> list[str]:
    """Declared exclusions plus every path an agent Read-deny rule protects — never read."""
    out = {norm_path(e) for e in pc.get("discovery_exclusions", []) if norm_path(e)}
    text = readable(repo, ".claude/settings.local.json", sorted(out))
    try:
        deny = (json.loads(text).get("permissions") or {}).get("deny", []) if text else []
    except json.JSONDecodeError:
        deny = []
    for x in deny:
        m = re.match(r"Read\(\./(.+?)(/\*\*)?\)$", x)
        if m:
            out.add(norm_path(m.group(1)))
    return sorted(out)


def ruleset_targets(full: dict, rel: str, default_branch: str | None) -> tuple[bool, bool]:
    """(applies to the release branch, decided exactly). Wildcard patterns are not decided exactly."""
    cond = full.get("conditions", {}).get("ref_name", {})
    inc, exc = cond.get("include", []), cond.get("exclude", [])
    ref = f"refs/heads/{rel}"
    exact = not any(re.search(r"[*?\[]", p) for p in inc + exc)

    def hit(pats):
        return any(p == ref or p == "~ALL" or (p == "~DEFAULT_BRANCH" and default_branch == rel)
                   or fnmatch.fnmatchcase(ref, p) for p in pats)
    return hit(inc) and not hit(exc), exact


def check_ask_rules(rep: Report, repo: Path, excl: list[str]):
    """The owner's yes in chat is enforced only if merges stop in every harness (core §10 layer 2)."""
    need = ["Bash(gh pr merge:*)", "Bash(gh run rerun:*)"]
    text = readable(repo, ".claude/settings.local.json", excl)
    if text is None:
        rep.add("1-2 ask rules (Claude)", "MANUAL", "settings.local.json missing or excluded — check ask rules by hand")
    else:
        try:
            perm = json.loads(text).get("permissions") or {}
        except json.JSONDecodeError:
            perm = {}
        missing = [x for x in need if x not in perm.get("ask", []) and x not in perm.get("deny", [])]
        rep.add("1-2 ask rules (Claude)", "FAIL" if missing else "PASS",
                f"missing ask rules: {missing} — the agent could merge or re-run without the owner's yes"
                if missing else "merge and re-run stop for the owner's yes (ask or deny)")
    rules = readable(repo, ".codex/rules/artel.rules", excl)
    if rules is None:
        rep.add("1-2 ask rules (Codex)", "WARN", "no .codex/rules/artel.rules — Codex sessions are not fenced here")
    else:
        miss = [p for p in ('"gh", "pr", "merge"', '"gh", "run", "rerun"')
                if not re.search(rf'pattern = \[{p}\], decision = "(prompt|forbidden)"', rules)]
        rep.add("1-2 ask rules (Codex)", "FAIL" if miss else "PASS",
                f"missing prompt rules for {miss}" if miss else "merge and re-run stop for the owner's yes")


def check_vcs(rep: Report, repo: Path, slug: str, pc: dict, uc: dict, excl: list[str]):
    rel = pc.get("release_branch", "main")
    agent = uc.get("owner", {}).get("agent_github_login")
    if agent:
        try:
            p = gh_json(["api", f"repos/{slug}/collaborators/{agent}/permission"], repo)
            role = p.get("role_name") or p.get("permission")
            rep.add("1-2 agent role", "PASS" if role in ("write", "triage", "read") else "FAIL",
                    f"{agent} has '{role}' on {slug} (must not be admin/maintain)")
        except RuntimeError as e:
            rep.add("1-2 agent role", "MANUAL", f"cannot read {agent}'s role (not a collaborator, or no owner gh "
                    f"login): {e}")
    else:
        rep.add("1-2 agent role", "WARN", "no agent account in ~/.artel/artel.toml — agents act as the owner")
    try:
        default_branch = gh_json(["api", f"repos/{slug}", "--jq", "{d:.default_branch}"], repo)["d"]
        found, inexact = None, []
        for r in gh_json(["api", f"repos/{slug}/rulesets"], repo) or []:
            full = gh_json(["api", f"repos/{slug}/rulesets/{r['id']}"], repo)
            applies, exact = ruleset_targets(full, rel, default_branch)
            if full.get("enforcement") == "active" and not exact:
                inexact.append(full.get("name"))
            if full.get("enforcement") == "active" and applies and exact:
                found = full
                break
        if not found and inexact:
            rep.add("1-2 release ruleset", "MANUAL", f"rulesets with wildcard targeting {inexact} — confirm by hand "
                    f"that one applies to {rel}")
        elif not found:
            rep.add("1-2 release ruleset", "FAIL", f"no active ruleset applies to {rel}")
        else:
            types = {x["type"]: x.get("parameters", {}) for x in found.get("rules", [])}
            pr = types.get("pull_request")
            problems = []
            if not pr:
                problems.append("no pull-request rule (direct merges possible)")
            for t in ("non_fast_forward", "deletion"):
                if t not in types:
                    problems.append(f"missing {t}")
            for b in found.get("bypass_actors", []):
                if not (b.get("actor_type") == "RepositoryRole" and b.get("actor_id") == 5
                        and b.get("bypass_mode") == "pull_request"):
                    problems.append(f"bypass actor {b} (only the admin role in pull_request mode is allowed)")
            server = [c["context"] for c in types.get("required_status_checks", {}).get("required_status_checks", [])]
            missing = [c for c in pc.get("required_checks", []) if c not in server]
            if missing:
                problems.append(f"required checks from .artel/project.toml not enforced: {missing}")
            rep.add("1-2 release ruleset", "FAIL" if problems else "PASS",
                    f"'{found['name']}' (id {found['id']}); required checks: {server or 'none'}"
                    + (f"; problems: {'; '.join(problems)}" if problems else ""))
            if not server:
                rep.add("1-2 required checks", "WARN", "no required status checks on the release branch")
    except RuntimeError as e:
        rep.add("1-2 release ruleset", "MANUAL", f"cannot read rulesets (owner gh login needed): {e}")
    rep.add("1-2 live probe", "MANUAL", "as the agent, a direct push to the release branch must be refused (GH013) "
            "and `gh pr merge --help` blocked as needing the owner's yes in both harnesses — procedure in "
            "references/github.md; repeat after any ruleset, ask-rule, role or harness change")
    cfgdir = uc.get("owner", {}).get("agent_gh_config_dir")
    if agent and cfgdir:
        env = {**os.environ, "GH_CONFIG_DIR": str(Path(cfgdir).expanduser())}
        env.pop("GH_TOKEN", None)
        env.pop("GITHUB_TOKEN", None)
        r = run(["gh", "api", "-i", "user"], repo, env)
        login = re.search(r'"login":\s*"([^"]+)"', r.stdout)
        scopes = re.search(r"(?im)^x-oauth-scopes:\s*(.*)$", r.stdout)
        if r.returncode != 0 or not login:
            rep.add("agent token", "FAIL", f"agent gh login unusable ({(r.stderr or '').strip()[:120]})")
        elif not scopes:
            rep.add("agent token", "MANUAL", f"login {login.group(1)}; scopes not reported (fine-grained token?) — "
                    "confirm it cannot write workflow files")
        else:
            sc = [s.strip() for s in scopes.group(1).split(",") if s.strip()]
            bad = [s for s in sc if s in ("workflow", "admin:org", "delete_repo", "admin:repo_hook")]
            # owner-accepted scopes (user config accepted_risks = ["agent-token-scope:<scope>"]) are reported, not failed
            accepted = {r.split(":", 1)[1] for r in uc.get("accepted_risks", []) if r.startswith("agent-token-scope:")}
            open_bad = [s for s in bad if s not in accepted]
            status = "FAIL" if open_bad or login.group(1) != agent else ("WARN" if bad else "PASS")
            rep.add("agent token", status, f"login {login.group(1)}; scopes {sc}"
                    + (f"; forbidden: {open_bad}" if open_bad else "")
                    + (f"; accepted by the owner: {sorted(set(bad) & accepted)}" if set(bad) & accepted else "")
                    + (" — with `workflow` the agent can push workflow changes; see the ruleset and ask-rule rows of this "
                       "report for what still stops it" if "workflow" in (set(bad) & accepted) else ""))
    env_name = pc.get("prod_environment", "prod")
    try:
        e = gh_json(["api", f"repos/{slug}/environments/{env_name}"], repo)
        pol = e.get("deployment_branch_policy") or {}
        ok = False
        if pol.get("custom_branch_policies"):
            pols = gh_json(["api", f"repos/{slug}/environments/{env_name}/deployment-branch-policies"],
                           repo).get("branch_policies", [])
            got = [(b.get("name"), b.get("type", "branch")) for b in pols]
            ok = got == [(rel, "branch")]
            detail = f"custom policies {got}"
        elif pol.get("protected_branches"):
            detail = "any protected branch may deploy"
        else:
            detail = "no branch policy"
        rep.add("3 prod environment", "PASS" if ok else "FAIL",
                f"environment '{env_name}': {detail}" + ("" if ok else f" (must be exactly branch {rel})"))
    except RuntimeError as e:
        rep.add("3 prod environment", "FAIL" if "Not Found" in str(e) else "MANUAL",
                f"environment '{env_name}': {e}")
    try:
        names = {s["name"] for s in gh_json(["secret", "list", "-R", slug, "--json", "name"], repo)}
        risky = sorted(s for s in names if re.search(r"SSH|DEPLOY|PROD|VPS|SERVER|KUBE|S3|BACKUP", s))
        rep.add("3 repo-level prod secrets", "WARN" if risky else ("PASS" if not names else "MANUAL"),
                (f"{len(risky)} production-looking secrets at repository level (any branch's workflow can read "
                 f"them; move to environment '{env_name}'): {', '.join(risky)}") if risky else
                ("no repository-level secrets" if not names else f"{len(names)} repository secrets, none with a "
                 "production-looking name — confirm none is a production secret"))
    except RuntimeError as e:
        rep.add("3 repo-level prod secrets", "MANUAL", f"cannot list repository secrets: {e}")
    allowed = set(pc.get("prod_operations_allowed", []))
    for wf in sorted((repo / ".github" / "workflows").glob("*.y*ml")):
        t = readable(repo, f".github/workflows/{wf.name}", excl)
        if t is None:
            continue
        if "workflow_dispatch" in t and re.search(rf"environment:\s*['\"]?({re.escape(env_name)}\b|\$\{{\{{)", t):
            guard = [i + 1 for i, l in enumerate(t.splitlines())
                     if re.match(r"\s*if:.*github\.triggering_actor\s*[!=]=", l)]
            note = " · listed in prod_operations_allowed" if wf.name in allowed else ""
            rep.add(f"3 dispatch guard {wf.name}", "MANUAL" if guard else "WARN",
                    (f"if-condition on github.triggering_actor at line(s) {guard} — confirm it gates the deploy job"
                     if guard else "manual dispatch can reach production without an owner-actor guard") + note)


def check_rollback(rep: Report, repo: Path, excl: list[str]):
    cands = [f".github/workflows/{p.name}" for p in (repo / ".github" / "workflows").glob("*.y*ml")]
    cands += [p.relative_to(repo).as_posix() for d in ("scripts", "deploy") for p in (repo / d).rglob("*")
              if p.is_file()]
    hits = [c for c in cands if (t := readable(repo, c, excl)) and re.search(r"rollback", t, re.I)]
    rep.add("4 rollback mechanism", "MANUAL" if hits else "WARN",
            (f"candidates: {', '.join(hits[:6])} — verify it takes no ref and resolves only the newest verified "
             "release tag (dry run or stage)") if hits else "no rollback mechanism found — G6: incidents need the owner")


def is_venv(d: Path) -> bool:
    try:
        return (d / "pyvenv.cfg").exists()
    except OSError:
        return False  # unreadable directory: os.walk reports it through onerror


def check_secrets(rep: Report, repo: Path, excl: list[str]):
    scanned, skipped, unread, hits, env_files = 0, 0, 0, [], []
    walk_errors: list[str] = []
    for root, dirs, files in os.walk(repo, onerror=lambda e: walk_errors.append(str(e.filename))):
        rel_root = Path(root).relative_to(repo).as_posix()
        rel_root = "" if rel_root == "." else rel_root
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != "site-packages"
                   and not is_venv(Path(root) / d)  # virtualenvs under any name
                   and not excluded(f"{rel_root}/{d}".lstrip("/"), excl)]
        for f in files:
            rel = f"{rel_root}/{f}".lstrip("/")
            if excluded(rel, excl):
                continue
            p = Path(root) / f
            if p.is_symlink():
                skipped += 1
                continue
            if re.search(r"(^|/)\.env(\.|$)", rel) and not rel.endswith((".example", ".sample", ".template")):
                env_files.append(rel)
            try:
                if p.stat().st_size > MAX_SCAN:
                    skipped += 1
                    continue
                t = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                unread += 1
                continue
            scanned += 1
            for name, pat in SECRET_PATTERNS.items():
                if re.search(pat, t):
                    hits.append((rel, name))
    tracked_env = set(run(["git", "ls-files", "--", *env_files], repo).stdout.split()) if env_files else set()
    local_env = set(env_files) - tracked_env
    in_env = [f"{r}: {n}" for r, n in hits if r in local_env]
    hits = [f"{r}: {n}" for r, n in hits if r not in local_env]
    unread += len(walk_errors)
    detail = (f"{scanned} files scanned, {skipped} skipped (size > 2 MB or symlink), {unread} unreadable "
              f"(incl. {len(walk_errors)} directories); "
              f"heavy dirs not walked: {', '.join(sorted(SKIP_DIRS))}; excluded: {excl or 'none'}")
    if hits or tracked_env:
        rep.add("5 secrets in working copy", "FAIL", "; ".join(hits[:10] + [f"{x}: env file tracked by git"
                                                                       for x in tracked_env])
                + (f" … +{len(hits) - 10}" if len(hits) > 10 else "") + f" · {detail}")
    else:
        rep.add("5 secrets in working copy", "PASS" if not (skipped or unread) else "WARN",
                f"no known secret pattern outside local env files · {detail}")
    if local_env:
        rep.add("5 env files", "WARN" if in_env else "MANUAL",
                (f"key-shaped values in untracked env files the agent can read: {in_env[:8]} — confirm they are "
                 "development keys (production keys live only in CI and on servers); otherwise remove and rotate")
                if in_env else f"agent-readable env files {sorted(local_env)[:8]} — confirm development values only")
    rep.add("5 personal data", "MANUAL", "personal data in agent-readable paths is not detected automatically — "
            "confirm none outside the exclusions (exports, dumps, recordings, chat logs)")
    if excluded(".claude/settings.local.json", excl):
        rep.add("5 agent environment", "MANUAL", ".claude/settings.local.json is excluded — check its env by hand")
        d = {}
    else:
        text = readable(repo, ".claude/settings.local.json", excl)
        try:
            d = json.loads(text) if text else {}
        except json.JSONDecodeError as e:
            rep.add("5 agent environment", "FAIL", f"settings.local.json unreadable: {e.msg}")
            return
    envk = sorted(k for k in (d.get("env") or {}) if SECRET_NAME.search(k))
    harness = re.compile(r"^(CLAUDE_CODE_|ORCA_|GIT_CONFIG_KEY_\d+$|GIT_CONFIG_VALUE_\d+$)")
    proc = sorted(k for k in os.environ if SECRET_NAME.search(k) and not harness.match(k))
    if not excluded(".claude/settings.local.json", excl):
        rep.add("5 agent environment", "FAIL" if envk else "PASS",
                f"settings env: {'secret-like keys ' + str(envk) if envk else 'no secret-like keys'}")
    rep.add("5 process environment", "WARN" if proc else "PASS",
            (f"this process has secret-like variables {proc} — if doctor runs in an agent session, the agent has "
             "them too" if proc else "no secret-like variables in this process") +
            " (run doctor from an agent session to check the agent's own environment)")


def block_of(text: str) -> tuple[str | None, str]:
    b, e = text.count("<!-- artel:begin"), text.count("<!-- artel:end -->")
    if b == 0 and e == 0:
        return None, "no artel block"
    if b != 1 or e != 1 or text.index("<!-- artel:begin") > text.index("<!-- artel:end -->"):
        return None, f"malformed artel markers ({b} begin, {e} end)"
    return text[text.index("<!-- artel:begin"):text.index("<!-- artel:end -->")], "ok"


def check_harness(rep: Report, repo: Path, uc: dict, excl: list[str]):
    cm, am = repo / "CLAUDE.md", repo / "AGENTS.md"
    if excluded("CLAUDE.md", excl) or excluded("AGENTS.md", excl):
        rep.add("6 instruction files", "MANUAL", "an instruction file is excluded — compare the artel blocks by hand")
    elif not cm.exists():
        rep.add("6 instruction files", "FAIL", "no CLAUDE.md")
    else:
        c, why_c = block_of(cm.read_text(encoding="utf-8"))
        if c is None:
            rep.add("6 instruction files", "FAIL", f"CLAUDE.md: {why_c} — run artel-init --adopt")
        elif not am.exists():
            rep.add("6 instruction files", "FAIL", "AGENTS.md missing — Codex sessions get no project rules")
        else:
            a, why_a = block_of(am.read_text(encoding="utf-8"))
            same = a is not None and a == c
            rep.add("6 instruction files", "PASS" if same else "FAIL",
                    "artel block identical in CLAUDE.md and AGENTS.md" if same else
                    f"AGENTS.md: {why_a if a is None else 'block differs'} — regenerate it (never edit by hand)")
    agents = Path.home() / ".claude" / "agents"
    if not agents.is_dir():
        rep.add("7 reviewer pinning", "MANUAL", f"{agents} not found — check reviewer model pinning in your harness")
    else:
        unpinned = []
        for r in REVIEWERS:
            p = agents / f"{r}.md"
            if not p.exists():
                unpinned.append(f"{r} (missing)")
                continue
            text = p.read_text(encoding="utf-8")
            fm = text.split("---", 2)[1] if text.startswith("---") else ""
            m = re.search(r"(?m)^model:\s*(\S+)", fm)
            wrapper_pin = re.search(r"codex exec[^\n]*\s-m\s+\S+", text)
            if (not m or m.group(1) in ("inherit", "")) and not wrapper_pin:
                unpinned.append(r)
        rep.add("7 reviewer pinning", "FAIL" if unpinned else "PASS",
                f"unpinned: {unpinned}" if unpinned else "every reviewer agent pins a model")
    fams = sorted({p.get("family") for p in uc.get("providers", []) if p.get("family")})
    rep.add("7 review independence", "MANUAL" if len(fams) >= 2 else "WARN",
            f"families available: {fams} — that each review uses a family other than the author's is checked per "
            "wave in the review log" if len(fams) >= 2 else "single family — G1: reviews marked 'independence "
            "weakened'")
    rep.add("8-10 orchestrator", "MANUAL", "'Needs You' for gate questions, phone push, an orchestrator-launched "
            "harness reads the instruction file — prove once per orchestrator/harness version")


def check_matrix(rep: Report, uc: dict):
    """Check 11: every role can be picked with any one family unavailable; review roles for any author."""
    import contextlib
    import importlib.util
    import io
    mpath = Path(__file__).resolve().parent.parent.parent / "artel" / "scripts" / "matrix.py"
    if not mpath.exists() or not uc:
        rep.add("11 matrix failover", "MANUAL", "matrix.py or ~/.artel/artel.toml not found — check role chains by hand")
        return
    spec = importlib.util.spec_from_file_location("artel_matrix", mpath)
    matrix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(matrix)
    roles = tomllib.loads(matrix.ROLES.read_text(encoding="utf-8"))["roles"]
    families = sorted({p.get("family") for p in uc.get("providers", []) if p.get("family")})
    models = [m for p in uc.get("providers", []) for m in (p.get("models") or {}).values()]
    if len(families) < 2:
        rep.add("11 matrix failover", "WARN", f"single family {families} — G1: no failover to another family")
        return
    gaps = []
    for role, spec_ in roles.items():
        for tier in ("t01", "t23"):
            for fam in families:
                for author in (models if spec_.get("review") else [None]):
                    argv = ["--role", role, "--tier", tier, "--no-limits", "--exclude-family", fam, "--json"]
                    if author:
                        argv += ["--author", author]
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        code = matrix.pick(argv)
                    if code != 0:
                        gaps.append(f"{role} {tier} without {fam}" + (f" (author {author})" if author else ""))
    by_role: dict[str, set[str]] = {}
    for g in gaps:
        role, _, rest = g.partition(" ")
        by_role.setdefault(role, set()).add(rest)
    listing = "; ".join(f"{r}: {', '.join(sorted(c))}" for r, c in sorted(by_role.items()))
    rep.add("11 matrix failover", "WARN" if gaps else "PASS",
            (f"{len(gaps)} cases in {len(by_role)} roles with no candidate — the role waits for that family unless a "
             f"candidate is added to its chain in ~/.artel/artel.toml [roles]: {listing}") if gaps else
            f"every role has a candidate with any one of {families} unavailable; review roles for every author model")


def main() -> int:
    repo = Path(sys.argv[sys.argv.index("--repo") + 1] if "--repo" in sys.argv[:-1] else ".").resolve()
    pc = load_toml(repo / ".artel" / "project.toml")
    uc = load_toml(Path(os.environ.get("ARTEL_CONFIG", Path.home() / ".artel" / "artel.toml")))
    excl = exclusions(repo, pc)
    rep = Report()
    if not pc:
        rep.add("0 artel project", "WARN", "no .artel/project.toml — defaults used (release branch 'main', env 'prod')")
    slug = github_slug(run(["git", "remote", "get-url", "origin"], repo).stdout)
    if not slug:
        rep.add("1-3 VCS host", "MANUAL", "origin is not GitHub — check the contract items on your host by hand")
    elif run(["gh", "--version"], repo).returncode != 0:
        rep.add("1-3 VCS host", "MANUAL", "gh CLI not available — host checks skipped")
    else:
        check_vcs(rep, repo, slug, pc, uc, excl)
    check_ask_rules(rep, repo, excl)
    check_rollback(rep, repo, excl)
    check_secrets(rep, repo, excl)
    check_harness(rep, repo, uc, excl)
    check_matrix(rep, uc)
    if "--json" in sys.argv:
        print(json.dumps(rep.rows, ensure_ascii=False, indent=2))
    else:
        print(f"artel doctor · {repo}")
        for r in rep.rows:
            print(f"  {r['status']:6} {r['check']:30} {r['detail']}")
        n = {s: sum(r["status"] == s for r in rep.rows) for s in ("PASS", "WARN", "FAIL", "MANUAL")}
        print("  " + " · ".join(f"{k} {v}" for k, v in n.items()))
    return 1 if any(r["status"] == "FAIL" for r in rep.rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
