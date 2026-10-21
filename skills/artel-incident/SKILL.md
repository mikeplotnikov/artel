---
name: artel-incident
description: |
  Artel Route I: production of a project on artel (or being onboarded to it) is broken — contain with
  a pre-authorised rollback, preserve evidence without personal data, fix with a failing test, ship the
  hotfix through the owner's gate.

  Use when: "прод упал", "инцидент", "ошибка в проде", "production is down", "hotfix", or monitoring
  reports an outage, in a repository with `.artel/project.toml` or `work/onboarding/`.

  Do NOT use for: non-production bugs (artel-change); projects without artel.
---

# Artel — Route I (incident)

Contain first, fix second. If a step leaves a doubt, [route-i.md](references/route-i.md) decides.

1. **Confirm the signal**: a failing health check, an error-rate rise, or a reproducible failure of a
   user-facing flow — never an agent's impression. Notify the owner at once (what fails, since when).
2. **Contain — rollback without waiting for the owner**, only through the project's rollback mechanism
   (the allowed operation in `.artel/project.toml`) and only if all hold:
   1. the target is the newest verified release tag **and it is not the running revision**;
   2. code only — data and schema never; if the running release has a migration, only when it was
      declared backward-compatible;
   3. the trigger is the signal from step 1;
   4. the owner is notified, and recovery is verified after rollback.
   If any condition fails or there is no mechanism (G6): no autonomous rollback — give the owner a
   prepared forward-fix or revert plan. If recovery is not verified after rollback: stop autonomous
   actions; the owner decides.
3. **Evidence**: logs, the failing request, versions — through the project's personal-data scrubber
   before any model sees them. No scrubber: ask the owner for excerpts without personal data.
4. **Diagnose → a test that fails** on the pre-fix revision. When a library behaves unexpectedly, ask its
   code wiki (DeepWiki) or read its source before reasoning from memory.
5. **Fix** (implementer) with the fast lanes: code + tests, + security if auth, money or personal data
   are touched; two waves by another family (`artel-review`, runner with `--max-handovers 0`: during an incident a
   limit does not switch providers — the wave stops and you stay rolled back; G1: another model, marked).
6. **Gate: hotfix release** — the owner's yes in chat; merge and production deploy as in Route B.
7. **Confirm recovery**; add a post-mortem item to the backlog: what failed, why it was not caught,
   which test or check catches it now.

No provider switch during an incident: without a reviewer, stay rolled back.
