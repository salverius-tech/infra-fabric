from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("canonical_ssh_identity", ROOT / "canonical_ssh_identity.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeProvider:
    def __init__(self, value: str) -> None:
        self.value = value

    def resolve(self, path: str) -> str:
        if path != "secrets.bootstrap.ssh_private_key":
            raise ValueError("unexpected path")
        return self.value


class CanonicalSshIdentityTests(unittest.TestCase):
    def make_key(self, directory: Path) -> tuple[Path, str]:
        private = directory / "source-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private)],
            check=True,
            capture_output=True,
            text=True,
        )
        return private, (private.with_name(private.name + ".pub")).read_text(encoding="utf-8").strip()

    def test_materializes_matching_private_key_with_restrictive_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            private, public = self.make_key(directory)
            destination = directory / "materialized" / "bootstrap"
            result = module.materialize_private_key(
                FakeProvider(private.read_text(encoding="utf-8")),
                destination=destination,
                public_keys=[public],
            )
            self.assertEqual(result, destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), private.read_text(encoding="utf-8"))
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_rejects_nonmatching_private_key_and_removes_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            private, _public = self.make_key(directory)
            destination = directory / "materialized" / "bootstrap"
            with self.assertRaisesRegex(module.CanonicalSshIdentityError, "does not match"):
                module.materialize_private_key(
                    FakeProvider(private.read_text(encoding="utf-8")),
                    destination=destination,
                    public_keys=["ssh-ed25519 AAAA_not_the_matching_key"],
                )
            self.assertFalse(destination.exists())

    def test_rejects_passphrase_protected_key_without_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            private = directory / "source-key"
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "passphrase", "-f", str(private)],
                check=True,
                capture_output=True,
                text=True,
            )
            public = private.with_name(private.name + ".pub").read_text(encoding="utf-8")
            with self.assertRaisesRegex(module.CanonicalSshIdentityError, "invalid or passphrase-protected"):
                module.materialize_private_key(
                    FakeProvider(private.read_text(encoding="utf-8")),
                    destination=directory / "materialized",
                    public_keys=[public],
                )


if __name__ == "__main__":
    unittest.main()
