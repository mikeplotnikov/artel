---
name: artel-testing
description: |
  Artel testing in a project on artel: acceptance tests written before the code by another session and
  protected from the implementer, required test levels by tier and profile, test quality proven by
  executed mutants on changed lines.

  Use when: `artel-change` reaches the test step of a slice, a reviewer proposes mutants, or the owner
  asks about tests, mutants or flaky tests in a repository with `.artel/project.toml`.

  Do NOT use for: test strategy in projects without artel (test-master).
---

# Artel — testing

What each tier and profile requires (tier table, profile adjustments, test levels, data, flakiness,
CI gates) is in [testing-policy.md](references/testing-policy.md) — read it once per slice to pick
the required tests. This skill is the procedure.

## 1. Acceptance tests first (before implementation, T1+)

1. Author: a session with the `acceptance_test_author` role (`matrix.py pick --role
   acceptance_test_author --tier <t01|t23>`) — never the implementer's session.
2. One test or more per acceptance criterion, at the smallest boundary that reliably catches the risk.
3. Run them on the base revision: each must **fail**; save the failing output to the slice artefacts.
4. T2–T3: the test reviewer (other family) reviews them in design mode before implementation.
5. List their paths in the slice as **protected**. The implementer prompt says: "If a test contradicts
   the spec, stop and report; never edit tests to make them pass." Only the coordinator edits
   protected tests, with the reason in `approvals.md`; at T3 only with the owner's yes.

## 2. Before merge

- `git diff --name-only <base>...HEAD` must not touch protected paths — the coordinator checks this
  until the project's CI does it (the CI check is an onboarding addition, Route B).
- Flag removed tests or assertions and new skip/only/xfail markers to the reviewer.
- A failure listed in `work/onboarding/test-baseline.md` is pre-existing, not the slice's regression;
  anything else is.

## 3. Executed mutants

Required: **critical** profile from T1, **standard** from T2, **light** never.
1. The test reviewer proposes mutants for changed decision lines: string and regex matching, comments
   and attribute values, boundary values, set vs count, missing branches, error paths.
2. Write them as JSON (`[{"id","file","find","replace","why"}]`, each `find` matching exactly once) and
   run `python3 <this skill dir>/scripts/mutate.py --mutants mutants.json --test "<test command>"`.
3. Exit 1: mutants survived — each survivor is a finding. Exit 2: harness problem (red control run,
   an invalid mutant, failed restoration) — fix and rerun; survivors in the same report still count.
   Exit 0: all killed. Mutation runs happen in review, not in CI.

## 4. Flaky tests

Quarantine ≤ 14 days with a backlog item in light and standard; never on T3 paths — investigate as a
possible race.
