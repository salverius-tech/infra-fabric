from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OperationalCutoverTests(unittest.TestCase):
    def test_operational_scripts_are_valid_bash(self) -> None:
        for name in ("validate-values.sh", "plan-infra.sh", "apply-infra.sh"):
            result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=f"{name}: {result.stderr}")

    def test_canonical_site_requires_complete_projection_set(self) -> None:
        required = "manifest.json terraform.auto.tfvars.json ansible-inventory.json ansible-vars.json dns-records.json"
        for name in ("validate-values.sh", "plan-infra.sh", "apply-infra.sh"):
            text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn(required, text)
            self.assertIn("verify-projections.py", text)

    def test_plan_uses_canonical_variables_and_apply_uses_canonical_ansible(self) -> None:
        plan = (ROOT / "scripts" / "plan-infra.sh").read_text(encoding="utf-8")
        apply = (ROOT / "scripts" / "apply-infra.sh").read_text(encoding="utf-8")
        self.assertIn('generated/terraform.auto.tfvars.json', plan)
        self.assertIn('enabled_services_args=()', plan)
        self.assertIn('--canonical-ansible', apply)
        self.assertIn('generated/ansible-inventory.json', apply)


if __name__ == "__main__":
    unittest.main()
