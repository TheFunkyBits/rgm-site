# RGM site deployment

This repository contains only the root-level static deployment artifact for
`https://thefunkybits.github.io/rgm-site/`.

Historical publication state, catalog requests, release records, and deployment receipts remain in
[the publication-state repository](https://github.com/TheFunkyBits/rgm-publication). The old prepared Pages workflow is
retired from current source; its historical implementation remains in Git. Direct edits to `main` are
not an independent publication path after bootstrap.

The older `/rgm/` catalog and catalog-v4 schema URLs remain in their original publication history;
they are not copied here. The v8 and v9 catalog URLs and the previously published trust-key URL
remain served here. Changes to served resources require their own site-publication transaction.

The read-only [current-site validator](.github/scripts/validate_current_site.py) checks path
confinement and old-client URL presence without rehashing historical catalogs. For an explicitly
selected successor version, an installed client publisher may also verify typed catalog
semantics; this check does not build the publisher, deploy Pages, or attest served bytes.

Previously served split v8/v9 releases retain their signed resources under root-level `catalog/vN/`.
No new signed catalog can be assembled or activated by current publication source. A new
trust-key resource or change to previously served content
requires its own authorization. No current workflow accepts a signed prepared-state dispatch.

The separate versioned Pages workflow is dormant until the site-owner policy cutover is reviewed
and its strict marker is present in the committed site tree. Its presence alone does not authorize
a deployment or a catalog tag, and it does not change the still-served signed v8/v9 resources.
The site-owned assembler accepts a selected new catalog only after that marker is tracked;
the prepared-state assembler is no longer in the current tree. The versioned workflow rechecks authenticated
site `main` before artifact upload and before deployment, so a queued stale workflow cannot
intentionally replace a newer Pages artifact. The new workflow's index-URL observation reports
availability, not equality to the staged catalog bytes.

After the separately approved coordinated cutover, new successor `catalog/vN/` versions will
be **unsigned** and created only by the publication-owned versioned script and this site-owned
versioned workflow. The workflow requires one selected, fresh, create-only site commit and
rechecks authenticated `main` before upload and deployment. Only after first-attempt success
and public index availability can the owner create matching annotated content/site `catalog-vN`
tags. Neither a tag nor a successful URL proves the bytes served to a player. The historical
signed v8/v9 paths and prior trust URL remain untouched. Until the cutover marker, both owning
policies and tested replacements agree, there is **no authorized interim catalog release**.
The replacement removes future artifact-identity gates, not historic source/offer custody or
separate authorization for publication, support cutoff and irreversible cleanup.
