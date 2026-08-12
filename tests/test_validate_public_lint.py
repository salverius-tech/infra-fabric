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


if __name__ == "__main__":
    unittest.main()
