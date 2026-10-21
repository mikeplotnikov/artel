---
name: artel-new
description: |
  Artel Route A: a new product from idea to first production release — brief, architecture and stack,
  bootstrap, roadmap, walking skeleton, then features through Route B and a readiness check.

  Use when: the owner starts a new product with artel ("новый продукт по артели", "new product with
  artel"), or the `artel` entry finds an empty directory or `work/product/STATE.md`.

  Do NOT use for: creating a project from a template outside artel (project-initialization).
---

# Artel — Route A (new product)

Progress pointer: `work/product/STATE.md` (create it in the working directory before step 1). A
provider switch is allowed between stages. If a step leaves a doubt,
[route-a.md](references/route-a.md) decides; release types are in
[release-types.md](references/release-types.md).

1. **Brief** — in a `spec_writer` worker started from `matrix.py pick --role spec_writer` (as in
   `artel-change` §3; the owner answers in its window): interview in batches of 3–4 (completeness checked ≤ 3 times) — problem, users, the daily
   habit the product attaches to, value, success metrics, constraints, out of scope. Propose the
   profile (money, personal data, production clients → at least standard). **Gate: brief** (light:
   brief + stack in one gate).
2. **Architecture and stack** (standard, critical): data flows, data model, integrations, deploy
   target and release type; versions and capabilities of the chosen libraries and services from current
   sources (Context7, DeepWiki, official docs), never from memory. Each decision: decision · why · security · scalability · ≥ 2 real
   alternatives · "⚠️ needs validation" when data is missing. Review by another family
   (`artel-review`). **Gate: architecture + stack.**
3. **Bootstrap**:
   1. The owner creates the repository (or says yes to `gh repo create <name> --private` run as the
      owner) and adds the project to the orchestrator.
   2. `git init` / clone; create the development and release branches; push both.
   3. `python3 <artel-init dir>/scripts/init.py --adopt --protect --profile <p> --data-class <c>
      [--check <CI job>]` — dry run, show the owner, then `--apply` (`--protect` needs the owner's
      admin login). Regenerate `AGENTS.md`; commit to the development branch.
   4. Move `work/product/` into the repository.
4. **Roadmap** (standard, critical): milestones → features, each a Route B change. **Gate: roadmap
   scope.**
5. **Walking skeleton** = the first Route B change at T2: build + CI skeleton + deploy to the
   development environment + one smoke, one unit, one integration test; if the data class is personal
   data, the personal-data scrubber for logs. Monitoring, backups and a restore test come with real
   data, before the first production release.
6. **Features** via `artel-change`. Before the first production release: readiness checklist
   (monitoring, backups with a restore test, rollback mechanism for the release type, secrets only in
   CI and on servers, `artel-doctor` without FAIL) → release gate. After that release mark
   `work/product/STATE.md` done — later work enters through `artel-change`.
