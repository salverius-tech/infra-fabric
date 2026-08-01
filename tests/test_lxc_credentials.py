from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = ROOT / "infra/ansible/roles/root_credentials/tasks/main.yml"
ROLE_DEFAULTS = ROOT / "infra/ansible/roles/root_credentials/defaults/main.yml"


class RootCredentialsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = ROLE_TASKS.read_text(encoding="utf-8")
        cls.defaults = ROLE_DEFAULTS.read_text(encoding="utf-8")

    def test_root_password_comes_from_private_environment_and_is_hidden(self) -> None:
        self.assertIn("INFRA_BOOTSTRAP_ROOT_PASSWORD", self.tasks)
        self.assertNotIn("TF_VAR_lxc_root_password", self.tasks)
        self.assertIn("no_log: true", self.tasks)
        self.assertIn("password_hash('sha512', root_credentials_root_password_hash_salt)", self.tasks)
        self.assertIn("update_password: always", self.tasks)

    def test_hash_salt_is_stable_for_idempotent_rotation(self) -> None:
        self.assertIn("root_credentials_root_password_hash_salt:", self.defaults)

    def test_bootstrap_playbook_owns_root_rotation(self) -> None:
        playbook = ROOT / "infra/ansible/playbooks/bootstrap-root-password.yml"
        self.assertIn("role: root_credentials", playbook.read_text(encoding="utf-8"))

    def test_service_playbooks_do_not_rotate_root_password(self) -> None:
        for service in ("hermes", "technitium", "forgejo", "infisical", "tailscale-client"):
            playbook = ROOT / f"infra/ansible/playbooks/{service}.yml"
            text = playbook.read_text(encoding="utf-8")
            self.assertNotIn("role: lxc_credentials", text)
            self.assertNotIn("role: root_credentials", text)


if __name__ == "__main__":
    unittest.main()
