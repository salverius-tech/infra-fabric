"""Report-only static discovery of Ansible inventory consumers.

This module does not execute Ansible, decrypt secrets, write canonical values, or
change migration/candidate readiness. It records inventory identities and the
repository locations where supported consumers reference them.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class DiscoveryError(ValueError):
    """Raised when the report-only discovery boundary cannot be trusted."""


@dataclass(frozen=True)
class ConsumerReference:
    path: str
    line: int
    expression: str


@dataclass
class InventoryObservation:
    source: str
    key: str
    source_path: str
    value_type: str
    classification: str
    canonical_path: str | None
    secret: bool
    dynamic: bool
    consumers: list[ConsumerReference] = field(default_factory=list)
    disposition: str = "review-required"


@dataclass
class AnsibleDiscoveryReport:
    schema_version: int
    repo: str
    inventory: str
    source_files: list[str]
    observations: list[InventoryObservation]
    unsupported_constructs: list[dict[str, Any]]


def _load_migration_module() -> Any:
    path = Path(__file__).with_name("migrate-values.py")
    spec = importlib.util.spec_from_file_location("legacy_migration_helpers", path)
    if spec is None or spec.loader is None:
        raise DiscoveryError(f"cannot load legacy parser: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_legacy_discovery_module() -> Any:
    path = Path(__file__).with_name("legacy_values_discovery.py")
    spec = importlib.util.spec_from_file_location("legacy_values_discovery_helpers", path)
    if spec is None or spec.loader is None:
        raise DiscoveryError(f"cannot load legacy discovery helpers: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _inventory_keys(path: Path) -> tuple[list[tuple[str, str, str, bool]], list[dict[str, Any]]]:
    """Read inventory identities without retaining inventory values in the report."""
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - environment setup failure
        raise DiscoveryError("PyYAML is required for Ansible inventory discovery") from error

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DiscoveryError(f"cannot parse Ansible inventory {path}: {error}") from error
    if not isinstance(document, dict):
        raise DiscoveryError("Ansible inventory must contain a mapping")

    keys: list[tuple[str, str, str, bool]] = []
    unsupported: list[dict[str, Any]] = []

    def identity_for(path_parts: tuple[str, ...]) -> str:
        if "vars" in path_parts:
            path_parts = path_parts[path_parts.index("vars") + 1 :]
        return ".".join(path_parts)

    def is_dynamic(value: Any) -> bool:
        return isinstance(value, str) and any(token in value for token in ("{{", "lookup(", "{%"))

    def walk(value: Any, path_parts: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    unsupported.append({"path": ".".join(path_parts), "reason": "non-string key"})
                    continue
                child_path = (*path_parts, key)
                if isinstance(child, dict):
                    walk(child, child_path)
                elif isinstance(child, list):
                    keys.append((identity_for(child_path), ".".join(child_path), "list", is_dynamic(child)))
                else:
                    keys.append((identity_for(child_path), ".".join(child_path), type(child).__name__, is_dynamic(child)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, (*path_parts, str(index)))

    walk(document, ())
    return keys, unsupported


def _consumer_files(ansible_root: Path, inventory: Path) -> list[Path]:
    allowed = {".yml", ".yaml", ".j2", ".py", ".sh"}
    files: list[Path] = []
    for path in sorted(ansible_root.rglob("*")):
        if not path.is_file() or path == inventory or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() in allowed:
            files.append(path)
    return files


def _safe_expression(line: str) -> str:
    redacted = re.sub(
        r"(?i)(password|token|secret|private[_-]?key|auth[_-]?key|api[_-]?key)\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^,\s]+)",
        r"\1=<redacted>",
        line,
    )
    redacted = re.sub(r"(?i)lookup\([^)]*\)", "lookup(<redacted>)", redacted)
    return redacted[:240]


def _references(key: str, files: list[Path], repo: Path) -> list[ConsumerReference]:
    parts = key.split(".")
    candidates = [key]
    if len(parts) > 1:
        if key.startswith("all.hosts."):
            candidates.append(parts[-1])
        else:
            candidates.append(parts[0])
    tokens = [re.compile(rf"(?<![A-Za-z0-9_]){re.escape(candidate)}(?![A-Za-z0-9_])") for candidate in dict.fromkeys(candidates)]
    references: list[ConsumerReference] = []
    seen: set[tuple[str, int]] = set()
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(lines, 1):
            if any(token.search(line) for token in tokens):
                identity = (path.relative_to(repo).as_posix(), line_number)
                if identity in seen:
                    continue
                seen.add(identity)
                references.append(
                    ConsumerReference(
                        path=identity[0],
                        line=line_number,
                        expression=_safe_expression(line.strip()),
                    )
                )
    return references


def _secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in ("password", "token", "secret", "private_key", "auth_key", "api_key"))


def _classify(key: str, value_type: str, migration: Any, legacy_discovery: Any) -> tuple[str, str | None, bool, str]:
    classification_key = key.rsplit(".", 1)[-1]
    secret = _secret_key(key)
    classification, canonical_path = legacy_discovery._classification(classification_key, migration)
    if secret or classification == "secret":
        return "secret/provider", None, True, "secret contract required"
    if classification == "mapped":
        return "mapped", canonical_path, False, "canonical owner candidate"
    if classification_key.startswith(("ansible_", "caddy_")) or classification_key.endswith(("_enabled", "_restore_backup")) or "bootstrap" in classification_key:
        return "operational/review", None, False, "review-required: execution or lifecycle semantics require consumer review"
    return "review-required", None, False, "review-required: no approved canonical owner"


def discover_ansible(repo: Path, inventory: Path | None = None) -> AnsibleDiscoveryReport:
    repo = repo.resolve()
    ansible_root = repo / "infra" / "ansible"
    public_inventory = (repo / "scaffold" / "ansible" / "inventory" / "local.yml").resolve()
    inventory = (inventory or public_inventory).resolve()
    if not ansible_root.is_dir():
        raise DiscoveryError(f"Ansible root does not exist: {ansible_root}")
    if not inventory.is_file():
        raise DiscoveryError(f"Ansible inventory does not exist: {inventory}")
    if inventory != public_inventory:
        raise DiscoveryError("only the public scaffold Ansible inventory is supported")

    keys, unsupported = _inventory_keys(inventory)
    migration = _load_migration_module()
    legacy_discovery = _load_legacy_discovery_module()
    consumer_files = _consumer_files(ansible_root, inventory)
    observations: list[InventoryObservation] = []
    for key, source_path, value_type, source_dynamic in keys:
        classification, canonical_path, secret, disposition = _classify(
            key, value_type, migration, legacy_discovery
        )
        consumers = _references(key, consumer_files, repo)
        dynamic = source_dynamic or any("lookup(" in reference.expression or "{{" in reference.expression for reference in consumers)
        if not consumers:
            disposition = "review-required: no supported consumer reference"
        observations.append(
            InventoryObservation(
                source="ansible-inventory",
                key=key,
                source_path=source_path,
                value_type=value_type,
                classification=classification,
                canonical_path=canonical_path,
                secret=secret,
                dynamic=dynamic,
                consumers=consumers,
                disposition=disposition,
            )
        )

    source_files = [inventory.relative_to(repo).as_posix(), *[path.relative_to(repo).as_posix() for path in consumer_files]]
    return AnsibleDiscoveryReport(
        schema_version=1,
        repo=str(repo),
        inventory=inventory.relative_to(repo).as_posix(),
        source_files=source_files,
        observations=observations,
        unsupported_constructs=unsupported,
    )


def render_report(report: AnsibleDiscoveryReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "repo": report.repo,
        "inventory": report.inventory,
        "source_files": report.source_files,
        "observations": [
            {
                **asdict(observation),
                "consumers": [asdict(reference) for reference in observation.consumers],
            }
            for observation in report.observations
        ],
        "unsupported_constructs": report.unsupported_constructs,
        "summary": {
            "discovered": len(report.observations),
            "with_consumer_references": sum(bool(item.consumers) for item in report.observations),
            "mapped": sum(item.classification == "mapped" for item in report.observations),
            "secret_or_provider": sum(item.secret for item in report.observations),
            "review_required": sum(
                item.classification in {"review-required", "operational/review"}
                or item.disposition.startswith("review-required")
                for item in report.observations
            ),
            "candidate_generation_allowed": False,
            "consumer_cutover_allowed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report-only Ansible inventory consumer discovery")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        rendered = render_report(discover_ansible(args.repo, args.inventory))
        text = json.dumps(rendered, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
    except (DiscoveryError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
