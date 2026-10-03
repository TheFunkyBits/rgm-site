"""Static Pages dispatch and availability observation, never served-byte identity."""

from __future__ import annotations

from collections.abc import Callable
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


COMMIT = re.compile(r"[0-9a-f]{40}\Z")
API_ROOT = "https://api.github.com/repos/TheFunkyBits/rgm-site/actions/workflows/pages.yml"
SITE_ROOT = "https://thefunkybits.github.io/rgm-site/"
WORKFLOW_PATH = ".github/workflows/pages.yml"


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Pages observation repeats a JSON field")
        value[key] = item
    return value


def _constant(value):
    raise ValueError("Pages observation contains a nonfinite number")


class StaticPagesGateway:
    def __init__(self, token: str, *, open_request=None):
        if any(character.isspace() or not character.isprintable() for character in token):
            raise ValueError("Private Pages credential is invalid")
        self._token = token
        self._open = open_request or build_opener(_NoRedirects()).open

    @staticmethod
    def _title(commit):
        if not COMMIT.fullmatch(commit):
            raise ValueError("Pages needs a reviewed full site commit")
        return f"Deploy RGM site ({commit})"

    def require_dispatch_token(self):
        if not self._token:
            raise ValueError("A private Pages credential is required for dispatch")

    def _request(self, url, *, data=None, served=False):
        headers = {"User-Agent": "rgm-site-operator"}
        if not served:
            headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, headers=headers, data=data, method="POST" if data is not None else "GET")
        try:
            with self._open(request, timeout=20) as response:
                if response.status != (204 if data is not None else 200) or response.geturl() != url:
                    raise ValueError("Pages endpoint returned an unexpected or redirected response")
                return b"" if served or data is not None else response.read()
        except (HTTPError, URLError, TimeoutError):
            raise ValueError("Pages outcome is unavailable or ambiguous; inspect, never replay") from None

    def _runs(self):
        page, count, results, seen = 1, None, [], set()
        while count is None or len(results) < count:
            url = f"{API_ROOT}/runs?{urlencode({'event': 'workflow_dispatch', 'branch': 'main', 'per_page': 100, 'page': page})}"
            try:
                document = json.loads(
                    self._request(url).decode("utf-8"), object_pairs_hook=_unique, parse_constant=_constant
                )
            except (UnicodeDecodeError, ValueError) as error:
                raise ValueError("Pages run listing is invalid or ambiguous") from error
            if (
                type(document) is not dict
                or type(document.get("total_count")) is not int
                or document["total_count"] < 0
                or type(document.get("workflow_runs")) is not list
            ):
                raise ValueError("Pages run listing has an invalid shape")
            if count is None:
                count = document["total_count"]
            if count != document["total_count"]:
                raise ValueError("Pages listing changed during inspection")
            for run in document["workflow_runs"]:
                if (
                    type(run) is not dict
                    or type(run.get("id")) is not int
                    or run["id"] <= 0
                    or run["id"] in seen
                ):
                    raise ValueError("Pages run listing contains duplicate or invalid runs")
                seen.add(run["id"])
                results.append(run)
            if len(results) > count or len(results) < count and not document["workflow_runs"]:
                raise ValueError("Pages listing is incomplete or ambiguous")
            page += 1
        return results

    def _matching_runs(self, commit):
        title, matches = self._title(commit), []
        for run in self._runs():
            if run.get("head_sha") == commit or run.get("display_title") == title:
                if (
                    run.get("display_title") != title
                    or run.get("head_sha") != commit
                    or run.get("head_branch") != "main"
                    or run.get("event") != "workflow_dispatch"
                    or run.get("path") != WORKFLOW_PATH
                ):
                    raise ValueError("A conflicting static Pages run exists")
                matches.append(run)
        return matches

    def require_vacant_dispatch(self, commit):
        if self._matching_runs(commit):
            raise ValueError("Pages dispatch already exists; inspect, never redispatch")

    def dispatch(self, commit, *, record_attempt: Callable[[str], None]):
        self.require_dispatch_token()
        self.require_vacant_dispatch(commit)
        record_attempt(commit)
        self._request(
            f"{API_ROOT}/dispatches",
            data=json.dumps(
                {
                    "ref": "main",
                    "inputs": {"site-commit": commit},
                },
                separators=(",", ":"),
            ).encode("utf-8"),
        )

    def inspect_deployment(self, commit):
        matches = self._matching_runs(commit)
        if not matches:
            return "run-not-visible"
        if len(matches) != 1:
            raise ValueError("Pages deployment is ambiguous")
        run = matches[0]
        if type(run.get("run_attempt")) is not int or run["run_attempt"] != 1:
            raise ValueError("Pages workflow was repeated or has no attempt number")
        if run.get("status") in {"queued", "in_progress", "waiting", "requested", "pending"}:
            if run.get("conclusion") is not None:
                raise ValueError("Pending Pages workflow has a conclusion")
            return "workflow-pending"
        if run.get("status") != "completed":
            raise ValueError("Pages workflow status is unknown")
        if run.get("conclusion") != "success":
            if run.get("conclusion") in {
                "failure",
                "cancelled",
                "timed_out",
                "action_required",
                "startup_failure",
            }:
                return "workflow-failed"
            raise ValueError("Pages workflow conclusion is unknown")
        try:
            self._request(SITE_ROOT, served=True)
            self._request(SITE_ROOT + "privacy/", served=True)
        except ValueError:
            return "pages-unavailable"
        return "served"
