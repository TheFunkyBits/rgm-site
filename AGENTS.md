# Repository Agent Guidance

This guide applies to this public repository, including standalone checkouts. Its ownership,
validation and publication constraints do not require a private parent checkout.

## Scope

This public repository owns app intro/privacy, minimal local static resources, their
authorized reviewed-commit Pages workflow and static-site publication/reconciliation tooling.
Operator code lives under `.github/scripts`; private locks and durable operation controls live
in Git administration, outside tracked source and served output. It does not own catalog requests,
reservations, release records, deployment receipts or app snapshot tags.

## Current Contract Hygiene

Proactively hunt for and remove retired, obsolete, redundant, legacy and history-only material
in the authorized resources/guidance and connected references before/during work and final review.
Determine necessity from actual consumers, registrations, links and obligations, not age or
keywords; a self-only test does not justify an unused helper. Remove complete unnecessary slices,
including whole files. Do not keep tombstones, historical explanations, unused compatibility
aliases, retired-name scanners/tests or active history archives solely to remember removed material.

Existing Git history is the historical reference. Internal retirement needs no preservation
commit, staging, new ref/tag, exact-byte check, receipt/attestation or archive prerequisite,
regardless of committed, modified, untracked or newly created status. Lack of history is not a
reason to commit or preserve obsolete internal work. Transfer useful current facts, rationale,
approved goals and meaningful assertions first; preserve functionality and unrelated/concurrent edits.

Scoped internal retirement needs no additional cleanup request. Obtain approval before crossing
authorized repositories or artifact classes; no blanket sweep or silent deliverable expansion.
Each candidate needs grounded removal, a specific current retention reason or an explicit blocker.
Leave no known safely removable residue in scope and disclose unresolved dependencies.

Preserve existing Git objects/refs/tags and independent legal/source/offer/observation custody,
currently served/release-bound material, player data and unresolved operational inputs. Unused
resources may be retired only without bypassing their actual publication/retention contracts.
This rule authorizes no served-byte rewrite, deployment, external deletion or Git mutation;
those keep their owning approvals.

## Publication

Use `.github/scripts/static_site_release.py` for `begin`, read-only `inspect` and narrowly
pre-dispatch `reconcile`. Apart from the recorded bootstrap commit, remote `main` may advance only
through this site-owned publisher for approved publication, or the tested
`rgm-dev/scripts/git_workspace.py` route for separately approved fast-forward source delivery,
using either reviewed selections or a caller-owned policy with explicit all-current confirmation.
Both retain exact captured scope and drift/refusal safeguards; neither is deployment approval.
Source delivery commits/pushes only selected source and never dispatches Pages or uses
publication tokens/readiness to imply deployment approval. Its private Git controls are separate
from the site publisher's original records and must not overwrite them.
The publisher selects a reviewed site commit/base on clean canonical main; record durable
push/dispatch intent before mutation. Lost acknowledgements stop for inspection, never replay.
Keep credentials and journals private and do not bundle them into Pages. Publication remains
blocked until coordinated owner-policy and executable-route verification, marker activation
and distinct publication authorization.

Do not copy catalogs, Profiles, trust-key resources or retired URL-bound schemas into this tree.
External catalog hosting is gone and all clients use embedded app data. The current allowlist
has no compatibility/archive resources; never recreate, redirect or reuse retired URLs.

Keep page copy focused on the app and truthful privacy facts: adaptations/catalog are app-bound;
images and explicit YouTube playback load directly from external providers. Never rehost media or
add game files, Profiles, catalogs, remote embeds, tracking scripts or extra public pages.

## Verification Timing

Complete all authorized edits for the current task across every affected repository before
running any build or test command. While any authorized edit remains unfinished, do not launch
Gradle configuration/dry-runs, compilation, `testClasses`, assemble/test tasks, filtered tests,
Python unittest/pytest, native CTest or custom smoke checks. A narrow/focused check, `--tests`
filter, finished file/module/repository or convenient prerequisite is not early-run permission.
Do not split the task or relabel a build/test as preflight, validation or diagnostics to bypass this rule.
During editing, use targeted reads, source analysis, existing diagnostics and normal Git diff review;
prepare regression tests and the final verification commands without executing them.

After the edit phase, run the smallest required verification set, combining compatible tasks and
serializing Gradle. Preserve valid unaffected evidence rather than repeat checks for freshness.
If verification fails, retain the result, finish all related corrective edits, then rerun only
invalidated checks and required dependency gates. This scheduling rule never waives required checks.
Guidance-only changes use read-only content/diff review, not application builds/tests; expressly
requested test-only work with no planned edits may proceed directly to verification.

Higher-priority mandatory validation remains binding. Before an unavoidable early executable
gate, disclose the exact conflicting requirement and why read-only/editor diagnostics cannot
satisfy it; never silently use a generic mandatory-check exception or claim this policy overrides
agent instructions.

## Static Pages Contract

Source style uses standalone public developer CLIs through local wrappers and target-owned
`config/style.json`. Select absolute `RGM_DEV_ROOT` or wrapper `--dev-root`; it needs no private
parent, Gradle build, copied engine or crossrepo import. Check acquires nothing; setup is explicit.
Hosted configuration needs a reviewed full public dev SHA and separate Git/CI approval. Actual host
passes require observed execution; hosted qualification is deliberately unrun for this rollout.
Never bundle the developer checkout/cache into Pages or add it to app snapshot-tag membership.

The static workflow and `assemble_static_pages.py` require a reviewed clean main commit and
tracked `.github/static-pages-cutover.json` with contract `rgm-static-pages-v1`. Check its current
state; activation follows offline validation and owner readiness, not mere implementation. The artifact allowlist is intro/privacy plus
explicit minimal resources; queued jobs recheck canonical main before upload and deployment.
There is no catalog writer/version/tag route. Existing Git/retirement anchors remain immutable;
independently required source/offer fulfilment remains separate from static publication. No marker,
HTTP success or source tag authorizes external deletion or proves delivery/content identity.
