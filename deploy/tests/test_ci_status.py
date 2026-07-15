import importlib.machinery
import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "bin" / "goal-ci-status"
loader = importlib.machinery.SourceFileLoader("goal_ci_status", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


class CiStatusTests(unittest.TestCase):
    sha = "a" * 40

    def run_payload(self, **overrides):
        run = {
            "id": 1,
            "run_attempt": 1,
            "head_sha": self.sha,
            "head_branch": "main",
            "event": "push",
            "status": "completed",
            "conclusion": "success",
        }
        run.update(overrides)
        return module.classify({"workflow_runs": [run]}, self.sha)

    def test_accepts_successful_main_push_for_exact_sha(self):
        self.assertEqual(self.run_payload(), "success")

    def test_rejects_pull_request_run(self):
        self.assertEqual(self.run_payload(event="pull_request"), "missing")

    def test_rejects_other_branch_or_sha(self):
        self.assertEqual(self.run_payload(head_branch="feature"), "missing")
        self.assertEqual(self.run_payload(head_sha="b" * 40), "missing")

    def test_defers_running_ci_and_blocks_terminal_failure(self):
        self.assertEqual(self.run_payload(status="in_progress", conclusion=None), "pending")
        self.assertEqual(self.run_payload(conclusion="failure"), "failure")

    def test_prefers_latest_attempt(self):
        old = {
            "id": 1,
            "run_attempt": 1,
            "head_sha": self.sha,
            "head_branch": "main",
            "event": "push",
            "status": "completed",
            "conclusion": "failure",
        }
        new = {**old, "id": 2, "run_attempt": 2, "conclusion": "success"}
        self.assertEqual(module.classify({"workflow_runs": [old, new]}, self.sha), "success")


if __name__ == "__main__":
    unittest.main()
