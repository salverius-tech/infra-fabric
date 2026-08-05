#!/usr/bin/env python3
"""Initialize a canonical site's bootstrap SSH identity through SOPS."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ruamel.yaml import YAML

from canonical_ssh_identity import derive_public_key
from canonical_values import load_site
from secret_provider import SopsAgeProvider, SecretProviderError, canonical_sops_filename

LOGICAL_PATH = "secrets.bootstrap.ssh_private_key"


class SshInitializationError(ValueError):
    """Raised when bootstrap SSH initialization cannot proceed safely."""


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def _resolve(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for component in path.split("."):
        if not isinstance(value, dict) or component not in value:
            raise KeyError(path)
        value = value[component]
    return value


def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
    current: dict[str, Any] = data
    components = path.split(".")
    for component in components[:-1]:
        child = current.get(component)
        if child is None:
            child = {}
            current[component] = child
        if not isinstance(child, dict):
            raise SshInitializationError(f"secret namespace is not a mapping: {component}")
        current = child
    current[components[-1]] = value


def _sops_yaml(sops: str, bundle: Path, data: dict[str, Any], key_file: Path) -> bytes:
    yaml = _yaml()
    from io import StringIO

    plaintext = StringIO()
    yaml.dump(data, plaintext)
    env = os.environ.copy()
    env["SOPS_AGE_KEY_FILE"] = str(key_file)
    result = subprocess.run(
        [
            sops,
            "--encrypt",
            "--input-type",
            "yaml",
            "--output-type",
            "yaml",
            "--filename-override",
            canonical_sops_filename(bundle),
            "--config",
            str(bundle.parent / ".sops.yaml"),
            "/dev/stdin",
        ],
        input=plaintext.getvalue(),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise SshInitializationError("SOPS encryption failed")
    return result.stdout.encode("utf-8")


def _generate_key(directory: Path) -> tuple[str, str]:
    private = directory / "bootstrap"
    result = subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private)],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        raise SshInitializationError("bootstrap SSH key generation failed")
    try:
        private_text = private.read_text(encoding="utf-8")
        key_type, key_material = derive_public_key(private)
        public = f"{key_type} {key_material}"
    except (OSError, ValueError) as error:
        raise SshInitializationError("generated bootstrap SSH key could not be verified") from error
    return private_text, public


def _atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _backup_path(path: Path) -> Path:
    with tempfile.NamedTemporaryFile(prefix=f".{path.name}.backup-", dir=path.parent, delete=False) as handle:
        return Path(handle.name)


def _replace_bundle_and_site(bundle: Path, ciphertext: bytes, site_file: Path, site_temp: Path) -> None:
    bundle_backup: Path | None = None
    site_backup: Path | None = None
    try:
        if bundle.exists():
            bundle_backup = _backup_path(bundle)
            os.replace(bundle, bundle_backup)
        if site_file.exists():
            site_backup = _backup_path(site_file)
            os.replace(site_file, site_backup)
        _atomic_write(bundle, ciphertext)
        os.replace(site_temp, site_file)
    except BaseException:
        bundle.unlink(missing_ok=True)
        site_file.unlink(missing_ok=True)
        if bundle_backup is not None and bundle_backup.exists():
            os.replace(bundle_backup, bundle)
        if site_backup is not None and site_backup.exists():
            os.replace(site_backup, site_file)
        raise
    finally:
        if bundle_backup is not None:
            bundle_backup.unlink(missing_ok=True)
        if site_backup is not None:
            site_backup.unlink(missing_ok=True)


def initialize(site_file: Path, bundle: Path, key_file: Path, *, sops: str = "sops") -> str:
    if not key_file.is_file() or not os.access(key_file, os.R_OK):
        raise SshInitializationError("external SOPS age identity is missing or unreadable")
    model = load_site(site_file, expected_site=os.environ.get("VALUES_SITE"), catalog_path=Path("infra/services.json"))
    public_keys = list(model.bootstrap.ssh.public_keys)
    if not public_keys:
        raise SshInitializationError("bootstrap.ssh.public_keys must contain at least one key")

    existing_private = None
    if bundle.is_file():
        try:
            provider = SopsAgeProvider(bundle, key_file=key_file)
        except (SecretProviderError, OSError) as error:
            raise SshInitializationError("existing SOPS bundle could not be decrypted") from error
        try:
            if LOGICAL_PATH in provider.discover():
                existing_private = provider.resolve(LOGICAL_PATH)
        except (SecretProviderError, OSError) as error:
            raise SshInitializationError("existing SOPS bundle could not resolve bootstrap SSH identity") from error

    if existing_private:
        with tempfile.TemporaryDirectory(prefix="ssh-initialize-") as temp_dir:
            private = Path(temp_dir) / "bootstrap"
            private.write_text(existing_private, encoding="utf-8")
            os.chmod(private, 0o600)
            actual = derive_public_key(private)
        if actual not in {tuple(key.strip().split()[:2]) for key in public_keys}:
            raise SshInitializationError("existing bootstrap SSH private key does not match site public keys")
        return "already initialized"

    with tempfile.TemporaryDirectory(prefix="ssh-initialize-") as temp_dir:
        private_text, public = _generate_key(Path(temp_dir))
        encrypted_data: dict[str, Any] = {}
        if bundle.is_file():
            try:
                existing = SopsAgeProvider(bundle, key_file=key_file)
                encrypted_data = existing._data.copy()  # validated in-memory bundle only
            except (SecretProviderError, OSError) as error:
                raise SshInitializationError("existing SOPS bundle could not be decrypted") from error
        _set_path(encrypted_data, LOGICAL_PATH, private_text)
        ciphertext = _sops_yaml(sops, bundle, encrypted_data, key_file)

        site_yaml = _yaml()
        site_data = site_yaml.load(site_file.read_text(encoding="utf-8"))
        bootstrap = site_data.setdefault("bootstrap", {})
        ssh = bootstrap.setdefault("ssh", {})
        declared = list(ssh.setdefault("public_keys", []))
        scaffold_placeholder = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIpublicsafeexample public@example.invalid"
        if scaffold_placeholder in declared:
            declared[declared.index(scaffold_placeholder)] = public
        elif public not in declared:
            declared.append(public)
        ssh["public_keys"] = declared

        site_buffer = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=site_file.parent, prefix=f".{site_file.name}.", delete=False)
        site_temp = Path(site_buffer.name)
        try:
            site_yaml.dump(site_data, site_buffer)
            site_buffer.close()
            load_site(site_temp, expected_site=os.environ.get("VALUES_SITE"), catalog_path=Path("infra/services.json"))
            _replace_bundle_and_site(bundle, ciphertext, site_file, site_temp)
        finally:
            site_buffer.close() if not site_buffer.closed else None
            site_temp.unlink(missing_ok=True)
    return "initialized"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-file", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, default=Path(os.environ.get("SOPS_AGE_KEY_FILE", "")))
    parser.add_argument("--sops", default="sops")
    args = parser.parse_args(argv)
    try:
        print(initialize(args.site_file, args.bundle, args.key_file, sops=args.sops))
    except (SshInitializationError, OSError, ValueError) as error:
        print(f"SSH initialization failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
