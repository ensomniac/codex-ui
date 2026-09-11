import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("review_lib", Path(__file__).parents[1] / "scripts/review_lib.py")
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH is required for signature tests")
class TrustedReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.key = Path(cls.temp.name) / "test-key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(cls.key)], check=True)
        cls.signers = Path(cls.temp.name) / "allowed_signers"
        cls.signers.write_text('ryan-agent namespaces="codex-ui-review" ' + cls.key.with_suffix('.pub').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_genuine_signature_round_trip_and_changed_head_rejection(self):
        value = review.payload(12, "a" * 40, "b" * 40)
        signature = review.sign(value, self.key)
        self.assertTrue(review.verify(value, signature, value, self.signers))
        newer = review.payload(12, "c" * 40, "b" * 40)
        self.assertFalse(review.verify(value, signature, newer, self.signers))

    def test_signature_cannot_be_replayed_for_another_pr_or_base(self):
        value = review.payload(12, "a" * 40, "b" * 40)
        signature = review.sign(value, self.key)
        self.assertFalse(review.verify(value, signature, review.payload(13, "a" * 40, "b" * 40), self.signers))
        self.assertFalse(review.verify(value, signature, review.payload(12, "a" * 40, "c" * 40), self.signers))

    def test_unsigned_and_other_identity_approvals_do_not_count(self):
        pr = {"number": 12, "head": {"sha": "a" * 40}, "base": {"sha": "b" * 40}}
        value = review.payload(12, "a" * 40, "b" * 40)
        body = review.envelope(value, review.sign(value, self.key))
        item = {"id": 1, "user": {"login": "ensomniac"}, "state": "APPROVED", "commit_id": "a" * 40, "body": body}
        self.assertTrue(review.approved(pr, [item], self.signers))
        self.assertFalse(review.approved(pr, [{**item, "body": "LGTM"}], self.signers))
        self.assertFalse(review.approved(pr, [{**item, "user": {"login": "another-agent"}}], self.signers))
        dismissed = {**item, "id": 2, "state": "DISMISSED"}
        self.assertFalse(review.approved(pr, [item, dismissed], self.signers))

    def test_expired_or_modified_payload_is_rejected(self):
        value = review.payload(12, "a" * 40, "b" * 40, issued=1)
        self.assertFalse(review.verify(value, review.sign(value, self.key), value, self.signers))
        current = review.payload(12, "a" * 40, "b" * 40)
        signature = review.sign(current, self.key)
        current["issued"] -= 1
        self.assertFalse(review.verify(current, signature, current, self.signers))
