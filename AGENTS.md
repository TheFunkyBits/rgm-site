# Repository Agent Guidance

Shared workspace policy: `../../.github/copilot-instructions.md`.

## Scope

This public repository owns only root-level, served RGM site artifacts and the workflow that deploys
an exact prepared artifact. It does not own catalog requests, reservations, release records,
deployment receipts, publication locks, app snapshot tags, or publication-state tooling.

## Publication

`TheFunkyBits/rgm-publication` is the state authority. Except for the recorded bootstrap commit, only the
state-owned publisher may advance `main`. A Pages deployment must validate an exact prepared state
record, exact site commit, and full artifact manifest before it uploads any files.

Do not copy historical catalog releases or URL-bound schemas from `rgm`. New catalog or trust-key
resources require their own authorized, create-only state-to-site publication transaction. Keep
the currently served v8/v9 catalog paths and old trust-key URL unchanged except through their
separately authorized retirement and site-publication transactions.

Keep served page copy focused on user-facing catalog, trust, and privacy facts; describe the
downloaded adaptation data accurately without detailing internal content contracts.
