"""Stateless commands: read a JSON request, print a JSON decision (also served by the web app)."""

import json
import secrets
from datetime import date

from .core import LicenseError, Registry, Terms


def add_commands(sub):
    c = sub.add_parser("check", help="would the owner's terms allow this licence, and what would it cost")
    c.add_argument("request", help="JSON with the owner's 'terms' and a licence 'request'")


def run(a):
    with open(a.request, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("terms"), dict)
        or not isinstance(data.get("request"), dict)
    ):
        raise ValueError("request must be an object with 'terms' and 'request' objects")
    t = data["terms"]
    terms = Terms(
        set(t["allowed_uses"]),
        set(t.get("territories", ["worldwide"])),
        int(t.get("max_days", 365)),
        bool(t.get("exclusive_available", False)),
    )
    reg = Registry(secrets.token_bytes(32))  # throwaway key: a check issues no usable certificate
    reg.register("owner", [b"likeness"], "face", terms)
    r = data["request"]
    try:
        reg.request(
            "owner",
            r.get("licensee", "licensee"),
            r["use"],
            r["territory"],
            date.fromisoformat(r.get("start", date.today().isoformat())),
            int(r["days"]),
            bool(r.get("exclusive", False)),
            set(r.get("purpose_tags", [])),
        )
    except LicenseError as e:
        print(json.dumps({"allowed": False, "reason": str(e)}, indent=2))
        return 1
    lic = next(iter(reg.licenses.values()))
    print(json.dumps({"allowed": True, "fee": lic["fee"], "start": lic["start"], "end": lic["end"]}, indent=2))
    return 0
