"""Stripe Connect payouts for a marketplace ledger (shared runtime, identical in every marketplace).

The marketplace's own ledger says what each payee has earned in total. This module pays the difference
between that and what was already transferred, through Stripe Connect:

  payee-onboard NAME --email E   create (or reuse) a Stripe Express account and print its onboarding link
  payee-status NAME              whether Stripe lets that account receive transfers yet
  payout-send [--dry-run]        transfer what is owed to every onboarded payee

Safety:
- CONNECT_STRIPE_KEY is the platform account's secret key, kept apart from STRIPE_SECRET_KEY (the hosted
  server's own subscription billing), so payouts never come from the wrong account.
- Each transfer's Stripe idempotency key is derived from the payee and their cumulative earnings, so running
  payout-send twice, or retrying after a timeout, never pays twice.
- Payees whose account cannot receive transfers yet are skipped and named, never paid somewhere else.
- Transfers are recorded in a file beside the ledger (<store>.connect.json); amounts go out in the smallest
  currency unit (cents).
- Transfers draw on the platform's Stripe balance: collecting the money from buyers (Checkout, invoices) comes
  first, and Stripe refuses a transfer the balance cannot cover.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.stripe.com/v1"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ACCT_RE = re.compile(r"^acct_[A-Za-z0-9]{6,}$")


class ConnectError(ValueError):
    pass


def _call(method: str, path: str, key: str, form: dict | None = None, idempotency_key: str | None = None) -> dict:
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    headers = {"Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    req = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        with e:
            try:
                err = json.loads(e.read()).get("error", {})
            except ValueError:
                err = {}
        raise ConnectError(f"Stripe said {e.code}: {err.get('message') or err.get('code') or 'no detail'}") from None
    except (urllib.error.URLError, OSError) as e:
        raise ConnectError(f"could not reach Stripe: {e}; running the same command again is safe") from None


class Connect:
    def __init__(self, key: str | None = None, call=None):
        self.key = key if key is not None else os.environ.get("CONNECT_STRIPE_KEY", "")
        if not self.key.startswith(("sk_", "rk_")):
            raise ConnectError("set CONNECT_STRIPE_KEY to the platform's Stripe secret key to pay out")
        self.call = call

    def _c(self, *a, **kw):
        return (self.call or _call)(*a, **kw)

    def create_account(self, payee: str, email: str) -> str:
        res = self._c(
            "POST",
            "/accounts",
            self.key,
            {
                "type": "express",
                "email": email,
                "capabilities[transfers][requested]": "true",
                "metadata[payee]": payee,
            },
            f"connect-account-{payee}",
        )
        if not ACCT_RE.match(str(res.get("id", ""))):
            raise ConnectError(f"unexpected answer from Stripe: {str(res)[:200]}")
        return res["id"]

    def onboarding_link(self, acct: str, base_url: str) -> str:
        res = self._c(
            "POST",
            "/account_links",
            self.key,
            {
                "account": acct,
                "refresh_url": f"{base_url}/",
                "return_url": f"{base_url}/",
                "type": "account_onboarding",
            },
        )
        if not str(res.get("url", "")).startswith("https://"):
            raise ConnectError(f"unexpected answer from Stripe: {str(res)[:200]}")
        return res["url"]

    def can_receive(self, acct: str) -> tuple[bool, str]:
        res = self._c("GET", f"/accounts/{acct}", self.key)
        state = (res.get("capabilities") or {}).get("transfers", "inactive")
        if state == "active":
            return True, "ready to receive transfers"
        due = (res.get("requirements") or {}).get("currently_due") or []
        return False, f"transfers {state}" + (f"; Stripe still needs: {', '.join(due[:5])}" if due else "")

    def transfer(self, acct: str, cents: int, currency: str, key: str, payee: str, product: str) -> dict:
        res = self._c(
            "POST",
            "/transfers",
            self.key,
            {
                "amount": str(cents),
                "currency": currency,
                "destination": acct,
                "description": f"{product} payout to {payee}",
                "metadata[payee]": payee,
                "metadata[product]": product,
            },
            key,
        )
        if res.get("object") != "transfer" or not res.get("id"):
            raise ConnectError(f"unexpected answer from Stripe: {str(res)[:200]}")
        return res


class Book:
    """Who is onboarded and what was transferred, kept beside the marketplace's own ledger."""

    def __init__(self, store: str):
        self.path = f"{os.path.splitext(store)[0]}.connect.json"
        try:
            with open(self.path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except FileNotFoundError:
            doc = {}
        self.accounts: dict[str, str] = dict(doc.get("accounts", {}))
        self.transfers: list[dict] = list(doc.get("transfers", []))

    def save(self):
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"accounts": self.accounts, "transfers": self.transfers}, fh, indent=2)
        os.replace(tmp, self.path)

    def sent_cents(self, payee: str, currency: str) -> int:
        return sum(t["cents"] for t in self.transfers if t["payee"] == payee and t["currency"] == currency)


