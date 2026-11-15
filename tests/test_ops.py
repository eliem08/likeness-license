import contextlib
import io
import os
import tempfile
import unittest

from likeness_license.__main__ import main
from likeness_license.ops import load


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(list(argv))
    return code, out.getvalue()


class LikenessOpsTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("LIKENESS_SECRET", None)
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "likeness.json")
        self.s = ["--store", self.path]
        self.media = os.path.join(self.tmp.name, "voice.wav")
        with open(self.media, "wb") as fh:
            fh.write(b"\x00\x01ana-voice")
        self.ok("owner-register", "Ana", self.media, "--kind", "voice", "--uses", "advertising", "games")

    def tearDown(self):
        self.tmp.cleanup()

    def ok(self, *argv):
        code, out = run(*argv, *self.s)
        self.assertEqual(code, 0, out)
        return out

    def issue(self, *extra):
        out = self.ok("license", "Ana", "Acme", "--use", "advertising", "--days", "90", "--start", "2026-12-01", *extra)
        return out.strip().splitlines()[-1]

    def test_certificate_verifies_after_a_restart_and_only_for_its_terms(self):
        cert = self.issue()
        day = ["--on", "2026-12-15"]
        # every CLI call builds a new Registry: this passes only because the key is durable
        self.assertEqual(run("verify", cert, "--use", "advertising", *day, *self.s)[0], 0)
        self.assertEqual(run("verify", cert, "--use", "games", *day, *self.s)[0], 1)
        self.assertEqual(run("verify", cert, "--use", "advertising", "--on", "2027-06-01", *self.s)[0], 1)
        self.assertEqual(run("verify", cert[:-4] + "0000", "--use", "advertising", *day, *self.s)[0], 1)
        self.ok("revoke", "LIC-00001")
        self.assertEqual(run("verify", cert, "--use", "advertising", *day, *self.s)[0], 1)

    def test_owner_terms_are_enforced(self):
        for extra in (["--purpose", "political"], ["--exclusive"], ["--days", "900"]):
            argv = ["license", "Ana", "PAC", "--use", "advertising", "--days", "30", *extra]
            with self.subTest(extra=extra):
                self.assertEqual(run(*argv, *self.s)[0], 1)
        self.assertEqual(run("license", "Ana", "Studio", "--use", "film", "--days", "30", *self.s)[0], 1)
        self.assertEqual(load(self.path).licenses, {})

    def test_same_media_cannot_be_claimed_by_someone_else(self):
        self.assertIn("registered to Ana", self.ok("whose", self.media))
        code, out = run("owner-register", "Mallory", self.media, "--kind", "voice", "--uses", "film", *self.s)
        self.assertEqual(code, 1, out)
        other = os.path.join(self.tmp.name, "other.wav")
        with open(other, "wb") as fh:
            fh.write(b"someone else")
        self.assertEqual(run("whose", other, *self.s)[0], 1)

    def test_usage_drives_the_royalty_statement(self):
        self.issue()
        self.ok("usage", "LIC-00001", "--impressions", "250000", "--generations", "4000")
        self.assertIn("royalty $   700.00", self.ok("statement", "Ana"))
        self.assertEqual(run("usage", "LIC-00001", "--impressions", "-5", *self.s)[0], 1)
        self.assertEqual(run("usage", "LIC-99999", "--impressions", "5", *self.s)[0], 1)


if __name__ == "__main__":
    unittest.main()
