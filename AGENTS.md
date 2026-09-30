# Repository Agent Guidance

Shared workspace policy: `../../.github/copilot-instructions.md`.

## Scope

This public repository owns only root-level, served RGM site artifacts and the workflow that deploys
an authorized versioned catalog artifact. It does not own catalog requests, reservations, release records,
deployment receipts, publication locks, app snapshot tags, or publication-state tooling.

## Publication

`TheFunkyBits/rgm-publication` is the state authority. Except for the recorded bootstrap commit, only the
state-owned publisher may advance `main`. The old prepared-state Pages writer and workflow have
been retired from this current tree. Publication remains blocked until coordinated owner-policy
and executable-route verification, marker activation and distinct publication authorization.
There is no interim signed-catalog compatibility workflow.

Do not copy historical catalog releases or URL-bound schemas from `rgm`. New catalog or trust-key
resources require their own authorized, create-only state-to-site publication transaction. Keep
the currently served v8/v9 catalog paths and old trust-key URL unchanged except through their
separately authorized retirement and site-publication transactions.

Keep served page copy focused on user-facing catalog, trust, and privacy facts; describe the
downloaded adaptation data accurately without detailing internal content contracts.

## Prospective successor catalogs

The separate versioned workflow is dormant until coordinated owner-policy cutover and its
tracked site marker. After cutover, new catalogs are unsigned, create-only versions advanced
only through the tested publication-owned script and site-owned assembler; the paired
`catalog-v<N>` content/site tags map versions to source commits, not exact served bytes.
The retired signed writers are not a publication path. The versioned Pages gate rejects the
still-absent marker; implementation and offline verification do not activate it. No interim catalog
release may use an incomplete route before coordinated readiness and separate release approval.
Inspection or a queued Pages job cannot justify a redispatch, overwrite, tag move, or old
v8/v9/trust-URL edit. Historical release obligations and source/offer custody remain independent.
