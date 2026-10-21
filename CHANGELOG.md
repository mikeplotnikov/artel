# Changelog

## 0.3.1 — 2026-10-06

- doctor: agent-token scopes the owner accepted (`accepted_risks = ["agent-token-scope:<scope>"]` in the user config) are reported as WARN with what they allow, not FAIL; any other forbidden scope or a wrong login still fails.
- Owner decisions recorded in the instance: the agent token keeps the `workflow` scope; the new-work threshold (D2) applies to the spec writer too.

## 0.3.0 — 2026-10-06

- Matrix v2 (`roles.toml` schema 2): ordered chains per role, review roles, bans (Luna on every review role), new-work threshold 90% (owner D2).
- `matrix.py pick`: the only way to choose a model — skips banned, exhausted and over-threshold families, never gives a review to the author's model, prefers another family, marks "independence weakened"; returns launch commands for the harness and Orca; `--exclude-family`.
- Limit failover (core §2.2, §8; owner decisions D1–D3, text approved 06.10): `artel-review/scripts/review_run.py` hands an interrupted wave to the next model (limit line of the harness + Orca limits), protects the partial wave file, resumes or refuses re-runs, keeps scope against a baseline; reviewers append findings as they go (`references/lane-prompt.md`); implementer handover packet; pass by another family before the release request for T2–T3 slices reviewed with weakened independence; no handover during incidents.
- Spec writer runs as its own Fable worker started by the coordinator (Orca), the owner is never asked to switch `/model`; `interview-completeness-checker` and `code-researcher` pinned to Sonnet high (local deviation from Molyanov, logged).
- doctor check 11: every role pickable with one family down; lists all roles without a candidate.
- Adapters: limit signatures (Codex from source, Claude from transcripts), headless reviewer launch, Orca role workers; new `docs/adapters/omp.md`.
- DeepSeek as a reserve third family (owner decision 06.10): `reserve_families`, pick pass 3, `omp` harness in pick and the runner (diff written to a file — omp refuses shell commands headless). Calibration on the C1 set: V4 Pro 2/7, V4.1 Flash 0/7 → V4 Pro is the reserve reviewer.
- Reviews of this release ran through the new runner itself: wave 1 (Sonnet on Codex code, Sol on Opus text), wave 2 (Sonnet by owner exception — Anthropic over threshold; Sol), and DeepSeek on the DeepSeek integration; every fix has a test that fails on the previous code.

## 0.2.3 — 2026-10-05 (owner request: documentation sources)

- Core principle 9: external facts (versioned libraries, SDKs, APIs, CLIs; behaviour of public repositories) come from sources — a documentation source such as Context7, a code wiki such as DeepWiki, official docs, a test stand for vendor REST APIs — never from model memory; unchecked facts are marked "unverified (from memory)" and get a test or a review question.
- Route B plan lists the external facts of the slice (library@version → source) and passes them to the implementer; Route A takes stack versions from current sources; Route I asks the code wiki before debugging a library from memory.
- Contract: optional capability O9 (documentation sources in every harness), degradation G9.
- Adapters: Claude Code (user-scope MCP) and Codex (`[mcp_servers]` with `default_tools_approval_mode = "approve"`, verified with Codex 0.160.0).

## 0.2.2 — 2026-10-04 (owner decision: approvals in chat)

- Release gate moved from manual approval on the VCS host to the owner's yes in chat, enforced by harness ask rules: Claude Code `permissions.ask` and Codex `decision = "prompt"` for merge, production dispatch, re-run and API write calls. Verified: in unconfirmed-execution mode both block these when nobody can answer, and unlisted commands run.
- Rulesets: 0 required approvals; PR, required checks, no force-push or deletion stay. `init.py --protect` creates rulesets that way, and `--contain` writes ask/prompt rules (legacy denies are reported as conflicts, never removed).
- `doctor.py`: no approval requirement; new check 1–2 "ask rules" for both harnesses; live probe = GH013 on direct push + merge blocked in both harnesses.
- Core §6.3 step 6, §10 layers 2–3, contract O2/check 2, GitHub adapter, skills `artel`, `artel-change`, `artel-incident`, `artel-doctor` updated. Residual risk accepted by the owner: the VCS host no longer refuses an agent merge by itself.

## 0.2.1 — 2026-10-04 (build review; author's fixes under the owner's standing rule on spec contradictions, open for owner review)

