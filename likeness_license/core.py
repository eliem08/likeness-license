"""Likeness registry, licence terms, signed certificates, verification and royalties."""

from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import os
from dataclasses import dataclass, field
from datetime import date, timedelta

__all__ = ["Terms", "Registry", "LicenseError"]

USES = {"advertising", "film", "games", "training", "education", "social"}


class LicenseError(Exception):
    pass


@dataclass
class Terms:
    allowed_uses: set
    territories: set = field(default_factory=lambda: {"worldwide"})
    max_days: int = 365
    exclusive_available: bool = False
    prohibited: set = field(default_factory=lambda: {"political", "adult", "endorsement", "deceased_impersonation"})
    flat_fee: dict = field(
        default_factory=lambda: {
            "advertising": 5000,
            "film": 8000,
            "games": 3000,
            "training": 2000,
            "education": 500,
            "social": 1000,
        }
    )
    per_1k_impressions: float = 2.0
    per_generation: float = 0.05
    exclusive_multiplier: float = 3.0


class Registry:
    def __init__(self, secret: bytes | None = None):
        self.secret = secret or os.environ.get("LIKENESS_SECRET", "dev-secret").encode()
        self.owners: dict[str, dict] = {}
        self.licenses: dict[str, dict] = {}
        self.revoked: set[str] = set()
        self.usage: dict[str, dict] = {}
        self._ids = itertools.count(1)

    def register(self, owner: str, media: list[bytes], kind: str, terms: Terms) -> dict:
        prints = sorted(hashlib.sha256(m).hexdigest() for m in media)
        self.owners[owner] = {"kind": kind, "fingerprints": prints, "terms": terms}
        return {"owner": owner, "fingerprints": prints}

    def owner_of(self, media: bytes) -> str | None:
        h = hashlib.sha256(media).hexdigest()
        return next((o for o, rec in self.owners.items() if h in rec["fingerprints"]), None)

    def _sign(self, payload: dict) -> str:
        body = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()
        sig = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{sig}"

    def _open(self, cert: str) -> dict:
        body, sig = cert.rsplit(".", 1)
        if not hmac.compare_digest(sig, hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()):
            raise LicenseError("invalid signature")
        return json.loads(base64.urlsafe_b64decode(body))

    def request(
        self,
        owner: str,
        licensee: str,
        use: str,
        territory: str,
        start: date,
        days: int,
        exclusive: bool = False,
        purpose_tags: set | None = None,
    ) -> str:
        rec = self.owners.get(owner)
        if not rec:
            raise LicenseError("unknown owner")
        t: Terms = rec["terms"]
        if use not in USES or use not in t.allowed_uses:
            raise LicenseError(f"use {use!r} not permitted by owner")
        bad = (purpose_tags or set()) & t.prohibited
        if bad:
            raise LicenseError(f"prohibited purpose: {sorted(bad)}")
        if "worldwide" not in t.territories and territory not in t.territories:
            raise LicenseError(f"territory {territory} not permitted")
        if days > t.max_days:
            raise LicenseError(f"max duration is {t.max_days} days")
        if exclusive and not t.exclusive_available:
            raise LicenseError("owner does not offer exclusivity")
        end = start + timedelta(days=days)
        for lid, lic in self.licenses.items():
            if lid in self.revoked or lic["owner"] != owner or lic["use"] != use:
                continue
            overlap = date.fromisoformat(lic["start"]) < end and start < date.fromisoformat(lic["end"])
            if overlap and (lic["exclusive"] or exclusive):
                raise LicenseError(f"conflicts with exclusive licence {lid}")
        fee = t.flat_fee.get(use, 0) * (days / 365) * (t.exclusive_multiplier if exclusive else 1)
        lid = f"LIC-{next(self._ids):05d}"
        payload = {
            "id": lid,
            "owner": owner,
            "licensee": licensee,
            "use": use,
            "territory": territory,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "exclusive": exclusive,
            "fee": round(fee, 2),
            "fingerprints": rec["fingerprints"],
        }
        self.licenses[lid] = payload
        self.usage[lid] = {"impressions": 0, "generations": 0}
        return self._sign(payload)

    def verify(self, cert: str, use: str, territory: str, on: date) -> tuple[bool, str]:
        try:
            p = self._open(cert)
        except (LicenseError, ValueError) as e:
            return False, str(e)
        if p["id"] in self.revoked:
            return False, "licence revoked"
        if use != p["use"]:
            return False, f"licence covers {p['use']}, not {use}"
        if p["territory"] not in ("worldwide", territory):
            return False, f"licence territory is {p['territory']}"
        if not date.fromisoformat(p["start"]) <= on < date.fromisoformat(p["end"]):
            return False, "outside licence period"
        return True, f"valid: {p['id']} ({p['owner']} -> {p['licensee']})"

    def revoke(self, license_id: str):
        self.revoked.add(license_id)

    def report_usage(self, license_id: str, impressions: int = 0, generations: int = 0):
        u = self.usage[license_id]
        u["impressions"] += impressions
        u["generations"] += generations

    def statement(self, owner: str) -> dict:
        t: Terms = self.owners[owner]["terms"]
        lines, total = [], 0.0
        for lid, lic in self.licenses.items():
            if lic["owner"] != owner:
                continue
            u = self.usage[lid]
            royalty = u["impressions"] / 1000 * t.per_1k_impressions + u["generations"] * t.per_generation
            amount = lic["fee"] + royalty
            total += amount
            lines.append({"license": lid, "licensee": lic["licensee"], "fee": lic["fee"], "royalty": round(royalty, 2)})
        return {"owner": owner, "lines": lines, "total": round(total, 2)}
