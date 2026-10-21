---
name: artel
description: |
  Entry point of the artel development framework: loads the project's artel state, picks the route
  (onboarding, new product, change, incident, audit, or a plain status answer), states the plan and
  hands off to the route skill.

  Use when: "/artel", "артель", "запусти артель", "работаем по артели", "artel status", or any
  development request in a repository that has `.artel/project.toml`.

  Do NOT use for: projects without `.artel/project.toml` unless the owner names artel; sessions the
  artel coordinator started for one slice or one review (they follow their task packet).
---

# Artel — entry

Rules: [core-rules.md](references/core-rules.md) — read only the section a step names. The artel
repository path is in `~/.artel/repo`.

## 1. Where are we (read, no questions)

Check in this order and stop at the first match:

1. **Interrupted session** — signs: `work/*/STATE.md` older than the newest commit or than
   uncommitted changes, an Orca worker without completion, a review wave file without `## Done`.
   Then, before anything else, reconstruct from traces: read `work/*/STATE.md` and `work/*/approvals.md`;
   `git status` and `git diff` in the repository and in every worktree (`git worktree list`);
   commits newer than `STATE.md`; Orca workers and worktrees (`orca worktree ps --json`).
   Classify each piece of work as done / half-done / not started, run the tests of what was touched,
   rewrite `STATE.md` from the facts, then continue from step 2. As the coordinator you decide what
   artel rules define; whatever needs the owner goes to the owner as a question (this does not lift
   a harness's own emergency limits on decisions — when they apply, ask).
   If production is broken, item 2 comes first; reconstruct afterwards.
2. **Production is broken** (the owner says so, or monitoring reports it) → `artel-incident`, whatever
   the project's state — even mid-onboarding.
3. `work/onboarding/STATE.md` exists and is not marked done → resume `artel-onboard`.
4. `work/product/STATE.md` exists and is not marked done → resume `artel-new`.
5. No `.artel/project.toml`: the directory has code or git history → `artel-onboard`; empty, or the
   owner describes a new product → `artel-new`.
6. Otherwise read `.artel/project.toml`, the active `work/*/STATE.md`, open questions in
   `work/*/approvals.md`, the project status file.

## 2. Classify and state the plan

| Route | When | Skill |
|---|---|---|
| B — change | a feature or a bug | `artel-change` |
| Audit | "find problems in X" | `artel-audit` |
| Question | status, explanation, no change | answer from the files read in §1; stop here |

For work routes only:
- **Limits**: with Orca, `orca account list --json` → `result.rateLimits.claude.{session,weekly}` and
  `result.rateLimits.codex.weekly` (`usedPercent`, `resetsAt`); the accounts list comes first, the limits
  follow — read the whole output. No quota data → ask the owner before long or parallel work (G7).
- **Models — never chosen from memory**: for every role you start, run `python3 <this skill
  dir>/scripts/matrix.py pick --role <role> --tier <t01|t23> [--author <model id>] --json` (author for
  review roles) and launch with its `launch` model and effort — Orca: `launch.orca` is the agent/model
  part, add `--spec <packet>` (or `--task`) and `--worktree <…>`; without Orca the harness command. It skips banned and limit-exhausted families and marks `independence_weakened`; copy that
  flag and its `notes` into the artefact. Exit 2 = no user config → `artel-init`; exit 3 = no candidate
  → ask the owner. A role you cannot launch yourself (e.g. a model the current session is not on) is
  started as a separate worker — never ask the owner to switch `/model`.
- **Tier** by consequences (core-rules §5). Escalate on CI/CD, containers, environment files,
  secrets, feature flags, money/legal/consent wording, authorisation, migrations, personal data,
  backups, and `escalate_paths` from `.artel/project.toml`. In doubt, the higher tier.

Tell the owner in one message: route, tier, profile, next step, roles → models, gates ahead. Then
proceed; the route skill does not repeat this.

## 3. Rules on every route

- **Gates** are only those of the project's profile (core-rules §7). A gate stops the work: ask with
  `AskUserQuestion` — the only form Orca shows as "Needs You" (owner exception to "plain-text
  questions", global CLAUDE.md); other harnesses use their question prompt. Record decision and scope
  in `work/<feature>/approvals.md`. A rejected gate returns to the previous stage with the reasons.
- **Rights belong to roles**, regardless of provider; the implementer commits and pushes to the
  development branch. Reviewers come from another model family (core-rules §2).
- **Owner's yes in chat** (no manual approvals on GitHub): before a merge into the release branch, a
  production deploy or a re-run, ask the owner in one line what will happen; the harness also stops
  these commands (ask rules) until the owner allows them — then do it yourself as the agent account.
- **Hard stops**: never push to the release branch directly; never merge into it, dispatch or re-run
  production workflows (outside `prod_operations_allowed`) without the owner's yes; never read
  `discovery_exclusions`; no personal data to any model; never print, copy or commit secrets. A denial
  or an unanswered ask from the VCS host or the harness is final, never worked around.
- **State**: at every boundary rewrite `work/<feature>/STATE.md` as a pointer (route, stage/slice,
  run/task ids, open questions, next step; ≤ 4 KB; never appended).
- **Sessions**: one slice per fresh session or worker; implementation and review in separate
  sessions; the coordinator routes, records and asks. Limits checked before every slice; slices
  sequential unless file ownership is disjoint.
- **Provider switch** at a unit boundary, or mid-work only through limit failover (`artel-review` runner,
  `artel-change` implementer handover); never during an incident.
- **Evidence**: every claim to the owner has a locator (file:line, command + output, URL). Facts about
  a library, SDK, API or CLI come from a source for the version in use — Context7 (how to call it),
  DeepWiki (why it behaves so), official docs — never from memory; unchecked → "unverified".

## 4. Hand off

Load the route skill and follow it. Come back here only when the owner changes the request.
