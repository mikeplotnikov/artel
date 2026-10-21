---
name: artel-audit
description: |
  Artel audit of one area of a project on artel: a gap table over seven planes before anything is
  fixed, an owner gate on which gaps to fix, one Route B change per gap. Also the gap table of
  onboarding.

  Use when: the owner asks to find problems in a module or flow of a repository with
  `.artel/project.toml` ("проведи аудит модуля", "найди проблемы в …"), or `artel-onboard` step 4
  needs the gap table.

  Do NOT use for: an OWASP security review of changed code (security-auditor); whole-project reviews
  outside artel.
---

# Artel — audit

If a step leaves a doubt, [audit.md](references/audit.md) decides.

1. **Choose the area** (module, flow, service). In onboarding, rank areas by the snapshot's risk
   signals (money, personal data, auth, migrations, deploy) and take them in that order.
2. **Gap table over seven planes**: security · integrations · data · error handling · observability ·
   interface · settings (including "saved but never read"). Each plane gets findings or "not
   applicable — because …". Each finding: `file:line`, evidence, trigger conditions, impact, severity
   (critical / major / minor).
3. **Save** to `work/<area>-audit/audit.md` (in onboarding: `work/onboarding/audit.md`). Do not fix
   while auditing. **Inside onboarding stop here** — the onboarding gate decides the gaps.
4. **Gate: which gaps to fix**, in what order.
5. **Each chosen gap = a separate Route B change** (`artel-change`).
