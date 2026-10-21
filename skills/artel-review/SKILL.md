---
name: artel-review
description: |
  Artel review waves for a slice or a spec in a project on artel: reviewer set chosen before wave 1,
  reviewers from another model family, finding contract, wave 2 on the fix diff, then stop.

  Use when: `artel-change`, `artel-new` or `artel-onboard` reaches a review step, or the owner asks for
  an artel review wave ("первая волна", "вторая волна") in a repository with `.artel/project.toml`.

  Do NOT use for: ad-hoc code review or a Codex second opinion outside artel (code-reviewing,
  codex-delegation).
---

# Artel — review

## 1. Who reviews

- **Another family** than the artefact's author. Model, effort and launch command come only from
  `python3 <artel skill dir>/scripts/matrix.py pick --role reviewer_<lane> --tier <t01|t23> --author
  <author model id> --json` — it prefers another family, never returns the author's model, skips
  exhausted families and sets `independence_weakened` when only the author's family is left.
- **Run each lane with the runner**, in the background: `python3 <this skill dir>/scripts/review_run.py
  --repo . --feature <f> --lane <lane> --wave <K> --role reviewer_<lane> --tier <t01|t23> --author
  <author model id> --base <ref> --head <ref> --checklist "<lane checklist>"`. It picks the reviewer,
  launches it headless, and when the reviewer's provider runs out of limit mid-wave it hands the same
  wave file to the next model of the chain (`independence_weakened` when that is the author's family).
  Read its status JSON: `done` → findings; `failed`, `no_candidate`, `scope_violation` → decide or ask
  the owner. **Single-family setup (G1)**: as above, always weakened; T3 additionally needs a human or
  another-family API review.
- **Launch**: Claude Code reviewer agents (`code-reviewer`, `test-reviewer`, `security-auditor`,
  `infrastructure-reviewer`, `layout-reviewer`, `documentation-reviewer`) are Anthropic-family;
  `codex-reviewer` or `codex exec -m <model> -c model_reasoning_effort=<effort> --sandbox read-only`
  is OpenAI-family; from Codex, `claude -p --model <model>` gives an Anthropic review. With Orca, a
  separate worker with `--agent` and `--model`; check `launch.effective`.
- Each reviewer gets its own disposable test resources — never a shared test database.

## 2. Reviewer set — fixed before wave 1

Code (always) · tests (tests changed or acceptance tests added) · security (auth, input, secrets,
personal data, money, external calls) · infrastructure (CI/CD, containers, environment, deploy,
backups) · layout (UI) · docs (T0-b documents). **T3: all lanes.**

## 3. Finding contract

Every reviewer prompt includes the contract in [lane-prompt.md](references/lane-prompt.md): findings
and a coverage log are appended to `work/<feature>/reviews/wave-<K>-<lane>.md` as the reviewer goes,
and a `## Done` line closes the file — so an interrupted wave can be handed over.

Each finding: location · evidence · trigger conditions · impact · `user_decision_required`. Findings
are diagnoses: the coordinator validates each; the implementer fixes the agreed ones; the owner is
asked where `user_decision_required` is true or a fix changes scope or behaviour. The test lane runs
executed mutants only where `artel-testing` §3 requires them.

## 4. Waves

1. Wave 1 on the slice diff, full set. 2. Fixes by the implementer. 3. Wave 2 on the fix diff only,
fresh context, other family; low/medium effort at T0–T1, high at T2–T3. 4. After wave 2 only targeted
fix-and-verify, then an owner question — **no wave 3**. 5. Save each wave to `work/<feature>/reviews/`
and one row per wave to the review log: date · project · lane · author model · reviewer model/effort ·
tier · findings by severity · what wave 2 caught · limit used · reviewer replaced mid-wave (from → to,
reason) · independence weakened · pre-release pass (done / not needed).

T0-b: one cheap review, wave 2 only if wave 1 changed the result. T0-a, T0-c: no review.
