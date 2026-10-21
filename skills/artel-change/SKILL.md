---
name: artel-change
description: |
  Artel Route B: a feature or a bug in a project on artel, at risk tier T0–T3 — spec, acceptance tests
  first, slices in fresh workers, two cross-family review waves, merge to the development branch,
  release request approved by the owner.

  Use when: the `artel` entry routes a change here, or the owner asks for a feature, bug fix or the
  next slice in a repository with `.artel/project.toml`.

  Do NOT use for: repositories without `.artel/project.toml` (use the regular code-writing workflow).
---

# Artel — Route B (change)

The `artel` entry has already stated route, tier, profile and models — do not repeat that. Feature
folder: `work/<feature>/` with `user-spec.md`, `STATE.md`, `approvals.md`, `reviews/`. If a step
leaves a doubt, [route-b.md](references/route-b.md) decides; tier verification T0-a/b/c is in the
`artel` skill's `references/core-rules.md` §5.

## 1. Intake

Check the backlog (GitHub Issues or the project's backlog file) for a duplicate; link it.

## 2. T0 — short path

One slice, no spec. Verify by tier and close: **T0-a** docs check only (no test suite, no deploy);
**T0-b** one cheap review by the other family (`artel-review`); **T0-c** CI + a visual check. Commit
and push to the development branch; it ships with the next release. Done — skip §3–§6.

## 3. Spec (T1–T3, bugs)

- **Bug**: the spec is the reproduction plus a test that fails on the pre-fix revision.
- **T1** short spec, **T2/T3** full spec, written by the `spec_writer` role in its **own session**:
  `matrix.py pick --role spec_writer --tier <t01|t23> --json` → with Orca, start a worker with
  `launch.orca` + `--spec <packet> --worktree current` (packet: the request in the owner's words, links to code research and sources, the
  `user-spec-planning` rules below; allow the Orca reporting commands). The owner answers the interview
  in that worker's window; the coordinator never asks the owner to switch `/model`. Without an
  orchestrator (G4): open a separate harness session with the `launch` command for its harness and
  tell the owner where to answer. The worker runs
  `user-spec-planning` with these rules on top — interview in batches of 3–4, completeness checked ≤ 3 times, code research before drafting; validation round
  1 runs all lanes (adequacy, quality, facts; at least one lane from the other family), rounds 2–3
  check only the delta; after round 3 open items go to the owner, who approves with them recorded or
  orders round 4. **Gate: spec**.
- **Slices** (when the feature exceeds one): a slice section in the user-spec — goal · acceptance
  criteria traced to the spec · files and ownership · tier · author model · series (infrastructure /
  backend / interface). Size ≤ ~150 new lines, ≤ 3 from-scratch parts, one layer; producers before
  consumers.

With Orca: one Run per feature, one Task per slice with dependencies
([orca.md](references/orca.md)); light profile runs without a Run.

## 4. Per slice — fresh session or worker; code-editing work in its own worktree

1. **Acceptance tests first** by a session other than the implementer's (`artel-testing`).
2. **Plan** `work/<feature>/plan-<slice>.md`: reuse table, risks with `file:line`, out of scope (never
   empty — write "—"), **external facts** — each library/SDK/API/CLI the slice calls, with the version in
   use and the source checked (Context7 for how to call it, DeepWiki for why it behaves so; unchecked →
   "unverified (from memory)" plus a test or a review question), no research steps. Copy these lines into the
   implementer's task packet.
3. **Implement** with the implementer model; unit tests by the implementer; protected tests untouched
   — if one contradicts the spec, stop and report. **Limit handover**: if the implementer's provider
   runs out mid-slice (its limit message; Orca limits), pick the next implementer with that family
   excluded (`matrix.py pick --role implementer_<…> --tier … --exclude-family <family>`) and start it in
   the same worktree with a packet: the slice goal and criteria, `git diff` of the work so far, the last
   test run, "verify what exists, then finish". Record the handover in `STATE.md`.
4. **Review** — `artel-review`. The **implementer** makes the fixes; the coordinator validates findings
   and asks the owner where needed. Infrastructure changes also need proof the step works; a feature
   flag flip needs a pre-registered measurement and a rollback plan.
5. **Merge** into the development branch → CI green → automatic deploy to development/stage where the
   project has one → smoke test by change type.
6. **Close** when plan, tests, review results and CI link exist; rewrite `STATE.md`. Standard and
   critical: a criterion not traceable to the spec or a diff over budget → **gate: scope change**;
   light records the change in the spec.

## 5. Feature done

Acceptance criteria verified on stage (critical) or development (light, standard); UI: screenshots and
a checklist for the owner; operator-facing: "automate with an agent vs build UI" note; project
knowledge updated in the same change; release notes drafted.

## 6. Release

First, in a multi-family setup, every T2–T3 slice in the release whose review says "independence weakened"
(by limit failover) gets a pass by another family (`artel-review`, wave on the slice diff) once that family's limit is back; the release
request waits for it, the development branch does not. Then the agent account opens the release request
(development → release) with scope, evidence, risks,
rollback plan → CI green → **ask the owner in chat** (release gate: one message — what goes out, risk,
rollback) → after the yes, the agent account merges (`gh pr merge`; the harness asks once more) →
production deploy of exactly that revision by the agent account (ask rule) or an allowed operation →
post-deploy smoke and watch window → verified release tag → close. Cadence from `.artel/project.toml`.
