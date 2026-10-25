import argparse
import csv
import os
import sys
from datetime import date

from .commands import add_commands, run
from .core import LicenseError, Registry, Terms


def demo():
    reg = Registry(b"demo-secret")
    reg.register(
        "ava.voice",
        [b"sample-1.wav bytes", b"sample-2.wav bytes"],
        "voice",
        Terms({"advertising", "games", "education"}, territories={"US", "EU"}, exclusive_available=True),
    )
    cert = reg.request("ava.voice", "Pixel Games", "games", "US", date(2026, 11, 1), 180)
    print("issued licence for Pixel Games (games, US, 180 days)")
    print("  verify games/US:", reg.verify(cert, "games", "US", date(2026, 12, 1)))
    print("  verify advertising/US:", reg.verify(cert, "advertising", "US", date(2026, 12, 1)))
    for req in [("BadCo", "advertising", "US", {"political"}), ("FarCo", "games", "JP", set())]:
        try:
            reg.request("ava.voice", req[0], req[1], req[2], date(2026, 11, 1), 30, purpose_tags=req[3])
        except LicenseError as e:
            print(f"  refused {req[0]}: {e}")
    reg.report_usage("LIC-00001", impressions=250_000, generations=4_000)
    print("statement:", reg.statement("ava.voice"))


def build_parser():
    ap = argparse.ArgumentParser(prog="likeness-license")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    add_commands(sub)
    return ap


def _run(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.cmd != "demo":
        return run(a)
    demo()
    return 0


def main(argv=None):
    """Run the CLI; a bad input file or argument exits 2 with a one-line error instead of a traceback.

    Set AGENT_ECONOMY_DEBUG=1 to see the full traceback.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        return _run(argv)
    except (OSError, ValueError, KeyError, csv.Error) as e:
        if os.environ.get("AGENT_ECONOMY_DEBUG"):
            raise
        msg = e.args[0] if isinstance(e, KeyError) and e.args else e
        print(f"error: {msg}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
