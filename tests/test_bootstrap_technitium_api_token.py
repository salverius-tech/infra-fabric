from __future__ import annotations

import importlib.util
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
    def write_env(self, content: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        with handle:
            handle.write(content)
        return Path(handle.name)

    def test_generates_admin_password_and_api_token_from_default_credentials(self) -> None:
        path = self.write_env(
            "export TECHNITIUM_API_URL='http://192.0.2.53:5380/api'\n"
            "export TECHNITIUM_API_TOKEN='REPLACE_AFTER_TOKEN_CREATION'\n"
        )
        try:
            with mock.patch.object(bootstrap_token, "TechnitiumBootstrapClient", FakeClient), mock.patch.object(
                bootstrap_token.secrets, "token_urlsafe", return_value="REPLACE_GENERATED_ADMIN_PASSWORD"
            ):
                changed = bootstrap_token.bootstrap(path, retries=1, delay=0, token_name="homelab-infra")

            self.assertTrue(changed)
            text = path.read_text(encoding="utf-8")
            self.assertIn("TECHNITIUM_ADMIN_PASSWORD=REPLACE_GENERATED_ADMIN_PASSWORD", text)
            self.assertIn("TECHNITIUM_API_TOKEN=REPLACE_API_TOKEN_VALUE", text)
            assert FakeClient.last is not None
            self.assertIn(("/user/changePassword", {"pass": "admin", "newPass": "REPLACE_GENERATED_ADMIN_PASSWORD"}, "REPLACE_SESSION_TOKEN"), FakeClient.last.calls)
            self.assertIn(("/user/createToken", {"tokenName": "homelab-infra"}, "REPLACE_SESSION_TOKEN"), FakeClient.last.calls)
        finally:
            path.unlink()

    def test_existing_valid_token_is_left_unchanged(self) -> None:
        path = self.write_env(
            "export TECHNITIUM_API_URL='http://192.0.2.53:5380/api'\n"
            "export TECHNITIUM_API_TOKEN='example-token'\n"  # public-safety: allow-secret
        )
        try:
            with mock.patch.object(bootstrap_token, "TechnitiumBootstrapClient", ValidTokenFakeClient):
                changed = bootstrap_token.bootstrap(path, retries=1, delay=0, token_name="homelab-infra")

            self.assertFalse(changed)
            text = path.read_text(encoding="utf-8")
            self.assertIn("TECHNITIUM_API_TOKEN='example-token'", text)  # public-safety: allow-secret
            self.assertNotIn("TECHNITIUM_ADMIN_PASSWORD", text)
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
