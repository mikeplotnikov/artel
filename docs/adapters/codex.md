# Adapter: Codex CLI (harness)

Verified on codex-cli 0.159.3 (2026-10-03); see `evidence/INDEX.md` → tools.

- **Instruction file**: `AGENTS.md` (generated from the source instruction file, e.g. `CLAUDE.md`); global rules in `~/.codex/AGENTS.md` (managed block).
- **Agents**: `~/.codex/agents/*.toml` — set `model` and `model_reasoning_effort` explicitly; without them a subagent inherits the parent's model, silently breaking "reviewer family ≠ author family".
- **Invocation**: `codex exec -m <model> -c model_reasoning_effort=<level> ... </dev/null`; never inherit `~/.codex/config.toml` defaults.
- **Hooks**: PreToolUse/SessionStart/Stop exist, but a hook error, timeout or malformed response marks the hook failed and **continues the tool call** (fail-open); changed hooks are skipped until re-trusted. Treat as convenience; hard stops on the VCS host.
- **Orca-launched Codex** may use an isolated `CODEX_HOME`; verify it reads `AGENTS.md` (`artel doctor` check 10).
- **Unconfirmed mode**: `--dangerously-bypass-approvals-and-sandbox` only under contract G2.
- **Documentation sources (O9)**: remote MCP servers in `~/.codex/config.toml` — `[mcp_servers.context7]
  url = "https://mcp.context7.com/mcp"` and `[mcp_servers.deepwiki] url = "https://mcp.deepwiki.com/mcp"`,
  each with `default_tools_approval_mode = "approve"` (read-only lookups; without it a read-only sandbox refuses
  the call: "MCP tool call requires approval, but approval policy is never"). Context7 works without a key at the
  free tier; with a key, keep it in the OS keychain and set `http_headers_helper` to a script that reads it and
  prints `{"CONTEXT7_API_KEY": "<key>"}` — never the key in the file (verified 2026-10-05: a bogus key from the
  helper returns "Invalid API key", the real one answers). Verified 2026-10-05 with
  Codex 0.160.0: both answered from `codex exec --sandbox read-only`. Check with `codex mcp list`.
- **Limit exhaustion (failover signature)**: `codex exec` prints `ERROR: You’ve hit your usage limit…` (or a text with
  `spend cap`, usually ending `Try again at <time>.`) and exits 1 — but exit 1 also follows any other unretried error, so
  the text decides (sources: `openai/codex` `rust-v0.160.0`, `codex-rs/protocol/src/error.rs:692–811`,
  `codex-rs/exec/src/lib.rs:1261–1323`). The session rollout (`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`) records each
  tool call as it happens. Reviewers that must write their wave file need `--sandbox workspace-write`; the runner checks
  afterwards that only `work/<feature>/reviews/` changed.
