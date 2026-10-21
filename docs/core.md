# Artel — core methodology

Version: 0.3.1 (2026-10-06; limit failover, matrix resolver, reserve third family — text approved by the owner). Status: approved by the owner on 2026-10-04 (0.1.0; route O state report and plan review added with owner approval in 0.2.0); 0.2.1 = fixes from the build review (CHANGELOG), made by the author under the owner's standing rule on spec contradictions, open for the owner's review; rollout follows the owner instance plan.
Scope: provider-, harness-, orchestrator- and VCS-host-neutral rules. Tool-specific mechanics live in `docs/adapters/`; required capabilities and degradation rules in `docs/contract.md`; a user's concrete setup in their instance (`artel.toml` + instance docs).
Evidence: `evidence/INDEX.md`. A claim without a locator is not part of the methodology.

## 1. Purpose

Artel is a framework for agentic software development: from "open a chat" to "released to production", for products of any size — from a weekend bot or parser to a client product in production.
Goals, all at once: fast · economical in tokens and subscription limits · no loss of product quality · minimal attention from the human owner · independent of any single model provider.
Audience v1: solo developers (one human owner, many agents). Team mode is a non-goal of v1.

Origins: artel's own design, grounded in measurements on real projects (`evidence/`). Ideas studied along the way: the Molyanov AI-First framework (commit b5db526) and Trailmark (commit aa85aad), both MIT — see `NOTICE`.

## 2. Principles

1. **Rights belong to roles, not providers.** Any model admitted to a role has that role's rights. Admission = passing the role's calibration tasks (§12).
2. **Independent review.** The reviewer of an artefact comes from a model family other than its author's (families are defined in the user's config). If no other family is available when a review starts, or the reviewer's provider runs out of limit mid-wave, the review continues with the next model of the role's chain that is not the author's own model (`matrix.py pick`), and the review artefact is marked "independence weakened" with the reason. At T2–T3 such a slice gets a pass by another family before the release request, once that family's limit is back; the development branch is not held. In a single-family setup (G1) the G1 rule below applies instead. Exceptions, always recorded in the review artefact:
   - single-family setups: same family, different model, marked "independence weakened"; at T3 an additional review by a human or by an API model of another family is mandatory;
   - instance-level exceptions justified by calibration data (e.g. a lane with proven high-impact catches), listed in the instance config.
3. **Process weight follows risk.** The risk tier is determined by consequences (data, reversibility, money, authorisation, migrations, deployment), not by file type, and escalates automatically on risky paths and signals.
4. **State lives in files** (the repository), never only in a chat session or in a tool's local database. Any capable model can continue from the files.
5. **Hard stops live on the server side** (VCS host rules, CI). Hooks inside agent harnesses are convenience: harnesses can run without confirmations and some hook systems fail open (`evidence/INDEX.md` → tools, Codex hooks).
6. **A step is done only when its artefact exists.** Owner approvals are recorded with their scope.
7. **No infrastructure for its own sake.** A new mechanism is added only when the simple one has hit a named ceiling.
8. **Facts carry locators.** Numbers in artel documents are generated from data, not typed.
9. **External facts come from sources, not from model memory.** How to call a versioned library, SDK, API or CLI comes from its documentation for the version in use (a documentation source such as Context7, or the official docs); why a public library behaves as it does, or how a public repository is built, comes from a code wiki (such as DeepWiki) or its source — before debugging from memory or cloning a repository to study it. Vendor REST APIs that no source covers are verified against a test stand. A fact that could not be checked is marked "unverified (from memory)" in the artefact and becomes a test or a review question.

## 3. Glossary

