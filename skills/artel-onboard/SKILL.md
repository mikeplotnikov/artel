---
name: artel-onboard
description: |
  Artel Route O: brings a project already in progress onto artel — read-only snapshot, one-page state
  report with confirmation questions, review of the existing plan, one owner gate, then adoption,
  protection, unfinished work, documentation and cutover.

  Use when: "подключи артель к проекту", "первый запуск артели", "переведи проект на артель",
  "onboard this project to artel", or the `artel` entry finds no `.artel/project.toml` in a
  repository with history.

  Do NOT use for: user onboarding features inside a product ("онбординг пользователей").
---

# Artel — Route O (onboarding)

Work in `work/onboarding/`. Resume point: `work/onboarding/STATE.md` (stage, gate status, next step) —
on start, read it and continue from the recorded stage. If the steps below leave a doubt, the spec
text in [route-o.md](references/route-o.md) decides.

**Until the gate nothing in the project changes** — code, settings, branches, docs — except the
containment the owner approves in step 2 and the files in `work/onboarding/`.

## Depth

Profile is proposed in step 3 from the snapshot and confirmed at the gate; critical signals (money,
personal data, production clients) raise depth automatically, only the owner lowers it.
- **Light**: steps 1–3; a short 5–6 from the snapshot alone (no reading agents) — including the
  executable-config inventory from its `agent_config` section; then 7, 8, 9, 11 (no O5).
- **Standard**: all steps, one reading agent. **Critical**: all steps, up to three reading agents.

## Steps

1. **O0 Intake** (≤ 10 owner minutes, one batch). First pre-fill from files, each fact with a locator,
   and read the **current fences**: `python3 <artel-init dir>/scripts/init.py --contain --diff` (dry
   run) — Read-deny paths already present are exclusions already; deny rules already present are
   containment already done; ask only about what is missing. Counts (branches, worktrees, commands)
   come from a command, never from estimation. Then ask: what the project is, in production or not;
   what is in flight; no-go areas; paths agents must never read (client materials, recordings, chat
   exports, secrets); production operations agents perform today and which to keep; apply the missing
   containment now? Write `intake.md` ([format](references/templates.md#intakemd-o0)).
2. **O0.5 Containment** (owner's yes, any profile): `python3 <artel-init dir>/scripts/init.py
   --contain --exclude <path>… --allow-op <kept workflow>…`, dry run first, then `--apply`. Show what
   was added.
3. **O1 Snapshot**: `python3 <this skill dir>/scripts/snapshot.py --repo . --out
   work/onboarding/snapshot.json --exclude <path>…`. No model, repeatable. Note `as_of` and the
   proposed profile in `STATE.md`.
4. **O2 Read** (standard, critical). Each reading agent reads only tracked files outside the
   exclusions and has a stop condition (required topics evidenced, or "not applicable" with a reason;
   the rest listed as accepted unknowns): (a) architecture map — data flows, data model,
   integrations, deploy paths; (b) gap table with `artel-audit` over the areas ranked by the
   snapshot's risk signals — **table only, no gate, no fixes**; (c) executable-config inventory —
   hooks, project skills, VCS hooks, pinned models: keep / replace / disable each. Old documents are
   checked only if they route agents. Also record the **test baseline**: run the suite three times,
   list existing and flaky failures in `test-baseline.md`.
5. **O2a State report** (`state-report.md`, [format](references/templates.md#state-reportmd-o2a--one-page-plain-language)):
   one page in the owner's language — what runs in production, what is done but not released, what is
   in progress, what lies ahead by the project's own plans, where documents contradict facts (each
   with a locator). Show it, then confirmation questions in batches of 3–4; record answers in
   `approvals.md`.
6. **O2b Plan review** (`plan-review.md` + in-flight ledger, [format](references/templates.md#plan-reviewmd-o2b)):
   each item of the existing plan — spec slices, roadmap, backlog priorities, open branches and
   worktrees — gets keep / adjust / add / drop with reason and evidence. List separately what artel
   requires: production deploys only through the release branch (T3), owner guards on manually
   dispatched production workflows, rollback mechanism, protected-test CI check, personal-data
   scrubber if the data class needs one, gaps from step 4.
7. **Onboarding gate (single)** — one `AskUserQuestion`: state at `as_of`, profile, reviewed plan,
   in-flight dispositions, protection plan with the production-operations list, gap priorities,
   documentation and backlog migration. Record in `approvals.md`; set the gate status in `STATE.md`.
   On rejection, return to the stage the owner names.
8. **O3 Adopt and protect**: `init.py --adopt` with the approved settings (dry run, then `--apply`);
   regenerate `AGENTS.md` from `CLAUDE.md` with the project's sync tool; commit `.artel/project.toml`,
   `CLAUDE.md`, `AGENTS.md` to the development branch. Run `artel-doctor` and act on its mapping: a
   secret in agent reach **stops work** until removed and rotated; VCS-host settings go to the owner;
   harness and reviewer failures exclude or degrade that harness or reviewer; the rest become Route B
   changes (`artel-change`) in the order the gate approved. Run the manual live probe for layers 1–2.
9. **O4 In-flight work** per the ledger: approved spec → adopted as is; no spec → "spec from reality"
   (what exists + owner-confirmed delta + characterization tests); mid-review-wave → finish the wave
   first. Boundary: merged to the development branch or branch closed.
10. **O5 Documentation**: keep the topology; index ≤ 50 KB; archive prior-methodology files after a
    secret scan, rewrite links; backlog items get a verdict, only open ones migrate.
11. **O6 Cutover**: snapshot into `work/onboarding/snapshot-cutover.json`, diff against the gate
    snapshot (ignore `work/onboarding/` and artel's own files), show the owner what changed since the
    gate. Apply the inventory by hand — disable or replace each old hook, skill and VCS hook as
    approved. Done when no old hook or skill fires unplanned. Then **O7**: a T0, then a T1 via
    `artel-change`; audit gaps one per change; the owner raises autonomy after the first slices pass
    both review waves without escaped defects. Mark `STATE.md` done.

## Anti-patterns

Trusting old documents or file dates; counting artel files as project activity; scanning without
ranking; fixing while auditing; big-bang migration; deleting or duplicating prior artefacts;
refactoring to fit; discovery without a stop condition; state only in chat; "it doesn't exist" without
an inventory; reviving cancelled concepts of the prior methodology; autopilot before trust is earned.
