from __future__ import annotations

import subprocess
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
        self.assertIn("INFRA_SSH_IDENTITY_SOURCE", text)

    def test_sops_source_materializes_distinct_canonical_bootstrap_and_proxmox_identities(
        self,
    ) -> None:
        text = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("INFRA_SSH_IDENTITY_SOURCE:-external", text)
        self.assertIn("canonical_ssh_identity.py", text)
        self.assertIn("canonical-bootstrap", text)
        self.assertIn("canonical-proxmox-management", text)
        self.assertNotIn(
            '--optional --destination "${ssh_dir}/canonical-proxmox-management"', text
        )
        self.assertIn('&& "${INFRA_SSH_IDENTITY_SOURCE:-external}" != "sops"', text)

    def test_direct_service_apply_uses_sops_backed_canonical_identity_transport(
        self,
    ) -> None:
        text = (ROOT / "scripts" / "apply-service.sh").read_text(encoding="utf-8")
        self.assertIn("INFRA_COPY_SSH_KEYS=true INFRA_SSH_IDENTITY_SOURCE=sops", text)

    def test_canonical_setup_defers_sops_ssh_transport_until_explicit_initialization(
        self,
    ) -> None:
        dumped = subprocess.run(
            ["just", "--dump"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        self.assertRegex(dumped, r'(?m)^setup remote="" site=""\s*:')
        self.assertRegex(dumped, r'(?m)^ssh-initialize SITE="dev"\s*:')
        self.assertIn(
            "Setup does not create credentials or invoke legacy wizards", dumped
        )


if __name__ == "__main__":
    unittest.main()