- **Owner** — the human who approves gates. **Coordinator** — the agent session that routes work, records state and asks the owner. **Worker** — an agent session executing one unit of work.
- **Slice** — one reviewable change: ≤ ~150 new lines of code, ≤ 3 from-scratch parts, one layer (infrastructure / backend / interface). Larger → split.
- **Wave** — one round of independent review. **Lane** — one review perspective (code, tests, security, infrastructure, layout, docs).
- **Data class** — the most sensitive data a project handles: public · internal · personal data · secrets/credentials. Personal data proposes the critical profile and requires a personal-data scrubber for logs (created at `artel init` or onboarding) and discovery exclusions.
- **Verified release tag** — a `release-*` tag created only after the post-deploy smoke test and watch window passed; rollback targets the newest verified tag.
- **Session** — one agent context (a new chat or a reset), independent of orchestration runs. "Without an orchestration run" still allows several sessions.
- **Fast lanes** — the minimal lane set for an incident fix: code + tests (+ security if the fix touches auth, money or personal data).
- **Severity** — critical (data loss, security breach, prod outage, money error); major (wrong behaviour for users, failed acceptance criterion); minor (everything else).
- **Smoke test by change type** — the minimal post-deploy check for what changed: API → one request per changed endpoint; UI → open each changed screen; job/cron → one dry run; migration → schema version + one read/write; config → service healthy.
- **Calibration** — running candidate models on the owner's past tasks with known outcomes to admit a model to a role (§12).

## 4. Project profiles

Chosen at project creation or onboarding; proposed from signals in code and config, confirmed by the owner. Signals of authorisation, money, personal data or production clients force at least the standard profile and propose critical; lowering a profile is an owner decision.

| Profile | Typical | Essence |
|---|---|---|
| Light | bot, parser, internal utility without money/personal data | short brief+stack, short specs, minimal gates, no stage |
| Standard | product with users, no money or personal data | + architecture, roadmap gates |
| Critical | client production, personal data, money, migrations | full gate set, stage, owner acceptance |

Release cadence (each feature immediately vs a release train every N days) is a per-product setting.

## 5. Risk tiers

| Tier | Definition (by consequences) | Verification |
|---|---|---|
| T0-a | journals, handoffs, work notes, code comments | docs check only (links, size budgets, secret scan) — no test suite, no deploy |
| T0-b | documents people act on (status, specs, runbooks, rules) | one cheap review by another family; wave 2 only if wave 1 changed the result |
| T0-c | interface copy and styling without money, legal or consent wording | CI + visual check if user-visible |
| T1 | new or changed behaviour outside critical paths | two waves, other family; acceptance tests first (§9) |
| T2 | changes to existing behaviour that production users or integrations rely on; data-model changes | two waves at high effort; + T2 testing (§9) |
| T3 | authorisation, money, personal data, migrations, deployment mechanism, infrastructure, backups | all lanes regardless of triggers; security mandatory; + T3 testing (§9) |

**Never T0** (automatic escalation by path, enforced by a hook and a CI check): CI/CD workflow files, container and infrastructure definitions, environment files, secrets, feature flags, and any copy with money/legal/consent meaning. Infrastructure changes need the infrastructure lens from another family **and proof that the step works** (a run or a measurement). Turning on a feature flag needs a pre-registered measurement and a rollback plan. Rationale: one-line flag flips and workflow edits caused production incidents in the evidence projects; pure documentation did not (`evidence/INDEX.md` → t0).

## 6. Routes

### 6.1 Entry
The owner opens the project → a coordinator session (model per role matrix; higher effort for T2–T3). At start it loads: project status (≤ 4 KB), the current task pointer `STATE.md`, open owner questions, remaining limits per provider. Limits are checked again before every slice; slices run sequentially unless their file ownership is disjoint. First turn: "what are we doing?" — 1–3 questions classify route and tier; the coordinator states the plan and proceeds. Order of precedence: a production incident goes to Route I whatever the project's state; an unfinished Route O or Route A (its `STATE.md` exists and is not marked done) is resumed before anything else. Sessions the coordinator starts for one slice or one review follow their task packet and the hard stops; they do not re-run entry. A coordinator that takes over after an interrupted session first reconstructs the state from its traces — the pointer, uncommitted diffs in every worktree, commits newer than the pointer, orchestrator workers — and rewrites the pointer before continuing.

