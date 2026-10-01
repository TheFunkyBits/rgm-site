# Repository Agent Guidance

This guide applies to this public repository, including standalone checkouts. Its ownership,
validation and publication constraints do not require a private parent checkout.

## Scope

This public repository owns only app intro/privacy, minimal local static resources and their
authorized reviewed-commit Pages workflow. It does not own catalog requests, reservations, release records,
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

Keep page copy focused on the app and truthful privacy facts: adaptations/catalog are app-bound;
images and explicit YouTube playback load directly from external providers. Never rehost media or
add game files, Profiles, catalogs, remote embeds, tracking scripts or extra public pages.

## Static Pages Cutover

The static workflow and `assemble_static_pages.py` require a reviewed clean main commit and
tracked `.github/static-pages-cutover.json` with contract `rgm-static-pages-v1`. Check its current
state; activation follows offline validation and owner readiness, not mere implementation. The artifact allowlist is intro/privacy plus
explicit minimal resources; queued jobs recheck canonical main before upload and deployment.
There is no new catalog writer/version/tag route. Removing hosted
resources requires final-served/removed source anchors, explicit cutoff/window waiver, non-reuse
and independent source/offer fulfilment; no marker, HTTP success or source tag authorizes deletion.

The owner guarantees no old-app/external-catalog clients remain. The approved cutoff removes
active/served legacy graphs and trust resources without a compatibility window; immutable Git
history and independently required source/offer custody remain separate obligations.
