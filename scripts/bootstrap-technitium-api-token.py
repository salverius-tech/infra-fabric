#!/usr/bin/env python3
"""Rotate a Technitium API token into the canonical SOPS bundle when needed."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))

CANONICAL_API_CREDENTIAL_PATH = "services.technitium.secrets.api_token"
DEFAULT_TOKEN_NAME = "infra-fabric"  # public-safety: allow-secret


class BootstrapError(ValueError):
    pass


def _canonical_secret_setter():
    path = Path(__file__).with_name("canonical-secret-set.py")
    spec = importlib.util.spec_from_file_location("canonical_secret_set", path)
    if spec is None or spec.loader is None:
        raise BootstrapError("canonical secret setter is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.set_secret


set_canonical_secret = _canonical_secret_setter()


class TechnitiumBootstrapClient:
    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    def call(
        self,
        path: str,
        params: Mapping[str, str] | None = None,
        token: str | None = None,
        timeout: int = 30,
        method: str = "POST",
    ) -> dict[str, Any]:
        data = urllib.parse.urlencode(params or {}).encode()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        request = urllib.request.Request(
            f"{self.api_url}{path}", data=data if method == "POST" else None, headers=headers, method=method
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode())
        if result.get("status") != "ok":
            raise BootstrapError(str(result))
        return result

    def wait_for_status(self, retries: int, delay: int) -> dict[str, Any]:
        last_error: Exception | None = None
        for _attempt in range(retries):
            try:
                return self.call("/status", timeout=10, method="GET")
            except BootstrapError as error:
                if "invalid-token" in str(error).lower():
                    return {"status": "ok", "hasDefaultCredentials": False}
                last_error = error
                time.sleep(delay)
            except Exception as error:  # noqa: BLE001 - report the final connection/API failure.
                last_error = error
                time.sleep(delay)
        raise BootstrapError(f"Technitium API did not become ready: {last_error}")


def validate_existing_token(client: TechnitiumBootstrapClient, token: str) -> bool:
    if not token:
        return False
    try:
        client.call("/user/session/get", token=token)
    except Exception:  # noqa: BLE001 - invalid/expired token should trigger rotation.
        return False
    return True


def login(client: TechnitiumBootstrapClient, password: str, user: str = "admin") -> str:
    result = client.call("/user/login", {"user": user, "pass": password, "includeInfo": "true"})
    token = str(result.get("token", ""))
    if not token:
        raise BootstrapError("Technitium login did not return a session token")
    return token


def create_api_token(client: TechnitiumBootstrapClient, session_token: str, token_name: str) -> str:
    result = client.call("/user/createToken", {"tokenName": token_name}, token=session_token)
    token = str(result.get("token", ""))
    if not token:
        raise BootstrapError("Technitium createToken did not return an API token")
    return token


def bootstrap_canonical(
    *,
    api_url: str,
    api_token: str,
    admin_password: str,
    bundle: Path,
    key_file: Path,
    retries: int,
    delay: int,
    token_name: str,
) -> bool:
    if not api_url or not admin_password:
        raise BootstrapError("canonical Technitium API URL and administrator password are required")
    client = TechnitiumBootstrapClient(api_url)
    client.wait_for_status(retries, delay)
    if validate_existing_token(client, api_token):
        print("Canonical Technitium API token already works.")
        return False
    try:
        session_token = login(client, admin_password)
    except BootstrapError as configured_login_error:
        try:
            default_session_token = login(client, "admin")
        except BootstrapError:
            raise configured_login_error
        client.call("/user/changePassword", {"pass": "admin", "newPass": admin_password}, token=default_session_token)
        session_token = login(client, admin_password)
    api_token = create_api_token(client, session_token, token_name)
    try:
        set_canonical_secret(bundle, CANONICAL_API_CREDENTIAL_PATH, api_token, key_file, replace=True, sops="sops")
    except Exception as error:  # noqa: BLE001 - preserve a redacted canonical persistence boundary.
        raise BootstrapError("canonical Technitium API token persistence failed") from error
    print("Rotated canonical Technitium API token.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--retries", type=int, default=20)
    parser.add_argument("--delay", type=int, default=6)
    parser.add_argument("--token-name", default=DEFAULT_TOKEN_NAME)
    args = parser.parse_args(argv)
    try:
        bootstrap_canonical(
            api_url=os.environ.get("TECHNITIUM_API_URL", ""),
            api_token=os.environ.get("TECHNITIUM_API_TOKEN", ""),
            admin_password=os.environ.get("TECHNITIUM_ADMIN_PASSWORD", ""),
            bundle=args.bundle,
            key_file=args.key_file,
            retries=args.retries,
            delay=args.delay,
            token_name=args.token_name,
        )
    except BootstrapError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
