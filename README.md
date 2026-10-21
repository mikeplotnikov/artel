# Artel

Agentic software development for a solo developer and many AI agents — from "open a chat" to "released", for anything from a weekend bot to a client product in production. Fast, economical, no loss of quality, provider-independent.

Status: **0.3.1** — specification approved 2026-10-04 (0.2.1 = build-review fixes, see `CHANGELOG.md`); ten skills with scripts built and run on two real projects. Install: `git clone https://github.com/mikeplotnikov/artel && artel/bin/install.sh`; start: `docs/quickstart.ru.md` (Russian).

Requirements: Python 3.11+ (standard library only), `git`, `gh` (GitHub CLI); recommended — documentation sources in every harness (Context7, DeepWiki; `docs/adapters/`). Optional adapters: if installed, two steps are handed to external skills and agents — the spec interview and validation (`user-spec-planning`) and the reviewer agents (`code-reviewer`, `test-reviewer`, `security-auditor`, `infrastructure-reviewer`, `layout-reviewer`, `documentation-reviewer`, `codex-reviewer`); secret rotation uses `secret-handoff`. Compatible `user-spec-planning` and the first six reviewers are published in [molyanov-ai-dev](https://github.com/pavel-molyanov/molyanov-ai-dev) (MIT); `codex-reviewer` and `secret-handoff` are not part of this repository. Without an adapter, run that step by hand under the same rules.

- `docs/core.md` — the methodology (routes, risk tiers, gates, roles, testing, protection).
- `docs/contract.md` — required capabilities, degradation rules, `artel doctor` checks.
- `docs/adapters/` — Orca, no orchestrator, GitHub, Claude Code, Codex.
- `skills/` — the ten artel skills (entry `artel`) with their scripts; `bin/install.sh` installs them.
- `artel.toml.example` — per-user configuration.
- `evidence/INDEX.md` — sources behind the rules.

Русская версия: `README.ru.md`. Licence: MIT (`LICENSE`), with upstream notices in `NOTICE`.
