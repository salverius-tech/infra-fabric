"""Read-only CI contract for scheduled supply-chain evidence."""

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/validate.yml"
COMMIT_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


class SupplyChainWorkflowTests(unittest.TestCase):
    def test_manual_and_scheduled_read_only_scan_job_is_present(self) -> None:
        workflow = yaml.load(
            WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
        )
        triggers = workflow["on"]
        job = workflow["jobs"]["supply-chain-evidence"]

        self.assertIn("workflow_dispatch", triggers)
        self.assertRegex(triggers["schedule"][0]["cron"], r"^\d+ \d+ \* \* \d+$")
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertIn("schedule", job["if"])
        self.assertIn("workflow_dispatch", job["if"])

        actions = [step for step in job["steps"] if "uses" in step]
        self.assertTrue(actions)
        for step in actions:
            self.assertRegex(step["uses"], COMMIT_ACTION)

        dry_run = next(
            step
            for step in job["steps"]
            if step.get("name")
            == "Report public pin update eligibility without private site values"
        )
        self.assertIn("scripts/require-site-context.sh", dry_run["run"])
        self.assertIn("scripts/python.sh scripts/update.py --dry-run", dry_run["run"])
        self.assertIn("export VALUES_SITE=update-dry-run", dry_run["run"])
        self.assertIn(
            "export SOPS_AGE_KEY_FILE=/run/secrets/sops-age-key", dry_run["run"]
        )

        sbom = next(
            step for step in actions if step["uses"].startswith("anchore/sbom-action@")
        )
        scan = next(
            step
            for step in actions
            if step["uses"].startswith("aquasecurity/trivy-action@")
        )
        self.assertEqual(sbom["with"]["format"], "spdx-json")
        self.assertEqual(sbom["with"]["upload-artifact"], "true")
        self.assertEqual(scan["with"]["severity"], "HIGH,CRITICAL")
        self.assertEqual(scan["with"]["exit-code"], "1")
        self.assertEqual(scan["with"]["ignore-unfixed"], "false")


if __name__ == "__main__":
    unittest.main()
