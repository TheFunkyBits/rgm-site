# RGM site deployment

This repository contains only the root-level static deployment artifact for
`https://thefunkybits.github.io/rgm-site/`.

Publication state, catalog version allocation, release records, and deployment receipts remain in
[`TheFunkyBits/rgm-publication`](https://github.com/TheFunkyBits/rgm-publication). The Pages workflow deploys only an
artifact bound to an exact prepared state record from that repository. Direct edits to `main` are
not a publication path after bootstrap.

The older `/rgm/` catalog and catalog-v4 schema URLs remain in their original publication history;
they are not copied here. The v8 and v9 catalog URLs and the previously published trust-key URL
remain served here. Changes to served resources require their own site-publication transaction.

New split releases use strict counter-free signed records under root-level `catalog/vN/`; they do
not introduce another public JSON Schema. A new versionless trust-key resource needs its own
authorized create-only site transaction. The workflow accepts only an exact prepared state record
and matching site commit; it must not be dispatched for an arbitrary branch or local edit.
