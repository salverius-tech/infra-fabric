from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("canonical_secret_set", ROOT / "scripts" / "canonical-secret-set.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CanonicalSecretSetTests(unittest.TestCase):
    def test_set_path_creates_namespaces(self) -> None:
        data: dict[str, object] = {}
        module.set_path(data, "secrets.providers.proxmox.api_token", "VALUE")
        self.assertEqual(
            data,
            {"secrets": {"providers": {"proxmox": {"api_token": "VALUE"}}}},
        )

    def test_set_path_rejects_scalar_namespace(self) -> None:
        data: dict[str, object] = {"secrets": "not-a-mapping"}
        with self.assertRaises(module.SecretSetError):
            module.set_path(data, "secrets.providers.proxmox.api_token", "VALUE")

    def test_set_path_rejects_empty_path_component(self) -> None:
        with self.assertRaises(module.SecretSetError):
            module.set_path({}, "secrets..provider", "VALUE")

    def test_set_secret_rejects_noncanonical_target_before_provider_access(self) -> None:
        with self.assertRaisesRegex(module.SecretSetError, "canonical namespace"):
            module.set_secret(
                Path("missing-bundle"),
                "operator.password",
                "synthetic",
                Path("missing-key"),
                replace=False,
                sops="sops",
            )

    def test_encrypt_uses_exact_site_filename_and_adjacent_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "values" / "sites" / "dev" / "secrets.sops.yaml"
            bundle.parent.mkdir(parents=True)
            policy = bundle.parent / ".sops.yaml"
            with patch.object(
                module.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout="ciphertext"),
            ) as run:
                module.encrypt("sops", bundle, {"secret": "synthetic"}, Path(temporary) / "key")
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--filename-override") + 1], "values/sites/dev/secrets.sops.yaml")
        self.assertEqual(command[command.index("--config") + 1], str(policy))


if __name__ == "__main__":
    unittest.main()
