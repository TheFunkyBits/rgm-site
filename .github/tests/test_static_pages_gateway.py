from __future__ import annotations

import json
from pathlib import Path
import sys
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rgm_site_tools.static_pages_gateway import (
    API_ROOT,
    SITE_ROOT,
    WORKFLOW_PATH,
    StaticPagesGateway,
)


COMMIT = "a" * 40


class Response:
    def __init__(self, url, status, body=b"", served=False):
        self.url, self.status, self.body, self.served = url, status, body, served

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return None

    def geturl(self):
        return self.url

    def read(self):
        if self.served:
            raise AssertionError("Availability observation must not compare served bytes")
        return self.body


class FakeStaticHttp:
    def __init__(self):
        self.runs, self.requests = [], []
        self.dispatches = 0
        self.lose_ack = False
        self.privacy_status = 200

    @staticmethod
    def run(commit=COMMIT):
        return {
            "id": 1,
            "display_title": f"Deploy RGM site ({commit})",
            "head_sha": commit,
            "head_branch": "main",
            "event": "workflow_dispatch",
            "path": WORKFLOW_PATH,
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 1,
        }

    def open(self, request, timeout):
        url = request.full_url
        self.requests.append(request)
        if request.get_method() == "POST":
            self.dispatches += 1
            document = json.loads(request.data)
            assert document == {"ref": "main", "inputs": {"site-commit": COMMIT}}
            if self.lose_ack:
                raise URLError("synthetic lost acknowledgement")
            return Response(url, 204)
        if url.startswith(API_ROOT + "/runs?"):
            page = int(parse_qs(urlsplit(url).query)["page"][0])
            return Response(
                url,
                200,
                json.dumps(
                    {"total_count": len(self.runs), "workflow_runs": self.runs[(page - 1) * 100 : page * 100]}
                ).encode(),
            )
        if url in {SITE_ROOT, SITE_ROOT + "privacy/"}:
            return Response(url, self.privacy_status if url.endswith("privacy/") else 200, served=True)
        raise AssertionError("Unexpected static Pages request")


class StaticPagesGatewayTest(unittest.TestCase):
    def setUp(self):
        self.http = FakeStaticHttp()
        self.gateway = StaticPagesGateway("synthetic-token", open_request=self.http.open)
        self.attempts = set()

    def record(self, commit):
        if commit in self.attempts:
            raise ValueError("Dispatch already recorded")
        self.attempts.add(commit)

    def test_one_dispatch_observes_both_pages_without_public_credentials_or_byte_reads(self):
        self.gateway.dispatch(COMMIT, record_attempt=self.record)
        self.assertEqual({COMMIT}, self.attempts)
        self.http.runs = [self.http.run()]
        self.assertEqual("served", self.gateway.inspect_deployment(COMMIT))
        public = [request for request in self.http.requests if request.full_url.startswith(SITE_ROOT)]
        self.assertEqual([SITE_ROOT, SITE_ROOT + "privacy/"], [request.full_url for request in public])
        self.assertTrue(all(request.get_header("Authorization") is None for request in public))
        self.assertEqual(1, self.http.dispatches)

    def test_lost_acknowledgement_and_invisible_run_never_replay(self):
        self.http.lose_ack = True
        with self.assertRaisesRegex(ValueError, "never replay"):
            self.gateway.dispatch(COMMIT, record_attempt=self.record)
        with self.assertRaisesRegex(ValueError, "already recorded"):
            self.gateway.dispatch(COMMIT, record_attempt=self.record)
        self.assertEqual(1, self.http.dispatches)

    def test_failed_intent_write_prevents_post(self):
        def unavailable(commit):
            raise OSError("intent cannot be written")

        with self.assertRaises(OSError):
            self.gateway.dispatch(COMMIT, record_attempt=unavailable)
        self.assertEqual(0, self.http.dispatches)

    def test_privacy_missing_pending_failed_and_rerun_do_not_pass(self):
        original = self.http.run()
        self.assertEqual("run-not-visible", self.gateway.inspect_deployment(COMMIT))
        self.http.runs = [{**original, "status": "queued", "conclusion": None}]
        self.assertEqual("workflow-pending", self.gateway.inspect_deployment(COMMIT))
        self.http.runs = [{**original, "conclusion": "failure"}]
        self.assertEqual("workflow-failed", self.gateway.inspect_deployment(COMMIT))
        self.http.runs = [{**original, "run_attempt": 2}]
        with self.assertRaises(ValueError):
            self.gateway.inspect_deployment(COMMIT)
        self.http.runs = [original]
        self.http.privacy_status = 404
        self.assertEqual("pages-unavailable", self.gateway.inspect_deployment(COMMIT))

    def test_conflicts_duplicates_and_full_pagination_are_checked(self):
        original = self.http.run()
        self.http.runs = [original, {**original, "id": 2}]
        with self.assertRaises(ValueError):
            self.gateway.inspect_deployment(COMMIT)
        self.http.runs = [{**original, "path": "other.yml"}]
        with self.assertRaises(ValueError):
            self.gateway.inspect_deployment(COMMIT)
        self.http.runs = [{**self.http.run("b" * 40), "id": index} for index in range(1, 101)] + [
            {**original, "id": 101}
        ]
        self.assertEqual("served", self.gateway.inspect_deployment(COMMIT))

    def test_read_only_observation_does_not_require_a_token(self):
        self.http.runs = [self.http.run()]
        reader = StaticPagesGateway("", open_request=self.http.open)
        self.assertEqual("served", reader.inspect_deployment(COMMIT))
        self.assertTrue(all(request.get_header("Authorization") is None for request in self.http.requests))
        with self.assertRaises(ValueError):
            reader.dispatch(COMMIT, record_attempt=self.record)


if __name__ == "__main__":
    unittest.main()
