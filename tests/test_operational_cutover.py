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

    def test_operator_site_actions_require_selected_site_context(self) -> None:
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        for recipe in ("actions-status", "actions-watch", "actions-logs", "actions-runners", "clean-plans"):
            start = justfile.index(f"{recipe}")
            next_recipe = justfile.find("\n# ", start + 1)
            block = justfile[start:] if next_recipe < 0 else justfile[start:next_recipe]
            self.assertIn("scripts/require-site-context.sh", block, recipe)

    def test_service_state_uses_selected_canonical_inventory(self) -> None:
        script = (ROOT / "scripts" / "service-state.sh").read_text(encoding="utf-8")
        self.assertIn("require_canonical_authority", script)
        self.assertIn('generated/ansible-inventory.json', script)
        self.assertNotIn("ansible/inventory/local.yml", script)
        self.assertNotIn("infra/ansible/inventory/tfvars.py", script)

    def test_update_requires_selected_canonical_context(self) -> None:
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        start = justfile.index("update:")
        block = justfile[start:justfile.index("\n# ", start + 1)]
        self.assertIn("scripts/require-site-context.sh", block)
        self.assertIn("require_canonical_authority", block)


if __name__ == "__main__":
    unittest.main()