Spec (`docs/core.md`):
- Entry precedence: a production incident goes to Route I in any project state; unfinished Route O / Route A resumes first; coordinator-started slice/review sessions do not re-run entry.
- Route A bootstrap: the owner creates the repository; `artel init --adopt --protect`; CI skeleton and personal-data scrubber come with the walking skeleton (was: a nonexistent `artel init` that did everything).
- Route I: the objective signal includes a reproducible user-facing failure; no autonomous rollback when the newest verified tag is the running revision; failed recovery stops autonomy; without a scrubber the owner supplies log excerpts; G1 hotfix review by another model.
- Audit inside onboarding stops at the gap table (the onboarding gate decides).
- Route O: profile proposed after O1 (not at intake); containment for any profile; test baseline recorded in O2; progress in `work/onboarding/STATE.md` (was `state.yml`); **O3 now adopts first** (`artel init --adopt`, then doctor with the contract's failure mapping) because O3/O4 consumed what only O6 produced; O6 is the cutover check plus applying the executable-config inventory; trust ramp ends by the owner after clean slices (the token baseline had no producer); light profile gets a short O2a/O2b and O3/O4.

Skills: descriptions scoped to artel projects with Do-NOT lines (they are installed globally); SKILL.md files are the procedure and the generated references decide doubts (removed drift: rollback signal, deploy owner, testing rules); entry no longer loads the full matrix for questions; Route B no longer repeats the entry's plan; T0 short path; the implementer makes review fixes; mutants only where the testing tier table requires them; references needed after copy-out are bundled (`github.md`, `orca.md`, `release-types.md`, `artel.toml.example`); `roles.toml` moved to `references/` and gained layout and docs reviewer rows.

Scripts (Codex cross-family review, 29 findings):
- `init.py`: all checks before any write, writes committed together; refuses when agent settings hold secret-like env keys and never prints that file (a `--diff` could print an allow rule with a secret); Codex rules in a marked block, other rules kept; strings escaped (a workflow file name could inject an `allow` rule); `.codex/config.toml` with other settings is not overwritten; worktree-safe `info/exclude`; existing `project.toml` keys kept; marker handling exact; `rollback*` workflows allowed by the default `rollback` operation.
- `doctor.py`: PASS only where the data shows it — unreadable host data is MANUAL; ruleset include/exclude and default branch evaluated; stale-approval dismissal and configured required checks enforced; environment policy type checked; owner guard needs an `if:` condition and stays MANUAL; whole working copy walked (ignored files too, virtualenvs skipped) with skipped/unread counts; env-file key hits are WARN for the owner to confirm; personal data and review independence are MANUAL; malformed instruction-file markers fail; missing `gh` handled; exclusions honoured everywhere.
- `snapshot.py`: one exclusion filter for every section; exact-file and `./` exclusions; GitHub slug parsed by host; `--out` only outside the repo or under `work/onboarding/`; hooks and pinned models of project agents recorded; artel's own files not counted as activity.
- `mutate.py`: SIGTERM/SIGINT/SIGHUP restore the file; timeout kills the whole process group; unreadable files become invalid mutants; survivors make exit 1 even when other mutants are invalid.
- `matrix.py`: argparse; unknown role → exit 2 with the list.

Wave 2 (Codex, fix diff `6d5d34d..670be15`, 13 findings — targeted fix-and-verify, no wave 3): Codex config owned only when artel-marked and holding only artel's variables; another tool's rules file kept verbatim (multi-line rules survived); legacy denies that block an allowed rollback are reported, never removed; workflow names of any shape are fenced (escaped, not filtered); quoted TOML keys round-trip; doctor never reads excluded settings or instruction files, treats wildcard ruleset targeting as MANUAL and counts unreadable directories; snapshot does not follow symlinks into exclusions; mutate stops the test process group on interruption and cannot be interrupted while restoring; Route A has an explicit done state; light onboarding takes its executable-config inventory from the snapshot and skips O5.

## 0.2.0 — 2026-10-04 (build)

- Route O: explicit O2a state report with confirmation questions and O2b plan review (keep / adjust / add / drop) before the single onboarding gate — owner request and approval.
- Skills, scripts and installer built from the approved spec.

## 0.1.0 — 2026-10-04 (approved by the owner)

- Approved by the owner on 2026-10-04 ("утверждаю").
- Split the single Russian spec into: `docs/core.md` (methodology, English), `docs/contract.md` (capabilities, degradation, `artel doctor`), `docs/adapters/` (Orca, none, GitHub, Claude Code, Codex), the author's private instance (not published), and `evidence/`.
- Added the testing policy (acceptance tests first by another session, protected tests, executed mutants on changed lines, tiered requirements, flaky-test and test-data rules).
- Fixed contradictions found in cross-model review: T0-a vs docs-only CI, T0-c defined by consequences, scope gate per profile, layer-5 vs accepted client-material risk, tier boundaries by consequences, undefined terms now in a glossary.
- Unconfirmed execution became an opt-in preset gated by `artel doctor`.
- Deliberate changes of meaning vs the old spec (logged so later passes don't "synchronise" them away): T2 is now defined by consequences (existing behaviour users or integrations rely on; data-model changes) instead of "production client work"; T3 includes infrastructure; T2 effort "high" (matrix detail moved to the instance); T0-a verification is a docs check without the test suite; the walking skeleton ships one smoke, one unit and one integration test; unconfirmed execution is opt-in after `artel doctor` (the owner's instance keeps it on until phase 1 as a recorded deviation).
- Restored rules dropped in the first split: sequential slices unless file ownership is disjoint; limits re-checked before every slice; light profile and T0 without an orchestration run; automation section (core §11a); provider-switch preconditions (guards ported, doctor passed); upstream commit pins; "T0 ships with the next release".
- `artel doctor`: checks 9 (notification delivery) and 10 (orchestrator-launched harness reads the instruction file) added; failure → degradation mapping made explicit.
- GitHub adapter: rollback takes no ref (latest release tag only); required test job always runs instead of path filters.
- Removed a verbatim upstream guide and e-mail addresses from the owner's calibration evidence.
- Final cross-model review fixes: release tags are created only after the post-deploy check, rollback targets the newest verified tag (regression from the previous commit); light profile = no orchestration run but separate sessions; T2/T3 storage/migration/backup tests only where applicable; doctor check 5 also covers personal data and gates unconfirmed execution; doctor check 4 never redeploys production; CI moved from required R5 to optional O8 with degradation G8; data classes, verified tag and session defined; gate rejection/re-entry, spend and outside-send scopes, calibration admission rule and G5 N=10 defined; PII scrubber at init/onboarding and per-reviewer test resources restored (dropped in the split, not previously logged); lost orchestrator state rebuilt from spec + VCS + approvals.
