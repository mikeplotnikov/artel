#!/usr/bin/env python3
"""artel-init: put a project on artel, or contain agent risks before onboarding (core §6.6, §10).

Modes (combine as needed; default is a dry run that prints the plan — add --apply to write):
  --contain    agent fences: Claude deny rules + Codex prefix rules (release-branch pushes, remote
               shells, production workflow dispatch/re-run except allowed operations, excluded paths).
               Existing rules are kept. Local files only (listed in the repo's info/exclude).
  --identity   agent sessions act as the agent account: git credentials via `gh auth git-credential`
               (owner by default, agent when GH_CONFIG_DIR is set), env for Claude and Codex sessions.
  --adopt      write .artel/project.toml (existing keys kept), the managed artel block in CLAUDE.md,
               then --contain and --identity. Only the marked block of CLAUDE.md is replaced.
  --protect    release-branch ruleset on GitHub (PR, required checks, 0 approvals — the owner approves in
               chat through harness ask rules; owner bypass via PR
               only). Never touches an existing ruleset. Needs the owner's own gh login (admin).

All checks run before anything is written; writes happen together at the end. Refuses to touch
.claude/settings.local.json when it holds secret-like env keys (names are printed, never values), and
never prints that file's content — only the rules and keys it adds.

Usage: init.py [--repo .] [--adopt|--contain|--identity|--protect ...] [--profile critical]
               [--release main] [--dev dev] [--allow-op ops.yml] [--exclude clients/]
               [--check backend] [--data-class personal-data] [--apply] [--diff]
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

BEGIN, END = "<!-- artel:begin", "<!-- artel:end -->"
RULES_BEGIN, RULES_END = "# artel:begin (managed by artel-init)", "# artel:end"
SHELLS = ["ssh", "scp", "rsync", "sshpass", "ssh-copy-id"]
SECRET_KEY = re.compile(r"TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|_KEY$|_KEY_|^KEY_|API_?KEY", re.I)
MANAGED_KEYS = ("profile", "data_class", "release_branch", "dev_branch", "required_checks",
                "prod_operations_allowed", "discovery_exclusions")


def sh(args: list[str], cwd: Path, check: bool = True) -> str:
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    except OSError as e:
        raise SystemExit(f"cannot run {args[0]}: {e}") from e
    if check and r.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(args)}\n{r.stderr.strip()}")
    return r.stdout.strip()


def user_cfg() -> dict:
    p = Path(os.environ.get("ARTEL_CONFIG", Path.home() / ".artel" / "artel.toml"))
    return tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {toml_value(x)}" for k, x in v.items()) + " }"
    return json.dumps(str(v), ensure_ascii=False)


def q(s: str) -> str:
    """A string literal valid in Starlark (Codex rules) and TOML basic strings."""
    return json.dumps(s, ensure_ascii=True)


def github_slug(url: str) -> str | None:
    m = re.match(r"^(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^@/\s]+@)?github\.com/)"
                 r"([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def norm_path(e: str) -> str:
    e = e.strip().replace("\\", "/")
    while e.startswith("./"):
        e = e[2:]
    return e.strip("/")


class Plan:
    """Collects writes and commands; nothing touches disk until commit()."""

    def __init__(self, apply: bool, diff: bool):
        self.apply, self.diff = apply, diff
        self.steps: list[str] = []
        self.pending: dict[Path, str] = {}
        self.cmds: list[list[str]] = []

    def read(self, path: Path) -> str | None:
        if path in self.pending:
            return self.pending[path]
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write(self, path: Path, content: str, why: str, summary: list[str] | None = None):
        old = self.read(path)
        if old == content:
            self.steps.append(f"unchanged  {path}  ({why})")
            return
        on_disk = path.read_text(encoding="utf-8") if path.exists() else None
        self.steps.append(f"{'create' if on_disk is None else 'update'}     {path}  ({why})")
        if self.diff:
            if summary is not None:  # sensitive file: show only what artel adds
                self.steps.extend("    + " + s for s in summary)
            else:
                self.steps.extend("    " + l for l in difflib.unified_diff(
                    (old or "").splitlines(), content.splitlines(), "current", "artel", lineterm="", n=1))
        self.pending[path] = content

    def cmd(self, args: list[str], why: str):
        self.steps.append(f"run        {' '.join(args)}  ({why})")
        self.cmds.append(args)

    def commit(self, repo: Path):
        if not self.apply:
            return
        for path, content in self.pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        for args in self.cmds:
            sh(args, repo)


def project_settings(repo: Path, a) -> dict:
    p = repo / ".artel" / "project.toml"
    cur = tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    flags = {"profile": a.profile, "data_class": a.data_class, "release_branch": a.release, "dev_branch": a.dev,
             "required_checks": a.check, "prod_operations_allowed": a.allow_op,
             "discovery_exclusions": [norm_path(e) + ("/" if e.rstrip().endswith("/") or (repo / norm_path(e)).is_dir()
                                                     or not Path(norm_path(e)).suffix else "") for e in a.exclude]}
    defaults = {"artel": "0.2", "profile": "standard", "data_class": "internal", "release_branch": "main",
                "dev_branch": "dev", "release_cadence": "per_feature", "stage": False, "prod_environment": "prod",
                "required_checks": [], "prod_operations_allowed": ["rollback"], "discovery_exclusions": [],
                "escalate_paths": [], "accepted_risks": []}
    s = {**defaults, **cur}
    for k, v in flags.items():
        if v not in (None, []):
            s[k] = v
    return s


def toml_key(k: str) -> str:
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else json.dumps(k, ensure_ascii=False)


def render_project_toml(s: dict) -> str:
    head = "# Artel project settings — read by the artel skills. Edit by hand or via artel-init.\n"
    text = head + "".join(f"{toml_key(k)} = {toml_value(v)}\n" for k, v in s.items())
    if tomllib.loads(text) != s:
        raise SystemExit(".artel/project.toml would not round-trip (unsupported value types) — edit it by hand")
    return text


def workflows(repo: Path) -> list[str]:
    d = repo / ".github" / "workflows"
    return sorted(p.name for p in d.glob("*.y*ml")) if d.exists() else []


def settings_json(plan: Plan, repo: Path) -> tuple[Path, dict]:
    sp = repo / ".claude" / "settings.local.json"
    raw = plan.read(sp)
    return sp, (json.loads(raw) if raw else {})


def preflight(repo: Path) -> None:
    """Refuse before any write when the agent settings file holds secret-like env keys."""
    sp = repo / ".claude" / "settings.local.json"
    if not sp.exists():
        return
    try:
        d = json.loads(sp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"{sp} is not valid JSON ({e.msg} at line {e.lineno}) — fix it first")
    bad = sorted(k for k in (d.get("env") or {}) if SECRET_KEY.search(k))
    if bad:
        raise SystemExit(f"{sp} holds secret-like env keys {bad} — a secret within agent reach (doctor check 5). "
                         "Remove and rotate them (secret-handoff), then rerun. Nothing was written.")


def contain(repo: Path, s: dict, plan: Plan, git_exclude: Path):
    rel = s["release_branch"]
    names = workflows(repo)  # any file name is safe below: rules are escaped, never interpolated raw
    ops = s["prod_operations_allowed"]
    allowed_wf = [w for w in names if w in ops or ("rollback" in ops and w.startswith("rollback"))]
    denied_wf = [w for w in names if w not in allowed_wf]
    # never: direct pushes to the release branch, remote shells, excluded paths
    deny = [f"Bash(git push origin {rel})", f"Bash(git push origin {rel}:*)", f"Bash(git push origin HEAD:{rel})",
            f"Bash(git push * {rel})", f"Bash(git push *:{rel}*)", f"Bash(git push * {rel} *)"]
    deny += [f"Bash({c}:*)" for c in SHELLS]
    # only after the owner's yes in chat (owner decision 2026-10-04): merges, production dispatch, re-runs
    ask = ["Bash(gh pr merge:*)", "Bash(gh api *merge*)", "Bash(gh run rerun:*)", "Bash(gh api *rerun*)",
           "Bash(gh api *dispatches*)"]
    if not allowed_wf:
        ask.append("Bash(gh workflow run:*)")
    else:
        ask += [f"Bash(gh workflow run {w}:*)" for w in denied_wf]
        ask += [f"Bash(gh workflow run {i}*)" for i in range(1, 10)]  # dispatch by numeric workflow id
    for raw in s["discovery_exclusions"]:
        e = norm_path(raw)
        is_dir = raw.endswith("/") or (repo / e).is_dir() or not Path(e).suffix
        deny.append(f"Read(./{e}/**)" if is_dir else f"Read(./{e})")
    sp, d = settings_json(plan, repo)
    perm = d.setdefault("permissions", {})
    added = [x for x in deny if x not in perm.get("deny", [])]
    perm["deny"] = perm.get("deny", []) + added
    added_ask = [x for x in ask if x not in perm.get("ask", [])]
    perm["ask"] = perm.get("ask", []) + added_ask
    blocking = [x for x in perm["deny"] if x in ask or x == "Bash(gh workflow run:*)"
                or any(x == f"Bash(gh workflow run {w}:*)" for w in allowed_wf)]
    if blocking:
        plan.steps.append(f"conflict   existing deny rules forbid what artel now asks the owner about: {blocking} — "
                          "kept (deny rules are never removed, deny wins over ask); delete them by hand to allow "
                          "these after the owner's yes")
    risky = re.compile(r"(^Bash\(|&& |; )(" + "|".join(SHELLS) + r") |git push \S+ (\S+:)?" + re.escape(rel) + r"\b")
    shadowed = sum(bool(risky.search(x)) for x in perm.get("allow", []))
    plan.steps.append(f"note       Claude: {len(perm['deny'])} deny rules; {shadowed} old allow rules for the same "
                      "commands stay but are overridden (deny wins over allow)")
    plan.write(sp, json.dumps(d, ensure_ascii=False, indent=2) + "\n", "Claude agent fences",
               summary=[f"deny {x}" for x in added] + [f"ask {x}" for x in added_ask])

    def rule(pattern: list[str], why: str, decision: str = "forbidden") -> str:
        return (f"prefix_rule(pattern = [{', '.join(q(p) for p in pattern)}], decision = {q(decision)}, "
                f"justification = {q(why)})")
    rules = [rule(["git", "push", "origin", f], "artel: the release branch changes only through a pull request")
             for f in (rel, f"dev:{rel}", f"HEAD:{rel}")]
    rules += [rule([c], "artel: no direct production access for agents") for c in SHELLS]
    ask_why = "artel (ask the owner): runs after the owner's yes in chat"
    rules.append(rule(["gh", "pr", "merge"], ask_why, "prompt"))
    rules.append(rule(["gh", "run", "rerun"], ask_why, "prompt"))
    rules += [rule(["gh", "api", flag, m], ask_why, "prompt")
              for flag in ("-X", "--method") for m in ("PUT", "POST", "PATCH", "DELETE")]
    if not allowed_wf:
        rules.append(rule(["gh", "workflow", "run"], ask_why, "prompt"))
    else:
        rules += [rule(["gh", "workflow", "run", w], ask_why, "prompt") for w in denied_wf]
    rp = repo / ".codex" / "rules" / "artel.rules"
    old = plan.read(rp) or ""
    if RULES_BEGIN in old and RULES_END in old:
        before, rest = old.split(RULES_BEGIN, 1)
        after = rest.split(RULES_END, 1)[1].lstrip("\n")
        kept = [before.rstrip("\n"), after.rstrip("\n")]
    elif old.startswith("# artel"):  # file written by an earlier artel version: single-line rules only
        key = lambda l: re.sub(r",\s*justification\s*=.*\)$", ")", l.strip())
        mine = {key(r) for r in rules}
        legacy = [l for l in old.splitlines() if l.strip().startswith("prefix_rule(") and key(l) not in mine]
        kept = ["", ("# kept from the previous artel file\n" + "\n".join(legacy)) if legacy else ""]
        forbids = [l for l in legacy if 'decision = "forbidden"' in l and re.search(r'"gh", "(workflow|run|pr)"', l)]
        if forbids:
            plan.steps.append(f"conflict   {len(forbids)} kept Codex rules forbid what artel now asks the owner about "
                              "(dispatch, re-run, merge) — kept; delete them by hand to allow these after the "
                              "owner's yes")
    else:  # someone else's file: keep its text verbatim, add the artel block after it
        kept = [old.rstrip("\n"), ""]
    block = "\n".join([RULES_BEGIN, "# Codex-side fence mirroring the Claude deny rules; the hard stop is on the "
                       "VCS host.", *rules, RULES_END])
    content = "\n".join(p for p in (kept[0], block, kept[1]) if p) + "\n"
    plan.write(rp, content, "Codex agent fences (rules outside the artel block are kept)")
    cur = plan.read(git_exclude) or ""
    missing = [e for e in (".codex/rules/", ".codex/config.toml") if e not in cur.splitlines()]
    if missing:
        plan.write(git_exclude, cur + ("\n" if cur and not cur.endswith("\n") else "") + "\n".join(missing) + "\n",
                   "keep local agent config out of the project's history")


def identity(repo: Path, u: dict, plan: Plan):
    o = u.get("owner", {})
    login, cfgdir = o.get("agent_github_login"), o.get("agent_gh_config_dir")
    if not (login and cfgdir):
        plan.steps.append("skip       identity: owner.agent_github_login / agent_gh_config_dir not set in "
                          "~/.artel/artel.toml (agents would act as the owner — see the github adapter)")
        return
    cfgdir = str(Path(cfgdir).expanduser())
    uid = sh(["gh", "api", f"users/{login}", "--jq", ".id"], repo)
    if not uid.isdigit():
        raise SystemExit(f"unexpected id for {login}: {uid[:40]!r}")
    email = f"{uid}+{login}@users.noreply.github.com"
    env = {"ARTEL_AGENT": "1", "GH_CONFIG_DIR": cfgdir, "GIT_AUTHOR_NAME": login, "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": login, "GIT_COMMITTER_EMAIL": email}
    sp, d = settings_json(plan, repo)
    d.setdefault("env", {}).update(env)
    plan.write(sp, json.dumps(d, ensure_ascii=False, indent=2) + "\n", "Claude sessions act as the agent account",
               summary=[f"env {k}" for k in env])
    body = ("# artel: agent sessions act as the agent account, never as the owner.\n[shell_environment_policy]\n"
            "set = { " + ", ".join(f"{k} = {q(v)}" for k, v in env.items()) + " }\n")
    cp = repo / ".codex" / "config.toml"
    old = plan.read(cp)
    cur = tomllib.loads(old) if old else {}
    pol = cur.get("shell_environment_policy", {})
    artel_owned = old is None or (old.startswith("# artel") and set(cur) == {"shell_environment_policy"}
                                  and set(pol) == {"set"} and set(pol["set"]) <= set(env))
    if old is not None and cur.get("shell_environment_policy", {}).get("set") == env:
        plan.steps.append(f"unchanged  {cp}  (Codex sessions act as the agent account)")
    elif artel_owned:
        plan.write(cp, body, "Codex sessions act as the agent account")
    else:
        plan.steps.append(f"skip       {cp} has other settings — merge this block by hand:\n{body}")
    gh = sh(["bash", "-lc", "command -v gh"], repo)
    raw = subprocess.run(["git", "config", "--local", "--get-all", "credential.helper"], cwd=repo,
                         capture_output=True, text=True).stdout
    want = ["", f"!{gh} auth git-credential"]
    if raw.splitlines() != want:
        if raw:
            plan.cmd(["git", "config", "--local", "--unset-all", "credential.helper"], "reset local helpers")
        plan.cmd(["git", "config", "--local", "--add", "credential.helper", ""], "reset inherited helpers")
        plan.cmd(["git", "config", "--local", "--add", "credential.helper", want[1]],
                 "credentials follow GH_CONFIG_DIR (owner by default, agent in agent sessions)")
    else:
        plan.steps.append("unchanged  git credential helper")


def claude_block(s: dict) -> str:
    return (f"{BEGIN} (managed by artel-init; edit .artel/project.toml instead) -->\n"
            "## Artel\n\n"
            "This project runs on artel. For a development request from the owner, load the `artel` skill\n"
            "first; it routes the work and states the plan. A session started by the artel coordinator for one\n"
            "slice or one review follows its task packet and the hard stops below — it does not load `artel`.\n"
            "Where artel differs from older workflow rules, artel wins in this project: tiered review (T0\n"
            "without cross-family review), slices inside the user-spec, rights by role (any implementer\n"
            "commits and pushes to the development branch), gate questions via the harness's own question prompt.\n\n"
            f"- Profile: **{s['profile']}** · data class: {s['data_class']} · release branch: "
            f"`{s['release_branch']}` · development branch: `{s['dev_branch']}`\n"
            f"- Production operations agents may run: {', '.join(s['prod_operations_allowed']) or 'none'}\n"
            "- Owner's yes in chat (no manual approvals on GitHub): merging into the release branch, production\n"
            "  deploys and re-runs happen after the owner says yes; the harness asks before these commands run.\n"
            "- Hard stops: never push to the release branch directly; never merge, dispatch production workflows\n"
            "  (outside the list above) or re-run them without the owner's yes; never read the discovery\n"
            "  exclusions; personal data never goes to a model; secrets are never printed.\n"
            "- State: `work/<feature>/STATE.md` (pointer, rewritten), decisions in `approvals.md`.\n"
            f"{END}\n")


def adopt(repo: Path, s: dict, plan: Plan):
    plan.write(repo / ".artel" / "project.toml", render_project_toml(s), "artel project settings (other keys kept)")
    cm = repo / "CLAUDE.md"
    cur = plan.read(cm) or ""
    block = claude_block(s)
    nb, ne = cur.count(BEGIN), cur.count(END)
    if nb == 1 and ne == 1 and cur.index(BEGIN) < cur.index(END):
        tail = cur[cur.index(END) + len(END):]
        new = cur[:cur.index(BEGIN)] + block + (tail[1:] if tail.startswith("\n") else tail)
    elif nb == 0 and ne == 0:
        new = cur + ("\n" if cur and not cur.endswith("\n") else "") + ("\n" if cur else "") + block
    else:
        raise SystemExit(f"{cm}: artel markers are malformed ({nb} begin, {ne} end) — fix by hand, then rerun")
    plan.write(cm, new, "managed artel block (rest of the file untouched)")


def protect(repo: Path, s: dict, plan: Plan):
    slug = github_slug(sh(["git", "remote", "get-url", "origin"], repo, check=False))
    if not slug:
        plan.steps.append("skip       protect: origin is not GitHub (contract only for other hosts)")
        return
    rel = s["release_branch"]
    rules = [{"type": "deletion"}, {"type": "non_fast_forward"},
             {"type": "pull_request", "parameters": {"required_approving_review_count": 0,  # owner approves in chat
              "dismiss_stale_reviews_on_push": True, "require_code_owner_review": False,
              "require_last_push_approval": False, "required_review_thread_resolution": False,
              "allowed_merge_methods": ["merge", "squash", "rebase"]}}]
    if s["required_checks"]:
        rules.append({"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": False,
                      "required_status_checks": [{"context": c} for c in s["required_checks"]]}})
    body = {"name": f"{rel} protection (artel)", "target": "branch", "enforcement": "active",
            "conditions": {"ref_name": {"include": [f"refs/heads/{rel}"], "exclude": []}},
            "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
            "rules": rules}
    existing = json.loads(sh(["gh", "api", f"repos/{slug}/rulesets"], repo) or "[]")
    for r in existing:
        full = json.loads(sh(["gh", "api", f"repos/{slug}/rulesets/{r['id']}"], repo))
        inc = full.get("conditions", {}).get("ref_name", {}).get("include", [])
        if f"refs/heads/{rel}" in inc or "~DEFAULT_BRANCH" in inc or "~ALL" in inc or r.get("name") == body["name"]:
            plan.steps.append(f"skip       ruleset '{full['name']}' (id {r['id']}, {full.get('enforcement')}) already "
                              f"targets {rel} — never overwritten (it may hold required checks); artel-doctor checks it")
            return
    plan.steps.append(f"create     ruleset '{body['name']}' on {slug}")
    if plan.apply:
        r = subprocess.run(["gh", "api", "-X", "POST", f"repos/{slug}/rulesets", "--input", "-"], cwd=repo,
                           input=json.dumps(body), capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"ruleset failed: {r.stderr.strip()}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    for m in ("adopt", "contain", "identity", "protect"):
        ap.add_argument(f"--{m}", action="store_true")
    ap.add_argument("--profile", choices=["light", "standard", "critical"])
    ap.add_argument("--data-class", dest="data_class")
    ap.add_argument("--release")
    ap.add_argument("--dev")
    ap.add_argument("--allow-op", dest="allow_op", action="append", default=[])
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--check", action="append", default=[])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--diff", action="store_true", help="show the content changes of a dry run")
    a = ap.parse_args()
    if not any((a.adopt, a.contain, a.identity, a.protect)):
        ap.error("choose at least one of --adopt --contain --identity --protect")
    repo = Path(a.repo).resolve()
    top = sh(["git", "rev-parse", "--show-toplevel"], repo, check=False)
    if not top or Path(top).resolve() != repo:
        raise SystemExit(f"not a git repository root: {repo}")
    git_exclude = Path(sh(["git", "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"], repo))
    if a.adopt or a.contain or a.identity:
        preflight(repo)
    s = project_settings(repo, a)
    plan = Plan(a.apply, a.diff)
    if a.adopt:
        adopt(repo, s, plan)
    if a.adopt or a.contain:
        contain(repo, s, plan, git_exclude)
    if a.adopt or a.identity:
        identity(repo, user_cfg(), plan)
    if a.protect:
        protect(repo, s, plan)
    plan.commit(repo)
    print(("APPLIED" if a.apply else "DRY RUN — nothing written; add --apply") + f" · {repo}")
    for st in plan.steps:
        print("  " + st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
