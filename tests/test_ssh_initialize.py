from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ssh_initialize", ROOT / "scripts" / "ssh-initialize.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeProvider:
    def __init__(self, data: dict, private: str | None = None) -> None:
        self._data = data
        self.private = private

    def resolve(self, path: str) -> str:
        if self.private is None:
            raise KeyError(path)
        return self.private

    def discover(self) -> tuple[str, ...]:
        return ("secrets.bootstrap.ssh_private_key",) if self.private is not None else ()


class SshInitializeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.site_environment = os.environ.get("VALUES_SITE")
        os.environ["VALUES_SITE"] = "dev"

    def tearDown(self) -> None:
        if self.site_environment is None:
            os.environ.pop("VALUES_SITE", None)
        else:
            os.environ["VALUES_SITE"] = self.site_environment

    def test_generate_key_is_unencrypted_and_derivable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            private, public = module._generate_key(Path(temp_dir))
            self.assertIn("OPENSSH PRIVATE KEY", private)
            self.assertEqual(public[0], "s")
            self.assertTrue(public.startswith("ssh-ed25519 "))

    def test_initialize_adds_public_key_and_encrypts_private_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "dev"
            root.mkdir()
            site_file = root / "site.yaml"
            site_file.write_text((ROOT / "scaffold" / "sites" / "dev" / "site.yaml").read_text(encoding="utf-8"), encoding="utf-8")
            bundle = root / "secrets.sops.yaml"
            key_file = Path(temp_dir) / "age.key"
            key_file.write_text("age-placeholder\n", encoding="utf-8")
            os.chmod(key_file, 0o600)
            encrypted = {}

            def fake_encrypt(sops: str, path: Path, data: dict, key: Path) -> bytes:
                encrypted["data"] = data
                return b"ciphertext"

            with patch.object(module, "SopsAgeProvider", return_value=FakeProvider({})), patch.object(
                module, "_sops_yaml", side_effect=fake_encrypt
            ):
                result = module.initialize(site_file, bundle, key_file)
            self.assertEqual(result, "initialized")
            self.assertIn("secrets", encrypted["data"])
            site_text = site_file.read_text(encoding="utf-8")
            self.assertEqual(site_text.count("ssh-ed25519"), 2)
            self.assertEqual(site_text.count("publicsafeexample"), 1)

    def test_existing_matching_key_is_not_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "dev"
            root.mkdir()
            private_text, public = module._generate_key(root)
            private_path = root / "source-key"
            private_path.write_text(private_text, encoding="utf-8")
            site_file = root / "site.yaml"
            site_file.write_text((ROOT / "scaffold" / "sites" / "dev" / "site.yaml").read_text(encoding="utf-8").replace(
                "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIpublicsafeexample public@example.invalid", public
            ), encoding="utf-8")
            key_file = Path(temp_dir) / "age.key"
            key_file.write_text("age-placeholder\n", encoding="utf-8")
            os.chmod(key_file, 0o600)
            bundle = root / "bundle"
            bundle.write_text("ciphertext\n", encoding="utf-8")
            with patch.object(module, "SopsAgeProvider", return_value=FakeProvider({}, private_path.read_text(encoding="utf-8"))):
                self.assertEqual(module.initialize(site_file, bundle, key_file), "already initialized")


if __name__ == "__main__":
    unittest.main()
