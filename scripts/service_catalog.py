#!/usr/bin/env python3
"""Compatibility view of the logical service capability registry."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping


class ServiceCatalogError(ValueError):
    """Raised when a service catalog or selected service set is invalid."""


_LOGICAL_PART_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
SecretClassification = Literal["bootstrap", "runtime", "provider", "recovery", "generated"]
_SECRET_CLASSIFICATIONS = frozenset(("bootstrap", "runtime", "provider", "recovery", "generated"))


def _path_value(value: Any, path: str) -> Any:
    for part in path.split(".") if path else ():
        if isinstance(value, Mapping):
            value = value.get(part)
        else:
            value = getattr(value, part, None)
    return value


@dataclass(frozen=True)
class ServiceCapability:
    name: str
    state_capable: bool
    dependencies: tuple[str, ...]
    required_secrets: tuple[str, ...]
    secret_classifications: dict[str, SecretClassification]
    conditional_required_secrets: dict[str, tuple[str, ...]]
    inventory: dict[str, object]
    raw: dict[str, object]


class ServiceCatalog:
    def __init__(self, capabilities: dict[str, ServiceCapability]) -> None:
        self._capabilities = capabilities

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._capabilities)

    def get(self, name: str) -> ServiceCapability:
        try:
            return self._capabilities[name]
        except KeyError as error:
            raise ServiceCatalogError(f"unknown service catalog entry: {name}") from error

    def validate_selection(self, enabled: set[str]) -> None:
        unknown = sorted(enabled - self.names)
        if unknown:
            raise ServiceCatalogError(f"enabled services are not in catalog: {', '.join(unknown)}")
        for name in sorted(enabled):
            capability = self.get(name)
            missing = sorted(set(capability.dependencies) - enabled)
            if missing:
                raise ServiceCatalogError(
                    f"enabled service {name} requires disabled services: {', '.join(missing)}"
                )
        self._validate_acyclic()

    def required_secret_paths(self, enabled: set[str]) -> frozenset[str]:
        """Return catalog-declared logical secrets for an enabled service set."""
        self.validate_selection(enabled)
        conditional = {
            path
            for name in enabled
            for paths in self.get(name).conditional_required_secrets.values()
            for path in paths
        }
        return frozenset(
            path
            for name in sorted(enabled)
            for path in self.get(name).required_secrets
            if path not in conditional
        )

    def required_secret_paths_for_model(self, services: dict[str, object]) -> frozenset[str]:
        """Derive required logical secrets from canonical service enablement."""
        self.validate_model_services(services)
        enabled = {name for name, service in services.items() if getattr(service, "enabled", False)}
        paths = set(self.required_secret_paths(enabled))
        for name in sorted(enabled):
            service = services[name]
            configuration = getattr(service, "configuration", {})
            for condition, conditional_paths in self.get(name).conditional_required_secrets.items():
                if _path_value(configuration, condition.removeprefix("configuration.")) is True:
                    paths.update(conditional_paths)
        return frozenset(paths)

    def required_secret_report_for_model(self, services: Mapping[str, object]) -> tuple[dict[str, object], ...]:
        """Return value-free secret metadata including configuration conditions."""
        paths = self.required_secret_paths_for_model(dict(services))
        report: list[dict[str, object]] = []
        for path in sorted(paths):
            owner = next(
                (
                    capability
                    for capability in self._capabilities.values()
                    if path in capability.required_secrets
                    or any(path in values for values in capability.conditional_required_secrets.values())
                ),
                None,
            )
            entry: dict[str, object] = {"path": path, "required": True}
            if owner is not None:
                entry["service"] = owner.name
                classification = owner.secret_classifications.get(path)
                if classification is not None:
                    entry["classification"] = classification
            report.append(entry)
        return tuple(report)

    def required_secret_report(self, enabled: set[str]) -> tuple[dict[str, object], ...]:
        """Return a deterministic, value-free report of catalog requirements."""
        self.validate_selection(enabled)
        conditional_services = sorted(name for name in enabled if self.get(name).conditional_required_secrets)
        if conditional_services:
            raise ServiceCatalogError(
                "required_secret_report(enabled) cannot evaluate conditional secrets; use required_secret_report_for_model(): "
                + ", ".join(conditional_services)
            )
        report: list[dict[str, object]] = []
        for name in sorted(enabled):
            capability = self.get(name)
            for path in sorted(set(capability.required_secrets)):
                entry: dict[str, object] = {"service": name, "path": path, "required": True}
                classification = capability.secret_classifications.get(path)
                if classification is not None:
                    entry["classification"] = classification
                report.append(entry)
        return tuple(report)

    def validate_model_services(self, services: Mapping[str, object], resources: Any | None = None) -> None:
        """Validate canonical service ownership and catalog-derived resource compatibility."""
        unknown = sorted(set(services) - self.names)
        if unknown:
            raise ServiceCatalogError(f"canonical services are not in catalog: {', '.join(unknown)}")
        for name, service in services.items():
            declared = tuple(getattr(service, "dependencies", ()))
            expected = self.get(name).dependencies
            if declared and declared != expected:
                raise ServiceCatalogError(
                    f"service {name} declares dependencies {list(declared)!r}; catalog requires {list(expected)!r}"
                )
            state = getattr(service, "state", None)
            if state is not None and getattr(state, "capable", False) and not self.get(name).state_capable:
                raise ServiceCatalogError(f"service {name} declares state capability not present in catalog")
            if resources is not None and getattr(service, "enabled", False):
                resource_name = getattr(service, "resource", None)
                resource_map = {
                    **getattr(resources, "guests", {}),
                    **getattr(resources, "shared_hosts", {}),
                }
                resource = resource_map.get(resource_name)
                if resource is not None:
                    supported = set(self.get(name).raw.get("terraform_replace_addresses", {}))
                    if supported and getattr(resource, "type", None) not in supported:
                        raise ServiceCatalogError(
                            f"service {name} resource type {getattr(resource, 'type', None)!r} is not supported by catalog"
                        )

    def _validate_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise ServiceCatalogError(f"service dependency cycle includes {name}")
            if name in visited:
                return
            visiting.add(name)
            for dependency in self.get(name).dependencies:
                if dependency not in self.names:
                    raise ServiceCatalogError(f"service {name} depends on unknown service {dependency}")
                visit(dependency)
            visiting.remove(name)
            visited.add(name)

        for name in sorted(self.names):
            visit(name)


def load_catalog(path: Path) -> ServiceCatalog:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ServiceCatalogError(f"cannot load service catalog {path}") from error
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        raise ServiceCatalogError(f"service catalog must contain a services object: {path}")

    capabilities: dict[str, ServiceCapability] = {}
    for name, raw in data["services"].items():
        if not isinstance(name, str) or not isinstance(raw, dict):
            raise ServiceCatalogError(f"invalid service catalog entry: {name!r}")
        dependencies = raw.get("dependencies", [])
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            raise ServiceCatalogError(f"service {name} dependencies must be a list of strings")
        required_secrets = raw.get("required_secrets", [])
        if not isinstance(required_secrets, list) or not all(
            isinstance(item, str) and item and all(_LOGICAL_PART_RE.fullmatch(part) for part in item.split("."))
            for item in required_secrets
        ):
            raise ServiceCatalogError(f"service {name} required_secrets must be logical paths")
        secret_classifications = raw.get("secret_classifications", {})
        if not isinstance(secret_classifications, dict) or any(
            not isinstance(secret_path, str)
            or not isinstance(classification, str)
            or secret_path not in required_secrets
            or classification not in _SECRET_CLASSIFICATIONS
            for secret_path, classification in secret_classifications.items()
        ):
            raise ServiceCatalogError(
                f"service {name} secret_classifications must map required paths to supported classifications"
            )
        conditional_required_secrets = raw.get("conditional_required_secrets", {})
        if not isinstance(conditional_required_secrets, dict) or any(
            not isinstance(condition, str)
            or not condition
            or not all(_LOGICAL_PART_RE.fullmatch(part) for part in condition.split("."))
            or not isinstance(paths, list)
            or not all(
                isinstance(secret_path, str)
                and secret_path
                and all(_LOGICAL_PART_RE.fullmatch(part) for part in secret_path.split("."))
                for secret_path in paths
            )
            for condition, paths in conditional_required_secrets.items()
        ):
            raise ServiceCatalogError(f"service {name} conditional_required_secrets must map paths to logical secret lists")
        conditional_paths = {condition: tuple(paths) for condition, paths in conditional_required_secrets.items()}
        conditional_secret_paths = {secret_path for paths in conditional_paths.values() for secret_path in paths}
        undeclared = sorted(conditional_secret_paths - set(required_secrets) - set(secret_classifications))
        if undeclared:
            raise ServiceCatalogError(
                f"service {name} conditional secret paths must be declared: {', '.join(undeclared)}"
            )
        inventory = raw.get("inventory", {})
        if not isinstance(inventory, dict):
            raise ServiceCatalogError(f"service {name} inventory metadata must be an object")
        capabilities[name] = ServiceCapability(
            name=name,
            state_capable=raw.get("state_capable") is True,
            dependencies=tuple(dependencies),
            required_secrets=tuple(required_secrets),
            secret_classifications=dict(secret_classifications),
            conditional_required_secrets=conditional_paths,
            inventory=inventory,
            raw=raw,
        )
    catalog = ServiceCatalog(capabilities)
    catalog._validate_acyclic()
    return catalog


__all__ = ["SecretClassification", "ServiceCapability", "ServiceCatalog", "ServiceCatalogError", "load_catalog"]
