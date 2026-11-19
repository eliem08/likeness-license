"""Operating commands: run the likeness registry against a persistent store (also served by the web app).

The signing key is created once and kept next to the store (or taken from LIKENESS_SECRET), so a licence
certificate issued today still verifies after a restart. Fees and royalties are a ledger: `statement`
prints what each owner is owed.
"""

import itertools
import json
import os
import secrets
from dataclasses import asdict
from datetime import date

from . import connect
from .core import USES, LicenseError, Registry, Terms

OPS = ("owner-register", "whose", "license", "verify", "revoke", "usage", "statement", "licenses", *connect.COMMANDS)
MAX_MEDIA_BYTES = 20 * 1024 * 1024


def _key_for(store: str) -> bytes:
    env = os.environ.get("LIKENESS_SECRET")
    if env:
        return env.encode()
    path = f"{os.path.splitext(store)[0]}.key"
    try:
        with open(path, encoding="utf-8") as fh:
            key = fh.read().strip()
        if key:
            return key.encode()
    except FileNotFoundError:
        pass
    key = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key)
    return key.encode()


def load(path: str) -> Registry:
    reg = Registry(_key_for(path))
    try:
        with open(path, encoding="utf-8-sig") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return reg
    if not isinstance(doc, dict) or "owners" not in doc:
        raise LicenseError(f"{path}: not a likeness-license store")
    for owner, rec in doc["owners"].items():
        t = rec["terms"]
        for k in ("allowed_uses", "territories", "prohibited"):
            t[k] = set(t[k])
        reg.owners[owner] = {"kind": rec["kind"], "fingerprints": rec["fingerprints"], "terms": Terms(**t)}
    reg.licenses, reg.usage = doc.get("licenses", {}), doc.get("usage", {})
    reg.revoked = set(doc.get("revoked", []))
    reg._ids = itertools.count(int(doc.get("next_id", 1)))
    return reg


def save(reg: Registry, path: str):
    next_id = next(reg._ids)
    reg._ids = itertools.count(next_id)
    owners = {}
    for owner, rec in reg.owners.items():
        t = asdict(rec["terms"])
        for k in ("allowed_uses", "territories", "prohibited"):
            t[k] = sorted(t[k])
        owners[owner] = {"kind": rec["kind"], "fingerprints": rec["fingerprints"], "terms": t}
    doc = {
        "owners": owners,
        "licenses": reg.licenses,
        "usage": reg.usage,
        "revoked": sorted(reg.revoked),
        "next_id": next_id,
    }
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    os.replace(tmp, path)


def _media(path: str) -> bytes:
    if os.path.getsize(path) > MAX_MEDIA_BYTES:
        raise LicenseError(f"{path}: media over {MAX_MEDIA_BYTES // 2**20} MB")
    with open(path, "rb") as fh:
        data = fh.read()
    if not data:
        raise LicenseError(f"{path}: empty file")
    return data


def _day(text: str | None) -> date:
    if not text:
        return date.today()
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise LicenseError(f"{text!r} is not a date like 2026-12-01") from None


