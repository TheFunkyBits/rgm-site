# RGM site deployment

This repository contains only the root-level static deployment artifact for
`https://thefunkybits.github.io/rgm-site/`.

Publication state, catalog version allocation, release records, and deployment receipts remain in
[`TheFunkyBits/rgm`](https://github.com/TheFunkyBits/rgm). The Pages workflow deploys only an
artifact bound to an exact prepared state record from that repository. Direct edits to `main` are
not a publication path after bootstrap.

Historical catalog releases and catalog-v4 schemas are intentionally absent. They remain bound to
their original `rgm` history and URLs until separately retired.

Future split releases use root-level `catalog/vN/` artifacts and successor schema resources under
`spec/catalog-v5/`. The workflow accepts only an exact prepared state record and matching site
commit; it must not be dispatched for an arbitrary branch or local edit.
