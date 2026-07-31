from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PlanProjectionLifecycleTests(unittest.TestCase):
    def test_plan_script_is_shell_valid(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts" / "plan-infra.sh")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plan_script_preserves_previous_projection_set_until_install(self) -> None:
        content = (ROOT / "scripts" / "plan-infra.sh").read_text(encoding="utf-8")
        self.assertIn('generated_backup="$(mktemp -d', content)
        self.assertIn('mv "${generated_dir}" "${generated_backup}"', content)
        self.assertIn('if ! mv "${generated_tmp}" "${generated_dir}"; then', content)
        self.assertIn('python scripts/verify-projections.py', content)
        self.assertIn('--generated-dir "${generated_dir}"', content)
        self.assertIn('if [[ -n "${generated_backup}" && ! "${generated_verified}" == true && -e "${generated_backup}" ]]; then', content)
        self.assertIn('generated_verified=false', content)
        self.assertIn('generated_verified=true', content)
        self.assertIn('rm -rf "${generated_dir}" 2>/dev/null || true', content)
        self.assertIn('trap cleanup_generated_tmp EXIT', content)
        self.assertIn('-var-file=../../${INFRA_VALUES_DIR}/terraform.tfvars', content)
        self.assertIn('ansible_inventory="${INFRA_VALUES_DIR}/ansible/inventory/local.yml"', content)
        self.assertIn('ansible_inventory="${INFRA_VALUES_DIR}/generated/ansible-inventory.json"', content)
        self.assertIn('-i "${ansible_inventory}"', content)
        self.assertIn('INFRA_EQUIVALENCE_BEFORE_JSON', content)
        self.assertIn('tofu -chdir=infra/opentofu show -json', content)
        self.assertIn('scripts/report-plan-equivalence.py', content)
        apply_content = (ROOT / "scripts" / "apply-infra.sh").read_text(encoding="utf-8")
        validate_content = (ROOT / "scripts" / "validate-values.sh").read_text(encoding="utf-8")
        self.assertIn('apply-ansible-services.py', apply_content)
        for consumer_content in (apply_content, validate_content):
            self.assertIn('ansible_inventory="${INFRA_VALUES_DIR}/ansible/inventory/local.yml"', consumer_content)
            self.assertIn('ansible_inventory="${INFRA_VALUES_DIR}/generated/ansible-inventory.json"', consumer_content)
            self.assertIn('"${ansible_inventory}"', consumer_content)
        self.assertIn('Plan equivalence review failed', content)
        self.assertIn('rm -f "${equivalence_after_json}"', content)
        self.assertNotIn('cleanup_equivalence_json', content)
        self.assertEqual(content.count('trap cleanup_generated_tmp EXIT'), 1)
        self.assertNotIn('rm -rf "${generated_dir}"\n', content)


if __name__ == "__main__":
    unittest.main()
