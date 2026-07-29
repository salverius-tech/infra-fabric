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
        self.assertIn('if [[ -n "${generated_backup}" && ! -e "${generated_dir}" && -e "${generated_backup}" ]]; then', content)
        self.assertIn('trap cleanup_generated_tmp EXIT', content)
        self.assertIn('-var-file=../../${INFRA_VALUES_DIR}/terraform.tfvars', content)
        self.assertIn('ansible/inventory/local.yml', content)
        self.assertNotIn('rm -rf "${generated_dir}"', content)


if __name__ == "__main__":
    unittest.main()
