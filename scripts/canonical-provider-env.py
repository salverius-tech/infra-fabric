#!/usr/bin/env python3
"""Run one canonical provider command with transient SOPS-backed credentials."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

try:
    from secret_delivery import deliver_environment, provider_requirements
    from secret_provider import SopsAgeProvider, SecretProviderError
    from values_context import from_environment
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from secret_delivery import deliver_environment, provider_requirements
    from secret_provider import SopsAgeProvider, SecretProviderError
    from values_context import from_environment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="proxmox", choices=("proxmox",))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command.pop(0)
    if not command:
        parser.error("a provider command is required after --")

    context = from_environment(Path.cwd())
    if context.canonical_site_path is None:
        print("canonical provider environment requires a selected canonical site", file=sys.stderr)
        return 2
    bundle = context.values_dir / "secrets.sops.yaml"
    try:
        provider = SopsAgeProvider(bundle)
        environment = dict(os.environ)
        environment.update(
            deliver_environment(provider, consumer="opentofu-provider", requirements=provider_requirements(args.provider))
        )
        os.execvpe(command[0], command, environment)
    except (OSError, SecretProviderError, ValueError) as error:
        print(f"canonical provider credential handoff failed: {error}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())