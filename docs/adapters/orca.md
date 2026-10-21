# Adapter: Orca (orchestrator)

Verified on Orca 1.4.218 (2026-10-03); see `evidence/INDEX.md` → tools. Pin the version; Orca releases often.

- **Light profile and T0**: no Run; separate sessions for implementation and review still apply.
- **Feature = one Run; slice = Task with deps; worker** = `orca orchestration worker-start --task <id> --worktree new-child --agent claude|codex --model <id> --effort <level>`. A fresh worker is a new terminal, not a new worktree — pass `--worktree new-child` for code-editing workers. Verify `launch.effective` in the receipt; never trust the requested model.
- **Coordinator restart / provider switch**: `orca orchestration run-use --id <run>` + `STATE.md`. Orca's DB is local and unversioned (`orchestration reset --all` wipes it) — never the only copy of state.
- **Nesting depth** = 1 by default: a worker cannot start supervised workers.
- **Quota probe (O7)**: `orca account list --json` → `rateLimits.{claude.session,claude.weekly,claude.fableWeekly,codex.weekly}` and reset credits.
- **Stop-and-wait (R3)**: only structured prompts (`AskUserQuestion` in Claude Code) reach the Agent Dashboard "Needs You" column; plain-text questions show as "Done". Orca orchestration gates are coordinator-internal and have no UI. Phone push requires the mobile app paired; delivery must be tested (`artel doctor` check 9).
- **Visibility**: `orca terminal rename --title "<phase>·<feature>·<slice> <tier> <agent>"`, `orca worktree set --workspace-status|--comment`; review: `orca file open-changed` + Annotate AI Diff; UAT screenshots via Orca browser.
- **Session memory**: `orca search` across agents (index enabled in Settings, local).
- **Automations**: scheduled prompts to an agent (no shell action, no `--model`), need the app open or `orca serve` (beta); `--precheck` is a zero-token shell gate; missed-run grace per preset (weekday 720 min, weekly 1440). Use for digests and reports, not for critical checks.
- **Security**: Orca's `agentDefaultArgs` launch `claude --dangerously-skip-permissions` and `codex --dangerously-bypass-approvals-and-sandbox`. This is acceptable only after `artel doctor` proves server-side layers (contract G2); otherwise change Settings → Agent Permissions to manual.
- **Roles in their own session** (e.g. the spec writer on a model the coordinator is not running): `orca orchestration
  worker-start --spec <packet> --agent claude --model <id> [--effort <level>] --worktree current --json` → check
  `result.launch.effective.model`; follow with `worker-show --dispatch <id> --json` (`result.dispatch.status`, e.g.
  `completed`, `completedAt`) and `worker-read --dispatch <id> --source transcript`; free the terminal with
  `worker-release`. Verified 2026-10-06: a Fable worker ran on `claude-fable-5-1` (worker transcript 4/4) and could start
  subagents pinned to Sonnet. A worker must report through `orca orchestration send` (`worker_done`) — a packet that says
  "run nothing" conflicts with that; allow the reporting commands explicitly.
- **Headless reviewers are not Orca workers**: the review runner (`artel-review/scripts/review_run.py`) launches `codex exec`
  / `claude -p` itself, so it can read the exit and output and hand the wave over on a limit; the coordinator runs it in the
  background.
