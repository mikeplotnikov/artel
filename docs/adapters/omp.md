# Adapter: omp (third-family reviewer, headless)

Verified 2026-10-06 with omp 18.5.0 on macOS; DeepSeek through the direct DeepSeek API (`deepseek/deepseek-v4-pro` resolves to
provider `deepseek` — check the provider in `~/.omp/agent/sessions/<cwd>/*.jsonl`, since the same id also exists on OpenRouter).

- **Use**: reserve reviewer family (`roles.toml` `[policy] reserve_families`), picked only when no other candidate exists.
- **Launch** (from `matrix.py pick`): `omp -p <prompt> --model <id> --thinking <effort> --approval-mode write --mode text`, stdin
  closed (`</dev/null`) — without it omp waits on piped input ("Still starting … phase: readPipedInput").
- **Approval mode `write`**: file writes run; shell commands and `eval` are refused without a UI ("Tool \"eval\" requires approval
  but no interactive UI available"). The review runner therefore writes `git diff <base>..<head>` to the lane's `.diff` file and
  tells the reviewer to read it. Mode `yolo` is not used (owner rule for omp).
- **No Orca agent** for omp: it always runs headless through the review runner.
- **Limit / balance exhaustion**: no verified signature — an omp reviewer that stops without `## Done` is reported `failed`
  (no handover); the coordinator decides.
- **Calibration** (C1 test-review set, 2026-10-06): `deepseek-v4-pro` high 2/7, `deepseek-v4.1-flash` high (OpenRouter) 0/7
  formal (saw three holes, dismissed them). Live review of this adapter's own code: 2 valid minor findings.
