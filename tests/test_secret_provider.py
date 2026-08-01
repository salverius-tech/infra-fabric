from __future__ import annotations

import os
import signal
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from secret_provider import (
    SecretBundle,
    SecretProviderError,
    SopsAgeProvider,
    check_sops_age_availability,
    discover_age_key_file,
    inspect_sops_policy,
    secret_material_directory,
    validate_sops_age_recipients,
    write_secret_material,
)

class SecretProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(self._cleanup)
        self.bundle = self.root / "secrets.sops.yaml"
        self.bundle.write_text("services:\n  forgejo:\n    admin_password: placeholder-secret\n    secret_key: another-placeholder\n", encoding="utf-8")
        self.sops = self.root / "sops-fixture"
        self.sops_marker = self.root / "sops-invoked"
        self.sops.write_text(
            "#!/bin/sh\n" f"touch '{self.sops_marker}'\n" "shift 5\n" "cat \"$1\"\n",
            encoding="utf-8",
        )
        self.sops.chmod(self.sops.stat().st_mode | stat.S_IXUSR)

    def _cleanup(self) -> None:
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def test_resolves_logical_paths_without_including_values_in_metadata(self) -> None:
        provider = SopsAgeProvider(self.bundle, executable=str(self.sops))
        self.assertEqual(provider.resolve("services.forgejo.admin_password"), "placeholder-secret")
        self.assertEqual(provider.describe("services.forgejo.admin_password"), {
            "path": "services.forgejo.admin_password",
            "provider": "sops-age",
            "classification": "logical",
        })
        identity = provider.identity({"services.forgejo.admin_password"})
        self.assertEqual(len(identity.ciphertext_hash), 64)
        self.assertEqual(len(identity.secret_digest), 64)

    def test_digest_changes_only_when_selected_secret_changes(self) -> None:
        provider = SopsAgeProvider(self.bundle, executable=str(self.sops))
        first = provider.secret_digest({"services.forgejo.admin_password"})
        self.bundle.write_text(
            "services:\n  forgejo:\n    admin_password: rotated-placeholder\n    secret_key: another-placeholder\n",
            encoding="utf-8",
        )
        second = SopsAgeProvider(self.bundle, executable=str(self.sops)).secret_digest(
            {"services.forgejo.admin_password"}
        )
        self.assertNotEqual(first, second)

    def test_missing_logical_path_fails_without_exposing_value(self) -> None:
        provider = SopsAgeProvider(self.bundle, executable=str(self.sops))
        with self.assertRaisesRegex(SecretProviderError, "required secret is missing") as raised:
            provider.resolve("services.forgejo.missing")
        self.assertNotIn("placeholder-secret", str(raised.exception))

    def test_invalid_logical_paths_fail_closed(self) -> None:
        provider = SopsAgeProvider(self.bundle, executable=str(self.sops))
        for logical_path in ("", "..", "services..forgejo", "services.forgejo..admin_password", "Services.forgejo.token", "services/forgejo/token", "services.forgejo.bad key"):
            with self.subTest(logical_path=logical_path), self.assertRaises(SecretProviderError):
                provider.resolve(logical_path)

    def test_sops_failure_is_sanitized(self) -> None:
        failing = self.root / "sops-failing"
        failing.write_text("#!/bin/sh\nprintf 'secret-placeholder-error' >&2\nexit 7\n", encoding="utf-8")
        failing.chmod(failing.stat().st_mode | stat.S_IXUSR)
        with self.assertRaisesRegex(SecretProviderError, "could not decrypt") as raised:
            SopsAgeProvider(self.bundle, executable=str(failing))
        self.assertNotIn("secret-placeholder-error", str(raised.exception))

    def test_discovers_structure_and_validates_required_paths_without_values(self) -> None:
        provider = SopsAgeProvider(
            self.bundle,
            executable=str(self.sops),
            required_paths={"services.forgejo.admin_password"},
        )
        self.assertEqual(provider.discover(), (
            "services.forgejo.admin_password", "services.forgejo.secret_key",
        ))
        provider.validate_required({"services.forgejo.admin_password"})
        self.assertNotIn("placeholder-secret", repr(provider.describe("services.forgejo.admin_password")))

    def test_bundle_rejects_missing_required_path(self) -> None:
        with self.assertRaisesRegex(SecretProviderError, "required secret path is not present"):
            SecretBundle(
                {"services": {"forgejo": {"admin_password": "placeholder-secret"}}},
                frozenset({"services.forgejo.missing"}),
            )

    def test_bundle_repr_is_redacted(self) -> None:
        bundle = SecretBundle(
            {"services": {"forgejo": {"admin_password": "placeholder-secret"}}},
        )
        self.assertNotIn("placeholder-secret", repr(bundle))

    def test_discovers_external_age_key_file_without_reading_it(self) -> None:
        key_file = self.root / "age-keys.txt"
        key_file.write_text("PRIVATE-KEY-MATERIAL", encoding="utf-8")
        key_file.chmod(0o600)
        self.assertEqual(
            discover_age_key_file(environment={"SOPS_AGE_KEY_FILE": str(key_file)}),
            key_file.resolve(),
        )
        key_file.chmod(0o644)
        with self.assertRaisesRegex(SecretProviderError, "permissions are too broad"):
            discover_age_key_file(environment={"SOPS_AGE_KEY_FILE": str(key_file)})
        with self.assertRaisesRegex(SecretProviderError, "key file is unavailable"):
            discover_age_key_file(environment={"SOPS_AGE_KEY_FILE": str(self.root / "missing")})

    def test_metadata_only_sops_availability_does_not_decrypt_or_expose_values(self) -> None:
        key_file = self.root / "age-keys.txt"
        key_file.write_text("PRIVATE_KEY_SENTINEL", encoding="utf-8")
        key_file.chmod(0o600)
        result = check_sops_age_availability(
            self.bundle,
            executable=str(self.sops),
            key_file=key_file,
        )
        self.assertEqual(result["provider"], "sops-age")
        self.assertEqual(result["bundle_classification"], "encrypted-yaml")
        self.assertNotIn("PRIVATE_KEY_SENTINEL", repr(result))
        self.assertNotIn("placeholder-secret", repr(result))
        self.assertFalse(self.sops_marker.exists())

    def test_metadata_only_sops_availability_requires_executable(self) -> None:
        key_file = self.root / "age-keys.txt"
        key_file.write_text("PRIVATE_KEY_SENTINEL", encoding="utf-8")
        key_file.chmod(0o600)
        with self.assertRaisesRegex(SecretProviderError, "SOPS executable is unavailable"):
            check_sops_age_availability(
                self.bundle,
                executable=str(self.root / "missing-sops"),
                key_file=key_file,
            )

        with secret_material_directory(self.root) as directory:
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            material = write_secret_material(directory, "runtime.env", "SECRET=placeholder-secret\n")
            self.assertEqual(material.stat().st_mode & 0o777, 0o600)
            self.assertTrue(material.is_file())
        self.assertFalse(directory.exists())

    def test_secret_material_directory_cleans_up_on_sigterm(self) -> None:
        directory_path: Path | None = None
        with self.assertRaises(SystemExit) as raised:
            with secret_material_directory(self.root) as directory_path:
                material = write_secret_material(directory_path, "runtime.env", "SECRET=placeholder-secret\n")
                self.assertTrue(material.is_file())
                handler = cast(Callable[[int, object], object], signal.getsignal(signal.SIGTERM))
                handler(signal.SIGTERM, None)
        self.assertEqual(raised.exception.code, 128 + signal.SIGTERM)
        assert directory_path is not None
        self.assertFalse(directory_path.exists())

    def test_sops_age_recipient_policy_matches_public_metadata(self) -> None:
        encrypted = self.root / "encrypted.sops.yaml"
        encrypted.write_text(
            "secret: ENC[ age-encrypted ]\n"
            "sops:\n"
            "  age:\n"
            "    - recipient: age1example\n"
            "      enc: wrapped-key\n",
            encoding="utf-8",
        )
        validate_sops_age_recipients(encrypted, {"age1example"})
        with self.assertRaisesRegex(SecretProviderError, "policy does not match"):
            validate_sops_age_recipients(encrypted, {"age1other"})

    def test_sops_age_recipient_policy_rejects_placeholder_policy(self) -> None:
        encrypted = self.root / "encrypted.yaml"
        encrypted.write_text("sops:\n  age:\n    - recipient: age1REPLACE_WITH_SITE_RECIPIENT\n", encoding="utf-8")
        with self.assertRaises(SecretProviderError):
            validate_sops_age_recipients(encrypted, {"age1REPLACE_WITH_SITE_RECIPIENT"})

        missing = self.root / "missing-metadata.sops.yaml"
        missing.write_text("secret: ENC[ age-encrypted ]\n", encoding="utf-8")
        with self.assertRaisesRegex(SecretProviderError, "metadata is unavailable"):
            validate_sops_age_recipients(missing, {"age1example"})

        malformed = self.root / "malformed-metadata.sops.yaml"
        malformed.write_text("sops:\n  age: [{}]\n", encoding="utf-8")
        with self.assertRaisesRegex(SecretProviderError, "metadata is invalid"):
            validate_sops_age_recipients(malformed, {"age1example"})
    def test_sops_policy_inspection_reports_public_placeholder_without_values(self) -> None:
        policy = self.root / ".sops.yaml"
        policy.write_text(
            "creation_rules:\n  - path_regex: '^values/sites/[^/]+/secrets\\.sops\\.yaml$'\n    age: age1REPLACE_WITH_SITE_RECIPIENT\n",
            encoding="utf-8",
        )
        result = inspect_sops_policy(policy, site="dev")
        self.assertEqual(result["policy_scope"], "values/sites/dev/secrets.sops.yaml")
        self.assertEqual(result["recipient_policy"], "not-configured")
        self.assertNotIn("PRIVATE", repr(result))

    def test_sops_policy_inspection_rejects_wrong_scope_and_recipient_mismatch(self) -> None:
        policy = self.root / ".sops.yaml"
        policy.write_text(
            "creation_rules:\n  - path_regex: '^values/sites/[^/]+/other\\.yaml$'\n    age: age1example\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(SecretProviderError, "scope"):
            inspect_sops_policy(policy, site="dev")
        policy.write_text(
            "creation_rules:\n  - path_regex: '^values/sites/[^/]+/secrets\\.sops\\.yaml$'\n    age: age1example\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(SecretProviderError, "does not match"):
            inspect_sops_policy(policy, site="dev", expected_recipients={"age1other"})


if __name__ == "__main__":
    unittest.main()
