from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ssh_initialize", ROOT / "scripts" / "ssh-initialize.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeProvider:
    def __init__(self, data: dict, private: str | None = None, identities: dict[str, str] | None = None) -> None:
        self._data = data
        self.private = private
        self.identities = identities or ({"secrets.bootstrap.ssh_private_key": private} if private is not None else {})

    def resolve(self, path: str) -> str:
        if path not in self.identities:
            raise KeyError(path)
        return self.identities[path]

    def discover(self) -> tuple[str, ...]:
        return tuple(self.identities)


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
            site_file.write_text((ROOT / "tests" / "fixtures" / "sites" / "dev" / "site.yaml").read_text(encoding="utf-8"), encoding="utf-8")
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
            self.assertIn("ssh_private_key", encrypted["data"]["secrets"]["providers"]["proxmox"])
            site_text = site_file.read_text(encoding="utf-8")
            self.assertEqual(site_text.count("ssh-ed25519"), 3)
            self.assertEqual(site_text.count("publicsafeexample"), 1)
            self.assertNotIn("proxmoxmanagementexample", site_text)

    def test_existing_matching_identities_are_not_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "dev"
            root.mkdir()
            private_text, public = module._generate_key(root)
            private_path = root / "source-key"
            private_path.write_text(private_text, encoding="utf-8")
            site_file = root / "site.yaml"
            site_file.write_text((ROOT / "tests" / "fixtures" / "sites" / "dev" / "site.yaml").read_text(encoding="utf-8").replace(
                "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIpublicsafeexample public@example.invalid", public
            ), encoding="utf-8")
            key_file = Path(temp_dir) / "age.key"
            key_file.write_text("age-placeholder\n", encoding="utf-8")
            os.chmod(key_file, 0o600)
            bundle = root / "bundle"
            bundle.write_text("ciphertext\n", encoding="utf-8")
            management_private, management_public = module._generate_key(root, "management-source")
            site_file.write_text(
                site_file.read_text(encoding="utf-8").replace(
                    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIproxmoxmanagementexample proxmox-management@example.invalid",
                    management_public,
                ),
                encoding="utf-8",
            )
            with patch.object(module, "SopsAgeProvider", return_value=FakeProvider({}, identities={
                "secrets.bootstrap.ssh_private_key": private_path.read_text(encoding="utf-8"),
                "secrets.providers.proxmox.ssh_private_key": management_private,
            })):
                self.assertEqual(module.initialize(site_file, bundle, key_file), "already initialized")

    def test_sops_yaml_uses_exact_site_filename_and_adjacent_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "values" / "sites" / "dev" / "secrets.sops.yaml"
            bundle.parent.mkdir(parents=True)
            policy = bundle.parent / ".sops.yaml"
            with patch.object(
                module.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout="ciphertext"),
            ) as run:
                module._sops_yaml("sops", bundle, {"secret": "synthetic"}, Path(temporary) / "key")
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--filename-override") + 1], "secrets.sops.yaml")
        self.assertEqual(command[command.index("--config") + 1], str(policy))


if __name__ == "__main__":
    unittest.main()