def add_ops(sub):
    store = os.environ.get("LIKENESS_STORE", "likeness.json")
    p = sub.add_parser("owner-register", help="register a face or voice and the terms it may be licensed on")
    p.add_argument("owner")
    p.add_argument("media", help="a photo or voice sample that identifies the likeness")
    p.add_argument("--kind", choices=["face", "voice"], required=True)
    p.add_argument("--uses", nargs="+", required=True, choices=sorted(USES))
    p.add_argument("--territories", nargs="*", default=["worldwide"])
    p.add_argument("--max-days", type=int, default=365)
    p.add_argument("--exclusive-available", action="store_true")
    sub.add_parser("whose", help="who registered this media, if anyone").add_argument("media")
    p = sub.add_parser("license", help="issue a signed licence certificate if the owner's terms allow it")
    p.add_argument("owner")
    p.add_argument("licensee")
    p.add_argument("--use", required=True, choices=sorted(USES))
    p.add_argument("--territory", default="worldwide")
    p.add_argument("--start", help="YYYY-MM-DD, default today")
    p.add_argument("--days", type=int, required=True)
    p.add_argument("--exclusive", action="store_true")
    p.add_argument("--purpose", nargs="*", default=[], help="what it is for, e.g. advertising political")
    p = sub.add_parser("verify", help="check a certificate before generating or publishing")
    p.add_argument("certificate")
    p.add_argument("--use", required=True, choices=sorted(USES))
    p.add_argument("--territory", default="worldwide")
    p.add_argument("--on", help="YYYY-MM-DD, default today")
    sub.add_parser("revoke", help="withdraw a licence").add_argument("license_id")
    p = sub.add_parser("usage", help="a licensee reports impressions and generations, for royalties")
    p.add_argument("license_id")
    p.add_argument("--impressions", type=int, default=0)
    p.add_argument("--generations", type=int, default=0)
    sub.add_parser("statement", help="fees and royalties owed to an owner").add_argument("owner")
    sub.add_parser("licenses", help="every licence and whether it is active")
    connect.add_commands(sub)
    for name in OPS:
        sub.choices[name].add_argument("--store", default=store)


def run_ops(a) -> int:
    if a.cmd in connect.COMMANDS:
        return connect.run_command(a, _earned, "likeness-license")
    try:
        reg = load(a.store)
        code = _run(reg, a)
        save(reg, a.store)
        return code
    except LicenseError as e:
        print(f"refused: {e}")
        return 1


def _run(reg: Registry, a) -> int:
    c = a.cmd
    if c == "owner-register":
        terms = Terms(set(a.uses), set(a.territories), a.max_days, a.exclusive_available)
        reg.register(a.owner, [_media(a.media)], a.kind, terms)
        print(f"registered {a.owner} ({a.kind}); licensable for {', '.join(sorted(a.uses))}")
    elif c == "whose":
        owner = reg.owner_of(_media(a.media))
        print(f"registered to {owner}" if owner else "not registered")
        return 0 if owner else 1
    elif c == "license":
        cert = reg.request(a.owner, a.licensee, a.use, a.territory, _day(a.start), a.days, a.exclusive, set(a.purpose))
        lic = reg.licenses[max(reg.licenses)]
        print(f"{lic['id']} issued: {a.use} until {lic['end']}, fee ${lic['fee']:,.2f}\n{cert}")
    elif c == "verify":
        ok, reason = reg.verify(a.certificate, a.use, a.territory, _day(a.on))
        print(f"{'VALID' if ok else 'INVALID'}  {reason}")
        return 0 if ok else 1
    elif c in ("revoke", "usage"):
        if a.license_id not in reg.licenses:
            raise LicenseError(f"no licence {a.license_id!r}")
        if c == "revoke":
            reg.revoke(a.license_id)
            print(f"{a.license_id} revoked")
        else:
            reg.report_usage(a.license_id, a.impressions, a.generations)
            u = reg.usage[a.license_id]
            print(f"{a.license_id}: {u['impressions']:,} impressions, {u['generations']:,} generations to date")
    elif c == "statement":
        if a.owner not in reg.owners:
            raise LicenseError(f"no owner {a.owner!r}")
        st = reg.statement(a.owner)
        for line in st["lines"]:
            print(
                f"{line['license']}  {line['licensee']:<20} fee ${line['fee']:>10,.2f}  royalty ${line['royalty']:>9,.2f}"
            )
        print(f"owed to {a.owner}: ${st['total']:,.2f}")
    else:
        for lid, lic in reg.licenses.items():
            state = "revoked" if lid in reg.revoked else "active"
            print(
                f"{lid}  {state:<8}{lic['owner']:<16}-> {lic['licensee']:<16}{lic['use']:<12}{lic['start']} to {lic['end']}"
            )
        if not reg.licenses:
            print("no licences yet")
    return 0


def _earned(store: str) -> dict:
    """Cumulative fees and royalties per owner, from their statement."""
    reg = load(store)
    return {o: reg.statement(o)["total"] for o in reg.owners if reg.statement(o)["total"] > 0}
