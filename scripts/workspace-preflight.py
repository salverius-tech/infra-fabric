#!/usr/bin/env python3
"""Check that generated workspace files are writable before plan/apply."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

try:
    from canonical_projections import render_ansible_inventory, render_ansible_vars, render_dns_records, render_opentofu_variables
    from canonical_values import load_site, model_digest
    from projection_manifest import build_manifest, verify_manifest
    from service_catalog import load_catalog
    from values_context import from_environment
    from secret_provider import SecretProviderError, SopsAgeProvider, check_sops_age_availability, inspect_sops_policy, validate_sops_age_recipients
except ModuleNotFoundError:  # pragma: no cover - direct import in test loaders
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from canonical_projections import render_ansible_inventory, render_ansible_vars, render_dns_records, render_opentofu_variables
    from canonical_values import load_site, model_digest
    from projection_manifest import build_manifest, verify_manifest
    from service_catalog import load_catalog
    from values_context import from_environment
    from secret_provider import SecretProviderError, SopsAgeProvider, check_sops_age_availability, inspect_sops_policy, validate_sops_age_recipients


class PreflightError(RuntimeError):
    pass


def check_directory_writable(path: Path) -> None:
    if not path.is_dir():
        raise PreflightError(f"missing directory: {path}")
    probe = path / ".workspace-preflight.tmp"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        raise PreflightError(f"directory is not writable: {path}: {error}") from error


def check_file_writable(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_file():
        raise PreflightError(f"path is not a regular file: {path}")
    try:
        with path.open("ab"):
            pass
    except OSError as error:
        raise PreflightError(f"file is not writable: {path}: {error}") from error


def check_glob_writable(root: Path, pattern: str) -> None:
    for path in root.glob(pattern):
        check_file_writable(path)


def check_no_unexpected_artifacts(repo: Path) -> None:
    """Reject crash/state artifacts outside the private values repository."""
    forbidden = (
        repo / "infra" / "opentofu" / "errored.tfstate",
        repo / "infra" / "opentofu" / "crash.log",
        repo / "infra" / "opentofu" / "crash.*.log",
    )
    for pattern in forbidden:
        matches = [pattern] if "*" not in pattern.name else list(pattern.parent.glob(pattern.name))
        for path in matches:
            if path.exists():
                raise PreflightError(
                    f"unexpected OpenTofu artifact outside values/: {path}. "
                    "Remove it before continuing."
                )


def check_no_state_lock(values: Path) -> None:
    lock_file = values / ".terraform.tfstate.lock.info"
    if lock_file.exists():
        raise PreflightError(
            f"OpenTofu state lock exists: {lock_file}. Another plan/apply may be running. "
            "Remove it only after confirming no OpenTofu process is active."
        )


def _write_projection(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.preflight")
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _sops_policy_inputs(repo: Path) -> tuple[Path, set[str] | None]:
    """Read private policy metadata inputs without exposing key material."""
    policy = Path(os.environ.get("INFRA_SOPS_POLICY_PATH", str(repo / ".sops.yaml"))).expanduser()
    raw_recipients = os.environ.get("INFRA_SOPS_AGE_RECIPIENTS", "")
    if not raw_recipients:
        return policy, None
    recipients = {item.strip() for item in raw_recipients.split(",") if item.strip()}
    if not recipients:
        raise SecretProviderError("SOPS recipient policy is invalid")
    return policy, recipients


def check_canonical_secret_availability(repo: Path) -> dict[str, str] | None:
    """Check canonical encrypted-bundle prerequisites without decryption."""
    context = from_environment(repo)
    if context.canonical_site_path is None:
        return None
    if context.site is None:
        raise PreflightError("canonical secret availability preflight failed")
    bundle = context.values_dir / "secrets.sops.yaml"
    if not bundle.is_file():
        return
    try:
        policy, expected_recipients = _sops_policy_inputs(repo)
        policy_metadata = (
            inspect_sops_policy(policy, site=context.site, expected_recipients=expected_recipients)
            if policy.is_file()
            else {"recipient_policy": "unavailable"}
        )
        availability = check_sops_age_availability(
            bundle,
            environment={"SOPS_AGE_KEY_FILE": "/run/secrets/sops-age-key"},
            expected_recipients=expected_recipients,
        )
        return {**policy_metadata, **availability}
    except SecretProviderError as error:
        raise PreflightError("canonical secret availability preflight failed") from error


def check_canonical_projection(repo: Path) -> None:
    """Validate canonical input and its non-secret projections without mutation."""
    context = from_environment(repo)
    site_file = context.canonical_site_path
    if site_file is None:
        return
    catalog_path = repo / "infra" / "services.json"
    model = load_site(site_file, expected_site=context.site, catalog_path=catalog_path)
    catalog = load_catalog(catalog_path)
    projections = {
        "terraform.auto.tfvars.json": render_opentofu_variables(model),
        "ansible-inventory.json": render_ansible_inventory(model, catalog),
        "ansible-vars.json": render_ansible_vars(model, catalog),
        "dns-records.json": render_dns_records(model),
    }
    with tempfile.TemporaryDirectory(prefix="canonical-preflight-") as temporary:
        output = Path(temporary)
        output.chmod(0o700)
        for name, value in projections.items():
            _write_projection(output / name, value)
        manifest = build_manifest(
            site=model.site.name,
            schema_version=model.schema_version,
            model_digest=model_digest(model),
            secret_digest=None,
            projections=projections,
            renderer_version="canonical-renderer/0.1",
            source_commit="preflight",
        )
        _write_projection(output / "manifest.json", manifest)
        verify_manifest(
            manifest,
            site=model.site.name,
            model_digest=model_digest(model),
            secret_digest=None,
            projections=projections,
        )


def check_canonical_required_secrets(repo: Path, *, require_secrets: bool) -> tuple[dict[str, object], ...] | None:
    """Derive value-free required secret metadata and optionally validate the provider bundle."""
    context = from_environment(repo)
    site_file = context.canonical_site_path
    if site_file is None:
        return None
    model = load_site(site_file, expected_site=context.site, catalog_path=repo / "infra" / "services.json")
    catalog = load_catalog(repo / "infra" / "services.json")
    report = catalog.required_secret_report_for_model(model.services)
    if not require_secrets:
        return report
    paths: set[str] = {str(entry["path"]) for entry in report}
    if not paths:
        return report
    bundle = context.values_dir / "secrets.sops.yaml"
    if not bundle.is_file():
        raise PreflightError("required canonical secrets bundle is missing")
    _, expected_recipients = _sops_policy_inputs(repo)
    if expected_recipients is not None:
        try:
            validate_sops_age_recipients(bundle, expected_recipients)
        except SecretProviderError as error:
            raise PreflightError("canonical secret recipient policy preflight failed") from error
    provider = SopsAgeProvider(
        bundle,
        environment={"SOPS_AGE_KEY_FILE": "/run/secrets/sops-age-key"},
        required_paths=paths,
    )
    provider.validate_required(paths)
    return report


def run(root: Path, require_values: bool, require_secrets: bool = False) -> None:
    repo = root.resolve()
    check_directory_writable(repo)
    check_directory_writable(repo / "infra" / "opentofu")
    check_no_unexpected_artifacts(repo)
    check_file_writable(repo / "infra" / "opentofu" / ".terraform.lock.hcl")
    check_glob_writable(repo, "tfplan*")
    check_glob_writable(repo, "*.tfplan*")

    values = from_environment(repo).values_dir
    if require_values or values.exists():
        check_directory_writable(values)
        check_glob_writable(values, "terraform.tfstate*")
        check_glob_writable(values, "tfplan*")
        check_glob_writable(values, "*.tfplan*")
        check_glob_writable(values, "*.tfstate*")
        check_file_writable(values / ".terraform.tfstate.lock.info")
        check_no_state_lock(values)
    try:
        check_canonical_secret_availability(repo)
        check_canonical_required_secrets(repo, require_secrets=require_secrets)
        check_canonical_projection(repo)
    except (OSError, ValueError) as error:
        raise PreflightError(f"canonical projection preflight failed: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--require-values", action="store_true")
    parser.add_argument("--require-secrets", action="store_true", help="validate conditional logical secrets against the SOPS bundle")
    args = parser.parse_args(argv)

    try:
        run(args.root, args.require_values, args.require_secrets)
    except PreflightError as error:
        print(f"workspace preflight failed: {error}", file=sys.stderr)
        print(
            "Run `just setup` to rebuild/repair the tooling container, then retry. "
            "If the problem remains, fix file ownership or permissions for the path above.",
            file=sys.stderr,
        )
        return 1

    print("workspace preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
