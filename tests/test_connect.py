"""Stripe Connect payouts (generated from _tools/connect_test_template.py; the network is blocked)."""

import contextlib
import io
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from likeness_license import connect
from likeness_license.__main__ import main

ROOT = pathlib.Path(__file__).resolve().parent.parent
SETUP = {
    "agent_work": (
        "scribe",
        [
            ["agent-register", "scribe", "--skills", "writing", "--price", "80", "--eta-hours", "6"],
            ["job-post", "acme", "Write posts", "--skills", "writing", "--budget", "120", "--deadline-hours", "12"],
            ["bid", "J1", "scribe", "100"],
            ["award", "B2"],
            ["start", "J1"],
            ["submit", "J1", "--deliverable", "https://example.com/posts"],
            ["approve", "J1", "--rating", "5"],
        ],
    ),
    "gpu_bnb": (
        "maya",
        [
            ["host-list", "maya", "--gpu", "RTX 4090", "--vram-gb", "24", "--hourly", "0.6", "--window", "18-24"],
            ["book", "L1", "sam", "--start", "2026-12-01T18:00", "--end", "2026-12-01T22:00"],
            ["complete", "B2"],
        ],
    ),
    "chore_footage": (
        "ana",
        [
            [
                "submit",
                "ana",
                "fold-laundry",
                str(ROOT / "examples" / "sample-clip.txt"),
                "--seconds",
                "120",
                "--resolution",
                "1080p",
                "--fps",
                "30",
                "--hands-visible",
                "0.9",
                "--lighting",
                "0.9",
                "--consent-signed",
            ],
        ],
    ),
    "likeness_license": (
        "Ana Diaz",
        [
            [
                "owner-register",
                "Ana Diaz",
                str(ROOT / "examples" / "sample-voice.txt"),
                "--kind",
                "voice",
                "--uses",
                "advertising",
            ],
            ["license", "Ana Diaz", "Acme Ads", "--use", "advertising", "--days", "90"],
            ["usage", "LIC-00001", "--impressions", "250000", "--generations", "4000"],
        ],
    ),
}


class FakeStripe:
    """Answers like Stripe for the four calls used, and honours idempotency keys the way Stripe does."""

    def __init__(self, ready=True):
        self.ready, self.calls, self.by_key, self.transfers = ready, [], {}, []

    def __call__(self, method, path, key, form=None, idempotency_key=None):
        self.calls.append((method, path, form, idempotency_key))
        if idempotency_key in self.by_key:
            return self.by_key[idempotency_key]
        if path == "/accounts":
            res = {"id": "acct_1TestPayee", "object": "account"}
        elif path == "/account_links":
            res = {"object": "account_link", "url": "https://connect.stripe.com/setup/e/acct_1TestPayee/abc"}
        elif path.startswith("/accounts/"):
            state = "active" if self.ready else "inactive"
            res = {
                "id": path.split("/")[-1],
                "capabilities": {"transfers": state},
                "requirements": {"currently_due": [] if self.ready else ["external_account"]},
            }
        elif path == "/transfers":
            res = {"object": "transfer", "id": f"tr_{len(self.transfers) + 1:04d}", "amount": int(form["amount"])}
            self.transfers.append(form)
        else:
            raise AssertionError(path)
        if idempotency_key:
            self.by_key[idempotency_key] = res
        return res


class ConnectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = os.path.join(self.tmp.name, "store.json")
        env = {"CONNECT_STRIPE_KEY": "sk_test_platform", "PUBLIC_URL": "https://market.example.com"}
        self.patches = [
            mock.patch.dict(os.environ, env),
            mock.patch("urllib.request.urlopen", side_effect=AssertionError("tests must not touch the network")),
        ]
        for p in self.patches:
            p.start()
        self.payee, steps = SETUP["likeness_license"]
        for argv in steps:
            code, out = self.cli(*argv)
            self.assertIn(code, (0, 1), (argv, out))

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main([*argv, "--store", self.store])
        return code, out.getvalue()

    def test_onboard_then_pay_exactly_once(self):
        fake = FakeStripe()
        with mock.patch.object(connect, "_call", fake):
            _, out = self.cli("payout-send", "--dry-run")
            self.assertIn(f"skip {self.payee}", out)
            self.assertIn("not onboarded", out)
            code, out = self.cli("payee-onboard", self.payee, "--email", "payee@example.com")
            self.assertEqual(code, 0, out)
            self.assertIn("https://connect.stripe.com/setup/", out)
            self.assertEqual(self.cli("payee-status", self.payee)[0], 0)
            _, out = self.cli("payout-send", "--dry-run")
            self.assertIn(f"would pay {self.payee}", out)
            self.assertEqual(fake.transfers, [])  # a dry run moves nothing
            code, out = self.cli("payout-send")
            self.assertEqual(code, 0, out)
            self.assertIn(f"paid {self.payee}", out)
            self.assertEqual(len(fake.transfers), 1)
            self.assertEqual(fake.transfers[0]["destination"], "acct_1TestPayee")
            self.assertGreater(int(fake.transfers[0]["amount"]), 0)
            _, out = self.cli("payout-send")
            self.assertIn("nothing owed", out)
            self.assertEqual(len(fake.transfers), 1)  # never twice
        accounts = [c for c in fake.calls if c[1] == "/accounts"]
        self.assertEqual(accounts[0][2]["capabilities[transfers][requested]"], "true")

    def test_unfinished_onboarding_is_skipped_and_keys_make_retries_safe(self):
        fake = FakeStripe(ready=False)
        with mock.patch.object(connect, "_call", fake):
            self.cli("payee-onboard", self.payee, "--email", "payee@example.com")
            code, out = self.cli("payee-status", self.payee)
            self.assertEqual(code, 1)
            self.assertIn("external_account", out)
            _, out = self.cli("payout-send")
            self.assertIn("account not ready", out)
            self.assertEqual(fake.transfers, [])
            fake.ready = True
            _, out = self.cli("payout-send")
            self.assertIn(f"paid {self.payee}", out)
            key = next(c[3] for c in fake.calls if c[1] == "/transfers")
            self.assertTrue(key.startswith(("agent-work", "gpu-bnb", "chore-footage", "likeness-license")))
            # a retry with the same ledger state reuses the key, and Stripe answers with the first transfer
            again = connect.Connect(key="sk_test_platform", call=fake).transfer(
                "acct_1TestPayee", 1, "usd", key, self.payee, "x"
            )
            self.assertEqual(again["id"], "tr_0001")
            self.assertEqual(len(fake.transfers), 1)

    def test_refusals(self):
        with mock.patch.dict(os.environ, {"CONNECT_STRIPE_KEY": ""}):
            self.assertIn("CONNECT_STRIPE_KEY", self.cli("payee-onboard", self.payee, "--email", "a@b.co")[1])
        with (
            mock.patch.dict(os.environ, {"PUBLIC_URL": "http://insecure"}),
            mock.patch.object(connect, "_call", FakeStripe()),
        ):
            self.assertIn("PUBLIC_URL", self.cli("payee-onboard", self.payee, "--email", "a@b.co")[1])
        with mock.patch.object(connect, "_call", FakeStripe()):
            self.assertEqual(self.cli("payee-onboard", self.payee, "--email", "not-an-email")[0], 1)
            self.assertEqual(self.cli("payee-status", "nobody")[0], 1)
            self.assertEqual(self.cli("payout-send", "--currency", "dollars")[0], 1)


class RuntimeTests(unittest.TestCase):
    """The shared logic, independent of any marketplace's ledger."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.book = connect.Book(os.path.join(self.tmp.name, "x.json"))
        self.book.accounts = {"p": "acct_1TestPayee"}
        self.net = mock.patch("urllib.request.urlopen", side_effect=AssertionError("no network"))
        self.net.start()

    def tearDown(self):
        self.net.stop()
        self.tmp.cleanup()

    def test_cumulative_pays_only_the_difference(self):
        fake = FakeStripe()
        c = connect.Connect(key="sk_test_x", call=fake)
        connect.payout_run(self.book, c, {"p": 100.0}, "demo")
        connect.payout_run(self.book, c, {"p": 130.5}, "demo")
        self.assertEqual([f["amount"] for f in fake.transfers], ["10000", "3050"])
        self.assertEqual(connect.payout_run(self.book, c, {"p": 130.5}, "demo"), ["nothing owed above the minimum"])

    def test_settle_mode_records_in_the_ledger(self):
        fake, settled = FakeStripe(), []
        c = connect.Connect(key="sk_test_x", call=fake)
        connect.payout_run(self.book, c, {"p": 40.0}, "demo", settle=lambda *a: settled.append(a))
        self.assertEqual(settled, [("p", 40.0, "tr_0001")])

    def test_a_failed_transfer_is_reported_not_recorded(self):
        def failing(method, path, key, form=None, idempotency_key=None):
            if path == "/transfers":
                raise connect.ConnectError("Stripe said 400: insufficient funds in your Stripe balance")
            return FakeStripe()(method, path, key, form, idempotency_key)

        lines = connect.payout_run(self.book, connect.Connect(key="sk_test_x", call=failing), {"p": 5.0}, "demo")
        self.assertIn("FAILED p", lines[0])
        self.assertIn("insufficient funds", lines[0])
        self.assertEqual(self.book.transfers, [])


if __name__ == "__main__":
    unittest.main()
