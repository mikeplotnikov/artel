#!/usr/bin/env python3
"""Resolve the artel role → model matrix for this user (core §8).

Reads the default role table (../references/roles.toml) and the user's instance config
(~/.artel/artel.toml, or $ARTEL_CONFIG). Prints, per role and tier group, the first available
candidate and the next one from another family (the cross-family fallback / reviewer option).
Exit 2 when the user config is missing (degradation G5: matrix is "uncalibrated for you").

Usage: matrix.py [--json] [--role ROLE]   (unknown role → exit 2 with the list of roles)
       matrix.py pick --role ROLE --tier {t01,t23} [--author MODEL_ID]
                      [--limits FILE | --no-limits] [--exclude-family FAMILY ...] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROLES = HERE.parent / "references" / "roles.toml"


def load_user() -> dict | None:
    path = Path(os.environ.get("ARTEL_CONFIG", Path.home() / ".artel" / "artel.toml"))
    if not path.exists():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


def available(user: dict) -> dict[str, dict[str, str]]:
    """family -> {class: model_id} for providers the user has."""
    out: dict[str, dict[str, str]] = {}
    for p in user.get("providers", []):
        fam = p.get("family")
        models = p.get("models", {})
        if fam and models:
            out.setdefault(fam, {}).update(models)
    return out


def resolve(cands: list[str], avail: dict[str, dict[str, str]]) -> list[dict]:
    res = []
    for c in cands:
        spec, _, effort = c.partition("@")
        fam, _, cls = spec.partition(".")
        model = avail.get(fam, {}).get(cls)
        if model:
            res.append({"family": fam, "class": cls, "model": model, "effort": effort or "medium"})
    return res


G7 = "G7: limits unknown — ask the owner before long or parallel work"
TIERS = ("t01", "t23")


def load_limits(args: argparse.Namespace) -> dict | None:
    if args.no_limits:
        return None
    try:
        if args.limits:
            raw = Path(args.limits).read_text(encoding="utf-8")
        else:
            raw = subprocess.run(["orca", "account", "list", "--json"],
                                 capture_output=True, text=True, check=True, timeout=20).stdout
        limits = json.loads(raw).get("result", {}).get("rateLimits")
        return limits if isinstance(limits, dict) and limits else None
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        return None


def family_windows(limits: dict, family: str, model: str) -> dict:
    provider = limits.get({"anthropic": "claude", "openai": "codex"}.get(family, family), {})
    if not isinstance(provider, dict):
        return {}
    names = None
    if family == "anthropic":
        names = {"session", "weekly"}
        if "fable" in model.lower():
            names.add("fableWeekly")
    return {name: window["usedPercent"] for name, window in provider.items()
            if (names is None or name in names) and isinstance(window, dict)
            and isinstance(window.get("usedPercent"), (int, float))}


def pick(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Pick a model from the role's ordered chain")
    ap.add_argument("--role", required=True)
    ap.add_argument("--tier", required=True)
    ap.add_argument("--author")
    ap.add_argument("--exclude-family", action="append", default=[])
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--limits")
    group.add_argument("--no-limits", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    defaults = tomllib.loads(ROLES.read_text(encoding="utf-8"))
    roles = defaults["roles"]
    if args.role not in roles:
        print(f"unknown role {args.role!r}; roles: {', '.join(roles)}", file=sys.stderr)
        return 2
    if args.tier not in TIERS:
        print(f"unknown tier {args.tier!r}; tiers: {', '.join(TIERS)}", file=sys.stderr)
        return 2
    user = load_user()
    if user is None:
        print("artel: no user config — degradation G5: matrix uncalibrated", file=sys.stderr)
        return 2
    avail = available(user)
    configured_families = {p.get("family") for p in user.get("providers", [])}
    role = roles[args.role]
    author_family = None
    if role.get("review") and args.author:
        author_family = next((p.get("family") for p in user.get("providers", [])
                              if args.author in p.get("models", {}).values()), None)
        if author_family is None:
            print(f"unknown author model {args.author!r}; not found in user providers", file=sys.stderr)
            return 2
    chain = user.get("roles", {}).get(args.role, {}).get(args.tier, role[args.tier])
    threshold = user.get("policy", {}).get("new_work_threshold",
                                          defaults["policy"]["new_work_threshold"])
    reserve_families = user.get("policy", {}).get("reserve_families",
                                               defaults["policy"].get("reserve_families", []))
    limits = load_limits(args)
    notes = [G7] if limits is None else []
    skipped, remaining = [], []
    for candidate in chain:
        spec, _, effort = candidate.partition("@")
        family, _, cls = spec.partition(".")
        model = avail.get(family, {}).get(cls)
        why = None
        if family in args.exclude_family:
            why = "excluded"
        elif family not in configured_families:
            why = "family not configured"
        elif not model:
            why = "class has no model id"
        elif spec in role.get("banned", []):
            why = "banned"
        elif limits is not None:
            windows = family_windows(limits, family, model)
            if not windows:
                note = f"limits unknown for {family}: treated as available — ask the owner if it matters"
                if note not in notes:
                    notes.append(note)
            used = max(windows.values(), default=0)
            if used >= 100:
                why = "exhausted"
            elif used >= threshold:
                why = "over threshold"
        if why is None and role.get("review") and model == args.author:
            why = "author's own model"
        if why is None and role.get("review") and family in reserve_families and family == author_family:
            why = "reserve is author's family"
        if why:
            skipped.append({"candidate": candidate, "why": why})
        else:
            harness = next(p["harness"] for p in reversed(user.get("providers", []))
                           if p.get("family") == family and p.get("models", {}).get(cls) == model)
            remaining.append({"family": family, "class": cls, "model": model,
                              "effort": effort or "medium", "harness": harness})
    if not remaining:
        error = {"error": f"no candidate available for {args.role} {args.tier}", "skipped": skipped}
        print(json.dumps(error, ensure_ascii=False))
        return 3
    regular = [c for c in remaining if c["family"] not in reserve_families]
    reserve = [c for c in remaining if c["family"] in reserve_families]
    chosen = (regular or reserve)[0]
    weakened = False
    if role.get("review"):
        if author_family:
            independent = next((c for c in regular if c["family"] != author_family), None)
            chosen = independent or (regular or reserve)[0]
            weakened = chosen["family"] == author_family
        else:
            notes.append("author unknown — independence not checked")
    if chosen["family"] in reserve_families:
        notes.append(f"reserve family {chosen['family']}")
    model, effort, harness = chosen["model"], chosen["effort"], chosen["harness"]
    if harness == "omp":
        command = (f"omp -p <prompt> --model {model} --thinking {effort} "
                   "--approval-mode write --mode text")
        orca = None
        notes.append("no Orca agent for omp — run headless")
    elif harness in ("claude-code", "codex"):
        agent = "claude" if harness == "claude-code" else "codex"
        command = (f"claude --model {model} --effort {effort}" if agent == "claude" else
                   f"codex exec -m {model} -c model_reasoning_effort={effort}")
        orca = f"orca orchestration worker-start --agent {agent} --model {model} --effort {effort}"
    else:
        print(f"unsupported harness {harness!r} for {model}; supported: claude-code, codex, omp", file=sys.stderr)
        return 2
    result = {"role": args.role, "tier": args.tier, **chosen,
              "independence_weakened": weakened, "notes": notes, "skipped": skipped,
              "limits": "unknown" if limits is None else
              {family: family_windows(limits, family, model) for family in avail},
              "launch": {harness: command,
                         "orca": orca}}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        suffix = []
        if role.get("review") and author_family:
            suffix.append("independence weakened" if weakened else "independence ok")
        suffix.extend(notes)
        print(f"{args.role} {args.tier} → {model}@{effort} ({harness})"
              + (" · " + " · ".join(suffix) if suffix else ""))
    return 0


def main() -> int:
    if sys.argv[1:2] == ["pick"]:
        return pick(sys.argv[2:])
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--role")
    a = ap.parse_args()
    as_json, only = a.json, a.role
    defaults = tomllib.loads(ROLES.read_text(encoding="utf-8"))["roles"]
    if only and only not in defaults:
        print(f"unknown role {only!r}; roles: {', '.join(defaults)}", file=sys.stderr)
        return 2
    user = load_user()
    if user is None:
        print("artel: no user config (~/.artel/artel.toml) — degradation G5: matrix uncalibrated; "
              "run the artel-init skill to create it.", file=sys.stderr)
        return 2
    avail = available(user)
    overrides = user.get("roles", {})
    families = sorted(avail)
    table = {}
    for role, tiers in defaults.items():
        if only and role != only:
            continue
        row = {}
        for tier in TIERS:
            cands = tiers[tier]
            cands = overrides.get(role, {}).get(tier, cands)
            r = resolve(cands, avail)
            primary = r[0] if r else None
            other = next((x for x in r if primary and x["family"] != primary["family"]), None)
            row[tier] = {"primary": primary, "other_family": other}
        table[role] = row
    degradations = []
    if len(families) < 2:
        degradations.append("G1: single model family — reviews use the same family, different model, "
                            "marked 'independence weakened'; T3 needs an extra human or API review")
    if not user.get("calibrated", False):
        degradations.append("G5: matrix not calibrated on your tasks — log the first 10 slices")
    if as_json:
        print(json.dumps({"families": families, "matrix": table, "degradations": degradations},
                         ensure_ascii=False, indent=2))
        return 0
    fmt = lambda x: f"{x['model']}@{x['effort']}" if x else "—"
    print(f"families: {', '.join(families) or 'none'}")
    for role, row in table.items():
        print(f"{role:26} T0-1: {fmt(row['t01']['primary']):28} other: {fmt(row['t01']['other_family']):24} "
              f"T2-3: {fmt(row['t23']['primary']):28} other: {fmt(row['t23']['other_family'])}")
    for d in degradations:
        print(f"degradation {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
