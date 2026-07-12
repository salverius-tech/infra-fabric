from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "tools" / "docker-entrypoint.sh"
COMPOSE = ROOT / "compose.yaml"


class SshKeyHandlingTests(unittest.TestCase):
    def test_private_key_copy_requires_one_explicit_identity(self) -> None:
        text = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("INFRA_SSH_IDENTITY_FILE", text)
        self.assertIn("must name one SSH identity file", text)
        self.assertNotIn("find /ssh-ro -maxdepth 1 -type f", text)

    def test_compose_passes_selected_identity_name_only(self) -> None:
        text = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("INFRA_SSH_IDENTITY_FILE", text)


if __name__ == "__main__":
    unittest.main()
