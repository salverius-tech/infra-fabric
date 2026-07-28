#!/usr/bin/env python3
"""Compatibility view of the logical service capability registry."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


class ServiceCatalogError(ValueError):
    """Raised when a service catalog or selected service set is invalid."""


_LOGICAL_PART_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")


@dataclass(frozen=True)
class ServiceCapability:
    name: str
    state_capable: bool
    dependencies: tuple[str, ...]
    required_secrets: tuple[str, ...]
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
        return frozenset(
            path
            for name in sorted(enabled)
            for path in self.get(name).required_secrets
        )

    def required_secret_paths_for_model(self, services: dict[str, object]) -> frozenset[str]:
        """Derive required logical secrets from canonical service enablement."""
        self.validate_model_services(services)
        enabled = {name for name, service in services.items() if getattr(service, "enabled", False)}
        return self.required_secret_paths(enabled)

    def validate_model_services(self, services: dict[str, object]) -> None:
        """Validate the complete canonical service map against catalog ownership."""
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
        inventory = raw.get("inventory", {})
        if not isinstance(inventory, dict):
            raise ServiceCatalogError(f"service {name} inventory metadata must be an object")
        capabilities[name] = ServiceCapability(
            name=name,
            state_capable=raw.get("state_capable") is True,
            dependencies=tuple(dependencies),
            required_secrets=tuple(required_secrets),
            inventory=inventory,
            raw=raw,
        )
    catalog = ServiceCatalog(capabilities)
    catalog._validate_acyclic()
    return catalog


__all__ = ["ServiceCapability", "ServiceCatalog", "ServiceCatalogError", "load_catalog"]
