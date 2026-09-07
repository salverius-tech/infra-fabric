from __future__ import annotations

import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate-public.sh"


class ValidatePublicLintTests(unittest.TestCase):
    def test_ansible_lint_uses_isolated_temporary_workspace(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('lint_root="$(mktemp -d)"', text)
        self.assertIn('fixture_root="$(mktemp -d)"', text)
        self.assertIn("scaffold/sites/_template/site.yaml", text)
        self.assertIn("scripts/canonical-render.py", text)
        self.assertIn("scripts/verify-projections.py", text)
        self.assertIn("terraform.auto.tfvars.json", text)
        self.assertIn("ansible-inventory.json", text)
        self.assertIn("ansible-vars.json", text)
        self.assertNotIn("scaffold/terraform.tfvars", text)
        self.assertNotIn("scaffold/ansible/inventory/local.yml", text)
        self.assertIn("cleanup_lint_root()", text)
        self.assertIn("trap cleanup_lint_root EXIT", text)
        self.assertIn("cp -a .ansible-lint ansible.cfg settings.example.json infra scaffold scripts", text)
        self.assertIn('cd "${lint_root}"', text)
        self.assertIn('ANSIBLE_CONFIG="${lint_root}/ansible.cfg" ansible-lint infra/ansible', text)
        self.assertNotIn("\nansible-lint infra/ansible\n", text)

    def test_public_gate_checks_reconciliation_freshness(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("python scripts/validate-design-reconciliation.py --check", text)

    def test_public_gate_renders_every_catalog_service_through_consumers(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("tests/fixtures/full-catalog-services.yaml", text)
        self.assertIn("tests/fixtures/resource-runtime.yaml", text)
        self.assertIn('full_catalog_root="${fixture_root}/full-catalog"', text)
        self.assertIn('full_catalog_inventory="${full_catalog_root}/generated/ansible-inventory.json"', text)
        self.assertIn('full_catalog_vars="${full_catalog_root}/generated/ansible-vars.json"', text)
        self.assertIn('full_catalog_playbooks', text)

    def test_public_safety_wrapper_includes_untracked_public_files(self) -> None:
        text = (SCRIPT.parent / "public-safety-check.sh").read_text(encoding="utf-8")
        self.assertIn("scripts/python.sh scripts/public-safety-check.py", text)
        self.assertNotIn("--tracked-files", text)


if __name__ == "__main__":
    unittest.main()
