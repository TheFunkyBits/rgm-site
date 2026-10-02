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

Existing Git and retirement anchors remain immutable. Never reuse, redirect or republish retired
URLs or versions. Independently required original source/offer custody and exact-scope external
deletion approval remain separate from site deployment. Neither readiness, tags nor successful
HTTP responses attest bytes or authorize replay/deletion.

Offline checks: `python -B -m unittest discover -s .github/tests`.
