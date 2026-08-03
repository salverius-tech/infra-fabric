from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "tools" / "docker-entrypoint.sh"
COMPOSE = ROOT / "compose.yaml"
BOOTSTRAP = ROOT / "scripts" / "bootstrap-pve-token.sh"
JUSTFILE = ROOT / "justfile"


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

    def test_sops_source_materializes_only_canonical_bootstrap_identity(self) -> None:
        text = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn('INFRA_SSH_IDENTITY_SOURCE:-external', text)
        self.assertIn("canonical_ssh_identity.py", text)
        self.assertIn("canonical-bootstrap", text)
        self.assertIn('&& "${INFRA_SSH_IDENTITY_SOURCE:-external}" != "sops"', text)

    def test_canonical_token_bootstrap_uses_materialized_identity(self) -> None:
        text = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn('ssh_identity_file="${HOME}/.ssh/${INFRA_SSH_IDENTITY_FILE}"', text)
        self.assertIn('IdentitiesOnly=yes', text)

    def test_canonical_setup_defers_sops_ssh_transport_until_explicit_initialization(self) -> None:
        text = JUSTFILE.read_text(encoding="utf-8")
        self.assertIn("INFRA_COPY_SSH_KEYS=true", text)
        setup = text[text.index("setup remote"):text.index("\n# Show private values")]
        self.assertNotIn("INFRA_SSH_IDENTITY_SOURCE", setup)
        self.assertIn("Skipping bootstrap credential initialization for canonical site", setup)
        self.assertIn("ssh-initialize SITE=", text)

    def test_proxmox_token_uses_infra_fabric_comments(self) -> None:
        text = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn('comment="infra-fabric OpenTofu token"', text)
        self.assertIn('infra-fabric OpenTofu service user', text)
        self.assertNotIn('homelab-infra OpenTofu token', text)
        self.assertNotIn('homelab-infra OpenTofu service user', text)


if __name__ == "__main__":
    unittest.main()
