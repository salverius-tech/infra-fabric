"""Supply-chain contract for the managed Tailscale client installation."""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "infra/ansible/roles/tailscale_client/tasks/main.yml"


class TailscaleSupplyChainTests(unittest.TestCase):
    def test_install_uses_checksum_verified_signed_repository(self) -> None:
        text = TASKS.read_text(encoding="utf-8")
        tasks = yaml.safe_load(text)

        self.assertNotIn("tailscale.com/install.sh", text)
        key = next(task for task in tasks if task.get("name") == "Install checksum-verified Tailscale repository key")
        repository = next(task for task in tasks if task.get("name") == "Configure signed Tailscale apt repository")
        package = next(task for task in tasks if task.get("name") == "Install Tailscale package")

        self.assertRegex(key["ansible.builtin.get_url"]["checksum"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(key["ansible.builtin.get_url"]["mode"], "0644")
        self.assertIn("signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg", repository["ansible.builtin.apt_repository"]["repo"])
        self.assertTrue(repository["ansible.builtin.apt_repository"]["update_cache"])
        self.assertEqual(package["ansible.builtin.apt"], {"name": "tailscale", "state": "present"})


if __name__ == "__main__":
    unittest.main()
