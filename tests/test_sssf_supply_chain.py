"""Static contracts for SSSF reviewed runtime artifacts."""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "infra/ansible/roles/sssf/defaults/main.yml"
TASKS = ROOT / "infra/ansible/roles/sssf/tasks/main.yml"


class SssfSupplyChainTests(unittest.TestCase):
    def test_runtime_pins_are_complete_and_checksum_shaped(self) -> None:
        defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
        self.assertEqual(defaults["sssf_artifact_path"], "/var/lib/infra-fabric/artifacts/sssf")
        for tool in ("uv", "pi", "bun"):
            self.assertRegex(defaults[f"sssf_{tool}_version"], r"^\d+\.\d+\.\d+$")
            self.assertRegex(defaults[f"sssf_{tool}_sha256"], r"^[0-9a-f]{64}$")

    def test_role_requires_controller_cached_checksum_verified_archives(self) -> None:
        text = TASKS.read_text(encoding="utf-8")
        tasks = yaml.safe_load(text)
        self.assertNotIn("astral.sh/uv/install.sh", text)
        self.assertNotIn("pi.dev/install.sh", text)
        self.assertNotIn("bun.sh/install", text)
        self.assertNotIn("| sh", text)
        self.assertNotIn("| bash", text)
        self.assertIn("delegate_to: localhost", text)
        self.assertIn("checksum_algorithm: sha256", text)
        self.assertIn("item.stat.checksum == item.item.checksum", text)
        self.assertIn("uv-x86_64-unknown-linux-gnu.tar.gz", text)
        self.assertIn("pi-linux-x64.tar.gz", text)
        self.assertIn("bun-linux-x64.zip", text)
        self.assertIn("ansible_architecture == 'x86_64'", text)
        self.assertIn("item.tool != 'bun' or sssf_visualizer_enabled | bool", text)
        self.assertIn("not item.skipped | default(false)", text)
        self.assertTrue(any(task.get("name") == "Extract checksum-verified Bun runtime" for task in tasks))


if __name__ == "__main__":
    unittest.main()
