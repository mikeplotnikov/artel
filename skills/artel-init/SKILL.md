---
name: artel-init
description: |
  Artel setup: the user's config (~/.artel/artel.toml), project settings (.artel/project.toml), the
  artel block in the instruction file, agent fences and identity, release-branch protection. Dry run
  by default.

  Use when: an artel route calls it (onboarding containment and adoption, new-product bootstrap), the
  role matrix reports no user config, or the owner asks to set artel up ("настрой артель", "artel
  init").
---

# Artel — init

Script: `python3 <this skill dir>/scripts/init.py`. It prints a plan and writes nothing without
`--apply`; `--diff` shows content changes. Show the owner the dry run before applying.

## User config (once per person)

Missing `~/.artel/artel.toml`: copy [artel.toml.example](references/artel.toml.example), fill
providers (family, access, model ids per class `top` / `flagship` / `mid` / `cheap`), owner and agent
logins, orchestrator, `calibrated = false`. Show `python3 <artel skill dir>/scripts/matrix.py`.

## Modes

| Mode | Writes | Used by |
|---|---|---|
| `--contain` | `.claude/settings.local.json` deny rules, `.codex/rules/artel.rules`, `.git/info/exclude` | onboarding O0.5 |
| `--identity` | agent env for Claude and Codex sessions, local git credential helper | when the agent account is added later |
| `--adopt` | `.artel/project.toml`, artel block in `CLAUDE.md`, + `--contain` + `--identity` | onboarding O3, new product |
| `--protect` | release-branch ruleset on GitHub; never overwrites an existing one | new product (owner's admin login) |

Settings: `--profile`, `--data-class`, `--release`, `--dev`, `--allow-op <workflow file>` (production
operations agents may run; a workflow named `rollback*` is allowed by the default `rollback` entry),
`--exclude <path>`, `--check <required CI job>`; otherwise taken from an existing
`.artel/project.toml`.

## After `--adopt`

1. Regenerate `AGENTS.md` from `CLAUDE.md` with the project's sync tool (reference setup:
   `sync-to-codex.sh --project <root> --apply` from molyanov-ai-dev `scripts/`, with
   `--allow-project-outside-root` for projects outside `~/projects`); never edit it by hand.
2. Run `artel-doctor`.
3. Commit `.artel/project.toml`, `CLAUDE.md`, `AGENTS.md` to the development branch; local agent
   config (`.claude/settings.local.json`, `.codex/`) stays uncommitted.

Existing deny rules are kept; old allow rules stay (deny wins) and are counted; an existing
`.codex/config.toml` without artel's block is not overwritten — the script prints the block to merge.
No secrets are read or written.
