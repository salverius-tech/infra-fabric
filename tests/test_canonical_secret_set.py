from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

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


if __name__ == "__main__":
    unittest.main()
