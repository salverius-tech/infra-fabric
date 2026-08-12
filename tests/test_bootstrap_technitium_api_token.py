from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap-technitium-api-token.py"
spec = importlib.util.spec_from_file_location("bootstrap_technitium_api_token", SCRIPT)
assert spec and spec.loader
bootstrap_token = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bootstrap_token
spec.loader.exec_module(bootstrap_token)


class FakeClient:
    last: "FakeClient | None" = None

    def __init__(self, api_url: str) -> None:
        self.api_url = api_url
        self.calls: list[tuple[str, dict[str, str], str | None]] = []
        self.valid_existing_token = False
        FakeClient.last = self

    def wait_for_status(self, retries: int, delay: int) -> dict[str, object]:
        self.calls.append(("/status", {"retries": str(retries), "delay": str(delay)}, None))
        return {"status": "ok", "hasDefaultCredentials": True}

    def call(
        self,
        path: str,
        params: dict[str, str] | None = None,
        token: str | None = None,
        timeout: int = 30,
        method: str = "POST",
    ) -> dict[str, object]:
        self.calls.append((path, params or {}, token))
        if path == "/user/session/get":
            if self.valid_existing_token:
                return {"status": "ok"}
            raise bootstrap_token.BootstrapError("invalid-token")
        if path == "/user/login":
            return {"status": "ok", "token": "REPLACE_SESSION_TOKEN"}
        if path == "/user/changePassword":
            return {"status": "ok"}
        if path == "/user/createToken":
            return {"status": "ok", "token": "REPLACE_API_TOKEN_VALUE"}
        return {"status": "ok"}


class ValidTokenFakeClient(FakeClient):
    def __init__(self, api_url: str) -> None:
        super().__init__(api_url)
        self.valid_existing_token = True


class BootstrapTechnitiumApiTokenTests(unittest.TestCase):
    def test_status_invalid_token_marks_api_ready(self) -> None:
        client = bootstrap_token.TechnitiumBootstrapClient("http://example.invalid/api")
        with mock.patch.object(client, "call", side_effect=bootstrap_token.BootstrapError("invalid-token")):
            status = client.wait_for_status(retries=1, delay=0)

        self.assertEqual(status, {"status": "ok", "hasDefaultCredentials": False})

    def test_canonical_bootstrap_rotates_invalid_token_without_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "secrets.sops.yaml"
            key_file = root / "site.age"
            bundle.write_text("ciphertext\n", encoding="utf-8")
            key_file.write_text("identity\n", encoding="utf-8")
            stored: list[tuple[Path, str, str, Path]] = []

            def set_secret(
                bundle_path: Path,
                path: str,
                value: str,
                selected_key: Path,
                *,
                replace: bool,
                sops: str,
            ) -> str:
                self.assertTrue(replace)
                self.assertEqual(sops, "sops")
                stored.append((bundle_path, path, value, selected_key))
                return "updated"

            with (
                mock.patch.object(bootstrap_token, "TechnitiumBootstrapClient", FakeClient),
                mock.patch.object(bootstrap_token, "set_canonical_secret", side_effect=set_secret),
            ):
                changed = bootstrap_token.bootstrap_canonical(
                    api_url="http://example.invalid/api",
                    api_token="REPLACE_OLD_TOKEN",
                    admin_password="REPLACE_ADMIN_PASSWORD",
                    bundle=bundle,
                    key_file=key_file,
                    retries=1,
                    delay=0,
                    token_name="infra-fabric",
                )

        self.assertTrue(changed)
        self.assertEqual(stored, [(bundle, "services.technitium.secrets.api_token", "REPLACE_API_TOKEN_VALUE", key_file)])
        assert FakeClient.last is not None
        self.assertIn(("/user/createToken", {"tokenName": "infra-fabric"}, "REPLACE_SESSION_TOKEN"), FakeClient.last.calls)

    def test_canonical_bootstrap_leaves_valid_token_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "secrets.sops.yaml"
            key_file = root / "site.age"
            bundle.write_text("ciphertext\n", encoding="utf-8")
            key_file.write_text("identity\n", encoding="utf-8")
            with (
                mock.patch.object(bootstrap_token, "TechnitiumBootstrapClient", ValidTokenFakeClient),
                mock.patch.object(bootstrap_token, "set_canonical_secret") as set_secret,
            ):
                changed = bootstrap_token.bootstrap_canonical(
                    api_url="http://example.invalid/api",
                    api_token="REPLACE_VALID_TOKEN",
                    admin_password="REPLACE_ADMIN_PASSWORD",
                    bundle=bundle,
                    key_file=key_file,
                    retries=1,
                    delay=0,
                    token_name="infra-fabric",
                )

        self.assertFalse(changed)
        set_secret.assert_not_called()


if __name__ == "__main__":
    unittest.main()
