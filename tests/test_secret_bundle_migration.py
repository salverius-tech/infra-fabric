from __future__ import annotations

import unittest
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from secret_bundle_migration import (
    SecretBundleMigrationError,
    migrate_document,
    migrate_encrypted_bundle,
)


class SecretBundleMigrationTests(unittest.TestCase):
    def test_moves_legacy_operator_password_to_identity_neutral_path(self) -> None:
        document = {
            "operator": {"systemboss_password": "secret-value"},
            "bootstrap": {"root_password": "root-value"},
        }

        migrated, changed = migrate_document(document)

        self.assertTrue(changed)
        self.assertEqual(migrated["operator"], {"password": "secret-value"})
        self.assertEqual(migrated["bootstrap"], {"root_password": "root-value"})
        self.assertNotIn("systemboss_password", migrated["operator"])

    def test_identical_legacy_and_new_values_collapse_to_new_path(self) -> None:
        document = {"operator": {"systemboss_password": "same", "password": "same"}}

        migrated, changed = migrate_document(document)

        self.assertTrue(changed)
        self.assertEqual(migrated, {"operator": {"password": "same"}})

    def test_conflicting_legacy_and_new_values_fail_closed(self) -> None:
        document = {"operator": {"systemboss_password": "old", "password": "new"}}

        with self.assertRaises(SecretBundleMigrationError):
            migrate_document(document)

    def test_bundle_without_legacy_path_is_unchanged(self) -> None:
        document = {"operator": {"password": "current"}}

        migrated, changed = migrate_document(document)

        self.assertFalse(changed)
        self.assertEqual(migrated, document)

    def test_encrypted_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "secrets.sops.yaml"
            bundle.write_text("ciphertext", encoding="utf-8")
            with patch(
                "secret_bundle_migration._run_sops",
                return_value="operator:\n  systemboss_password: old\n",
            ):
                result = migrate_encrypted_bundle(bundle)

            self.assertTrue(result["changed"])
            self.assertEqual(bundle.read_text(encoding="utf-8"), "ciphertext")
            self.assertFalse(bundle.with_name("secrets.sops.yaml.pre-migration").exists())

    def test_encrypted_apply_backups_and_replaces_ciphertext(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "secrets.sops.yaml"
            bundle.write_text("old-ciphertext", encoding="utf-8")

            def fake_sops(args: list[str], **_: object) -> str:
                if "--decrypt" in args:
                    return "operator:\n  systemboss_password: old\n"
                return "new-ciphertext"

            with patch("secret_bundle_migration._run_sops", side_effect=fake_sops):
                result = migrate_encrypted_bundle(bundle, apply=True)

            self.assertEqual(bundle.read_text(encoding="utf-8"), "new-ciphertext")
            self.assertEqual(
                bundle.with_name("secrets.sops.yaml.pre-migration").read_text(encoding="utf-8"),
                "old-ciphertext",
            )
            self.assertIn("backup", result)


if __name__ == "__main__":
    unittest.main()