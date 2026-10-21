---
name: artel-doctor
description: |
  Artel conformance check of a project: agent cannot push or merge to the release branch, production
  deploys only from it, rollback, no secrets in agent reach, instruction files in sync, reviewers
  pinned. Read-only; PASS / WARN / FAIL / MANUAL.

  Use when: "artel doctor", "проверь защиту артели", after `artel-init`, at onboarding O3, after any
  change to the harness, VCS host settings or permissions.
---

# Artel — doctor

Run `python3 <this skill dir>/scripts/doctor.py --repo .`; exit 1 = at least one FAIL. Contract:
[contract.md](references/contract.md). Show the owner the summary line and each FAIL and WARN with its
action — not the PASS rows.

| FAIL | Means | Action |
|---|---|---|
| 1–2 agent role / release ruleset / ask rules / agent token | the agent could change the release branch without the owner's yes | G2: no autonomous merges; fix host settings or ask rules |
| 3 prod environment | production can deploy from other branches | Route B change at T3 |
| 5 secrets / agent environment | a secret is within agent reach | **stop work** until removed and rotated (`secret-handoff`) |
| 6 instruction files | a harness gets stale rules | exclude that harness until regenerated |
| 7 reviewer pinning | a reviewer inherits the author's model | G1 for those reviewers until pinned |

WARN items (production secrets at repository level, a manually dispatched production workflow without
an owner guard, no rollback mechanism — G6) go to the onboarding plan review or the backlog with a
tier.

MANUAL items are proven once per change of the setting or tool version, with the date recorded in
`work/onboarding/approvals.md` or the instance log:
- **Live probe, checks 1–2**: the procedure in [github.md](references/github.md) ("Live probe") — as
  the agent, a direct push to the release branch is refused with `GH013`, and the merge command is
  blocked as needing the owner's yes in both harnesses.
- **Check 4**: the rollback mechanism takes no ref and resolves only the newest verified release tag
  (read it; dry run or stage — never a production redeploy).
- **Checks 8–10**: "Needs You" in the orchestrator, phone push, an orchestrator-launched harness reads
  the instruction file.