def public_url() -> str:
    url = os.environ.get("PUBLIC_URL", "").rstrip("/")
    if not url.startswith("https://"):
        raise ConnectError("set PUBLIC_URL to this server's https address; Stripe sends payees back there")
    return url


def onboard(book: Book, connect: Connect, payee: str, email: str) -> tuple[str, str]:
    if not payee.strip():
        raise ConnectError("payee name is empty")
    if not EMAIL_RE.match(email or ""):
        raise ConnectError(f"{email!r} is not an email address")
    base = public_url()
    acct = book.accounts.get(payee) or connect.create_account(payee, email)
    book.accounts[payee] = acct
    book.save()
    return acct, connect.onboarding_link(acct, base)


def payout_run(
    book: Book,
    connect: Connect | None,
    earned: dict[str, float],
    product: str,
    currency: str = "usd",
    min_amount: float = 1.0,
    dry_run: bool = False,
    settle=None,
) -> list[str]:
    """Transfer what each onboarded payee is owed. Returns one line per payee.

    Without `settle`, `earned` is cumulative and the amount owed is earned minus what was already sent.
    With `settle(payee, amount, transfer_id)`, `earned` is the current unpaid balance and settle records the
    payment in the marketplace's own ledger (which lowers that balance).
    """
    if not re.fullmatch(r"[a-z]{3}", currency):
        raise ConnectError("currency must be a three-letter code like usd")
    lines = []
    for payee, amount in sorted(earned.items()):
        total = round(float(amount) * 100)
        prior = sum(1 for t in book.transfers if t["payee"] == payee and t["currency"] == currency)
        owed = total if settle else total - book.sent_cents(payee, currency)
        if owed < round(min_amount * 100):
            continue
        acct = book.accounts.get(payee)
        money = f"{owed / 100:,.2f} {currency.upper()}"
        if not acct:
            lines.append(f"skip {payee}: {money} owed, not onboarded (payee-onboard {payee} --email ...)")
            continue
        if dry_run:
            lines.append(f"would pay {payee} {money} to {acct}")
            continue
        ok, why = connect.can_receive(acct)
        if not ok:
            lines.append(f"skip {payee}: {money} owed, account not ready ({why})")
            continue
        # the same ledger state always gives the same key, so a retry returns the first transfer, never a second
        key = (
            f"{product}-payout-{payee}-{currency}-{prior}-{total}"
            if settle
            else f"{product}-payout-{payee}-{currency}-{total}"
        )
        try:
            res = connect.transfer(acct, owed, currency, key, payee, product)
        except ConnectError as e:
            lines.append(f"FAILED {payee}: {money} not paid ({e})")
            continue
        book.transfers.append(
            {
                "payee": payee,
                "account": acct,
                "cents": owed,
                "currency": currency,
                "transfer": res["id"],
                "key": key,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        book.save()
        if settle:
            settle(payee, owed / 100, res["id"])
        lines.append(f"paid {payee} {money} ({res['id']})")
    return lines or ["nothing owed above the minimum"]


def add_commands(sub):
    """The marketplace's own loop adds --store to every command, these included."""
    p = sub.add_parser("payee-onboard", help="create a Stripe Express account for a payee and print the link")
    p.add_argument("payee")
    p.add_argument("--email", required=True)
    sub.add_parser("payee-status", help="can this payee's Stripe account receive transfers yet").add_argument("payee")
    p = sub.add_parser("payout-send", help="transfer what each onboarded payee is owed through Stripe Connect")
    p.add_argument("--currency", default="usd")
    p.add_argument("--min", type=float, default=1.0, help="skip payees owed less than this")
    p.add_argument("--dry-run", action="store_true", help="show the transfers without moving money")


COMMANDS = ("payee-onboard", "payee-status", "payout-send")


def run_command(a, earned_fn, product: str, settle_fn=None) -> int:
    """earned_fn(store) -> {payee: cumulative amount earned}. Returns an exit code; prints results."""
    try:
        book = Book(a.store)
        if a.cmd == "payee-onboard":
            acct, url = onboard(book, Connect(), a.payee, a.email)
            print(f"{a.payee}: Stripe account {acct}\nsend them this onboarding link (it expires): {url}")
        elif a.cmd == "payee-status":
            if a.payee not in book.accounts:
                raise ConnectError(f"{a.payee} is not onboarded")
            ok, why = Connect().can_receive(book.accounts[a.payee])
            print(f"{a.payee}: {why}")
            return 0 if ok else 1
        else:
            if not 0 <= a.min <= 1_000_000:
                raise ConnectError("--min must be between 0 and 1000000")
            connect = None if a.dry_run else Connect()
            settle = (lambda payee, amount, tid: settle_fn(a.store, payee, amount, tid)) if settle_fn else None
            for line in payout_run(
                book, connect, earned_fn(a.store), product, a.currency.lower(), a.min, a.dry_run, settle
            ):
                print(line)
        return 0
    except ConnectError as e:
        print(f"refused: {e}")
        return 1
