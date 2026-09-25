from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import re
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "examples" / "inspect_page.py"
SPEC = importlib.util.spec_from_file_location("inspect_page", SCRIPT)
inspect_page = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspect_page)


class InspectPageExampleTests(unittest.TestCase):
    def test_missing_argument_shows_usage_without_running_cli(self):
        stderr = io.StringIO()
        with mock.patch.object(inspect_page.subprocess, "run") as run, redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                inspect_page.main([])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("usage:", stderr.getvalue())
        self.assertIn("url_fragment", stderr.getvalue())
        run.assert_not_called()

    def test_help_describes_fragment_without_running_cli(self):
        stdout = io.StringIO()
        with mock.patch.object(inspect_page.subprocess, "run") as run, redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                inspect_page.main(["--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("distinctive part of the target tab URL", stdout.getvalue())
        self.assertRegex(stdout.getvalue(), r"my-\s*project/index\.html")
        run.assert_not_called()

    def test_forwards_fragment_with_spaces_as_one_argument(self):
        fragment = "my project/index.html"
        result = mock.Mock(returncode=0, stdout='{"ok": true}')
        stdout = io.StringIO()
        with mock.patch.object(inspect_page.subprocess, "run", return_value=result) as run:
            with redirect_stdout(stdout):
                inspect_page.main([fragment])

        self.assertEqual(run.call_args.args[0], [
            "codex-ui", "--compact", "chrome-dom", "--chrome-url", fragment,
            "--selector", "main", "--depth", "1",
        ])
        self.assertEqual(json.loads(stdout.getvalue()), {"ok": True})

    def test_preserves_json_error_exit_behavior(self):
        result = mock.Mock(returncode=1, stdout='{"error": {"message": "No matching tab"}}')
        with mock.patch.object(inspect_page.subprocess, "run", return_value=result):
            with self.assertRaises(SystemExit) as raised:
                inspect_page.main(["project/index.html"])

        self.assertEqual(raised.exception.code, "No matching tab")


if __name__ == "__main__":
    unittest.main()
