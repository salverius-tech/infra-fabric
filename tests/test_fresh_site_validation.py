from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FreshSiteValidationTests(unittest.TestCase):
    def test_setup_initializes_a_canonical_site_that_passes_non_secret_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            values_root = temporary_root / "values"
            fake_bin = temporary_root / "bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text("#!/usr/bin/env bash\nmkdir -p \"$2/.git\"\n", encoding="utf-8")
            fake_git.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
                "VALUES_DIR": str(values_root),
                "VALUES_SITE": "fresh",
                "VALUES_TEMPLATE_DIR": str(ROOT / "scaffold"),
            }
            initialized = subprocess.run(
                ["bash", str(ROOT / "scripts" / "values.sh"), "init"],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            self.assertTrue((values_root / "sites" / "fresh" / "site.yaml").is_file())
            self.assertFalse((values_root / "sites" / "fresh" / "secrets.sops.yaml").exists())

            checked = subprocess.run(
                ["bash", str(ROOT / "scripts" / "values.sh"), "check"],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_validate_command_renders_and_verifies_before_using_canonical_consumers(self) -> None:
        script = (ROOT / "scripts" / "validate-values.sh").read_text(encoding="utf-8")
        render = 'python scripts/canonical-render.py'
        verify = 'python scripts/verify-projections.py'
        inventory = 'ansible_inventory="${INFRA_VALUES_DIR}/generated/ansible-inventory.json"'
        self.assertIn(render, script)
        self.assertIn(verify, script)
        self.assertLess(script.index(render), script.index(verify))
        self.assertLess(script.index(verify), script.index(inventory))
        self.assertNotIn("Run just plan", script)


if __name__ == "__main__":
    unittest.main()