### 6.2 Route A — new product
1. Interview → brief (problem, users, which daily habit the product attaches to, value, success metrics, constraints, out of scope); interview completeness checked ≤ 3 times. → **Gate: brief** (light: the brief includes the stack choice and is approved as one gate).
2. Architecture and stack: data flows, data model, integrations, deploy target; versions and capabilities of the chosen libraries and services from current sources (§2.9); each decision as a record (decision · why · security · scalability · ≥ 2 real alternatives · "⚠️ needs validation" when data is missing); reviewed by another family. → **Gate: architecture+stack** (standard, critical).
3. Bootstrap: the owner creates the repository (or approves its creation) and registers it in the orchestrator; development and release branches; `artel init --adopt --protect`: project settings (profile, data class, tier-escalation paths, production-operations allow-list — only rollback by default), instruction-file block, agent fences and identity, release-branch protection; generated agent-instruction files. The CI skeleton and, if the data class is personal data, the personal-data scrubber arrive with the walking skeleton (step 5).
4. Roadmap: milestones → features. → **Gate: roadmap scope** (standard, critical).
5. Minimal walking skeleton = the first Route B change at T2: build + CI + deploy to the development environment + one smoke, one unit and one integration test. Monitoring, backups and a restore test arrive with real data, before the first production release.
6. Each feature = Route B. Before the first production release: readiness checklist → release gate. After that release Route A is done: its `STATE.md` is marked done and later work enters through Route B.

### 6.3 Route B — change (feature or bug), tiers T0–T3
1. **Intake**: what and why; duplicate check in the backlog; tier.
2. **Spec** (user-spec): T1 short, T2/T3 full; a bug = reproduction + failing test; T0 = none.
   - Interview in batches of 3–4 questions; completeness checked ≤ 3 times; code research before the spec.
   - Validation: round 1 — all lanes per role matrix; rounds 2–3 — only the delta; after round 3 open items go to the owner, who either approves with the open items recorded or orders round 4 (the counter never resets).
   - Approval only after validation. → **Gate: spec** (T1–T3).
3. **Slices** — a section inside the user-spec when the feature exceeds one slice: goal · acceptance criteria (each traced to a spec criterion) · files and ownership · tier · author model · series (infrastructure / backend / interface).
4. **Per slice** (fresh worker, fresh context, own worktree for code-editing workers):
   1. acceptance tests written first by a session other than the implementer (§9); protected;
   2. plan: reuse table, risks with `file:line`, "out of scope" (never empty — write "—"), external facts checked (library@version → source, §2.9), no research steps;
   3. implementation; unit tests by the implementer;
   4. reviewer set chosen **before** wave 1 (code / tests / security / infrastructure / layout / docs per triggers; all lanes at T3); each reviewer uses its own disposable test resources (never a shared test database);
   5. wave 1 — other family; finding format: location · evidence · trigger conditions · impact · `user_decision_required`; findings are diagnoses, not a work queue;
   6. fixes → wave 2 on the fix diff only → afterwards only targeted fix-and-verify, then an owner question; no wave 3;
   7. merge into the development branch (explicit coordinator step) → CI → automatic deploy to development/stage → smoke test by change type → the slice closes only when all required artefacts exist.
   - **T0** passes as one slice without spec and without orchestration run; verification per §5; ships with the next release. The light profile likewise runs without an orchestration run: the coordinator writes acceptance tests, implementation and review run in separate sessions (core §3 "session"), slices as needed.
   - **Scope check** (standard, critical): a slice criterion not traceable to the spec, or a diff over budget → **gate: scope change**. Light profile: the coordinator records the scope change in the spec.
5. **Feature done**: criteria verified on stage (critical) or development (light, standard); for UI — screenshots and an acceptance checklist for the owner; for operator-facing features — an audit "automate with an agent vs build UI"; project knowledge updated in the same change; release notes drafted.
6. **Release**: slices at T2–T3 whose review is marked "independence weakened" first get the pass by another family (§2.2); then an agent opens the release request (development → release branch) with scope, evidence, risks, rollback plan → CI green → the owner's yes in chat (the harness asks before the merge command runs; this is the release gate) → the agent identity merges → production deploy of exactly that revision (the deploy command asks the owner too, unless the operation is allowed without asking) → post-deploy smoke and watch window → verified release tag → close.

