"""Consumer-owned routing controls for the public developer CLI."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
ENTRY = ROOT / (
    ".github/scripts/style.py" if (ROOT / ".github/scripts/style.py").is_file() else "scripts/style.py"
)
OWNER = Path(os.environ.get("RGM_DEV_ROOT", ROOT.parent / "dev"))


class StyleRoutingTest(unittest.TestCase):
    def test_hosted_caller_uses_one_reviewed_public_ref_and_preserves_job_boundaries(self):
        tools = Path(os.environ.get("RGM_STYLE_TOOLS", Path.home() / ".cache/rgm-style-tools"))
        previous = list(sys.path)
        try:
            sys.path.insert(0, str(tools / "python"))
            import yaml

            workflow = yaml.load(
                (ROOT / ".github/workflows/style.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader
            )
        finally:
            sys.path[:] = previous
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(set(workflow["on"]), {"pull_request", "push"})
        job = workflow["jobs"]["check"]
        self.assertEqual(job["strategy"]["matrix"]["os"], ["ubuntu-24.04", "windows-2025"])
        self.assertEqual(job["timeout-minutes"], "30")
        if "environment" in job:
            self.assertEqual(job["environment"], "hosted-authoring-check")
        steps = job["steps"]
        checkouts = [step for step in steps if step.get("uses", "").startswith("actions/checkout@")]
        self.assertEqual(len(checkouts), 2)
        self.assertEqual(checkouts[0]["with"]["path"], "target")
        owner = checkouts[1]["with"]
        self.assertEqual(owner["repository"], "TheFunkyBits/rgm-dev")
        self.assertEqual(owner["ref"], "${{ vars.RGM_DEV_REVISION }}")
        self.assertEqual(owner["path"], "rgm-dev")
        self.assertTrue(all(step["with"]["persist-credentials"] == "false" for step in checkouts))
        self.assertTrue(all("token" not in step["with"] for step in checkouts))
        action = next(step for step in steps if step.get("uses") == "./rgm-dev/actions/style")
        self.assertEqual(action["with"]["target-root"], "target")
        self.assertEqual(action["with"]["tool-cache"], "${{ runner.temp }}/rgm-style-tools")
        self.assertEqual((ROOT / action["with"]["smoke-root"]).resolve(), Path(__file__).resolve().parent)
        inventory = self.invoke("inventory", "--dev-root", str(OWNER))
        self.assertEqual(inventory.returncode, 0, inventory.stderr.decode("utf-8", errors="replace"))
        expected = "true" if json.loads(inventory.stdout)["formatters"].get("kotlin", 0) else "false"
        self.assertEqual(action["with"]["kotlin"], expected)
        self.assertTrue(any("^[0-9a-f]{40}$" in step.get("run", "") for step in steps))
        self.assertFalse(any("upload" in step.get("uses", "") for step in steps))

    def invoke(self, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(ENTRY), *arguments],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )

    def test_explicit_owner_and_local_policy(self):
        result = self.invoke("inventory", "--dev-root", str(OWNER))
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        report = json.loads(result.stdout)
        self.assertGreater(report["eligible"], 0)
        self.assertTrue((ROOT / "config/style.json").is_file())

    def test_missing_owner_is_a_refusal_not_acquisition(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.invoke("inventory", "--dev-root", directory)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertIn(b"rgm-dev", result.stderr)

    def test_target_override_is_rejected(self):
        result = self.invoke("inventory", "--dev-root", str(OWNER), "--root", str(OWNER))
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"owned by this repository", result.stderr)


if __name__ == "__main__":
    unittest.main()
