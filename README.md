# likeness-license

[![CI](https://github.com/eliem08/likeness-license/actions/workflows/ci.yml/badge.svg)](https://github.com/eliem08/likeness-license/actions/workflows/ci.yml)

> **Getty Images for your face and voice** — license your likeness to AI safely.

Studios, game makers and ad agencies want to use real people's faces and
voices in AI-generated content. Today that's either theft or a bespoke
lawyer-heavy deal. `likeness-license` is the registry + licensing engine:
creators register their likeness, set terms and prices, buyers get a signed
licence, and anyone can verify whether a given use is licensed.

## What the MVP does

- **Register** likeness assets (face sets, voice samples) by SHA-256 fingerprint
  — the raw media never has to leave the creator's device
- **Terms** per owner: allowed uses (`advertising`, `film`, `games`, `training`,
  `education`), territories, max duration, exclusivity, **hard prohibitions**
  (`political`, `adult`, `endorsement`, `deceased_impersonation`…), pricing
  (flat fee + per-1k-impressions / per-generation royalty)
- **Licence issuance**: validates the request against terms and existing
  exclusive licences, prices it, and returns a **signed certificate** (HMAC-SHA256)
- **Verify**: `verify(cert, use, territory, on_date)` → valid / reason
- **Usage reporting & royalties**: buyers report impressions/generations → statement
- **Revocation** (e.g. on breach) with a public revocation list

## Quickstart

```bash
pip install -e .
likeness-license demo
```

## Roadmap

- Content credentials (C2PA) embedding licence IDs into generated media
- Detection side: scan the web for unlicensed uses of a registered face/voice
- Agency mode: talent agencies managing rosters, payout splits

## Development

Zero runtime dependencies; Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m unittest discover -s tests -t .           # unit + CLI smoke tests
ruff check . && ruff format --check .               # lint + format
```

```
likeness_license/core.py       domain logic (pure, importable, fully tested)
likeness_license/__main__.py   CLI (`likeness-license ...` / `python -m likeness_license ...`)
tests/                unit tests + generated CLI smoke tests
```

CI runs lint and tests on Ubuntu and Windows across Python 3.10, 3.12 and 3.13.
Design, data model, trade-offs and production path: **[ARCHITECTURE.md](ARCHITECTURE.md)**.

Part of the [agent-economy](https://github.com/eliem08/agent-economy) portfolio (idea #28).
