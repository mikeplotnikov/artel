# Evidence index

Every normative claim in `docs/` that rests on an external fact points here. Third-party texts are not copied into this repository: each entry gives the source URL, the fetch date, the sha256 prefix of the copy that was checked during research, and the claim it supports (paraphrased). All URLs in this index returned HTTP 200 on 2026-10-04; `market/sources.tsv` also records fetches that failed (status column).
Owner-specific evidence (calibration, audits of private projects, cross-model reviews) lives in the author's private instance and is not published.

## t0 — risk of "trivial" changes
- Derived from the owner's private project history (path-based classification of 2,505 commits — 1,471 + 1,034 — and their CI runs; positive control: a known flag-flip incident was found). Summary in core §5; concrete incident commits are kept in the author's private instance (not published).

## testing
| Source | Fetched | Claim supported |
|---|---|---|
| https://arxiv.org/abs/2402.13521 | 2026-10-04 | Supplying tests together with the task raises LLM code-generation success. |
| https://arxiv.org/abs/2410.21136 | 2026-10-04 | LLM-written assertions tend to record the code's actual behaviour rather than the intended one. |
| https://arxiv.org/abs/2510.20270 (ImpossibleBench; html sha256 f7b2b8e7…, text extract 1588c9bc…) | 2026-10-04 | Agents with test access may delete or bend failing tests; prompt wording reduced one model's cheating from 92% to 1% on one benchmark; hiding tests reduces cheating to near zero; vendors differ (special-casing vs editing tests). |
| https://arxiv.org/abs/2102.11378 | 2026-10-04 | Mutation testing at scale is applied to changed lines in code review, with mutant filtering, rather than as a global score. |
| https://code.claude.com/docs/en/best-practices | 2026-10-04 | Vendor guidance: reproduce a bug with a failing test first; one agent writes tests, another writes the code. |
| `evidence/testing/SOURCES.tsv` | 2026-10-04 | Full list of testing sources with sha256 (incl. arXiv 2505.09027, 2412.02883, 2503.15223, 2501.12862, 2510.09907, Google Testing Blog on flaky tests). |

## market (model choice)
| Source | Fetched | Claim supported |
|---|---|---|
| https://artificialanalysis.ai/agents/coding (page payload sha256 206bc557…, extracted records 2145ca1f…; table `evidence/market/aa_table.txt`) | 2026-10-03 | Coding-agent index by harness+model+effort, with cost per task; effort level changes score and cost more than model choice within a tier. |
| https://developers.openai.com/codex/pricing | 2026-10-03 | Codex Pro has no five-hour limit (weekly limits may apply); GPT-5.5 retires from Codex on 2026-10-14. |
| `evidence/market/sources.tsv` | 2026-10-03 | All vendor pricing/model pages used, with sha256. |

## tools
| Source | Fetched | Claim supported |
|---|---|---|
| https://code.claude.com/docs/en/hooks (sha256 755e3035…) | 2026-10-03 | SessionStart supports a `compact` source; PreToolUse hooks can block. |
| https://code.claude.com/docs/en/model-config (sha256 a1f50535…) | 2026-10-03 | `autoCompactWindow` setting (e.g. 200000) controls the auto-compaction threshold. |
| https://code.claude.com/docs/en/authentication (sha256 5117e406…) | 2026-10-03 | An API key outranks subscription login; a separate config directory isolates logins. |
| https://code.claude.com/docs/en/statusline | 2026-10-03 | Status line can show context usage. |
| https://developers.openai.com/codex/hooks (sha256 724881d8…) | 2026-10-03 | Hook errors, timeouts or malformed responses mark the hook failed and continue the tool call; hooks are a guardrail, not a complete enforcement boundary. |
| https://developers.openai.com/codex/subagents | 2026-10-03 | A subagent without a configured model inherits the parent's model and effort. |
| https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/approving-a-pull-request-with-required-reviews (sha256 7ea58f94…) | 2026-10-03 | Pull-request authors cannot approve their own pull requests. |
| https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment | 2026-10-03 | On Free/Pro/Team plans, environment required reviewers are available only for public repositories. |
| https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets | 2026-10-03 | Rulesets are available for private repositories on GitHub Pro. |
| https://www.onorca.dev/docs/cli/automations | 2026-10-03 | Orca automations: scheduled prompts, precheck, missed-run grace, remote host. |
| Claude Code 2.1.285 and codex-cli 0.159.3 (`--version`, `--help`) | 2026-10-03 | Harness versions the adapters were verified on. |
| Orca CLI 1.4.218 `--help`, bundled guides (`orca skills get orchestration`, `orca-cli`) | 2026-10-03 | worker-start flags and supported agents, `launch.effective`, `run-use`, nesting depth, account limits, dashboard "Needs You" only for structured prompts, default permission-bypass args. |
