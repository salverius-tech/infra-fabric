"""Regression coverage for deterministic site/resource credential hashes."""

from hashlib import sha256
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOST_TASKS = ROOT / "infra/ansible/roles/host_identity/tasks/main.yml"
ROOT_TASKS = ROOT / "infra/ansible/roles/root_credentials/tasks/main.yml"


def effective_salt(namespace: str, site: str, resource: str) -> str:
    return sha256(f"{namespace}:{site}:{resource}".encode()).hexdigest()[:16]


class StableCredentialHashTests(unittest.TestCase):
    def test_same_site_resource_produces_the_same_effective_salt(self) -> None:
        first = effective_salt("operator", "lab", "hermes")
        second = effective_salt("operator", "lab", "hermes")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)

    def test_site_or_resource_changes_produce_different_effective_salts(self) -> None:
        baseline = effective_salt("operator", "lab", "hermes")
        self.assertNotEqual(baseline, effective_salt("operator", "lab", "forgejo"))
        self.assertNotEqual(baseline, effective_salt("operator", "recovery", "hermes"))

    def test_roles_derive_salts_from_canonical_non_secret_identity(self) -> None:
        for path in (HOST_TASKS, ROOT_TASKS):
            text = path.read_text(encoding="utf-8")
            self.assertIn("canonical_site", text)
            self.assertIn("canonical_resource", text)
            self.assertIn("hash('sha256')", text)
            self.assertIn("[:16]", text)
            self.assertIn("no_log: true", text)

    def test_host_identity_root_recovery_hash_uses_host_specific_salt(self) -> None:
        text = HOST_TASKS.read_text(encoding="utf-8")
        recovery = text.split("- name: Set the protected root console recovery password", 1)[1].split(
            "- name: Remove temporary root SSH keys", 1
        )[0]
        self.assertIn("host_identity_root_password_hash_salt ~ ':' ~ canonical_site ~ ':' ~ canonical_resource", recovery)
        self.assertIn("hash('sha256')", recovery)
        self.assertIn("[:16]", recovery)
        self.assertIn("no_log: true", recovery)


if __name__ == "__main__":
    unittest.main()
