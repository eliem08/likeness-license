# likeness-license

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
