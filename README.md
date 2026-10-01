# RGM site deployment

The target deployment at `https://thefunkybits.github.io/rgm-site/` contains app intro, the existing
privacy page and explicit minimal local resources. The app packages catalog/Resolve/Profile JSON;
GOG images and user-initiated YouTube playback are external runtime references, never website assets.

The [static assembler](.github/scripts/assemble_static_pages.py) validates an exact pages-only
allowlist, local links/base paths and absence of remote media/scripts. It stages a reviewed clean
main commit only with tracked `.github/static-pages-cutover.json` contract `rgm-static-pages-v1`.
Check the marker's current state after offline validation and owner readiness. The [Pages workflow](.github/workflows/pages.yml) rechecks canonical
main before upload and deployment. The publication owner supplies separately authorized
`static_site_release.py begin/inspect/reconcile`, with durable intent before push/dispatch and
read-only observation of root/privacy. No new catalog release versions or ordinary tags exist.

The owner guarantees no legacy clients remain, so no compatibility-retention window is required. Complete
final-served anchors, explicit cutoff/window waiver, affected-owner/URL inventory, independent
source/offer custody and operational approval precede removal. Removed-state anchors follow
the scripted deployment and retired-URL observation; they are not a circular deployment input.
Neither readiness, tags nor successful HTTP responses attest bytes or authorize replay/deletion.

Offline checks: `python -B -m unittest discover -s .github/tests`. Git-native retirement custody and
pages-only artifact validation are different checks; do not report the former as completed cutoff.
