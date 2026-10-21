"""Exercise review waves through their CLI with real git and offline reviewer processes."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import time
import unittest

from test_matrix_pick import CONFIG, DEEPSEEK, THREE_FAMILY_CONFIG

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/artel-review/scripts/review_run.py"
FIXTURES = Path(__file__).parent / "fixtures"
OPENAI = "gpt-6.1-sol"
ANTHROPIC = "claude-sonnet-5-5"
CODEX_LIMIT = "ERROR: You’ve hit your usage limit. Try again at Oct 7, 2026 1:00 PM."
CLAUDE_LIMIT = "You've hit your session limit · resets 5pm (Europe/Saratov)"


class ReviewRun(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = (Path(self.temp.name) / "repo with spaces").resolve()
        self.repo.mkdir()
        self.git("init", "-q")
        (self.repo / "project.txt").write_text("original\n", encoding="utf-8")
        self.git("add", "project.txt")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        self.config = Path(self.temp.name) / "artel.toml"
        self.config.write_text(CONFIG, encoding="utf-8")
        self.capture = Path(self.temp.name) / "capture"
        self.env = {**os.environ, "ARTEL_CONFIG": str(self.config),
                    "ARTEL_REVIEW_CAPTURE_DIR": str(self.capture),
                    "ARTEL_REVIEW_FAKE": str(FIXTURES / "review_fake.py")}
        self.wave = self.repo / "work/demo/reviews/wave-1-code.md"

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True)

    def run_review(self, behaviors, *extra, author="claude-opus-5-5", fixture="available", code=0):
        limits = Path(self.temp.name) / "limits.json"
        limits.write_text((FIXTURES / f"{fixture}.json").read_text())
        self.env["ARTEL_REVIEW_LIMITS"] = str(limits)
        self.env["ARTEL_REVIEW_RUNNER"] = str(SCRIPT)
        behaviors = {model: dict(behavior) for model, behavior in behaviors.items()}
        for behavior in behaviors.values():
            behavior.setdefault("exhaust_family", behavior.get("mode") in {"limit", "early_limit", "next_log_hardlink"})
        self.env["ARTEL_REVIEW_BEHAVIORS"] = json.dumps(behaviors)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), "--feature", "demo",
             "--lane", "code", "--wave", "1", "--role", "reviewer_code", "--tier", "t23",
             "--author", author, "--base", "HEAD", "--head", "HEAD", "--checklist", "Check failure handling.",
             "--limits", str(limits), *extra],
            env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, code, result.stderr + result.stdout)
        data = json.loads(result.stdout)
        self.assertEqual(data, json.loads(self.wave.with_suffix(".status.json").read_text(encoding="utf-8")))
        for attempt in data["reviewers"]:
            self.assertLessEqual(datetime.fromisoformat(attempt["started"]),
                                 datetime.fromisoformat(attempt["finished"]))
            if not attempt["timed_out"]:
                self.assertIn("fake reviewer stdout", Path(attempt["log"]).read_text(encoding="utf-8"))
        return data

    def saved_prompt(self, model):
        return (self.capture / f"{model}.prompt.txt").read_text(encoding="utf-8")

    def test_omp_fake_reads_real_diff_and_finishes(self):
        self.config.write_text(THREE_FAMILY_CONFIG)
        (self.repo / "project.txt").write_text("changed for review\n")
        self.git("add", "project.txt")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "change")
        expected = self.git("diff", "HEAD~1..HEAD").stdout
        self.assertIn("+changed for review", expected)
        data = self.run_review({DEEPSEEK: {"check_diff": expected}}, "--base", "HEAD~1",
                               author=OPENAI, fixture="claude_session_exhausted")
        diff_file = self.wave.with_suffix(".diff")
        self.assertEqual(diff_file.read_text(), expected)
        self.assertIn(f"You cannot run shell commands. The diff under review is in {diff_file}; "
                      "read it and any repository file you need.", self.saved_prompt(DEEPSEEK))
        self.assertEqual(data["outcome"], "done")
        self.assertEqual(data["reviewers"][0]["harness"], "omp")
        self.assertFalse(data["independence_weakened"])
        self.wave.unlink()
        data = self.run_review({DEEPSEEK: {"mode": "scope", "path": "work/demo/reviews/wave-1-code.diff"}},
                               author=OPENAI, fixture="claude_session_exhausted")
        self.assertEqual(data["outcome"], "done")
        self.assertEqual(diff_file.read_text(), "outside review scope\n")

    def test_omp_without_done_fails_without_handover(self):
        self.config.write_text(THREE_FAMILY_CONFIG)
        data = self.run_review({DEEPSEEK: {"mode": "limit", "message": CODEX_LIMIT,
                                          "exhaust_family": False}}, author=OPENAI,
                               fixture="claude_session_exhausted", code=4)
        self.assertEqual(data["outcome"], "failed")
        self.assertEqual(len(data["reviewers"]), 1)
        self.assertIsNone(data["reviewers"][0]["matched_limit_line"])
        self.assertFalse(data["reviewers"][0]["limit_confirmed"])
        self.assertEqual(data["handover_chain"], [])

    def test_omp_native_command_without_hook(self):
        self.config.write_text(THREE_FAMILY_CONFIG)
        self.env.pop("ARTEL_REVIEW_FAKE")
        cli_dir = Path(self.temp.name) / "bin"
        cli_dir.mkdir()
        (cli_dir / "omp").symlink_to(FIXTURES / "review_cli_fake.py")
        self.env["PATH"] = str(cli_dir) + os.pathsep + os.environ["PATH"]
        data = self.run_review({DEEPSEEK: {}}, author=OPENAI, fixture="claude_session_exhausted")
        self.assertEqual(data["outcome"], "done")
        argv = json.loads((self.capture / f"{DEEPSEEK}.argv.json").read_text())
        self.assertEqual(argv, ["-p", self.saved_prompt(DEEPSEEK), "--model", DEEPSEEK,
                                "--thinking", "high", "--approval-mode", "write", "--mode", "text"])

    def test_done_and_filled_contract(self):
        data = self.run_review({OPENAI: {"mode": "done"}})
        self.assertEqual(data["outcome"], "done")
        self.assertEqual(len(data["reviewers"]), 1)
        self.assertEqual(data["reviewers"][0]["exit_code"], 0)
        self.assertFalse(data["independence_weakened"])
        self.assertEqual(data["handover_chain"], [])
        self.assertEqual(self.wave.read_text().count("### F"), 2)
        self.assertTrue(self.wave.read_text().splitlines()[-1].startswith("## Done"))
        prompt = self.saved_prompt(OPENAI)
        for value in ("code reviewer, wave 1", "slice demo of work/demo/ (tier t23)",
                      "Review the diff HEAD..HEAD", f"reviewer {OPENAI}@high",
                      "Check failure handling.", "work/demo/reviews/wave-1-code.md"):
            self.assertIn(value, prompt)
        for placeholder in ("<lane>", "<K>", "<slice>", "<feature>", "<ISO time>", "<base>", "<head>"):
            self.assertNotIn(placeholder, prompt)

    def test_codex_limit_handover_preserves_partial_review(self):
        data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT},
                                ANTHROPIC: {"old_model": OPENAI}})
        self.assertEqual(data["outcome"], "done")
        self.assertEqual([x["model"] for x in data["reviewers"]], [OPENAI, ANTHROPIC])
        self.assertEqual([x["harness"] for x in data["reviewers"]], ["codex", "claude-code"])
        self.assertEqual(data["reviewers"][0]["outcome"], "interrupted_limit")
        self.assertEqual(data["reviewers"][0]["matched_limit_line"], CODEX_LIMIT)
        self.assertEqual(data["reviewers"][0]["reset_text"], [CODEX_LIMIT])
        self.assertTrue(data["independence_weakened"])
        self.assertEqual(len(data["handover_chain"]), 1)
        self.assertEqual(data["handover_chain"][0]["from"], OPENAI)
        self.assertEqual(data["handover_chain"][0]["to"], ANTHROPIC)
        self.assertIn(CODEX_LIMIT, self.saved_prompt(ANTHROPIC))
        self.assertIn("- evidence: first finding", self.wave.read_text())
        self.assertIn(f"- confirmed by {ANTHROPIC}", self.wave.read_text())
        for n in (1, 2):
            self.assertTrue(Path(f"{self.wave}.{n}.log").exists())

    def test_claude_session_and_weekly_limit_handover(self):
        for window in ("session", "weekly"):
            with self.subTest(window=window):
                self.wave.unlink(missing_ok=True)
                message = CLAUDE_LIMIT.replace("session", window)
                data = self.run_review({ANTHROPIC: {"mode": "limit", "message": message},
                                        OPENAI: {"old_model": ANTHROPIC}}, author="gpt-6-luna")
                self.assertEqual([x["model"] for x in data["reviewers"]], [ANTHROPIC, OPENAI])
                self.assertEqual(data["outcome"], "done")
                self.assertTrue(data["independence_weakened"])
                self.assertEqual(data["reviewers"][0]["matched_limit_line"], message)
                self.assertIn(message, self.saved_prompt(OPENAI))

    def test_limit_before_wave_file_creation(self):
        data = self.run_review({OPENAI: {"mode": "early_limit", "message": CODEX_LIMIT},
                                ANTHROPIC: {"old_model": OPENAI, "no_partial": True}})
        self.assertEqual(data["outcome"], "done")
        self.assertEqual([x["model"] for x in data["reviewers"]], [OPENAI, ANTHROPIC])
        self.assertIn(ANTHROPIC, self.wave.read_text().splitlines()[0])
        self.assertEqual(self.wave.read_text().count("### F"), 2)

    def test_unrelated_exit_one_has_no_handover(self):
        data = self.run_review({OPENAI: {"mode": "error", "message": "ERROR: network unavailable"}}, code=4)
        self.assertEqual(data["outcome"], "failed")
        self.assertEqual(len(data["reviewers"]), 1)
        self.assertEqual(data["reviewers"][0]["exit_code"], 1)
        self.assertIsNone(data["reviewers"][0]["matched_limit_line"])
        self.assertEqual(data["handover_chain"], [])

    def test_scope_violation_overrides_done_and_preserves_changes(self):
        data = self.run_review({OPENAI: {"mode": "scope"}}, code=4)
        self.assertEqual(data["outcome"], "scope_violation")
        self.assertEqual(data["scope_violations"], ["project.txt"])
        self.assertEqual(data["reviewers"][0]["outcome"], "scope_violation")
        self.assertEqual((self.repo / "project.txt").read_text(), "outside review scope\n")
        self.assertEqual(data["handover_chain"], [])

    def test_scope_violation_untracked_unicode_and_spaces(self):
        path = "новый file.txt"
        data = self.run_review({OPENAI: {"mode": "scope", "path": path}}, code=4)
        self.assertEqual(data["scope_violations"], [path])

    def test_scope_violation_keeps_limit_evidence(self):
        data = self.run_review({OPENAI: {"mode": "scope", "message": CODEX_LIMIT}}, code=4)
        self.assertEqual(data["outcome"], "scope_violation")
        self.assertEqual(data["reviewers"][0]["matched_limit_line"], CODEX_LIMIT)
        self.assertEqual(data["reviewers"][0]["reset_text"], [CODEX_LIMIT])
        self.assertEqual(data["handover_chain"], [])

    def test_next_log_hardlink_does_not_overwrite_project_file(self):
        data = self.run_review({OPENAI: {"mode": "next_log_hardlink", "message": CODEX_LIMIT},
                                ANTHROPIC: {"old_model": OPENAI}})
        self.assertEqual(data["outcome"], "done")
        self.assertEqual((self.repo / "project.txt").read_text(), "original\n")
        self.assertNotEqual((self.repo / "project.txt").stat().st_ino,
                            Path(data["reviewers"][-1]["log"]).stat().st_ino)

    def test_status_symlink_does_not_overwrite_project_file(self):
        self.run_review({OPENAI: {"mode": "status_symlink"}})
        self.assertEqual((self.repo / "project.txt").read_text(), "original\n")
        self.assertFalse(self.wave.with_suffix(".status.json").is_symlink())
        self.assertNotIn("project.txt", self.git("status", "--porcelain").stdout)

    def test_status_hardlink_does_not_overwrite_project_file(self):
        self.run_review({OPENAI: {"mode": "status_hardlink"}})
        self.assertEqual((self.repo / "project.txt").read_text(), "original\n")
        self.assertNotEqual((self.repo / "project.txt").stat().st_ino,
                            self.wave.with_suffix(".status.json").stat().st_ino)

    def test_native_commands_without_hook(self):
        self.env.pop("ARTEL_REVIEW_FAKE")
        cli_dir = Path(self.temp.name) / "bin"
        cli_dir.mkdir()
        for executable in ("codex", "claude"):
            (cli_dir / executable).symlink_to(FIXTURES / "review_cli_fake.py")
        self.env["PATH"] = str(cli_dir) + os.pathsep + os.environ["PATH"]
        data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT},
                                ANTHROPIC: {"old_model": OPENAI}})
        self.assertEqual(data["outcome"], "done")
        codex = json.loads((self.capture / f"{OPENAI}.argv.json").read_text())
        self.assertEqual(codex, ["exec", "-C", str(self.repo), "-m", OPENAI,
                                 "-c", "model_reasoning_effort=high", "--sandbox", "workspace-write",
                                 self.saved_prompt(OPENAI)])
        claude = json.loads((self.capture / f"{ANTHROPIC}.argv.json").read_text())
        self.assertEqual(claude, ["-p", self.saved_prompt(ANTHROPIC), "--model", ANTHROPIC,
                                  "--effort", "high", "--allowedTools",
                                  "Read,Grep,Glob,Bash(git diff:*),Bash(git log:*),Bash(git show:*),"
                                  "Write(work/demo/reviews/**),Edit(work/demo/reviews/**)"])

    def test_scope_violation_staged_rename_checks_original_path(self):
        target = self.repo / "work/demo/reviews/moved-project.txt"
        data = self.run_review({OPENAI: {"mode": "rename"}}, code=4)
        self.assertEqual(data["scope_violations"], ["project.txt", "work/demo/reviews/moved-project.txt"])
        self.assertTrue(target.exists())

    def test_no_candidate_after_all_families_hit_limits(self):
        data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT},
                                ANTHROPIC: {"mode": "limit", "message": CLAUDE_LIMIT,
                                            "old_model": OPENAI}}, code=4)
        self.assertEqual(data["outcome"], "no_candidate")
        self.assertEqual(len(data["reviewers"]), 2)
        self.assertEqual(len(data["pick"]["skipped"]), 4)
        self.assertTrue(all(x["why"] == "excluded" for x in data["pick"]["skipped"][:3]))
        self.assertEqual(data["pick"]["skipped"][3],
                         {"candidate": "deepseek.mid@high", "why": "family not configured"})

    def test_no_candidate_when_remaining_model_is_author(self):
        data = self.run_review({ANTHROPIC: {"mode": "limit", "message": CLAUDE_LIMIT}},
                               author=OPENAI, code=4)
        self.assertEqual(data["outcome"], "no_candidate")
        self.assertEqual(len(data["reviewers"]), 1)
        self.assertEqual(data["handover_chain"], [])

    def test_no_initial_candidate(self):
        data = self.run_review({}, fixture="all_exhausted", code=4)
        self.assertEqual(data["outcome"], "no_candidate")
        self.assertEqual(data["reviewers"], [])

    def test_max_handovers_reached(self):
        data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT},
                                ANTHROPIC: {"mode": "limit", "message": CLAUDE_LIMIT,
                                            "old_model": OPENAI}}, "--max-handovers", "1", code=5)
        self.assertEqual(data["outcome"], "handovers_exhausted")
        self.assertEqual(len(data["reviewers"]), 2)
        self.assertEqual(len(data["handover_chain"]), 1)

    def test_zero_handovers(self):
        data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT}},
                               "--max-handovers", "0", code=5)
        self.assertEqual(data["outcome"], "handovers_exhausted")
        self.assertEqual(len(data["reviewers"]), 1)

    def test_codex_apostrophes_and_spend_cap(self):
        for message in (CODEX_LIMIT, CODEX_LIMIT.replace("’", "'"), "ERROR: spend cap reached",
                        "ERROR: usage limit reached"):
            with self.subTest(message=message):
                self.wave.unlink(missing_ok=True)
                data = self.run_review({OPENAI: {"mode": "limit", "message": message}},
                                       "--max-handovers", "0", code=5)
                self.assertEqual(data["reviewers"][0]["matched_limit_line"], message)

    def test_usage_alone_is_not_a_limit(self):
        data = self.run_review({OPENAI: {"mode": "error", "message": "usage"}}, code=4)
        self.assertEqual(data["outcome"], "failed")
        self.assertIsNone(data["reviewers"][0]["matched_limit_line"])

    def test_done_takes_precedence_over_limit_and_exit_code(self):
        data = self.run_review({OPENAI: {"mode": "done", "message": CODEX_LIMIT, "exit": 1}})
        self.assertEqual(data["outcome"], "done")
        self.assertEqual(len(data["reviewers"]), 1)

    def test_zero_exit_without_done_is_failed(self):
        data = self.run_review({OPENAI: {"mode": "error", "exit": 0}}, code=4)
        self.assertEqual(data["outcome"], "failed")

    def test_reset_text_on_separate_line_is_in_handover(self):
        line = "ERROR: You've hit your usage limit."
        reset = "Try again at Oct 7, 2026 1:00 PM."
        data = self.run_review({OPENAI: {"mode": "limit", "message": line + "\n" + reset},
                                ANTHROPIC: {"old_model": OPENAI}})
        self.assertEqual(data["reviewers"][0]["reset_text"], [reset])
        self.assertIn(reset, self.saved_prompt(ANTHROPIC))

    def test_limits_file_is_forwarded_to_matrix(self):
        data = self.run_review({ANTHROPIC: {}}, fixture="openai_exhausted")
        self.assertEqual(data["reviewers"][0]["model"], ANTHROPIC)
        self.assertTrue(data["independence_weakened"])

    def test_timeout_kills_child_process_group(self):
        data = self.run_review({OPENAI: {"mode": "timeout"}}, "--timeout", "0.8", code=4)
        self.assertEqual(data["outcome"], "failed")
        self.assertTrue(data["reviewers"][0]["timed_out"])
        self.assertLess(data["reviewers"][0]["exit_code"], 0)
        heartbeat = self.capture / "child-heartbeat.txt"
        self.assertTrue(heartbeat.exists(), "child process did not start")
        before = heartbeat.read_text()
        time.sleep(0.15)
        self.assertEqual(heartbeat.read_text(), before, "child survived the group timeout")
    def test_quoted_limit_signatures_do_not_handover(self):
        for message in ("+- docs: " + CODEX_LIMIT, "> " + CODEX_LIMIT,
                        "    " + CODEX_LIMIT, CLAUDE_LIMIT, "ERROR: " + CLAUDE_LIMIT):
            with self.subTest(message=message):
                self.wave.unlink(missing_ok=True)
                data = self.run_review({OPENAI: {"mode": "error", "message": message}, ANTHROPIC: {}}, code=4)
                self.assertEqual(data["outcome"], "failed")
                self.assertIsNone(data["reviewers"][0]["matched_limit_line"])
                self.assertEqual(data["handover_chain"], [])

    def test_limit_requires_exhausted_family_when_known(self):
        data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT,
                                       "exhaust_family": False}, ANTHROPIC: {}}, code=4)
        self.assertEqual(data["outcome"], "failed")
        self.assertIs(data["reviewers"][0]["limit_confirmed"], False)
        self.assertEqual(data["handover_chain"], [])

    def test_orca_confirms_exhaustion_after_zero_exit(self):
        cli_dir = Path(self.temp.name) / "bin"
        cli_dir.mkdir()
        (cli_dir / "orca").symlink_to(FIXTURES / "review_cli_fake.py")
        self.env["PATH"] = str(cli_dir) + os.pathsep + os.environ["PATH"]
        data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT, "exit": 0},
                                ANTHROPIC: {"old_model": OPENAI}}, "--limits", "")
        self.assertIs(data["reviewers"][0]["limit_confirmed"], True)
        self.assertEqual(data["reviewers"][0]["exit_code"], 0)
        self.assertEqual(data["outcome"], "done")

    def test_other_familys_exhaustion_does_not_confirm_limit(self):
        data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT,
                                       "exhaust_family": False}},
                               fixture="claude_session_exhausted", code=4)
        self.assertEqual(data["outcome"], "failed")
        self.assertIs(data["reviewers"][0]["limit_confirmed"], False)

    def test_unknown_limits_and_zero_exit_still_allow_handover(self):
        data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT,
                                       "exhaust_family": False, "exit": 0},
                                ANTHROPIC: {"old_model": OPENAI}},
                               "--limits", str(Path(self.temp.name) / "missing.json"))
        self.assertEqual(data["reviewers"][0]["limit_confirmed"], "unknown")
        self.assertEqual(data["reviewers"][0]["exit_code"], 0)
        self.assertEqual(data["outcome"], "done")

    def test_handover_overwrite_stops_and_keeps_backup(self):
        data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT},
                                ANTHROPIC: {"mode": "overwrite", "old_model": OPENAI}}, code=4)
        self.assertEqual(data["outcome"], "handover_overwrote")
        self.assertEqual(data["reviewers"][-1]["outcome"], "handover_overwrote")
        backup = Path(f"{self.wave}.before-1.md")
        self.assertIn(b"first finding", backup.read_bytes())
        self.assertNotIn(b"first finding", self.wave.read_bytes())
        self.assertEqual(len(data["reviewers"]), 2)

    def test_handover_and_resume_accept_in_section_insertions(self):
        for resume in (False, True):
            with self.subTest(resume=resume):
                self.wave.unlink(missing_ok=True)
                if resume:
                    self.run_review({OPENAI: {"mode": "error"}}, code=4)
                    data = self.run_review({OPENAI: {"resume": True, "insert_sections": True,
                                                    "annotation": "rejected by"}})
                    model = OPENAI
                else:
                    data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT},
                                            ANTHROPIC: {"old_model": OPENAI, "insert_sections": True}})
                    model = ANTHROPIC
                self.assertEqual(data["outcome"], "done")
                text = self.wave.read_text()
                self.assertLess(text.index("### F2"), text.index("## Coverage"))
                self.assertIn(f"by {model}", text)
                self.assertIn("- project.txt — checked: remaining code — result: F2", text)
                backup = Path(data["reviewers"][-1]["backup"]).read_text()
                lines = iter(text.splitlines())
                self.assertTrue(all(line in lines for line in backup.splitlines()))

    def test_deleted_old_finding_line_is_handover_overwrote(self):
        for change in ("delete_finding_line", "reorder_finding_lines"):
            with self.subTest(change=change):
                self.wave.unlink(missing_ok=True)
                data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT},
                                        ANTHROPIC: {"old_model": OPENAI, change: True}}, code=4)
                self.assertEqual(data["outcome"], "handover_overwrote")
                self.assertEqual(data["reviewers"][-1]["outcome"], "handover_overwrote")
                self.assertIn("- evidence: first finding", Path(data["reviewers"][-1]["backup"]).read_text())
                if change == "delete_finding_line":
                    self.assertNotIn("- evidence: first finding", self.wave.read_text())
                else:
                    self.assertLess(self.wave.read_text().index("- evidence: first finding"),
                                    self.wave.read_text().index("### F1"))

    def test_handover_same_size_edit_is_rejected(self):
        data = self.run_review({OPENAI: {"mode": "limit", "message": CODEX_LIMIT},
                                ANTHROPIC: {"old_model": OPENAI, "replace_same_length": True}}, code=4)
        self.assertEqual(data["outcome"], "handover_overwrote")
        self.assertIn(b"first finding", Path(f"{self.wave}.before-1.md").read_bytes())

    def test_completed_wave_refuses_rerun_and_keeps_history(self):
        first = self.run_review({OPENAI: {}})
        old_wave = self.wave.read_bytes()
        old_log = Path(first["reviewers"][0]["log"]).read_bytes()
        old_status = self.wave.with_suffix(".status.json").read_bytes()
        data = self.run_review({OPENAI: {"mode": "no_write"}}, code=4)
        self.assertEqual(data["outcome"], "already_done")
        self.assertEqual(data["reviewers"], [])
        self.assertEqual(self.wave.read_bytes(), old_wave)
        self.assertEqual(Path(first["reviewers"][0]["log"]).read_bytes(), old_log)
        self.assertEqual(self.wave.with_suffix(".status.1.json").read_bytes(), old_status)

    def test_resume_uses_handover_and_numbers_logs_and_status(self):
        first = self.run_review({OPENAI: {"mode": "error"}}, code=4)
        partial = self.wave.read_bytes()
        old_status = self.wave.with_suffix(".status.json").read_bytes()
        old_log = Path(first["reviewers"][0]["log"]).read_bytes()
        data = self.run_review({OPENAI: {"resume": True}})
        self.assertEqual(data["outcome"], "done")
        self.assertTrue(self.wave.read_bytes().startswith(partial))
        self.assertEqual(Path(f"{self.wave}.before-1.md").read_bytes(), partial)
        self.assertEqual(Path(data["reviewers"][0]["log"]), Path(f"{self.wave}.2.log"))
        self.assertEqual(Path(first["reviewers"][0]["log"]).read_bytes(), old_log)
        self.assertEqual(self.wave.with_suffix(".status.1.json").read_bytes(), old_status)
        self.assertIn("resumed by a new runner invocation", self.saved_prompt(OPENAI))

    def test_resume_overwrite_is_rejected(self):
        self.run_review({OPENAI: {"mode": "error"}}, code=4)
        partial = self.wave.read_bytes()
        data = self.run_review({OPENAI: {"mode": "overwrite", "resume": True}}, code=4)
        self.assertEqual(data["outcome"], "handover_overwrote")
        self.assertEqual(Path(f"{self.wave}.before-1.md").read_bytes(), partial)

    def test_force_new_archives_completed_wave_and_logs(self):
        first = self.run_review({OPENAI: {}})
        old_wave = self.wave.read_bytes()
        old_log = Path(first["reviewers"][0]["log"]).read_bytes()
        old_status = self.wave.with_suffix(".status.json").read_bytes()
        data = self.run_review({OPENAI: {}}, "--force-new")
        self.assertEqual(data["outcome"], "done")
        archives = list(self.wave.parent.glob(f"{self.wave.name}.old-*"))
        self.assertEqual(len(archives), 1)
        self.assertEqual((archives[0] / self.wave.name).read_bytes(), old_wave)
        self.assertEqual((archives[0] / Path(first["reviewers"][0]["log"]).name).read_bytes(), old_log)
        self.assertEqual((archives[0] / self.wave.with_suffix(".status.json").name).read_bytes(), old_status)

    def test_force_new_archives_unfinished_wave_and_starts_fresh(self):
        self.wave.parent.mkdir(parents=True, exist_ok=True)
        self.wave.write_text("# Wave 1 · stale partial\n## Findings\n## Coverage\n- wrong range\n", encoding="utf-8")
        old_wave = self.wave.read_bytes()
        data = self.run_review({OPENAI: {}}, "--force-new")
        self.assertEqual(data["outcome"], "done")
        self.assertEqual(data["handover_chain"], [])
        archives = list(self.wave.parent.glob(f"{self.wave.name}.old-*"))
        self.assertEqual(len(archives), 1)
        self.assertEqual((archives[0] / self.wave.name).read_bytes(), old_wave)

    def test_reset_text_only_from_the_limit_line(self):
        data = self.run_review({OPENAI: {"mode": "early_limit", "exhaust_family": False,
                                         "message": "quoted doc: the window resets at noon"}}, code=4)
        self.assertEqual(data["outcome"], "failed")
        self.assertEqual(data["reviewers"][0]["reset_text"], [])

    def test_runner_signals_kill_group_and_save_status(self):
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            with self.subTest(signal=sig):
                self.wave.unlink(missing_ok=True)
                heartbeat = self.capture / "child-heartbeat.txt"
                heartbeat.unlink(missing_ok=True)
                self.env["ARTEL_REVIEW_BEHAVIORS"] = json.dumps({OPENAI: {"mode": "timeout"}})
                process = subprocess.Popen(
                    [sys.executable, str(SCRIPT), "--repo", str(self.repo), "--feature", "demo",
                     "--lane", "code", "--wave", "1", "--role", "reviewer_code", "--tier", "t23",
                     "--author", "claude-opus-5-5", "--base", "HEAD", "--head", "HEAD",
                     "--checklist", "Check signals", "--limits", str(FIXTURES / "available.json")],
                    env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    deadline = time.monotonic() + 5
                    while not heartbeat.exists() and time.monotonic() < deadline:
                        time.sleep(.02)
                    self.assertTrue(heartbeat.exists(), "child process did not start")
                    process.send_signal(sig)
                    stdout, stderr = process.communicate(timeout=5)
                    before = heartbeat.read_text()
                    time.sleep(.1)
                    self.assertEqual(heartbeat.read_text(), before, "child survived runner signal")
                    self.assertEqual(process.returncode, 4, stderr)
                    data = json.loads(stdout)
                    self.assertEqual(data["outcome"], "interrupted_runner")
                    self.assertEqual(data, json.loads(self.wave.with_suffix(".status.json").read_text()))
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)
                    group_file = self.capture / "child-group.txt"
                    if group_file.exists():
                        try:
                            os.killpg(int(group_file.read_text()), signal.SIGKILL)
                        except ProcessLookupError:
                            pass

    def test_normal_exit_kills_background_children(self):
        try:
            data = self.run_review({OPENAI: {"mode": "background"}})
            self.assertEqual(data["outcome"], "done")
            heartbeat = self.capture / "child-heartbeat.txt"
            before = heartbeat.read_bytes() if heartbeat.exists() else b""
            time.sleep(.15)
            self.assertEqual(heartbeat.read_bytes() if heartbeat.exists() else b"", before)
        finally:
            group_file = self.capture / "child-group.txt"
            if group_file.exists():
                try:
                    os.killpg(int(group_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_preexisting_dirty_and_ignored_files_are_not_violations(self):
        (self.repo / "project.txt").write_text("owner's unfinished edit\n")
        (self.repo / ".gitignore").write_text("generated.txt\n")
        (self.repo / "generated.txt").write_text("already here\n")
        data = self.run_review({OPENAI: {}})
        self.assertEqual(data["outcome"], "done")
        self.assertEqual((self.repo / "project.txt").read_text(), "owner's unfinished edit\n")

    def test_new_ignored_file_is_scope_violation(self):
        (self.repo / ".git/info/exclude").write_text("generated.txt\n")
        data = self.run_review({OPENAI: {"mode": "scope", "path": "generated.txt"}}, code=4)
        self.assertEqual(data["scope_violations"], ["generated.txt"])

    def test_ignored_parent_excludes_lane_files_but_detects_other_changes(self):
        (self.repo / ".git/info/exclude").write_text("work/\n")
        self.assertEqual(self.run_review({OPENAI: {}})["outcome"], "done")
        self.wave.unlink()
        path = "work/generated.txt"
        data = self.run_review({OPENAI: {"mode": "scope", "path": path}}, code=4)
        self.assertEqual(data["scope_violations"], [path])

    def test_existing_ignored_directory_edit_is_scope_violation(self):
        (self.repo / ".git/info/exclude").write_text("generated/\n")
        folder = self.repo / "generated"
        folder.mkdir()
        (folder / "output.txt").write_text("existing output\n")
        path = "generated/output.txt"
        data = self.run_review({OPENAI: {"mode": "scope", "path": path}}, code=4)
        self.assertEqual(data["scope_violations"], [path])

    def test_ignored_noise_rewrites_are_exempt_but_other_ignored_files_are_not(self):
        (self.repo / ".git/info/exclude").write_text(".DS_Store\n*.pyc\n__pycache__/\ngenerated/\n")
        noise = [".DS_Store", "nested/.DS_Store", "cache.pyc", "nested/cache.pyc",
                 "nested/__pycache__/cache.pyc", "nested/__pycache__/metadata.txt"]
        other = "generated/output.txt"
        for path in [*noise, other]:
            file = self.repo / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("existing data\n")
        data = self.run_review({OPENAI: {"rewrite_paths": noise}})
        self.assertEqual(data["outcome"], "done")
        for path in noise:
            self.assertEqual((self.repo / path).read_text(), "rewritten during review\n")
        self.wave.unlink()
        data = self.run_review({OPENAI: {"rewrite_paths": [*noise, other]}}, code=4)
        self.assertEqual(data["outcome"], "scope_violation")
        self.assertEqual(data["scope_violations"], [other])

    def test_change_to_preexisting_dirty_file_is_scope_violation(self):
        (self.repo / "project.txt").write_text("owner's edit\n")
        data = self.run_review({OPENAI: {"mode": "scope"}}, code=4)
        self.assertEqual(data["scope_violations"], ["project.txt"])

    def test_head_and_branch_changes_are_scope_violations(self):
        for mode, violation in (("commit", "HEAD"), ("branch", "branch")):
            with self.subTest(mode=mode):
                self.wave.unlink(missing_ok=True)
                data = self.run_review({OPENAI: {"mode": mode}}, code=4)
                self.assertEqual(data["outcome"], "scope_violation")
                self.assertIn(violation, data["scope_violations"])

    def test_other_lane_outputs_are_not_this_lanes_violation(self):
        for suffix in (".md", ".diff"):
            with self.subTest(suffix=suffix):
                self.wave.unlink(missing_ok=True)
                data = self.run_review({OPENAI: {"mode": "scope",
                                               "path": f"work/demo/reviews/wave-1-security{suffix}"}})
                self.assertEqual(data["outcome"], "done")

    def test_other_wave_review_outputs_are_scope_violations(self):
        for wave in (0, 2):
            for suffix in (".md", ".diff", ".md.1.log", ".status.json", ".status.1.json", ".md.before-1.md"):
                paths = [f"work/demo/reviews/wave-{wave}-security{suffix}",
                         f"work/demo/reviews/wave-{wave}-security.md.old-20261006T000000Z/"
                         f"wave-1-security{suffix}",
                         "work/demo/reviews/wave-1-security.md.old-20261006T000000Z/"
                         f"wave-{wave}-security{suffix}"]
                for path in paths:
                    with self.subTest(path=path):
                        self.wave.unlink(missing_ok=True)
                        file = self.repo / path
                        file.parent.mkdir(parents=True, exist_ok=True)
                        file.write_text("historical review output\n")
                        data = self.run_review({OPENAI: {"mode": "scope", "path": path}}, code=4)
                        self.assertEqual(data["outcome"], "scope_violation")
                        self.assertEqual(data["scope_violations"], [path])

    def test_other_lane_force_new_archive_is_not_this_lanes_violation(self):
        self.wave.parent.mkdir(parents=True)
        other = self.wave.with_name("wave-1-security.md")
        other.write_text("# Security review\n## Done\n")
        Path(f"{other}.1.log").write_text("old log\n")
        other.with_suffix(".status.json").write_text('{"outcome": "done"}\n')
        data = self.run_review({OPENAI: {"mode": "archive_other_lane"}})
        self.assertEqual(data["outcome"], "done")
        archives = list(self.wave.parent.glob(f"{other.name}.old-*"))
        self.assertEqual(len(archives), 1)
        self.assertEqual((archives[0] / other.name).read_text(), "# Security review\n## Done\n")

    def test_signal_during_process_creation_is_deferred_until_cleanup(self):
        self.signal_driver("creation")

    def test_signal_during_cleanup_still_kills_background_children(self):
        self.signal_driver("cleanup")

    def signal_driver(self, stage):
        self.wave.parent.mkdir(parents=True)
        mode = "timeout" if stage == "creation" else "background"
        self.env["ARTEL_REVIEW_BEHAVIORS"] = json.dumps({OPENAI: {"mode": mode}})
        driver = '''
import argparse, importlib.util, json, os, signal, sys, time
from pathlib import Path
spec = importlib.util.spec_from_file_location("runner", sys.argv[1])
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
def interrupt(signum, frame):
    raise runner.RunnerInterrupted(signum)
signal.signal(signal.SIGTERM, interrupt)
real_popen = runner.subprocess.Popen
real_killpg = os.killpg
stage = sys.argv[4]
child = None
sent = False
cleaned = False
def popen(*args, **kwargs):
    global child
    child = real_popen(*args, **kwargs)
    if stage == "creation":
        os.kill(os.getpid(), signal.SIGTERM)
    return child
runner.subprocess.Popen = popen
def killpg(*args):
    global sent
    if stage == "cleanup" and not sent:
        sent = True
        os.kill(os.getpid(), signal.SIGTERM)
    return real_killpg(*args)
runner.os.killpg = killpg
wave = Path(sys.argv[3])
args = argparse.Namespace(repo=Path(sys.argv[2]), timeout=5)
try:
    result = runner.launch(args, {"harness": "codex", "model": "gpt-6.1-sol"},
                           "Wave file: " + str(wave), Path(str(wave) + ".1.log"))
    heartbeat = Path(os.environ["ARTEL_REVIEW_CAPTURE_DIR"]) / "child-heartbeat.txt"
    before = heartbeat.read_bytes() if heartbeat.exists() else b""
    time.sleep(.1)
    after = heartbeat.read_bytes() if heartbeat.exists() else b""
    cleaned = child.poll() is not None and before == after
    print(json.dumps({"signal": result[3], "child_reaped": child.poll() is not None,
                      "heartbeat_stopped": before == after}))
finally:
    if child is not None and not cleaned:
        try:
            real_killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()
'''
        result = subprocess.run([sys.executable, "-c", driver, str(SCRIPT), str(self.repo), str(self.wave), stage],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"signal": signal.SIGTERM, "child_reaped": True,
                                                   "heartbeat_stopped": True})

    def test_arbitrary_review_directory_file_is_scope_violation(self):
        path = "work/demo/reviews/unrelated.txt"
        data = self.run_review({OPENAI: {"mode": "scope", "path": path}}, code=4)
        self.assertEqual(data["scope_violations"], [path])

if __name__ == "__main__":
    unittest.main()
