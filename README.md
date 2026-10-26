<!-- sell-kit:start -->
# Likeness License

[![CI](https://github.com/eliem08/likeness-license/actions/workflows/ci.yml/badge.svg)](https://github.com/eliem08/likeness-license/actions/workflows/ci.yml)

> **License your face and voice to AI companies safely, and get paid for it.**

**Who it's for:** Creators, actors and talent agencies.

**The problem:** AI companies want faces and voices, and talent has no safe way to say yes on their own terms or track how their likeness is used.

**What you get:** A likeness registry, licence terms with prohibited uses, signed licences anyone can verify, and royalty statements.

## Quickstart

Customers receive a release archive with the wheel and the examples. Python 3.10+ and no other dependencies.

```bash
pip install likeness_license-0.1.0-py3-none-any.whl
likeness-license check examples/licence-request.json
likeness-license demo
```

## Web app and API

Every command is also a JSON API endpoint and a browser form, served by the built-in web app.

```bash
likeness-license-web --port 8000          # then open http://127.0.0.1:8000
likeness-license-web keys create --label "first customer"   # prints an API key (stored hashed)
docker build -t likeness-license . && docker run -p 8000:8000 -e API_KEYS=sk_... -v likeness-license-data:/data likeness-license
```

Every API call needs `Authorization: Bearer <key>` once any key exists; a server on a public address refuses to start without one. Calls are rate-limited per key (60/min, `--rate`) and metered: `likeness-license-web usage` prints calls per key for billing.

Endpoints: `POST /api/demo`, `POST /api/check`, plus `GET /healthz` and `GET /api/spec` (machine-readable field list).
Files are sent as `{"name": ..., "content": ...}`, folders as `{"files": [...]}` or a base64 zip.

## Deploy and sell

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/eliem08/likeness-license)

`render.yaml` (one click, above) and `fly.toml` (`fly launch --copy-config`) both run the Dockerfile with a persistent `/data` volume and a `/healthz` check.
To sell self-serve, set four variables and point a Stripe webhook at `https://<your-host>/billing/webhook` (events `checkout.session.completed` and `customer.subscription.deleted`):

| Variable | Example |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` |
| `STRIPE_PRICES` | `team=price_123,business=price_456` |
| `PUBLIC_URL` | `https://likeness-license.example.com` |

Buyers pick a plan on `/pricing`, pay on Stripe Checkout and see their API key once on the success page. Cancelling the subscription revokes the key. A selling server always requires a key.

## Pricing

Every plan starts with a 14-day free trial. Prices in USD, billed monthly unless noted.

| Plan | Price | Includes |
|---|---|---|
| **Creator** | $19 per month | Register your likeness; Licence terms; Royalty statements |
| **Agency** | $299 per month | Up to 50 talent; Bulk licensing; Verification API |
| **Studio** | Custom (per-licence fee, contact sales) | Licence talent at scale; Usage reporting; Legal templates |

To start a trial or buy a plan, [request access](https://github.com/eliem08/likeness-license/issues/new?title=Likeness%20License%20trial&labels=sales).

## Licence

Proprietary. Copyright (c) 2026 eliem08. All rights reserved. Use requires a paid plan or an active trial; see [LICENSE](LICENSE).
<!-- sell-kit:end -->

## What it does

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
