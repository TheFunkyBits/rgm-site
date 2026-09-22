# Repository Agent Guidance

Shared workspace policy: `../../.github/copilot-instructions.md`.

## Scope

This public repository owns only root-level, served RGM site artifacts and the workflow that deploys
an exact prepared artifact. It does not own catalog requests, reservations, release records,
deployment receipts, publication locks, app snapshot tags, or publication-state tooling.

## Publication

`TheFunkyBits/rgm` is the state authority. Except for the recorded bootstrap commit, only the
state-owned publisher may advance `main`. A Pages deployment must validate an exact prepared state
record, exact site commit, and full artifact manifest before it uploads any files.

Do not copy historical catalog releases or URL-bound schemas from `rgm`. New catalog and schema
content is created only through the versioned state-to-site publication transaction.