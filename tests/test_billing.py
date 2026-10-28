"""Billing shape: monthly checkout carries the 14-day trial; /pricing says so."""

import pathlib
import tempfile
import unittest

from likeness_license import web


class TestBillingTrial(unittest.TestCase):
    def _billing(self, tmp):
        env = {
            "STRIPE_SECRET_KEY": "sk_test_x",
            "STRIPE_WEBHOOK_SECRET": "whsec_test",
            "STRIPE_PRICES": "creator=price_123,agency=price_456",
            "PUBLIC_URL": "https://example.test",
        }
        srv = web.make_server("127.0.0.1", 0, pathlib.Path(tmp), env=env)
        return srv.RequestHandlerClass.billing

    def test_monthly_checkout_carries_14_day_trial(self):
        with tempfile.TemporaryDirectory() as t:
            billing = self._billing(t)
            sent = {}
            billing._stripe = lambda path, form: sent.update(form) or {"url": "https://checkout.test/s"}
            url = billing.checkout("creator")
            self.assertEqual(url, "https://checkout.test/s")
            self.assertEqual(sent["mode"], "subscription")
            self.assertEqual(sent["line_items[0][price]"], "price_123")
            self.assertEqual(sent["subscription_data[trial_period_days]"], "14")

    def test_pricing_page_notes_trial_when_billing_enabled(self):
        with tempfile.TemporaryDirectory() as t:
            billing = self._billing(t)
            self.assertTrue(billing.enabled)
            self.assertIn("14-day free trial", web.pricing_page(billing))


if __name__ == "__main__":
    unittest.main()
