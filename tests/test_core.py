import unittest
from datetime import date

from likeness_license import LicenseError, Registry, Terms

D = date(2026, 11, 1)


class Tests(unittest.TestCase):
    def setUp(self):
        self.r = Registry(b"k")
        self.r.register("ava", [b"face1", b"face2"], "face", Terms({"advertising", "games"}, territories={"US"}, exclusive_available=True))

    def test_fingerprint_lookup(self):
        self.assertEqual(self.r.owner_of(b"face2"), "ava")
        self.assertIsNone(self.r.owner_of(b"someone else"))

    def test_issue_and_verify(self):
        cert = self.r.request("ava", "studio", "games", "US", D, 100)
        self.assertTrue(self.r.verify(cert, "games", "US", date(2026, 12, 1))[0])
        self.assertFalse(self.r.verify(cert, "games", "US", date(2027, 6, 1))[0])
        self.assertFalse(self.r.verify(cert, "advertising", "US", date(2026, 12, 1))[0])
        self.assertEqual(self.r.verify(cert[:-3] + "abc", "games", "US", D), (False, "invalid signature"))

    def test_refusals(self):
        with self.assertRaises(LicenseError):
            self.r.request("ava", "x", "film", "US", D, 10)
        with self.assertRaises(LicenseError):
            self.r.request("ava", "x", "games", "FR", D, 10)
        with self.assertRaises(LicenseError):
            self.r.request("ava", "x", "advertising", "US", D, 10, purpose_tags={"political"})
        with self.assertRaises(LicenseError):
            self.r.request("ava", "x", "games", "US", D, 1000)

    def test_exclusivity_and_revocation(self):
        cert = self.r.request("ava", "a", "advertising", "US", D, 100, exclusive=True)
        with self.assertRaises(LicenseError):
            self.r.request("ava", "b", "advertising", "US", D, 10)
        self.r.revoke("LIC-00001")
        self.assertEqual(self.r.verify(cert, "advertising", "US", D), (False, "licence revoked"))
        self.r.request("ava", "b", "advertising", "US", D, 10)

    def test_statement(self):
        self.r.request("ava", "a", "games", "US", D, 365)
        self.r.report_usage("LIC-00001", impressions=10_000, generations=100)
        st = self.r.statement("ava")
        self.assertEqual(st["lines"][0]["royalty"], 25.0)
        self.assertEqual(st["total"], 3025.0)


if __name__ == "__main__":
    unittest.main()
