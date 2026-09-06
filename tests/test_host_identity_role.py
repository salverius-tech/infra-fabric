from __future__ import annotations

from pathlib import Path
import unittest


ROLE_TASKS = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "ansible"
    / "roles"
    / "host_identity"
    / "tasks"
    / "main.yml"
)


class HostIdentityRoleTests(unittest.TestCase):
    def test_operator_paths_and_task_labels_are_variable_driven(self) -> None:
        source = ROLE_TASKS.read_text(encoding="utf-8")

        self.assertNotIn("systemboss", source)
        self.assertIn('/etc/sudoers.d/{{ host_identity_operator_user }}', source)
        self.assertIn('/etc/sudoers.d/{{ host_identity_operator_user }}-bootstrap', source)
        self.assertIn("Apply pinned operator dotfiles as {{ host_identity_operator_user }}", source)
        self.assertIn("Run chezmoi as {{ host_identity_operator_user }}", source)


if __name__ == "__main__":
    unittest.main()
