#!/usr/bin/env python3
"""Generate a public-safe canonical service authoring manifest.

This tool is deliberately generate-only. It never edits the repository, creates
site values, decrypts or creates secrets, renders projections, plans, or applies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SERVICE_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
ARCHETYPES = {"dedicated-lxc", "dedicated-vm", "shared-host", "no-runtime"}
SECRET_CLASSES = {"bootstrap", "credential", "generated", "key", "password", "provider", "recovery", "runtime", "token", "certificate"}


def _required(value: str | None, label: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _secret_metadata(entries: list[str]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for entry in entries:
        parts = entry.split(":", 2)
        if len(parts) != 3:
            raise ValueError("secret metadata must be logical_path:class:environment")
        logical_path, classification, environment = (part.strip() for part in parts)
        if not logical_path.startswith("services.") or ".secrets." not in logical_path:
            raise ValueError("secret metadata logical path must use services.<service>.secrets.<key>")
        if classification not in SECRET_CLASSES:
            raise ValueError(f"unsupported secret metadata class: {classification}")
        _required(environment, "secret metadata environment")
        result.append(
            {
                "logical_path": logical_path,
                "classification": classification,
                "environment": environment,
            }
        )
    return sorted(result, key=lambda item: item["logical_path"])


def build_manifest(
    service_id: str,
    archetype: str,
    *,
    config_model: str | None = None,
    projection_contract: str | None = None,
    provisioning_contract: str | None = None,
    stateful: bool = False,
    state_contract: str | None = None,
    secret_metadata: list[str] | None = None,
) -> dict[str, Any]:
    service_id = _required(service_id, "service ID")
    if not SERVICE_ID.fullmatch(service_id):
        raise ValueError("service ID must match ^[a-z][a-z0-9_]{1,63}$")
    if archetype not in ARCHETYPES:
        raise ValueError(f"archetype must be one of: {', '.join(sorted(ARCHETYPES))}")

    config_model = _required(config_model, "configuration model")
    projection_contract = _required(projection_contract, "projection contract")
    if archetype in {"dedicated-lxc", "dedicated-vm", "shared-host"}:
        provisioning_contract = _required(provisioning_contract, "provisioning contract")
    if stateful:
        state_contract = _required(state_contract, "state contract")

    secrets = _secret_metadata(secret_metadata or [])
    return {
        "schema_version": 1,
        "service_id": service_id,
        "archetype": archetype,
        "contracts": {
            "configuration_model": config_model,
            "projection": projection_contract,
            "provisioning": provisioning_contract,
            "state": state_contract if stateful else None,
        },
        "stateful": stateful,
        "secrets": secrets,
        "required_work": [
            "catalog registration in infra/services.json",
            "canonical configuration model or explicit exemption",
            "canonical projection mappings",
            "OpenTofu resource/module contract" if provisioning_contract else "no OpenTofu resource ownership",
            "Ansible playbook and role contract" if provisioning_contract else "runtime integration contract",
            "secret delivery tests" if secrets else "secret-free service review",
            "state backup and restore contract" if stateful else "stateless lifecycle contract",
            "public-safe scaffold fixtures",
            "service-specific tests and operator documentation",
        ],
        "safety": {
            "repository_writes": False,
            "creates_secrets": False,
            "creates_site_values": False,
            "renders_projections": False,
            "runs_plan_or_apply": False,
        },
    }


def validate_repository_surfaces(
    repo: Path,
    service_id: str,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    """Return missing/invalid implementation surfaces for an existing service."""
    repo = repo.resolve()
    errors: list[str] = []
    catalog_entry: dict[str, Any] | None = None
    catalog = repo / "infra" / "services.json"
    if not catalog.is_file():
        errors.append("catalog registration: infra/services.json is missing")
    else:
        try:
            payload = json.loads(catalog.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"catalog registration: cannot parse infra/services.json ({exc})")
        else:
            services = payload.get("services", payload) if isinstance(payload, dict) else {}
            registered = service_id in services if isinstance(services, dict) else any(
                isinstance(item, dict) and item.get("id", item.get("name")) == service_id
                for item in services
            )
            if not registered:
                errors.append(f"catalog registration: service {service_id!r} is absent")
            elif isinstance(services, dict):
                entry = services[service_id]
                required_metadata = {
                    "configuration_schema",
                    "release_sources",
                    "allowed_override_namespaces",
                    "required_fields",
                    "runtime_owner",
                }
                if not isinstance(entry, dict):
                    errors.append(f"catalog metadata: service {service_id!r} must be an object")
                else:
                    catalog_entry = entry
                    missing_metadata = sorted(required_metadata - entry.keys())
                    if missing_metadata:
                        errors.append(
                            f"catalog metadata: service {service_id!r} is missing {', '.join(missing_metadata)}"
                        )
                    if not isinstance(entry.get("required_fields"), list) or not entry.get("required_fields"):
                        errors.append(f"catalog metadata: service {service_id!r} must declare required_fields")

    if catalog_entry is not None:
        for declared_playbook in catalog_entry.get("playbooks", []):
            playbook = repo / str(declared_playbook)
            if not playbook.is_file() or repo not in playbook.resolve().parents:
                errors.append(f"declared playbook: {declared_playbook} is missing")
        terraform_files = list((repo / "infra" / "opentofu").rglob("*.tf"))
        terraform_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in terraform_files)
        for address in catalog_entry.get("terraform_addresses", []):
            address_text = str(address)
            address_stem = address_text.removesuffix("[")
            module_name = address_stem.removeprefix("module.") if address_stem.startswith("module.") else ""
            module_declaration = f'module "{module_name}"' if module_name else ""
            if (
                address_text not in terraform_text
                and address_stem not in terraform_text
                and module_declaration not in terraform_text
            ):
                errors.append(f"Terraform address: {address} is not represented")
        fixture_directory = repo / "scaffold" / "fixtures"
        fixture_matches = [
            path for path in fixture_directory.rglob("*")
            if path.is_file() and service_id in path.read_text(encoding="utf-8", errors="ignore")
        ] if fixture_directory.is_dir() else []
        if not fixture_matches:
            errors.append(f"scaffold fixture: no fixture mentions {service_id!r}")
        if catalog_entry.get("state_capable") is True:
            state_policy = repo / "infra" / "ansible" / "vars" / "service-state.yml"
            if not state_policy.is_file() or service_id not in state_policy.read_text(encoding="utf-8", errors="ignore"):
                errors.append(f"state policy: {service_id!r} is not registered")
        required_secrets = catalog_entry.get("required_secrets", [])
        if manifest is not None and required_secrets:
            manifest_secrets = {
                str(secret.get("logical_path"))
                for secret in manifest.get("secrets", [])
                if isinstance(secret, dict)
            }
            missing_secrets = sorted(set(required_secrets) - manifest_secrets)
            if missing_secrets:
                errors.append(
                    f"secret contract: manifest is missing {', '.join(missing_secrets)}"
                )
            classifications = catalog_entry.get("secret_classifications", {})
            environments = catalog_entry.get("secret_environment", {})
            for logical_path in required_secrets:
                if logical_path not in classifications or logical_path not in environments:
                    errors.append(f"secret contract: catalog metadata is incomplete for {logical_path}")

    requires_independent_runtime = catalog_entry is None or catalog_entry.get("runtime_owner") != "none"
    required_files = (
        ("canonical configuration model", repo / "scripts" / "canonical_values.py"),
        ("canonical projection mapping", repo / "scripts" / "canonical_projections.py"),
    ) if requires_independent_runtime else ()
    configuration_schema = str(catalog_entry.get("configuration_schema", "")) if catalog_entry else ""
    canonical_model = repo / "scripts" / "canonical_values.py"
    if configuration_schema and (
        not canonical_model.is_file()
        or configuration_schema not in canonical_model.read_text(encoding="utf-8", errors="ignore")
    ):
        errors.append(f"configuration schema: {configuration_schema!r} is not represented")
    for label, path in required_files:
        if not path.is_file() or service_id not in path.read_text(encoding="utf-8"):
            errors.append(f"{label}: {service_id!r} is not represented")

    searched_surfaces = (
        (("OpenTofu resource/module", repo / "infra" / "opentofu"),) if requires_independent_runtime else ()
    ) + (
        ("Ansible playbook/role", repo / "infra" / "ansible"),
        ("service tests", repo / "tests"),
        ("operator documentation", repo / "docs"),
    )
    for label, directory in searched_surfaces:
        matches = [
            path for path in directory.rglob("*")
            if path.is_file() and path.suffix in {".py", ".tf", ".yml", ".yaml", ".md", ".json"}
            and service_id in path.read_text(encoding="utf-8", errors="ignore")
        ] if directory.is_dir() else []
        if not matches:
            errors.append(f"{label}: no repository surface mentions {service_id!r}")
    return errors


def validate_catalog_repository(repo: Path) -> dict[str, list[str]]:
    """Validate every service registered in the public catalog."""
    repo = repo.resolve()
    catalog = repo / "infra" / "services.json"
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    services = payload.get("services", payload) if isinstance(payload, dict) else {}
    if not isinstance(services, dict):
        raise ValueError("infra/services.json services must be an object")
    failures: dict[str, list[str]] = {}
    service_ids = set(services)
    for service_id in sorted(services):
        entry = services[service_id]
        errors = _validate_catalog_entry(service_id, entry, service_ids)
        errors.extend(validate_repository_surfaces(repo, service_id))
        if errors:
            failures[service_id] = errors
    return failures


def _validate_catalog_entry(service_id: str, entry: Any, service_ids: set[str]) -> list[str]:
    if not isinstance(entry, dict):
        return ["catalog entry must be an object"]
    errors: list[str] = []
    owner = entry.get("runtime_owner")
    independent_runtime = owner not in {"none", "shared_host"}
    if not isinstance(entry.get("configuration_schema"), str) or not entry["configuration_schema"]:
        errors.append("catalog metadata: configuration_schema is required")
    for field in ("required_fields", "allowed_override_namespaces", "dependencies"):
        if not isinstance(entry.get(field), list):
            errors.append(f"catalog metadata: {field} must be a list")
    release_sources = entry.get("release_sources")
    if independent_runtime and (not isinstance(release_sources, list) or not release_sources):
        errors.append("catalog metadata: release_sources is required for runtime services")
    terraform_addresses = entry.get("terraform_addresses")
    if independent_runtime and (not isinstance(terraform_addresses, list) or not terraform_addresses):
        errors.append("catalog metadata: terraform_addresses is required for runtime services")
    replacements = entry.get("terraform_replace_addresses")
    if independent_runtime and (not isinstance(replacements, dict) or not replacements.get("lxc") or not replacements.get("vm")):
        errors.append("catalog metadata: terraform_replace_addresses must define lxc and vm")
    inventory = entry.get("inventory")
    if independent_runtime:
        if not isinstance(inventory, dict):
            errors.append("catalog metadata: inventory is required for runtime services")
        else:
            for key in ("host", "group", "canonical_play_vars"):
                if not inventory.get(key):
                    errors.append(f"catalog metadata: inventory.{key} is required")
    dependencies = entry.get("dependencies", [])
    if isinstance(dependencies, list):
        for dependency in dependencies:
            if dependency not in service_ids:
                errors.append(f"catalog metadata: unknown dependency {dependency!r}")
    required_secrets = entry.get("required_secrets", [])
    classifications = entry.get("secret_classifications", {})
    environments = entry.get("secret_environment", {})
    if not isinstance(required_secrets, list) or not isinstance(classifications, dict) or not isinstance(environments, dict):
        errors.append("catalog metadata: secret contract fields have invalid types")
    else:
        for logical_path in required_secrets:
            if classifications.get(logical_path) not in SECRET_CLASSES:
                errors.append(f"catalog metadata: unsupported secret classification for {logical_path}")
            if not isinstance(environments.get(logical_path), str) or not environments[logical_path]:
                errors.append(f"catalog metadata: missing secret environment for {logical_path}")
    if entry.get("state_capable") and not isinstance(entry.get("state_order"), int):
        errors.append("catalog metadata: state_order is required for stateful services")
    return errors


def build_catalog_report(repo: Path) -> dict[str, Any]:
    """Build a deterministic, public-safe report for all catalog services."""
    repo = repo.resolve()
    catalog = repo / "infra" / "services.json"
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    services = payload.get("services", payload) if isinstance(payload, dict) else {}
    if not isinstance(services, dict):
        raise ValueError("infra/services.json services must be an object")
    failures = validate_catalog_repository(repo)
    service_reports = [
        {
            "service_id": service_id,
            "status": "fail" if service_id in failures else "pass",
            "errors": failures.get(service_id, []),
        }
        for service_id in sorted(services)
    ]
    failed = sum(report["status"] == "fail" for report in service_reports)
    return {
        "schema_version": 1,
        "report": "public-service-contracts",
        "services": service_reports,
        "summary": {
            "total": len(service_reports),
            "passed": len(service_reports) - failed,
            "failed": failed,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-id", required=True)
    parser.add_argument("--archetype", required=True, choices=sorted(ARCHETYPES))
    parser.add_argument("--config-model", required=True)
    parser.add_argument("--projection-contract", required=True)
    parser.add_argument("--provisioning-contract")
    parser.add_argument("--stateful", action="store_true")
    parser.add_argument("--state-contract")
    parser.add_argument("--secret", dest="secret_metadata", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-repository", type=Path, help="validate implementation surfaces without modifying them")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = build_manifest(
            args.service_id,
            args.archetype,
            config_model=args.config_model,
            projection_contract=args.projection_contract,
            provisioning_contract=args.provisioning_contract,
            stateful=args.stateful,
            state_contract=args.state_contract,
            secret_metadata=args.secret_metadata,
        )
    except ValueError as exc:
        print(f"service-author: {exc}", file=sys.stderr)
        return 2
    if args.check_repository:
        errors = validate_repository_surfaces(args.check_repository, args.service_id, manifest)
        if errors:
            for error in errors:
                print(f"service-author: {error}", file=sys.stderr)
            return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote public-safe authoring manifest: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
