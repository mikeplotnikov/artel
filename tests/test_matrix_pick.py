"""Exercise matrix selection through its public CLI with isolated configs and limits."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/artel/scripts/matrix.py"
FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = '''calibrated = true
[[providers]]
family = "anthropic"
harness = "claude-code"
models = { top = "claude-fable-5-1", flagship = "claude-opus-5-5", mid = "claude-sonnet-5-5" }
[[providers]]
family = "openai"
harness = "codex"
models = { mid = "gpt-6.1-sol", cheap = "gpt-6-luna" }
'''

DEEPSEEK = "deepseek/deepseek-v4-pro"
THREE_FAMILY_CONFIG = CONFIG + f'''
[[providers]]
family = "deepseek"
harness = "omp"
models = {{ mid = "{DEEPSEEK}" }}
'''


class MatrixPick(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "artel.toml"
        self.config.write_text(CONFIG)
        self.env = {**os.environ, "ARTEL_CONFIG": str(self.config)}

    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env,
                              capture_output=True, text=True, timeout=25)

    def pick(self, *extra, role="reviewer_code", tier="t23", fixture="available", code=0):
        args = ["pick", "--role", role, "--tier", tier, "--json"]
        if "--no-limits" not in extra:
            args += ["--limits", str(FIXTURES / f"{fixture}.json")]
        result = self.run_script(*args, *extra)
        self.assertEqual(result.returncode, code, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def override(self, text):
        self.config.write_text(CONFIG + text)

    def test_reserve_defaults_cover_every_review_role(self):
        import tomllib
        defaults = tomllib.loads((ROOT / "skills/artel/references/roles.toml").read_text())
        self.assertEqual(defaults["policy"].get("reserve_families"), ["deepseek"])
        for role, values in defaults["roles"].items():
            if values.get("review"):
                for tier in ("t01", "t23"):
                    with self.subTest(role=role, tier=tier):
                        self.assertEqual(values[tier][-1], "deepseek.mid@high")

    def test_reserve_reviews_sol_when_anthropic_exhausted(self):
        self.config.write_text(THREE_FAMILY_CONFIG)
        data = self.pick("--author", "gpt-6.1-sol", fixture="claude_session_exhausted")
        self.assertEqual((data["family"], data["model"]), ("deepseek", DEEPSEEK))
        self.assertFalse(data["independence_weakened"])
        self.assertIn("reserve family deepseek", data["notes"])
        self.assertIn("limits unknown for deepseek: treated as available — ask the owner if it matters",
                      data["notes"])
        self.assertEqual(data["limits"]["deepseek"], {})

    def test_nonreserve_other_family_beats_earlier_reserve(self):
        self.config.write_text(THREE_FAMILY_CONFIG)
        self.assertEqual(self.pick("--author", "claude-opus-5-5")["model"], "gpt-6.1-sol")
        self.config.write_text(THREE_FAMILY_CONFIG + '\n[roles.reviewer_code]\n'
                               't23 = ["deepseek.mid@high", "openai.mid@high", "anthropic.mid@high"]\n')
        data = self.pick("--author", "claude-opus-5-5")
        self.assertEqual(data["model"], "gpt-6.1-sol")
        self.assertFalse(data["independence_weakened"])
        self.assertNotIn("reserve family deepseek", data["notes"])

    def test_nonreserve_same_family_beats_reserve(self):
        self.config.write_text(THREE_FAMILY_CONFIG)
        data = self.pick("--author", "claude-opus-5-5", fixture="openai_exhausted")
        self.assertEqual(data["model"], "claude-sonnet-5-5")
        self.assertTrue(data["independence_weakened"])
        self.config.write_text(THREE_FAMILY_CONFIG + '\n[roles.reviewer_code]\n'
                               't23 = ["deepseek.mid@high", "openai.mid@high", "anthropic.mid@high"]\n')
        data = self.pick("--author", "claude-opus-5-5", fixture="openai_exhausted")
        self.assertEqual(data["model"], "claude-sonnet-5-5")
        self.assertTrue(data["independence_weakened"])
        self.assertNotIn("reserve family deepseek", data["notes"])

    def test_omp_launch_is_headless(self):
        self.config.write_text(THREE_FAMILY_CONFIG + '\n[roles.reviewer_code]\n'
                               't23 = ["deepseek.mid@high"]\n')
        data = self.pick("--author", "gpt-6.1-sol")
        self.assertEqual(data["launch"], {
            "omp": f"omp -p <prompt> --model {DEEPSEEK} --thinking high --approval-mode write --mode text",
            "orca": None})
        self.assertIn("no Orca agent for omp — run headless", data["notes"])

    def test_nonreview_prefers_nonreserve_then_reserve(self):
        self.config.write_text(THREE_FAMILY_CONFIG + '\n[roles.mechanical]\n'
                               't23 = ["deepseek.mid@high", "openai.cheap@low"]\n')
        data = self.pick(role="mechanical")
        self.assertEqual(data["model"], "gpt-6-luna")
        self.assertNotIn("reserve family deepseek", data["notes"])
        data = self.pick(role="mechanical", fixture="openai_exhausted")
        self.assertEqual(data["model"], DEEPSEEK)
        self.assertIn("reserve family deepseek", data["notes"])

    def test_reserve_policy_override(self):
        self.config.write_text(THREE_FAMILY_CONFIG + '\n[policy]\nreserve_families = ["openai"]\n'
                               '\n[roles.reviewer_code]\nt23 = ["openai.mid@high", "deepseek.mid@high"]\n')
        self.assertEqual(self.pick("--author", "claude-opus-5-5")["model"], DEEPSEEK)
        self.config.write_text(THREE_FAMILY_CONFIG + '\n[policy]\nreserve_families = []\n'
                               '\n[roles.reviewer_code]\nt23 = ["deepseek.mid@high", "openai.mid@high"]\n')
        self.assertEqual(self.pick("--author", "claude-opus-5-5")["model"], DEEPSEEK)

    def test_reserve_cannot_review_its_own_family(self):
        config = THREE_FAMILY_CONFIG.replace('mid = "' + DEEPSEEK + '"',
                                             'mid = "' + DEEPSEEK + '", flagship = "deepseek-author"')
        self.config.write_text(config + '\n[roles.reviewer_code]\nt23 = ["deepseek.mid@high"]\n')
        data = self.pick("--author", "deepseek-author", code=3)
        self.assertIn("error", data)

    def test_family_without_limit_windows_is_flagged(self):
        data = self.pick("--author", "claude-opus-5-5", fixture="codex_missing")
        self.assertEqual(data["model"], "gpt-6.1-sol")
        self.assertIn("limits unknown for openai: treated as available — ask the owner if it matters", data["notes"])

    def test_unknown_harness_is_an_error_not_a_codex_command(self):
        cfg = self.config.read_text().replace('harness = "codex"', 'harness = "opencode"')
        self.config.write_text(cfg)
        result = self.run_script("pick", "--role", "reviewer_code", "--tier", "t23", "--author", "claude-opus-5-5",
                                 "--limits", str(FIXTURES / "available.json"), "--json")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("unsupported harness 'opencode'", result.stderr)

    def test_review_opus_cross_family(self):
        data = self.pick("--author", "claude-opus-5-5")
        self.assertEqual((data["model"], data["effort"], data["independence_weakened"]),
                         ("gpt-6.1-sol", "high", False))
        self.assertEqual(data["launch"], {
            "codex": "codex exec -m gpt-6.1-sol -c model_reasoning_effort=high",
            "orca": "orca orchestration worker-start --agent codex --model gpt-6.1-sol --effort high"})
        self.assertEqual(data["limits"]["openai"], {"weekly": 9})

    def test_review_openai_cross_family(self):
        data = self.pick("--author", "gpt-6.1-sol")
        self.assertEqual(data["family"], "anthropic")
        self.assertFalse(data["independence_weakened"])
        self.assertIn({"candidate": "openai.mid@high", "why": "author's own model"}, data["skipped"])

    def test_excluded_family_weakens_review_independence(self):
        data = self.pick("--author", "claude-opus-5-5", "--exclude-family", "openai")
        self.assertEqual(data["model"], "claude-sonnet-5-5")
        self.assertTrue(data["independence_weakened"])
        self.assertIn({"candidate": "openai.mid@high", "why": "excluded"}, data["skipped"])

    def test_repeatable_exclusions_leave_no_candidate(self):
        data = self.pick("--exclude-family", "openai", "--exclude-family", "anthropic", code=3)
        self.assertEqual(len(data["skipped"]), 4)
        self.assertTrue(all(item["why"] == "excluded" for item in data["skipped"][:3]))
        self.assertEqual(data["skipped"][3], {"candidate": "deepseek.mid@high", "why": "family not configured"})

    def test_exclusion_precedes_limit_and_author_checks(self):
        data = self.pick("--author", "gpt-6.1-sol", "--exclude-family", "openai",
                         fixture="openai_exhausted")
        self.assertEqual(data["family"], "anthropic")
        self.assertIn({"candidate": "openai.mid@high", "why": "excluded"}, data["skipped"])

    def test_exclusion_without_limits_and_unknown_exclusion(self):
        data = self.pick("--no-limits", "--exclude-family", "anthropic")
        self.assertEqual(data["family"], "openai")
        self.assertEqual([item["why"] for item in data["skipped"]],
                         ["excluded", "excluded", "family not configured"])
        data = self.pick("--exclude-family", "not-configured", "--author", "claude-opus-5-5")
        self.assertEqual(data["model"], "gpt-6.1-sol")
        self.assertEqual(data["skipped"], [{"candidate": "anthropic.flagship@high", "why": "author's own model"},
                                           {"candidate": "deepseek.mid@high", "why": "family not configured"}])

    def test_cross_family_preferred_over_earlier_same_family(self):
        self.override('\n[roles.reviewer_code]\n'
                      't23 = ["anthropic.mid@high", "openai.mid@high", "anthropic.flagship@high"]\n')
        data = self.pick("--author", "claude-opus-5-5")
        self.assertEqual(data["model"], "gpt-6.1-sol")
        self.assertFalse(data["independence_weakened"])

    def test_openai_exhausted_review_opus(self):
        data = self.pick("--author", "claude-opus-5-5", fixture="openai_exhausted")
        self.assertEqual(data["model"], "claude-sonnet-5-5")
        self.assertTrue(data["independence_weakened"])
        self.assertEqual(data["launch"], {
            "claude-code": "claude --model claude-sonnet-5-5 --effort high",
            "orca": "orca orchestration worker-start --agent claude --model claude-sonnet-5-5 --effort high"})

    def test_openai_exhausted_never_review_own_model(self):
        data = self.pick("--author", "claude-sonnet-5-5", fixture="openai_exhausted")
        self.assertEqual(data["model"], "claude-opus-5-5")
        self.assertTrue(data["independence_weakened"])

    def test_threshold_override(self):
        self.override('\n[policy]\nnew_work_threshold = 90\n')
        for fixture in ("threshold", "threshold_equal"):
            with self.subTest(fixture=fixture):
                data = self.pick("--author", "claude-opus-5-5", fixture=fixture)
                self.assertEqual(data["model"], "claude-sonnet-5-5")
                self.assertIn({"candidate": "openai.mid@high", "why": "over threshold"}, data["skipped"])

    def test_session_windows_can_exhaust_each_family(self):
        for fixture, author, model, candidate in [
            ("codex_session_exhausted", "claude-opus-5-5", "claude-sonnet-5-5", "openai.mid@high"),
            ("claude_session_exhausted", "gpt-6.1-sol", "gpt-6.1-sol", "anthropic.mid@high"),
        ]:
            with self.subTest(fixture=fixture):
                if fixture.startswith("claude"):
                    data = self.pick(role="implementer_backend", fixture=fixture)
                    # Review of an OpenAI author has no remaining model once Claude is exhausted.
                    failed = self.pick("--author", author, fixture=fixture, code=3)
                    self.assertIn({"candidate": candidate, "why": "exhausted"}, failed["skipped"])
                else:
                    data = self.pick("--author", author, fixture=fixture)
                    self.assertIn({"candidate": candidate, "why": "exhausted"}, data["skipped"])
                self.assertEqual(data["model"], model)

    def test_fable_specific_window(self):
        exhausted = self.pick(role="spec_writer", fixture="fable_exhausted")
        self.assertEqual(exhausted["model"], "claude-opus-5-5")
        self.assertIn({"candidate": "anthropic.top@high", "why": "exhausted"}, exhausted["skipped"])
        self.assertEqual(self.pick(role="spec_writer")["model"], "claude-fable-5-1")

    def test_banned_candidate(self):
        self.override('\n[roles.reviewer_code]\nt23 = ["openai.cheap@low", "openai.mid@high"]\n')
        data = self.pick("--author", "claude-opus-5-5")
        self.assertEqual(data["model"], "gpt-6.1-sol")
        self.assertEqual(data["skipped"], [{"candidate": "openai.cheap@low", "why": "banned"}])

    def test_override_replaces_chain(self):
        self.override('\n[roles.implementer_backend]\nt23 = ["anthropic.mid@low"]\n')
        data = self.pick(role="implementer_backend")
        self.assertEqual((data["model"], data["effort"]), ("claude-sonnet-5-5", "low"))
        self.assertEqual(self.pick(role="implementer_backend", fixture="all_exhausted", code=3)["skipped"],
                         [{"candidate": "anthropic.mid@low", "why": "exhausted"}])

    def test_unknown_author(self):
        result = self.run_script("pick", "--role", "reviewer_code", "--tier", "t23",
                                 "--author", "missing", "--no-limits")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown author", result.stderr)

    def test_author_in_any_provider(self):
        self.config.write_text(CONFIG.replace('mid = "claude-sonnet-5-5"', 'mid = "older-sonnet"')
                               + '\n[[providers]]\nfamily = "anthropic"\nharness = "claude-code"\n'
                               + 'models = { mid = "claude-sonnet-5-5" }\n')
        data = self.pick("--author", "older-sonnet")
        self.assertEqual(data["model"], "gpt-6.1-sol")
        self.assertFalse(data["independence_weakened"])

    def test_unknown_role_and_tier(self):
        for role, tier, expected in [("missing", "t23", "reviewer_code"),
                                     ("reviewer_code", "bad", "t01, t23")]:
            with self.subTest(role=role, tier=tier):
                result = self.run_script("pick", "--role", role, "--tier", tier, "--no-limits")
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected, result.stderr)

    def test_all_exhausted(self):
        data = self.pick("--author", "claude-opus-5-5", fixture="all_exhausted", code=3)
        self.assertIn("error", data)
        self.assertEqual(len(data["skipped"]), 4)
        self.assertTrue(all(item["why"] == "exhausted" for item in data["skipped"][:3]))
        self.assertEqual(data["skipped"][3], {"candidate": "deepseek.mid@high", "why": "family not configured"})
        result = self.run_script("pick", "--role", "reviewer_code", "--tier", "t23",
                                 "--limits", str(FIXTURES / "all_exhausted.json"))
        self.assertEqual(result.returncode, 3)
        self.assertIn("skipped", json.loads(result.stdout))

    def test_orca_limits_acquisition_and_failure(self):
        executable = Path(self.temp.name) / "orca"
        self.env["PATH"] = self.temp.name
        command = ["pick", "--role", "reviewer_code", "--tier", "t23", "--json",
                   "--author", "claude-opus-5-5"]
        for body, expected in [
            ('test "$*" = "account list --json" || exit 1\ncat', None),
            ('exit 1', "unknown"),
            ('echo invalid-json', "unknown"),
        ]:
            with self.subTest(body=body):
                if expected is None:
                    body = ('test "$*" = "account list --json" || exit 1\n'
                            + f"/bin/cat '{FIXTURES / 'openai_exhausted.json'}'")
                executable.write_text("#!/bin/sh\n" + body + "\n")
                executable.chmod(0o755)
                result = self.run_script(*command)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                if expected is None:
                    self.assertEqual(data["model"], "claude-sonnet-5-5")
                    self.assertEqual(data["limits"]["openai"]["weekly"], 100)
                else:
                    self.assertEqual(data["limits"], expected)
                    self.assertIn("G7: limits unknown — ask the owner before long or parallel work", data["notes"])
        executable.unlink()
        result = self.run_script(*command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["limits"], "unknown")

    def test_unknown_limits_and_author_note(self):
        for args, fixture in [(('--no-limits',), "available"), ((), "unknown")]:
            with self.subTest(args=args):
                data = self.pick(*args, fixture=fixture)
                self.assertEqual(data["limits"], "unknown")
                self.assertIn("G7: limits unknown — ask the owner before long or parallel work", data["notes"])
                self.assertIn("author unknown — independence not checked", data["notes"])

    def test_missing_family_and_class(self):
        self.override('\n[roles.mechanical]\nt23 = ["missing.mid@high", "openai.top@high", "openai.cheap@low"]\n')
        data = self.pick(role="mechanical")
        self.assertEqual(data["model"], "gpt-6-luna")
        self.assertEqual([x["why"] for x in data["skipped"]],
                         ["family not configured", "class has no model id"])

    def test_configured_family_with_no_models(self):
        self.override('\n[[providers]]\nfamily = "empty"\nharness = "codex"\nmodels = {}\n'
                      '\n[roles.mechanical]\nt23 = ["empty.mid@high", "openai.cheap@low"]\n')
        data = self.pick(role="mechanical")
        self.assertEqual(data["skipped"], [{"candidate": "empty.mid@high", "why": "class has no model id"}])

    def test_non_review_ignores_author(self):
        data = self.pick("--author", "missing", role="implementer_backend")
        self.assertEqual(data["model"], "gpt-6.1-sol")
        self.assertFalse(data["independence_weakened"])
        self.assertEqual(data["notes"], [])

    def test_t01_and_human_output(self):
        self.assertEqual(self.pick(tier="t01")["effort"], "medium")
        result = self.run_script("pick", "--role", "reviewer_code", "--tier", "t23",
                                 "--author", "claude-opus-5-5", "--limits", str(FIXTURES / "available.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "reviewer_code t23 → gpt-6.1-sol@high (codex) · independence ok")

    def test_old_table_modes(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("families: anthropic, openai", result.stdout)
        self.assertIn("reviewer_code", result.stdout)
        result = self.run_script("--role", "reviewer_code", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        table = json.loads(result.stdout)["matrix"]
        self.assertEqual(list(table), ["reviewer_code"])
        self.assertEqual(table["reviewer_code"]["t23"]["primary"]["model"], "gpt-6.1-sol")


if __name__ == "__main__":
    unittest.main()
