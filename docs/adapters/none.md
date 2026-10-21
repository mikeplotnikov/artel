# Adapter: no orchestrator (degradation G4)

- One coordinator session; slices run sequentially; reset context between slices (new session or `/clear`), resuming from `STATE.md` + VCS.
- Code-editing work in a separate worktree: `git worktree add ../<repo>-<slice> -b slice/<id> <dev-branch>`; remove after merge.
- Reviews: separate sessions with the reviewer model; never in the implementer's session.
- Stop-and-wait: the harness's own question prompt; the owner is notified by the harness only.
