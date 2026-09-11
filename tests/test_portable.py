from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from codex_ui import cli, lifecycle, skills
from codex_ui.backends.registry import capabilities
from codex_ui.models import Rect, UIControlError


class ContractTests(unittest.TestCase):
    def test_unhealthy_doctor_is_a_failure(self):
        output = io.StringIO()
        with mock.patch.object(cli, "dispatch", return_value={"ok": False}), redirect_stdout(output):
            status = cli.main(["doctor"])
        self.assertEqual(status, 1)
        self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_exception_keeps_versioned_json(self):
        output = io.StringIO()
        with mock.patch.object(cli, "dispatch", side_effect=UIControlError("No window matched")), redirect_stdout(output):
            status = cli.main(["capture", "--app", "Missing"])
        result = json.loads(output.getvalue())
        self.assertEqual(status, 1)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["error"]["message"], "No window matched")

    def test_lifecycle_is_portable_without_claiming_desktop_support(self):
        for platform in ("linux", "win32"):
            result = capabilities(platform)
            self.assertFalse(result["desktop_supported"])
            self.assertTrue(result["lifecycle"]["upgrade"])

    def test_schema_discovers_required_arguments(self):
        schema = cli.command_schema()
        press = schema["commands"]["press"]["arguments"]
        self.assertTrue(next(a for a in press if a["name"] == "name")["required"])
        self.assertIn("upgrade", schema["commands"])
        self.assertIn("chrome-dom", schema["commands"])

    def test_negative_desktop_geometry_is_preserved(self):
        left = Rect(-1600, 0, 1600, 900)
        self.assertEqual(left.center, (-800, 450))
        self.assertEqual(left.intersection_area(Rect(-100, 0, 200, 100)), 10000)


class LifecycleTests(unittest.TestCase):
    def release(self, version="99.0.0"):
        name = f"ensomniac_codex_ui-{version}-py3-none-any.whl"
        return {"tag_name": f"v{version}", "html_url": "https://github.com/ensomniac/codex-ui/releases",
                "assets": [{"name": name, "digest": "sha256:" + "a" * 64,
                            "browser_download_url": f"https://github.com/ensomniac/codex-ui/releases/download/v{version}/{name}"}]}

    def test_check_never_starts_an_installer(self):
        with mock.patch.object(lifecycle, "latest_release", return_value=self.release()), mock.patch.object(lifecycle, "run_installer") as installer:
            result = lifecycle.upgrade(check=True)
        self.assertTrue(result["update_available"])
        self.assertFalse(result["updated"])
        installer.assert_not_called()

    def test_corrupt_download_never_reaches_the_installer(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"corrupt wheel"
        with mock.patch.object(lifecycle, "latest_release", return_value=self.release()), mock.patch.object(lifecycle, "manager", return_value="uv"), mock.patch.object(lifecycle, "urlopen", return_value=response), mock.patch.object(lifecycle, "run_installer") as installer:
            with self.assertRaisesRegex(UIControlError, "checksum"):
                lifecycle.upgrade()
        installer.assert_not_called()

    def test_release_cannot_redirect_to_another_repository(self):
        release = self.release()
        release["assets"][0]["browser_download_url"] = "https://example.com/tool.whl"
        with self.assertRaisesRegex(UIControlError, "origin"):
            lifecycle.wheel_asset(release)

    def test_stable_versions_do_not_accept_shell_or_prerelease_text(self):
        for value in ("2.0.0-rc1", "2.0.0;echo x", "main"):
            with self.assertRaises(UIControlError):
                lifecycle.version_tuple(value)

    def test_pinned_manager_installs_are_replaced_not_reused(self):
        with mock.patch.object(lifecycle.sys, "platform", "darwin"):
            for manager in ("uv", "pipx"):
                command = lifecycle.upgrade_command(manager, "/tmp/release.whl")
                self.assertIn("--force", command)
                self.assertEqual(command[-1], "/tmp/release.whl")

    def test_windows_upgrade_preserves_the_running_interpreter(self):
        with mock.patch.object(lifecycle.sys, "platform", "win32"), mock.patch.object(lifecycle.shutil, "which", return_value="uv.exe"):
            command = lifecycle.upgrade_command("uv", "release.whl")
        self.assertEqual(command[:3], ["uv", "pip", "install"])
        self.assertNotIn("--force", command)
        self.assertIn(lifecycle.sys.executable, command)

    def test_skill_replacement_preserves_the_previous_customization(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "control-local-ui"
            target.mkdir()
            (target / "SKILL.md").write_text("Local customization")
            result = skills.install("generic", str(target))
            self.assertEqual(Path(result["backup"]).read_text(), "Local customization")
            self.assertIn("codex-ui", (target / "SKILL.md").read_text())
            self.assertIsNone(skills.install("generic", str(target))["backup"])


if __name__ == "__main__":
    unittest.main()
