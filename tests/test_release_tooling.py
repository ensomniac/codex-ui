"""Regression cases for release-reference drift and actual prior release selection."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare import release_references
from smoke_release import select_previous


class ReleaseToolingTests(unittest.TestCase):
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