### 6.4 Route I — incident
1. Detect: product monitoring / availability check (not a scheduled model run).
2. **Contain — rollback without waiting for the owner**, via the pre-authorised rollback mechanism, under four conditions: (1) only to the newest verified release tag (core §3); (2) code only — data and schema never automatically; if the last release contained a migration, automatic rollback is allowed only if that migration was declared backward-compatible, otherwise ask the owner; (3) triggered by an objective signal (failing health check, error-rate rise, a reproducible failure of a user-facing flow); (4) the owner is notified immediately; recovery is verified after rollback. If the newest verified tag is the running revision, or any condition fails, there is no autonomous rollback: the owner gets a prepared forward-fix or revert plan. If recovery is not verified after rollback, autonomous actions stop and the owner decides.
3. Preserve evidence → diagnose (logs pass the project's personal-data scrubber; models never receive personal data — without a scrubber, the owner supplies excerpts free of personal data) → failing test → fix → two waves with fast lanes → **gate: hotfix release** → confirm recovery → post-mortem item in the backlog.
4. No provider switch during an incident: without an available reviewer of another family (or, under G1, of another model), stay rolled back.

### 6.5 Audit variant
"Find problems in X": choose the area first → gap table over 7 planes (security, integrations, data, error handling, observability, interface, settings — including "saved but never read") with explicit "not applicable" rows → **gate: which gaps** → each gap = a separate Route B change. Inside onboarding (O2) the audit stops at the gap table; the onboarding gate decides the gaps.

### 6.6 Route O — onboarding a project already in progress
For a project developed with another methodology or none, in production or not. Goal: understand the state, contain what is dangerous, sort out unfinished work, join without breaking anything.

Principles:
1. No change to the project before the onboarding gate — except emergency containment (O0.5), approved by the owner at intake.
2. Four distinct truths, never mixed: implemented behaviour (code), approved intent (approved specs), what runs in production (deploy and monitoring), live requirements (owner and clients). Code never replaces an approved spec.
3. Nothing is deleted. Only prior-methodology files are archived; links to them are rewritten; the archive never becomes a second source of truth (one live status file).
4. Existing documentation topology and working practices are kept; no rewriting "to fit the framework". An existing agent-instruction file is extended, not regenerated.
5. Discovery sees only version-controlled files minus an exclusion list (client materials, recordings, chat exports, secrets stay out of reach).
6. Depth follows the profile; the profile is proposed from code and config signals (§4); critical signals raise depth automatically; lowering is an owner decision.

Stages:
- **O0 Intake** (≤ 10 owner minutes): what the project is; what is in flight (branches, worktrees, open change requests, features); no-go areas; exclusion list; production operations agents perform today and which to keep without asking; whether to apply containment now. The profile is proposed after O1 from its signals and confirmed at the gate. Output: `work/onboarding/intake.md`.
- **O0.5 Emergency containment** (owner's yes at intake, any profile; reversible): remove direct production access, remote shells and pushes to the release branch from agent permissions — except operations kept in O0; close excluded paths to agents.
- **O1 Snapshot** — a script without model calls, repeatable: `as_of` (commit, time), branches, worktrees, uncommitted files, open change requests, CI health, branch protection, production deploy paths, permissions, hooks, skills, pinned models, document sizes, risk signals for the profile proposal. Output: `snapshot.json`.
- **O2 Read** by profile: light — skipped; standard — 1 agent; critical — ≤ 3 agents: architecture map; §6.5 audit over areas ranked by risk signals; executable-config inventory (hooks, skills, VCS hooks, pinned models: keep / replace / disable). Old documents are checked only if they route agents (instruction files, status, handoff); the rest is archived and verified when a slice touches a claim. Each direction has a stop condition (required topics evidenced or "not applicable" with a reason; the rest listed as accepted unknowns). Standard and critical also record a test baseline: the suite run three times, existing and flaky failures listed, so later slices can tell pre-existing failures from regressions.
- **O2a State report and confirmation** (the owner reads one page in plain language): where the project is (what runs in production, what is done, what is in progress), what lies ahead according to the project's own plans (approved specs and their slices, roadmap, backlog priorities), and where documents contradict the facts (each with a locator, e.g. "HANDOFF says PR #82 is open; it was merged on 2026-10-03"). Then confirmation questions in batches of 3–4 ("is X still the priority?", "is backlog item Y still relevant?"); answers are recorded in `work/onboarding/approvals.md`.
- **O2b Plan review**: every item of the pre-existing plan (spec slices, roadmap items, backlog priorities) gets a verdict — keep / adjust / add / drop — with the reason and evidence; items artel requires (e.g. rewriting production deploys, characterization tests, protection gaps) are listed separately as additions.
- **Onboarding gate (single)**: state at `as_of`; profile; the reviewed plan (O2b); in-flight ledger (per branch/worktree/feature: disposition and the next safe boundary); protection plan (including rewriting production deploys so they go only through the release branch — a T3 change — and the production-operations allow-list); gap priorities; documentation and backlog migration plan. Recorded in `work/onboarding/approvals.md`; progress in the `work/onboarding/STATE.md` pointer (stage, gate status, next step; resumable across sessions).
- **O3 Adopt and protect**: `artel init --adopt` (project settings, instruction-file block, agent fences and identity), generated instruction files regenerated; then `artel doctor`. Failures follow the contract's mapping: a secret within agent reach stops work until removed and rotated; VCS-host settings go to the owner; harness and reviewer failures exclude or degrade that harness or reviewer; the rest (production deploy rewrite — T3, owner guards, rollback mechanism, protected-test CI check, personal-data scrubber where the data class needs one) become Route B changes in the order the gate approved. Layers 1–2 are proven by real attempts (§10).
- **O4 In-flight work** per ledger: approved spec → adopted as is, with all its rules; no spec → "spec from reality" (what exists + owner-confirmed delta of intent + characterization tests pinning current behaviour); in the middle of a review wave → finish the wave, then switch. Boundary = "merged to the development branch" or "branch closed", never mid-wave. Done when every branch and worktree is merged, adopted or closed.
- **O5 Documentation**: keep the topology; index ≤ 50 KB; archive after a secret scan, databases with a text dump, links rewritten; backlog — verdict per item with evidence (open / done / superseded / duplicate), only open items migrate.
- **O6 Cutover**: rerun O1 into a new file and diff against the gate snapshot (onboarding's own files excluded); apply the executable-config inventory (each old hook, skill and VCS hook kept, replaced or disabled as approved). Done when no old hook or skill fires unplanned.
- **O7 First slices**: T0 first, then T1. Trust ramp: audit gaps fixed one per change with owner approval; the owner raises autonomy (unconfirmed execution, parallel slices) after the first slices pass both review waves without escaped defects.
- **Light profile**: O0 (+ O0.5 if approved) + O1 + a short O2a/O2b from the snapshot (state report, plan review, in-flight ledger, executable-config inventory from the snapshot's agent-config section) + gate + O3 + O4 for in-flight items + O6 + O7, in one session where possible.

Onboarding anti-patterns: trusting old documents and file dates; counting artel-generated files as project activity; scanning the whole project without ranking; fixing while auditing; big-bang migration; deleting or duplicating prior artefacts; refactoring to fit; discovery without a stop condition; state only in chat; "it doesn't exist" without an inventory; reviving cancelled concepts of the prior methodology; autopilot before trust is earned.

## 7. Owner gates

| Gate | Light | Standard | Critical |
|---|---|---|---|
| Brief and stack | ✓ (one step) | ✓ | ✓ |
| Onboarding (Route O, single gate) | ✓ | ✓ | ✓ |
| Architecture | — | ✓ | ✓ |
| Roadmap scope | — | ✓ | ✓ |
| Specs T1–T3 | ✓ short | ✓ | ✓ full |
| Production release | ✓ | ✓ | ✓ + stage and acceptance |
| Spend, new paid services (any recurring cost; one-off above the instance threshold, default 0) | ✓ | ✓ | ✓ |
| Sending anything outside (to people or systems outside the project: clients, public, third-party services receiving project data) | ✓ | ✓ | ✓ |
| New provider for code/data; secrets | ✓ | ✓ | ✓ |
| Changes to artel rules and agent permissions | ✓ | ✓ | ✓ |
| Irreversible operations on production data | — | ✓ | ✓ |
| Direct production access (remote shell, database) | — | ✓ | ✓ |
| Scope change mid-feature | — | ✓ | ✓ |
| Security exceptions, data-class changes | — | — | ✓ |

No gate: incident rollback (§6.4), T0 changes, deploys to development.
Rejection: a rejected gate returns the work to the previous stage with the owner's reasons recorded in `approvals.md`; the next submission states what changed.
A gate question must stop the coordinator and surface as "waiting for the owner" in the orchestrator UI (adapter-specific mechanism); the decision text is recorded in `work/<feature>/approvals.md`.

## 8. Roles and models

Roles: coordinator · spec writer · spec validator (adequacy / quality / facts) · architect · code explorer · implementer (backend / frontend) · acceptance-test author · reviewer (code / tests / security / infrastructure / layout / docs) · debugger · docs writer · mechanical worker.
The role → model matrix is **generated per user** from `artel.toml` (providers, subscriptions, families) and refined by calibration (§12). Selection criteria, in order: quality evidence for the role on the user's tasks > independent benchmarks for the closest task > cost per task and impact on the binding subscription limit. Flagship models at maximum effort are reserved for roles and tiers where evidence shows a gain ("no rocket for a nail").
**Model selection** is done by the matrix resolver, never from memory: each role has an ordered chain per tier group; `pick` takes the first candidate whose family the user has, that is not banned for the role, whose family is not exhausted or over the new-work threshold (90% of a usage window by default, set by the user), and — for review roles — that is not the author's model, preferring a family other than the author's. A role the current session cannot run is started as its own worker; the owner is never asked to switch models.
**Limit failover**: a provider running out mid-work is detected from the harness output together with the orchestrator's limit data. Reviews: the runner hands the wave to the next model with the partial wave file (findings and coverage written as the reviewer goes); the replacement confirms or rejects each finding and reviews the rest. Implementation: the slice's work in progress (worktree, uncommitted diff, test log) is handed to the next model of the implementer chain with a handover packet. Never during an incident without the owner.
Provider switch: at a unit-of-work boundary (between slices in Route B; between stages in Route A), or mid-work only through limit failover as above; never during an incident. The new role holder gets the same rights (Principle 1; e.g. an OpenAI-family implementer commits and pushes to the development branch itself), the same rules (generated instruction files from one source), the same hard stops (server side) and the same guard hooks — porting the guards to the new harness and passing `artel doctor` are preconditions for relying on a switch.

## 9. Testing policy

Default discipline: **acceptance tests first, then a mutation check** — not classic per-unit red-green TDD.
1. Each acceptance criterion of the spec becomes a test at the smallest boundary that reliably catches the risk. The test must fail on the base revision and pass after the change. Rationale: tests supplied up front raise agents' success rates; tests written by the implementer after the code tend to record what the code does rather than what it should do (`evidence/INDEX.md` → testing).
2. **Authorship.** Acceptance tests are written by a session other than the implementer's (coordinator or a dedicated test-author run); for T2–T3 they are reviewed in design mode before implementation. The implementer writes its own unit tests.
3. **Protection against gaming.** Acceptance-test paths are listed in the slice and protected: CI fails if the implementer's diff touches them; only the coordinator edits them, with a recorded reason (at T3 only with the owner's yes). A script flags removed tests or assertions and new skip/only/xfail markers for the reviewer. The implementer prompt says: "if a test contradicts the spec, stop and report; never edit tests to pass". Rationale: agents delete or bend failing tests; prompts and read-only tests cut this sharply (`evidence/INDEX.md` → testing).
4. **Test quality is checked by executing mutants on changed lines**, not by reviewer opinion. Reviewers propose mutants using a checklist (string and regex matching, comments, attribute values, set vs count, boundary values); the coordinator runs them and verifies file restoration by checksum; a surviving mutant is a finding. No global coverage or mutation-score percentage.

| Tier | Required |
|---|---|
| T0 | per §5; no new tests |
| T1 | acceptance tests first; test lane with the mutation checklist; executed mutants for changed logic in the critical profile |
| T2 | T1 + executed mutants on every changed decision line; integration tests against disposable instances of the real dependencies the change touches (database, filesystem, queue, external API sandbox); contract tests at every client/server or vendor seam |
| T3 | T2 + property or fuzz tests for parsers, money and authorisation input; where the system has persistent storage: migration up/down on a copy with data and a backup restore test; for infrastructure: plan/apply on a disposable environment; a negative control for every "nothing leaks" assertion |
| Bug / incident | a failing test on the pre-fix revision, linked in the change |

Profiles adjust the tier table (profile rules win where they differ): light — acceptance tests first for T1+, smoke test, unit tests for the core logic, failing test first for bugs, no executed mutants and no property tests at any tier, integration tests only where a database or external system is the risk; standard — executed mutants from T2; critical — executed mutants from T1, acceptance on stage.
Test levels (stack-agnostic): unit (one decision) · integration (real database / filesystem / queue) · contract (frozen sample of the other side's data checked against what is "required") · end-to-end (critical user journeys only) · visual/golden (pinned renderer, CI only) · smoke (per deploy, by change type). Web: HTTP API + browser; mobile: widget tests, goldens, device smoke; CLI: exit code + stdout/stderr contract; data/ML: fixture datasets, schema contracts, evaluation sets with tolerances declared in advance — model output is never asserted as an exact string.
Test data: synthetic only, seeded and deterministic; markers in "must not appear" checks must be impossible by chance; no production or personal data — not even as a planted positive control.
Flaky tests (pass and fail on the same revision): on onboarding the suite runs three times on unchanged code and existing failures become the baseline; quarantine is allowed in light and standard profiles for ≤ 14 days with a backlog item; never on T3 paths — every flake there is investigated as a possible race; failures from external feeds (vulnerability databases, network) run in separate labelled jobs.
CI gates: the full test job is a required check on the release branch and always runs (for docs-only changes it detects that and exits successfully — path filters on a required check leave it pending and block merges); the deploy gate requires every test job; mutation runs happen in review, not in CI, until their cost is measured.
New products: the walking skeleton ships one smoke, one unit and one integration test (against a disposable instance of its main dependency, if any). Onboarded projects: record the baseline (failures, flakes); add characterization tests only around code a slice is about to touch.
Not done: coverage percentages; mutation tooling, property tests or end-to-end for light projects; mocking the database where the database is the risk; shared test databases between reviewers; adopting a mutation tool for a stack before measuring its cost.

## 10. Protection

Five layers, each closing its own hole:
1. **Agent identity** — a separate VCS identity for agents with write access but no admin rights; the owner's credentials are not in agents' environment.
2. **Release gate in chat, enforced by the harness and the VCS host** (owner decision 2026-10-04: no manual approvals on the VCS host; works only if production is deployed exclusively from the release branch — where it is not, deployment is rewritten during onboarding as a T3 change): the VCS host requires a change request and the required CI checks for the release branch, forbids direct pushes, force-push and deletion; merging into the release branch, dispatching production workflows and re-running them are **ask rules** in every harness (Claude Code `permissions.ask`, Codex `decision = "prompt"`) — they stop the agent and ask the owner even in unconfirmed-execution mode (verified 2026-10-04: blocked when nobody can answer, unlisted commands run); after the owner's yes the agent identity merges or deploys. Residual risk, accepted by the owner: the host no longer refuses an agent merge by itself, so a write call outside the fenced command forms (e.g. a raw HTTP request with the agent's token) is not caught.
3. **Production operations of agents** — ask the owner by default, except rollback and the operations the owner lists at onboarding or `artel init` as allowed without asking.
4. **Rollback** — a pre-authorised mechanism that can only redeploy the newest verified release tag (§3; created after the post-deploy check of every gated release). Agents may trigger it; deploying production around the release branch is impossible.
5. **Local** (the VCS host cannot stop local reads): production secrets and personal data are absent from agents' environment and working copies — production secrets only in CI and on servers, locally only development values and synthetic data; harness hooks (secret protection, generated files, path denies) are an extra fence. If a user keeps client materials inside a working copy, this is recorded in the instance as an accepted residual risk with the mitigations used.

Data: the user's code may go to any provider the user allows; personal data never goes to any model; secrets never (absent per layer 5, plus secret scanning in CI).
**Unconfirmed execution** (harness modes that skip permission prompts) is an opt-in preset, allowed only after `artel doctor` has proven layers 1–2 and the layer-5 scan (no production secrets, no personal data outside declared and accepted exclusions) on the user's host (`docs/contract.md`, G2).

## 11. Documentation

Three layers by lifetime:
1. **Project knowledge** — durable truth (product, architecture, data model, integrations, operations, conventions); a router; one owner per fact; changed only at feature finalisation, inside the feature's change.
2. **Work artefacts** `work/<feature>/`: spec with slices, `STATE.md`, `approvals.md`, reviews; archived on completion.
3. **Journals**: one file per decision; release notes; review and delegation logs with structured fields (author model, reviewer model, tier, findings by severity, limit use), split by month.
Rules: size budgets enforced by hooks; no docs-only change requests; human README regenerated only when its sources change; an anti-patterns section in every skill. `STATE.md` is a pointer (≤ 4 KB, rewritten, not appended): orchestration run, tasks, open owner questions. If the orchestrator's state is lost, the task graph is rebuilt from the slice section of the spec and statuses from the VCS (merged branches) and `approvals.md`.

## 11a. Automation

Deterministic checks (production health, backups and restore, dependencies, vulnerabilities) run in the CI scheduler or host monitoring — never as model runs. Model-written outputs run as orchestrator automations or scheduled jobs: a morning digest (done / waiting for the owner / limits), a weekly limits and calibration report, a weekly backlog review, monthly lessons → rule candidates. Their data is gathered by scripts without model calls, a zero-token precheck skips runs when there is nothing new, and their prompts are read-only (proposals go to a file).

## 12. Learning and metrics

- Per feature: % of each provider's limit used, intake → release time, owner touches, review rounds, defects in production within 14 days.
- Admission rule (default, instance may tighten): a candidate is admitted when its result on the calibration set is at least the incumbent's (recall for review roles, verifier pass rate for implementation roles) at no higher cost on the binding limit; without an incumbent, after ≥ 3 calibration tasks with no critical miss.
- Calibration: before a model is admitted to a role, it runs on the user's past tasks with known outcomes (e.g. a past slice with known surviving mutants for test review; a past task with its original tests for implementation). Results go to the instance and regenerate the matrix.
- Monthly: lessons from structured logs → candidate rule/skill changes → owner approves.

## 13. Packaging

Target contents of a release (0.1.0 has the documents only): core, contract, adapters, skills, agents, templates, `artel.toml.example`, skills with their scripts, fixtures for gate-bearing skills, `CHANGELOG.md`, `LICENSE` and `NOTICE`. A user's instance (config, matrix, calibration, decisions, rollout) is private and not distributed. Supported in v1 (reference stack): Claude Code, Codex CLI, GitHub, Orca or no orchestrator. Other hosts and harnesses: contract only until someone uses them.
