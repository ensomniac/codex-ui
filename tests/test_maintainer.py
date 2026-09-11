"""Regression coverage for held PR builds and review races."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import maintainer


class MaintainerTests(unittest.TestCase):
    def setUp(self):
        self.pr = {"number": 2, "state": "open", "draft": False,
                   "user": {"login": "github-actions[bot]"},
                   "head": {"sha": "a" * 40}, "base": {"ref": "main", "sha": "b" * 40}}
        self.run = {"id": 10, "event": "pull_request", "head_sha": "a" * 40,
                    "pull_requests": [{"number": 2}], "html_url": "https://github.com/run/10",
                    "status": "completed", "conclusion": "success"}

    def test_held_pr_build_is_started_once_and_observed_until_success(self):
        held = {**self.run, "conclusion": "action_required"}
        queued = {**self.run, "status": "queued", "conclusion": None}
        responses = [{"workflow_runs": [held]}, None, queued, self.pr, self.run]
        with patch.object(maintainer, "gh_api", side_effect=responses) as api, \
                patch.object(maintainer.time, "sleep"):
            maintainer.ensure_ci(self.pr)
        writes = [call for call in api.call_args_list if call.kwargs.get("method") == "POST"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].args[0], "repos/ensomniac/codex-ui/actions/runs/10/approve")

    def test_branch_build_and_other_pr_cannot_satisfy_pr_ci(self):
        branch = {**self.run, "event": "workflow_dispatch"}
        other = {**self.run, "pull_requests": [{"number": 3}]}
        with patch.object(maintainer, "gh_api", return_value={"workflow_runs": [branch, other]}):
            with self.assertRaisesRegex(SystemExit, "no CI run"):
                maintainer.ensure_ci(self.pr)

    def test_latest_failed_build_is_not_hidden_by_an_older_success(self):
        failed = {**self.run, "id": 11, "conclusion": "failure"}
        with patch.object(maintainer, "gh_api", side_effect=[
            {"workflow_runs": [self.run, failed]}, failed,
        ]) as api:
            with self.assertRaisesRegex(SystemExit, "did not pass"):
                maintainer.ensure_ci(self.pr)
        self.assertFalse(any(call.kwargs.get("method") for call in api.call_args_list))

    def test_changed_head_or_base_stops_waiting_without_signing(self):
        queued = {**self.run, "status": "in_progress", "conclusion": None}
        for field in ("head", "base"):
            with self.subTest(field=field):
                changed = deepcopy(self.pr)
                changed[field]["sha"] = "c" * 40
                with patch.object(maintainer, "gh_api", side_effect=[
                    {"workflow_runs": [queued]}, queued, changed,
                ]), patch.object(maintainer.time, "sleep") as sleep:
                    with self.assertRaisesRegex(SystemExit, "changed"):
                        maintainer.ensure_ci(self.pr)
                sleep.assert_not_called()

    def test_other_identity_cannot_start_ci_or_sign(self):
        args = ["maintainer.py", "2", "--head", "a" * 40, "--body-file", "unused.md"]
        with patch.object(sys, "argv", args), \
                patch.object(maintainer, "gh_api", return_value={"login": "another-agent"}) as api:
            with self.assertRaisesRegex(SystemExit, "ensomniac GitHub identity"):
                maintainer.main()
        api.assert_called_once_with("user")


if __name__ == "__main__":
    unittest.main()
