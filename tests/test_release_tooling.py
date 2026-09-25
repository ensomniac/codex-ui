"""Regression cases for release-reference drift and actual prior release selection."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare import release_references
from release_notes import render_notes
from smoke_release import select_previous


class ReleaseToolingTests(unittest.TestCase):
    def test_release_notes_select_exact_version_and_preserve_subheadings(self):
        changelog = "# Changelog\n\n## 2.1.0 — today\n\n- Current fix.\n\n### Caveat\nKeep this.\n\n## 2.1.01 — older\nWrong.\n\n## 2.0.0 — older\nOld fix.\n"
        notes = render_notes("2.1.0", "Install v{version}.", changelog)
        self.assertIn("Install v2.1.0.", notes)
        self.assertIn("### Caveat\nKeep this.", notes)
        self.assertIn("/blob/v2.1.0/CHANGELOG.md", notes)
        self.assertNotIn("Old fix", notes)
        self.assertNotIn("Wrong", notes)

    def test_release_notes_reject_missing_empty_or_duplicate_sections(self):
        for changelog in ("## 2.0.0\nOld.", "## 2.1.0\n\n", "## 2.1.0\nA\n## 2.1.0\nB"):
            with self.subTest(changelog=changelog), self.assertRaises(ValueError):
                render_notes("2.1.0", "Intro", changelog)

    def test_release_notes_reject_nonstable_version(self):
        with self.assertRaises(ValueError):
            render_notes("2.1.0-rc1", "Intro", "## 2.1.0-rc1\nDraft.")

    def test_public_assets_advance_together_without_rewriting_history(self):
        text = ("https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac_codex_ui-2.0.1-py3-none-any.whl\n"
                "https://github.com/ensomniac/codex-ui/releases/download/v2.0.1/ensomniac-codex-ui-2.0.1.tgz\n"
                '<span data-version>2.0.1</span>\nWindows 2.0.0 users need the 2.0.1 fix.')
        changed = release_references(text, '2.1.0')
        self.assertIn('/v2.1.0/ensomniac_codex_ui-2.1.0-py3-none-any.whl', changed)
        self.assertIn('/v2.1.0/ensomniac-codex-ui-2.1.0.tgz', changed)
        self.assertIn('<span data-version>2.1.0</span>', changed)
        self.assertIn('Windows 2.0.0 users need the 2.0.1 fix.', changed)

    def test_previous_release_is_highest_stable_before_target(self):
        releases = [dict(tag_name='v2.0.0'), dict(tag_name='v2.1.0'), dict(tag_name='v2.0.1'),
                    dict(tag_name='v2.0.9', draft=True), dict(tag_name='v2.0.8', prerelease=True)]
        self.assertEqual(select_previous(releases, '2.1.0')['tag_name'], 'v2.0.1')

    def test_missing_previous_release_is_not_a_synthetic_success(self):
        with self.assertRaisesRegex(RuntimeError, 'No actual previous'):
            select_previous([dict(tag_name='v2.1.0')], '2.1.0')


if __name__ == '__main__':
    unittest.main()
