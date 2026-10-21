# Review lane prompt — contract (artel-review §3)

Paste this block into every reviewer's prompt, with the placeholders filled. It makes the review resumable: if the
reviewer stops mid-wave (a provider limit, a crash), everything it has found so far is already on disk, and the
replacement reviewer continues from the file instead of starting over.

```text
You are the <lane> reviewer, wave <K>, for slice <slice> of work/<feature>/ (tier <tier>).
Review the diff <base>..<head> in this repository. Diagnose only — never edit project files.

Write your work to work/<feature>/reviews/wave-<K>-<lane>.md AS YOU GO, not at the end. The file is your
only durable output: if you stop mid-review, whatever is not in the file is lost. One tool call per step:
your FIRST tool call creates the file; each finding and each coverage line is its own append (a separate
edit/write call) made right when you reach it — never compose the file in your head and write it once.
1. First tool call — create the file with this header:
   # Wave <K> · <lane> · reviewer <model id>@<effort> · started <ISO time>
   ## Findings
   ## Coverage
2. The moment you are confident about a finding, append it under "## Findings" — one block per finding:
   ### F<n> · <critical|major|minor> · <file>:<line>
   - evidence: <quote or command + output>
   - trigger: <conditions>
   - impact: <what breaks>
   - user_decision_required: <true|false>
3. Each time you finish a file or a function, append one line under "## Coverage":
   - <file>[:<function>] — checked: <what you checked> — result: <findings F.. | nothing found>
4. When you are done, append "## Done · <ISO time> · <n> findings" as the last line. A file without this line
   means the wave was interrupted.

<lane-specific checklist: code / tests (mutation checklist) / security / infrastructure / layout / docs>
```

## Handover prompt (replacement reviewer after an interruption)

```text
The previous <lane> reviewer (<model>) stopped mid-wave: <reason, e.g. provider limit, resets at …>.
Its partial work is in work/<feature>/reviews/wave-<K>-<lane>.md (no "## Done" line).
1. Re-check every finding F1..Fn against the code: keep (add "- confirmed by <your model>") or reject (add
   "- rejected by <your model>: <why>"). Do not delete lines.
2. Review everything not listed under "## Coverage", using the same contract (append as you go).
3. Add "## Handover · from <old model> to <your model> · <ISO time> · reason: <reason>" before your first new line,
   and the usual "## Done" line at the end.
```
