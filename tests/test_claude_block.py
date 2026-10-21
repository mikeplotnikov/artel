"""Guard: the managed artel block must survive instruction-file sync tools unchanged.

Sync tools that generate AGENTS.md from CLAUDE.md rewrite harness-specific terms (the reference
setup's sync-to-codex.py: adapt_common_text). doctor check 6 compares the two blocks byte for byte,
so any such term inside the block makes check 6 fail forever. Run: python3 -m unittest discover tests
(ARTEL_INIT may point at another init.py to prove the guard on an old version).
"""
import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = Path(os.environ.get("ARTEL_INIT", ROOT / "skills" / "artel-init" / "scripts" / "init.py"))
# terms rewritten by the reference sync tool (molyanov-ai-dev scripts/sync-to-codex.py, adapt_common_text)
SYNC_REWRITTEN = ["CLAUDE.md", ".claude", "Claude Code", "TodoWrite", "TaskCreate", "TeamCreate",
                  "AskUserQuestion", "Task tool"]


def load_init():
    spec = importlib.util.spec_from_file_location("artel_init", INIT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ClaudeBlockSurvivesSync(unittest.TestCase):
    def test_block_has_no_sync_rewritten_terms(self):
        init = load_init()
        settings = {"profile": "critical", "data_class": "personal-data", "release_branch": "main",
                    "dev_branch": "dev", "prod_operations_allowed": ["rollback", "ops.yml"]}
        block = init.claude_block(settings)
        found = [t for t in SYNC_REWRITTEN if t in block]
        self.assertEqual(found, [], f"block contains terms a sync tool rewrites: {found}")


if __name__ == "__main__":
    unittest.main()
