# Adapter: Claude Code (harness)

Verified on Claude Code 2.1.285 (2026-10-03); see `evidence/INDEX.md` → tools.

- **Instruction file**: `CLAUDE.md` (source of truth); `AGENTS.md` generated from it for other harnesses.
- **Agents**: `.claude/agents/*.md` with `model:` pinned for every reviewer/validator.
- **Hooks**: PreToolUse guards (secrets, generated files, path denies); SessionStart sources `startup|resume|clear|compact` → load project status + `STATE.md`; Stop hook can enforce `STATE.md` update at boundaries.
- **Context**: `"autoCompactWindow": 200000` in settings; a fresh session per slice is preferable (orchestrator worker or `/clear`).
- **Status line**: show context % and per-provider limits.
- **Stop-and-wait (R3)**: `AskUserQuestion` for gate questions.
- **Metered fallback reviewer**: separate `CLAUDE_CONFIG_DIR` with an API key (API key outranks subscription login), or Max usage credits in the same session.
- **Unconfirmed mode**: `--dangerously-skip-permissions` only under contract G2.
- **Documentation sources (O9)**: Context7 and DeepWiki as user-scope MCP servers (`claude mcp add --scope user
  --transport http context7 https://mcp.context7.com/mcp`, same for `deepwiki` with `https://mcp.deepwiki.com/mcp`);
  they then reach every project and every Orca-launched session. Check with `claude mcp list`.
- **Limit exhaustion (failover signature)**: an API error message `You've hit your session limit · resets …` or `You've
  hit your weekly limit · resets …` (seen 33 times in local transcripts with `isApiErrorMessage: true`); the exit code of
  `claude -p` in that case is not verified — the runner relies on the text and on Orca limits.
- **Headless reviewer**: `claude -p <prompt> --model <id> --effort <level> --allowedTools "Read,Grep,Glob,Bash(git
  diff:*),Bash(git log:*),Bash(git show:*),Write(work/<feature>/reviews/**),Edit(work/<feature>/reviews/**)"`; the
  prompt must name the tool-call pattern (first call creates the wave file, one append per finding) — without it a
  Sonnet reviewer wrote the whole file once at the end (live check 2026-10-06).
