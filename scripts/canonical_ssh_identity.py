#!/usr/bin/env python3
"""Materialize and verify a canonical bootstrap SSH identity transiently."""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Any


class CanonicalSshIdentityError(ValueError):
    """Raised when the canonical bootstrap SSH identity is invalid."""


def _key_identity(value: str) -> tuple[str, str]:
    fields = value.strip().split()
    if len(fields) < 2 or not (fields[0].startswith("ssh-") or fields[0].startswith("ecdsa-") or fields[0].startswith("sk-")):
        raise CanonicalSshIdentityError("canonical SSH public key is invalid")
    return fields[0], fields[1]


def derive_public_key(private_key: Path) -> tuple[str, str]:
    try:
        result = subprocess.run(
            ["ssh-keygen", "-y", "-f", str(private_key)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CanonicalSshIdentityError("SSH public-key derivation is unavailable") from error
    if result.returncode != 0:
        raise CanonicalSshIdentityError("bootstrap SSH private key is invalid or passphrase-protected")
    try:
        return _key_identity(result.stdout)
    except CanonicalSshIdentityError as error:
        raise CanonicalSshIdentityError("bootstrap SSH private key produced no valid public key") from error


def materialize_private_key(
    provider: Any,
    *,
    destination: Path,
    public_keys: list[str] | tuple[str, ...],
    logical_path: str = "secrets.bootstrap.ssh_private_key",
) -> Path:
    """Write one verified private key with mode 0600 and return its path."""
    try:
        private_key = provider.resolve(logical_path)
    except Exception as error:
        raise CanonicalSshIdentityError("canonical bootstrap SSH private key is unavailable") from error
    if not isinstance(private_key, str) or not private_key.strip():
        raise CanonicalSshIdentityError("canonical bootstrap SSH private key is empty")
    expected = {_key_identity(key) for key in public_keys}
    if not expected:
        raise CanonicalSshIdentityError("canonical bootstrap SSH public-key set is empty")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.write_text(private_key, encoding="utf-8")
        os.chmod(destination, 0o600)
        actual = derive_public_key(destination)
        if actual not in expected:
            raise CanonicalSshIdentityError("bootstrap SSH private key does not match site public keys")
        return destination
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _load_runtime() -> tuple[Path, Path, list[str]]:
    import sys

    repo = Path("/workspace")
    sys.path.insert(0, str(repo / "scripts"))
    from canonical_values import load_site

    values_dir = Path(os.environ["INFRA_VALUES_DIR"])
    if not values_dir.is_absolute():
        values_dir = repo / values_dir
    site_file = values_dir / "site.yaml"
    bundle_file = values_dir / "secrets.sops.yaml"
    model = load_site(site_file, expected_site=os.environ.get("VALUES_SITE"), catalog_path=repo / "infra" / "services.json")
    public_keys = list(model.bootstrap.ssh.public_keys)
    for keys in model.bootstrap.ssh.host_additional_keys.values():
        public_keys.extend(keys)
    return bundle_file, site_file, public_keys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    import sys

    repo = Path("/workspace")
    sys.path.insert(0, str(repo / "scripts"))
    from secret_provider import SopsAgeProvider

    bundle_file, _site_file, public_keys = _load_runtime()
    key_file = Path(os.environ["SOPS_AGE_KEY_FILE"])
    provider = SopsAgeProvider(bundle_file, key_file=key_file, required_paths={"secrets.bootstrap.ssh_private_key"})
    materialize_private_key(provider, destination=args.destination, public_keys=public_keys)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CanonicalSshIdentityError as error:
        print(str(error), file=__import__("sys").stderr)
        raise SystemExit(2) from error
