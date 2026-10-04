# RGM site deployment

## Source Formatting

Use Python 3.11+ to provision the pinned developer-only formatters, then apply and check authored text:

Select the independent public developer checkout with absolute `RGM_DEV_ROOT` or `--dev-root`;
an existing local sibling `dev` is supported without acquisition. The local wrappers pass target
policy `config/style.json`, not copied engines or crossrepo imports. Reuse a qualified formatter
cache. No private parent, Gradle build, publication or app snapshot-tag dependency is added.

```text
python -B .github/scripts/style_setup.py
python -B .github/scripts/style.py apply
python -B .github/scripts/style.py check
```

These source-only commands do not stage or deploy Pages. Hosted callers select reviewed public dev
through `RGM_DEV_REVISION`; Windows/Linux qualification is deliberately unrun. Exactly one final logical newline is enforced while
preserving meaningful whitespace, encoding and existing LF/CRLF. The contractually empty `.nojekyll`
marker, original/retained material and generated outputs remain excluded. Inspect an unresolved
transaction before replay; never delete its journal to force a run. Check never installs tools.

The target deployment at `https://thefunkybits.github.io/rgm-site/` contains app intro, the existing
privacy page and explicit minimal local resources. The app packages catalog/Resolve/Profile JSON;
GOG images and user-initiated YouTube playback are external runtime references, never website assets.

## Source Delivery

Separately approved reviewed fast-forward source commits/pushes may advance canonical `main`
through `rgm-dev/scripts/git_workspace.py`. Its [generic contract](https://github.com/TheFunkyBits/rgm-dev#git-workspace-delivery)
uses explicit repository/path selections and source-only Git operations; no private parent is
required for a standalone site selection. Keep that operation's private controls separate from
the Pages publisher's records. Source push may trigger style CI but never dispatches Pages,
uses `RGM_PAGES_TOKEN`, changes readiness markers or authorizes deployment. Do not substitute a
shell push, force update or manual workflow dispatch for either owning route.

## Reviewed Publication

The [static assembler](.github/scripts/assemble_static_pages.py) validates an exact pages-only
allowlist, local links/base paths and absence of remote media/scripts. It stages a reviewed clean
main commit only with tracked `.github/static-pages-cutover.json` contract `rgm-static-pages-v1`.
Check the marker's current state after offline validation and owner readiness. The [Pages workflow](.github/workflows/pages.yml) rechecks canonical
main before upload and deployment. The [site-owned publisher](.github/scripts/static_site_release.py)
provides separately authorized `begin`/`reconcile` and read-only `inspect`, with durable intent
before push/dispatch and observation of root/privacy. It needs only this standalone checkout;
operator code under `.github` is never served. No new catalog release versions or ordinary tags exist.

Local assembly publishes only to an unused canonical sibling destination outside the checkout.
The final move cannot replace even an empty directory created concurrently: Windows uses native
no-replace rename and Linux uses `renameat2(RENAME_NOREPLACE)`. Unsupported primitives fail closed.
Staging success is not publication authorization or delivered-content evidence.

All operations take absolute `--site-root`, `--git` and the full `--site-commit`. Begin additionally
selects `--site-base` and requires separately approved `--confirm-site=site-<commit>`; reconcile
retains the original selection and requires its own confirmation. Mutations use private
`RGM_PAGES_TOKEN`, never a command-line credential. Durable controls and the publication lock
live in this checkout's Git directory, not a public receipt. Lost acknowledgements stop for
inspection; reconcile may dispatch once only after observing the original push and only if
no dispatch was attempted. Never reconstruct a selection or replay push/deployment.

Existing Git and retirement anchors remain immutable. Never reuse, redirect or republish retired
URLs or versions. Independently required original source/offer custody and exact-scope external
deletion approval remain separate from site deployment. Neither readiness, tags nor successful
HTTP responses attest bytes or authorize replay/deletion.

Offline checks: `python -B -m unittest discover -s .github/tests`.

For editing tasks, run those checks only after all authorized edits across affected repositories
are complete. Guidance-only changes use content/diff review without application builds/tests;
see [AGENTS.md](AGENTS.md#verification-timing). Public Windows/Linux offline CI coverage remains
a separately reviewed/pinned rollout; an Ubuntu Pages deployment job is not cross-host test evidence.
