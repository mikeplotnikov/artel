# Adapter: GitHub (VCS host)

Verified 2026-10-03/04 on GitHub Pro with private repositories (personal account); see `evidence/INDEX.md`
→ tools and the reference instance's phase 1 log.

- **Agent identity (layer 1)**: a machine user (or a GitHub App) with **Write** on the repository, never
  Admin or Maintain. On repositories owned by a personal account a collaborator needs a **classic token**
  (fine-grained tokens of another user do not reach them); scopes `repo` and `read:org` only. **Never the
  `workflow` scope**: without it the agent cannot push changes to `.github/workflows/`, so it cannot
  rewrite the pipeline that guards production. Agent sessions select the identity with
  `GH_CONFIG_DIR=<agent gh config>`; the repository's local git credential helper is
  `gh auth git-credential`, so the same checkout pushes as the owner in the owner's terminal and as the
  agent in agent sessions (`artel-init --identity`).
- **Release gate (layer 2)**: ruleset on the release branch — require pull request (**0 required approvals**:
  the owner approves in chat, owner decision 2026-10-04), required status checks (full test job), block
  force-push and deletion; the only bypass actor is the repository admin role in pull-request mode. The
  owner's yes is enforced by the harness: `gh pr merge`, write calls of `gh api`, `gh workflow run` for
  production and `gh run rerun` are ask rules (Claude Code `permissions.ask`, Codex `decision = "prompt"`),
  which stop the agent even in unconfirmed-execution mode. The agent identity then merges. On
  Free/Pro/Team, environment required reviewers work only for public repositories, so they are not used.
- **Production deploy (layer 3)**: an environment (e.g. `prod`) with a deployment branch policy that
  allows only the release branch (this works on private Pro repositories); production secrets live in
  that environment, not at repository level, so a workflow on another branch cannot read them. Deploy on
  push to the release branch. A manually dispatched workflow that can reach production gets an owner
  guard: a first job that fails unless `github.triggering_actor` is the owner or the agent account (for re-runs, `actor` is
  the original author and `triggering_actor` the person re-running; runs can be re-run for 30 days), plus
  a `concurrency` group per environment. Agents dispatch or re-run production workflows only after the owner's yes (ask rules), except the
  operations listed in `.artel/project.toml` → `prod_operations_allowed`.
- **Rollback (layer 4)**: a `rollback` workflow without inputs that resolves the newest verified
  `release-*` tag (tags are created only after the post-deploy check passes) and redeploys it; it cannot
  take an arbitrary ref; schema downgrades are not part of it.
- **Live probe (doctor checks 1–2, manual)**: in a temporary clone, as the agent identity: (1) a probe branch
  with one empty commit and `git push origin HEAD:<release>` — expected refusal `GH013`; (2) in an agent
  session without anyone to answer (`claude -p … --dangerously-skip-permissions`, `codex exec
  --dangerously-bypass-approvals-and-sandbox`), `gh pr merge --help` must be refused as needing approval,
  and an unlisted command (e.g. `gh pr list`) must run; (3) delete the probe branch, confirm the release
  head is unchanged. Record the date. Repeat after any change to rulesets, ask rules or harness versions.
- **Backlog**: GitHub Issues (labels: route, tier, profile; milestones). `Closes #N` links issues to PRs.
- **Scheduled checks**: Actions `schedule` (cron offset from :00; runs on the default branch) for
  health/backup checks; Dependabot for dependencies and vulnerabilities.
- **CI cost**: the required test job always runs; on docs-only changes it detects that (e.g. a
  changed-files step) and exits successfully after a light docs check. Do not put `paths-ignore` on a
  required check — skipped required checks stay pending and block merging.
