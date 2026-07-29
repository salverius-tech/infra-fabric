#!/usr/bin/env python3
"""Report the Phase 0 source inventory used by the canonical-values mapping matrix.

This is deliberately an inventory check, not a claim that semantic mappings are
complete. It enumerates current OpenTofu variables and service-catalog entries,
assigns each variable to a bounded ownership family, and fails when a new
variable does not fit a reviewed family. The resulting JSON is public-safe.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


VARIABLE_RE = re.compile(r'^variable\s+"([^"]+)"', re.MULTILINE)
HCL_ASSIGNMENT_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=')
VALID_DISPOSITIONS = {"canonical", "derived", "ansible-only", "opentofu-only", "deprecated", "unsupported"}
MATRIX_HEADERS = (
    "Canonical path",
    "Type/condition",
    "Legacy source(s)",
    "Generated consumer field(s)",
    "Class",
    "Normalization/default",
    "Conflict behavior",
    "Secret class",
    "Destructive impact",
)
ENV_NAME_RE = re.compile(r'\b(?:TF_VAR_|INFRA_|VALUES_|PROXMOX_|ANSIBLE_|DNS_)[A-Z][A-Z0-9_]*\b')


class InventoryError(ValueError):
    """Raised when a source inventory cannot be classified safely."""


FAMILY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("selection", ("enabled_services", "service_runtime", "forgejo_runtime")),
    ("service_compatibility", ("service_storage",)),
    ("provider", ("proxmox_", "lxc_root_password", "lxc_ssh_public_keys")),
    ("platform_storage_image", ("rootfs_datastore_id", "template_datastore_id", "debian_template_", "guest_vm_", "forgejo_vm_", "lxc_template_download_timeout_seconds")),
    ("technitium_resource", ("technitium_container_",)),
    ("forgejo_resource_or_service", ("forgejo_container_", "forgejo_lan_ip", "forgejo_server_name", "forgejo_database", "forgejo_storage", "forgejo_startup_")),
    ("forgejo_runner_resource", ("forgejo_runner_",)),
    ("infisical_resource_or_service", ("infisical_",)),
    ("hermes_resource_or_service", ("hermes_",)),
    ("shared_onramp_resource", ("onramp_host_",)),
    ("tailscale_resource", ("tailscale_client_",)),
    ("searxng_service", ("searxng_",)),
)


def classify_variable(name: str) -> str:
    matches = [family for family, prefixes in FAMILY_PATTERNS if any(name == prefix or name.startswith(prefix) for prefix in prefixes)]
    if len(matches) != 1:
        raise InventoryError(f"unclassified or ambiguously classified OpenTofu variable: {name}")
    return matches[0]


def load_variables(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    names = VARIABLE_RE.findall(text)
    if not names:
        raise InventoryError(f"no OpenTofu variables found in {path}")
    return [{"name": name, "family": classify_variable(name)} for name in names]


def load_catalog(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    services = data.get("services")
    if not isinstance(services, dict) or not services:
        raise InventoryError(f"service catalog has no services: {path}")
    return {
        "default_services": data.get("default_services", []),
        "services": [
            {
                "name": name,
                "state_capable": bool(entry.get("state_capable")),
                "dependencies": list(entry.get("dependencies", [])),
                "playbooks": list(entry.get("playbooks", [])),
                "terraform_addresses": list(entry.get("terraform_addresses", [])),
                "inventory_fields": sorted(entry.get("inventory", {}).keys()),
            }
            for name, entry in sorted(services.items())
        ],
    }



def _matrix_token_matches(text: str, token: str) -> bool:
    """Match a complete source token, not a substring of a dotted/keyed value."""
    if not token:
        return False
    pattern = rf"(?<![A-Za-z0-9_.-]){re.escape(token)}(?![A-Za-z0-9_.-])"
    return re.search(pattern, text) is not None


def reconcile_matrix_inputs(source_inputs: dict[str, Any], matrix: dict[str, Any]) -> dict[str, Any]:
    rows = matrix["rows"]
    matched: list[dict[str, str]] = []
    unmatched: list[dict[str, str]] = []
    ambiguous: list[dict[str, Any]] = []
    for item in source_inputs["inputs"]:
        source_name = Path(item["source"]).name
        key = item["key"]
        if item["source"].endswith("dns-records.local.json") and key in {"settings", "zones", "a_records", "cname_records"}:
            unmatched.append({"source": item["source"], "key": key})
            continue
        candidates = [
            candidate
            for candidate in rows
            if _matrix_token_matches(candidate["Legacy source(s)"], key)
            or _matrix_token_matches(candidate["Legacy source(s)"], item["source"])
            or _matrix_token_matches(candidate["Legacy source(s)"], source_name)
        ]
        record = {"source": item["source"], "key": key}
        if not candidates:
            unmatched.append(record)
        elif len(candidates) > 1:
            ambiguous.append({**record, "canonical_paths": sorted(candidate["Canonical path"] for candidate in candidates)})
            unmatched.append(record)
        else:
            matched.append({**record, "canonical_path": candidates[0]["Canonical path"]})
    return {
        "input_count": len(source_inputs["inputs"]),
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "ambiguous_count": len(ambiguous),
        "matched": matched,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "status": "review-required" if unmatched or ambiguous else "complete",
    }


def classify_ambiguous_legacy_aliases(source_inputs: dict[str, Any]) -> dict[str, Any]:
    secret_keys = {"container_root_password", "container_ssh_public_keys"}
    aliases = [
        {"source": item["source"], "key": item["key"], "classification": "ambiguous", "scope": "resource-scoped", "canonical_owner": "review-required", "reason": "generic migration alias lacks explicit resource scope"}
        for item in source_inputs["inputs"]
        if item["source"].endswith("scripts/migrate-values.py") and item["key"].startswith("container_") and item["key"] not in secret_keys
    ]
    provider_secrets = [
        {"source": item["source"], "key": item["key"], "classification": "secret-provider-input", "scope": "provider-scoped", "canonical_owner": "review-required", "reason": "provider secret alias requires explicit delivery contract"}
        for item in source_inputs["inputs"]
        if item["source"].endswith("scripts/migrate-values.py") and item["key"] in secret_keys
    ]
    return {"ambiguous_resource_aliases": aliases, "provider_secret_aliases": provider_secrets, "status": "review-required" if aliases or provider_secrets else "complete"}


def load_consumer_contract(repo: Path) -> dict[str, Any]:
    paths = [repo / "scripts/plan-infra.sh", repo / "scripts/apply-infra.sh"]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    return {
        "paths": [str(path.relative_to(repo)) for path in paths],
        "legacy_terraform_input_present": "terraform.tfvars" in text,
        "legacy_static_inventory_present": "ansible/inventory/local.yml" in text,
        "canonical_projection_authoritative": False,
        "cutover_status": "deferred",
    }


def load_mapping_matrix(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header_index = next((index for index, line in enumerate(lines) if line.startswith("| Canonical path |")), None)
    if header_index is None:
        raise InventoryError(f"mapping matrix header missing: {path}")
    header = [cell.strip() for cell in lines[header_index].strip().strip("|").split("|")]
    if tuple(header) != MATRIX_HEADERS:
        raise InventoryError(f"mapping matrix headers changed: {path}")
    rows: list[dict[str, str]] = []
    invalid_rows: list[int] = []
    started = False
    for line_number, line in enumerate(lines[header_index + 2:], header_index + 3):
        if not line.startswith("|"):
            if started:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(set(cell) <= {"-", " "} for cell in cells):
            continue
        started = True
        if len(cells) != len(MATRIX_HEADERS):
            invalid_rows.append(line_number)
            continue
        row: dict[str, str] = {str(key): value for key, value in zip(MATRIX_HEADERS, cells)}
        row["Canonical path"] = row["Canonical path"].strip("`")
        if any(not value for value in row.values()):
            invalid_rows.append(line_number)
        rows.append(row)
    if invalid_rows:
        raise InventoryError(f"mapping matrix has incomplete rows at lines: {invalid_rows}")
    return {
        "path": str(path.relative_to(path.parents[2])),
        "headers": list(MATRIX_HEADERS),
        "row_count": len(rows),
        "rows": rows,
        "status": "semantic-coverage-incomplete",
    }


def _catalog_contract(catalog_path: Path) -> list[dict[str, Any]]:
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    return [
        {
            "name": name,
            "state_order": entry.get("state_order"),
            "terraform_replace_addresses": entry.get("terraform_replace_addresses", {}),
            "inventory": entry.get("inventory", {}),
        }
        for name, entry in sorted(data["services"].items())
    ]


def _source_path(repo: Path, relative: str) -> Path:
    path = repo / relative
    if not path.exists():
        raise InventoryError(f"required Phase 0 source is missing: {relative}")
    return path


def _assignment_keys(path: Path) -> list[str]:
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HCL_ASSIGNMENT_RE.match(line)
        if match and match.group(1) not in keys:
            keys.append(match.group(1))
    return keys


def _json_shape(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InventoryError(f"invalid JSON Phase 0 source: {path}") from error
    if not isinstance(data, dict):
        raise InventoryError(f"Phase 0 JSON source must contain an object: {path}")
    return {
        "top_level_keys": sorted(str(key) for key in data),
        "nested_keys": {
            str(key): sorted(str(item) for item in value) if isinstance(value, dict) else []
            for key, value in data.items()
        },
    }


def _env_references(paths: list[Path]) -> list[str]:
    found: set[str] = set()
    for path in paths:
        found.update(ENV_NAME_RE.findall(path.read_text(encoding="utf-8")))
    return sorted(found)


def _python_string_constants(path: Path, assignments: set[str]) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if not names & assignments:
            continue
        values.update(
            item.value
            for item in ast.walk(node.value)
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        )
    return sorted(values)


def _yaml_var_keys(path: Path) -> list[str]:
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^ {4}([A-Za-z_][A-Za-z0-9_]*)\s*:", line)
        if match and match.group(1) not in keys:
            keys.append(match.group(1))
    return keys


def _input_records(source: str, keys: list[str], disposition: str, review_reason: str) -> list[dict[str, str]]:
    if disposition not in VALID_DISPOSITIONS:
        raise InventoryError(f"invalid source-input disposition: {disposition}")
    return [
        {
            "source": source,
            "key": key,
            "disposition": disposition,
            "review_reason": review_reason,
            "canonical_owner": "review-required",
        }
        for key in keys
    ]


def load_source_input_inventory(repo: Path) -> dict[str, Any]:
    migration = repo / "scripts/migrate-values.py"
    migration_site = repo / "scripts/migrate-site-values.py"
    parser = repo / "scripts/parse-env.py"
    tfvars_keys = _assignment_keys(repo / "scaffold/terraform.tfvars")
    dns_keys = _json_shape(repo / "scaffold/dns-records.local.json")["top_level_keys"]
    ansible_keys = _yaml_var_keys(repo / "scaffold/ansible/inventory/local.yml")
    migration_keys = _python_string_constants(
        migration,
        {"SECRET_KEYS", "GENERATED_SECRET_KEYS", "ENV_TO_INVENTORY", "HISTORICAL_ENV_KEYS", "TF_VAR_RENAMES", "TECHNITIUM_TFVARS_RENAMES", "MIGRATION_ENV_KEYS"},
    )
    dotenv_keys = _python_string_constants(
        parser,
        {"PROXMOX_KEYS", "CADDY_KEYS", "TERRAFORM_KEYS", "TECHNITIUM_DNS_KEYS", "TECHNITIUM_BOOTSTRAP_KEYS", "FORGEJO_KEYS", "TAILSCALE_KEYS", "INFISICAL_KEYS", "HERMES_KEYS", "SEARXNG_KEYS", "EDGEROUTER_KEYS", "ALLOWED_KEYS"},
    )
    layout_keys = _python_string_constants(migration_site, {"MIGRATED_FILES"}) + ["terraform.tfstate*", "service-backups", "settings.local.json"]
    records = [
        *_input_records("scaffold/terraform.tfvars", tfvars_keys, "unsupported", "scaffold legacy input awaits canonical row"),
        *_input_records("scaffold/dns-records.local.json", dns_keys, "unsupported", "DNS ownership and record semantics await matrix row"),
        *_input_records("scaffold/ansible/inventory/local.yml", ansible_keys, "ansible-only", "static inventory remains a compatibility consumer"),
        *_input_records("scripts/migrate-values.py", migration_keys, "deprecated", "legacy migration alias or key awaits matrix reconciliation"),
        *_input_records("scripts/parse-env.py", dotenv_keys, "deprecated", "dotenv compatibility key awaits matrix reconciliation"),
        *_input_records("scripts/migrate-site-values.py", layout_keys, "unsupported", "site-layout artifact requires explicit migration/state policy"),
    ]
    return {
        "input_count": len(records),
        "inputs": records,
        "disposition_counts": {
            disposition: sum(item["disposition"] == disposition for item in records)
            for disposition in sorted({item["disposition"] for item in records})
        },
        "unique_identities": len({(item["source"], item["key"]) for item in records}),
        "status": "classification-complete-with-review-dispositions",
    }


def load_source_inventory(repo: Path, variables: list[dict[str, str]], catalog: dict[str, Any]) -> dict[str, Any]:
    """Inventory every Phase 0 source surface without claiming semantic coverage."""
    named_sources = [
        "infra/opentofu/variables.tf",
        "infra/services.json",
        "infra/ansible/inventory/tfvars.py",
        "scripts/migrate-values.py",
        "scripts/migrate-site-values.py",
        "scaffold/terraform.tfvars",
        "scaffold/dns-records.local.json",
        "scaffold/ansible/inventory/local.yml",
        "scaffold/sites/dev/site.yaml",
        "scaffold/sites/dev/site.json",
        "scripts/parse-env.py",
        "scripts/envfile.py",
        "scripts/run-infra.sh",
        "scripts/plan-infra.sh",
        "scripts/apply-infra.sh",
        "scripts/validate-values.sh",
    ]
    paths = [_source_path(repo, relative) for relative in named_sources]
    scaffold_tfvars = _assignment_keys(repo / "scaffold/terraform.tfvars")
    dns_shape = _json_shape(repo / "scaffold/dns-records.local.json")
    env_refs = _env_references([repo / relative for relative in named_sources if relative.endswith((".py", ".sh"))])
    return {
        "source_count": len(paths),
        "sources": [
            {
                "path": relative,
                "exists": True,
                "input_kind": {
                    "infra/opentofu/variables.tf": "opentofu_root_variables",
                    "infra/services.json": "service_catalog",
                    "infra/ansible/inventory/tfvars.py": "ansible_dynamic_inventory",
                    "scripts/migrate-values.py": "legacy_mutating_migration",
                    "scripts/migrate-site-values.py": "site_layout_migration",
                    "scaffold/terraform.tfvars": "scaffold_tfvars",
                    "scaffold/dns-records.local.json": "scaffold_dns_json",
                }.get(relative, "workflow_or_parser_contract"),
            }
            for relative in named_sources
        ],
        "scaffold": {
            "terraform_assignment_count": len(scaffold_tfvars),
            "terraform_assignments": scaffold_tfvars,
            "dns": dns_shape,
        },
        "ansible": {
            "catalog_service_count": len(catalog["services"]),
            "inventory_fields": sorted({field for service in catalog["services"] for field in service["inventory_fields"]}),
            "environment_references": env_refs,
        },
        "coverage": {
            "source_files_present": True,
            "opentofu_variables_inventoried": len(variables),
            "semantic_mapping_status": "incomplete-until-each-source-input-has-a-matrix-disposition",
        },
    }


def classify_deferred_input(item: dict[str, str]) -> tuple[str, str]:
    """Assign every unmatched source identity to an explicit safe disposition."""
    source = item["source"]
    key = item["key"]
    if source.endswith("scripts/migrate-site-values.py"):
        return "migration-only-or-unsupported", "site-layout artifact requires an explicit migration/state policy"
    if source.endswith("scaffold/dns-records.local.json"):
        return "ambiguous-or-destructive", "DNS document shape has no general canonical resolver/zone/record owner"
    if source.endswith("scripts/migrate-values.py") and key.startswith("container_"):
        return "ambiguous-or-destructive", "generic migration alias does not identify one resource"
    if key in {"debian_template_url", "debian_template_file_name", "debian_template_checksum_algorithm", "debian_template_checksum"}:
        return "ambiguous-or-destructive", "public scaffold transport conflicts with the canonical HTTPS image contract"
    if re.search(
        r"(?:^|_)(?:password|pass|secret|token|private[_-]?key|api[_-]?key|ssh_public_keys|auth_key|encryption_key)(?:_|$)",
        key,
        re.IGNORECASE,
    ):
        return "secret-or-protected", "protected material or delivery metadata requires an approved secret consumer contract"
    if key in {"PROXMOX_VE_ENDPOINT", "PROXMOX_VE_USERNAME", "PVE_HOST", "EDGEROUTER_ADDR", "EDGEROUTER_USER", "CF_API_EMAIL"}:
        return "secret-or-protected", "provider or external-system input has no canonical delivery boundary"
    return "behavior-without-typed-owner", "legacy behavior/configuration lacks an exact typed canonical owner and projection"


def deferred_classification(matrix_coverage: dict[str, Any]) -> dict[str, Any]:
    """Classify unmatched identities without reading or retaining their values."""
    items: list[dict[str, str]] = []
    for unmatched in matrix_coverage["unmatched"]:
        classification, reason = classify_deferred_input(unmatched)
        items.append({**unmatched, "classification": classification, "reason": reason})
    counts = {
        classification: sum(item["classification"] == classification for item in items)
        for classification in sorted({item["classification"] for item in items})
    }
    unclassified_count = sum("classification" not in item for item in items)
    return {
        "item_count": len(items),
        "classified_count": len(items) - unclassified_count,
        "unclassified_count": unclassified_count,
        "counts": counts,
        "items": items,
        "status": "complete" if not sum("classification" not in item for item in items) else "review-required",
    }


def candidate_generation_readiness(matrix_coverage: dict[str, Any], alias_classification: dict[str, Any] | None = None) -> dict[str, Any]:
    reasons: list[str] = []
    if matrix_coverage["unmatched_count"]:
        reasons.append("matrix coverage is incomplete")
    if matrix_coverage["ambiguous_count"]:
        reasons.append("matrix contains ambiguous source matches")
    if alias_classification and alias_classification["ambiguous_resource_aliases"]:
        reasons.append("generic migration aliases lack explicit resource scope")
    if alias_classification and alias_classification["provider_secret_aliases"]:
        reasons.append("provider secret aliases lack an approved delivery contract")
    return {
        "status": "blocked" if reasons else "ready",
        "candidate_generation_allowed": not reasons,
        "reasons": reasons,
    }


def build_report(repo: Path) -> dict[str, Any]:
    variables = load_variables(repo / "infra/opentofu/variables.tf")
    catalog = load_catalog(repo / "infra/services.json")
    source_inventory = load_source_inventory(repo, variables, catalog)
    source_inputs = load_source_input_inventory(repo)
    matrix = load_mapping_matrix(repo / "docs/canonical-values-mapping-v1.md")
    matrix_coverage = reconcile_matrix_inputs(source_inputs, matrix)
    deferred = deferred_classification(matrix_coverage)
    alias_classification = classify_ambiguous_legacy_aliases(source_inputs)
    candidate_readiness = candidate_generation_readiness(matrix_coverage, alias_classification)
    catalog_contract = _catalog_contract(repo / "infra/services.json")
    consumer_contract = load_consumer_contract(repo)
    return {
        "schema": 1,
        "purpose": "phase-0-source-inventory",
        "repository": "infra-fabric",
        "sources": [item["path"] for item in source_inventory["sources"]],
        "opentofu": {
            "variable_count": len(variables),
            "variables": variables,
        },
        "service_catalog": catalog,
        "service_contracts": catalog_contract,
        "mapping_matrix": matrix,
        "matrix_coverage": matrix_coverage,
        "deferred_classification": deferred,
        "legacy_alias_classification": alias_classification,
        "candidate_generation": candidate_readiness,
        "consumer_contract": consumer_contract,
        "source_inventory": source_inventory,
        "source_inputs": source_inputs,
        "classification": {
            "unclassified_variables": [],
            "inventory_status": "complete" if source_inputs["unique_identities"] == source_inputs["input_count"] else "incomplete",
            "classification_status": source_inputs["status"],
            "semantic_mapping_status": "incomplete",
            "consumer_cutover_status": consumer_contract["cutover_status"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_report(args.repo.resolve())
        encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
    except (OSError, InventoryError, json.JSONDecodeError) as error:
        print(f"canonical mapping inventory failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
