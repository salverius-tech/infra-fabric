#!/usr/bin/env python3
"""Fail-closed consumer delivery for canonical logical secrets.

This module deliberately keeps resolved values in memory. It does not write
secret projections, command-line arguments, logs, or persistent dotenv files.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from secret_provider import SecretProvider, SecretProviderError


class SecretDeliveryError(SecretProviderError):
    """Raised when a logical secret cannot be delivered to a consumer."""


@dataclass(frozen=True)
class SecretRequirement:
    path: str
    classification: str
    consumers: frozenset[str]
    environment_name: str | None = None
    service: str | None = None
    state_exposure: str = "forbidden"


@dataclass(frozen=True)
class DeliveredSecret:
    path: str
    consumer: str
    environment_name: str
    value: str


BOOTSTRAP_SSH_PRIVATE_KEY_PATH = "secrets.bootstrap.ssh_private_key"
PROXMOX_PROVIDER_PATH = "secrets.providers.proxmox.api_token"
_ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


# Environment names are explicit consumer bindings, never inferred from logical
# paths. Service bindings live beside the service's canonical requirement in the
# catalog; this module only turns that combined model into transient delivery.
DEFAULT_REQUIREMENTS: tuple[SecretRequirement, ...] = (
    SecretRequirement(
        "secrets.bootstrap.root_password",
        "bootstrap",
        frozenset({"ansible-bootstrap"}),
        "INFRA_BOOTSTRAP_ROOT_PASSWORD",
        state_exposure="forbidden",
    ),
)


OPERATOR_REQUIREMENTS: tuple[SecretRequirement, ...] = (
    SecretRequirement(
        "secrets.operator.password",
        "operator",
        frozenset({"ansible-host-identity"}),
        "INFRA_OPERATOR_PASSWORD",
        state_exposure="forbidden",
    ),
)


PROVIDER_REQUIREMENTS: tuple[SecretRequirement, ...] = (
    SecretRequirement(
        PROXMOX_PROVIDER_PATH,
        "provider",
        frozenset({"opentofu-provider"}),
        "PROXMOX_VE_API_TOKEN",
        state_exposure="forbidden",
    ),
)

ALL_REQUIREMENTS = DEFAULT_REQUIREMENTS + OPERATOR_REQUIREMENTS + PROVIDER_REQUIREMENTS


def operator_password_requirements() -> tuple[SecretRequirement, ...]:
    """Return the protected site-wide operator-password delivery contract."""
    return OPERATOR_REQUIREMENTS


def root_password_secret_path(
    resource_id: str,
    *,
    default_secret: str = "secrets.bootstrap.root_password",
    host_overrides: Mapping[str, str] | None = None,
) -> str:
    """Resolve a host root-password secret, preferring an explicit override."""
    overrides = host_overrides or {}
    return overrides.get(resource_id, default_secret)


def root_password_requirements(
    resource_ids: list[str] | tuple[str, ...],
    *,
    default_secret: str = "secrets.bootstrap.root_password",
    host_overrides: Mapping[str, str] | None = None,
    consumer: str = "ansible-bootstrap",
) -> tuple[SecretRequirement, ...]:
    """Build bootstrap delivery requirements for canonical resource IDs."""
    paths = {
        root_password_secret_path(resource_id, default_secret=default_secret, host_overrides=host_overrides)
        for resource_id in resource_ids
    }
    return tuple(
        SecretRequirement(path, "bootstrap", frozenset({consumer}), "INFRA_BOOTSTRAP_ROOT_PASSWORD")
        for path in sorted(paths)
    )


def requirements_for_model(
    catalog: object,
    services: Mapping[str, object],
    *,
    selected_services: list[str] | tuple[str, ...] | None = None,
) -> tuple[SecretRequirement, ...]:
    """Derive active service delivery requirements from the canonical model.

    The catalog evaluates feature conditions against the model. Its per-service
    bindings provide the only mapping from an approved logical path to a
    consumer environment name; no legacy path table is retained here.
    """
    enabled = {name for name, service in services.items() if getattr(service, "enabled", False)}
    selected = set(selected_services or enabled)
    if not selected <= enabled:
        raise SecretDeliveryError("requested service is not enabled in the canonical model")
    active_paths = catalog.required_secret_paths_for_model(dict(services))
    requirements: list[SecretRequirement] = []
    for service in sorted(selected):
        capability = catalog.get(service)
        for path in capability.required_secrets:
            if path not in active_paths:
                continue
            try:
                environment_name = capability.secret_environment[path]
            except KeyError as error:
                raise SecretDeliveryError("service secret has no catalog environment binding") from error
            requirements.append(
                SecretRequirement(
                    path,
                    capability.secret_classifications.get(path, "runtime"),
                    frozenset({f"ansible-service:{service}"}),
                    environment_name,
                    service,
                    "forbidden",
                )
            )
    return tuple(requirements)


def provider_requirements(provider: str = "proxmox") -> tuple[SecretRequirement, ...]:
    """Return the explicit canonical provider credential contract."""
    if provider != "proxmox":
        raise SecretDeliveryError("unsupported canonical provider")
    return PROVIDER_REQUIREMENTS


def requirement_index(
    requirements: tuple[SecretRequirement, ...] = DEFAULT_REQUIREMENTS,
) -> dict[str, SecretRequirement]:
    index: dict[str, SecretRequirement] = {}
    for requirement in requirements:
        if requirement.path in index:
            raise SecretDeliveryError("duplicate logical secret delivery requirement")
        if not requirement.path or not requirement.consumers or not requirement.environment_name:
            raise SecretDeliveryError("secret delivery requirement is incomplete")
        if not _ENVIRONMENT_NAME.fullmatch(requirement.environment_name):
            raise SecretDeliveryError("secret delivery environment name is invalid")
        index[requirement.path] = requirement
    return index


def deliver(
    provider: SecretProvider,
    *,
    path: str,
    consumer: str,
    requirements: tuple[SecretRequirement, ...] = DEFAULT_REQUIREMENTS,
) -> DeliveredSecret:
    """Resolve one permitted secret for one consumer, retaining it only in memory."""
    requirement = requirement_index(requirements).get(path)
    if requirement is None:
        raise SecretDeliveryError("secret path has no approved delivery contract")
    if consumer not in requirement.consumers:
        raise SecretDeliveryError("consumer is not permitted to receive this secret")
    try:
        value = provider.resolve(path)
    except SecretProviderError:
        raise
    except Exception as error:  # pragma: no cover - provider boundary defense
        raise SecretDeliveryError("secret provider resolution failed") from error
    if not isinstance(value, str) or not value:
        raise SecretDeliveryError("secret provider returned an invalid value")
    if "\n" in value or "\r" in value:
        raise SecretDeliveryError("secret provider returned a multiline environment value")
    return DeliveredSecret(path, consumer, requirement.environment_name or "", value)


def deliver_environment(
    provider: SecretProvider,
    *,
    consumer: str,
    requirements: tuple[SecretRequirement, ...] = DEFAULT_REQUIREMENTS,
) -> dict[str, str]:
    """Return a transient environment mapping for one approved consumer."""
    approved_consumers = {consumer_name for requirement in requirements for consumer_name in requirement.consumers}
    if consumer not in approved_consumers:
        raise SecretDeliveryError("consumer has no approved secret contract")
    environment: dict[str, str] = {}
    for requirement in requirements:
        if consumer not in requirement.consumers:
            continue
        delivered = deliver(provider, path=requirement.path, consumer=consumer, requirements=requirements)
        if delivered.environment_name in environment and environment[delivered.environment_name] != delivered.value:
            raise SecretDeliveryError("conflicting secret environment delivery")
        environment[delivered.environment_name] = delivered.value
    return environment


def deliver_services_environment(
    provider: SecretProvider,
    catalog: object,
    services: Mapping[str, object],
    *,
    selected_services: list[str] | tuple[str, ...] | None = None,
    bootstrap_requirements: tuple[SecretRequirement, ...] = DEFAULT_REQUIREMENTS,
) -> dict[str, str]:
    """Resolve bootstrap plus model-derived runtime secrets for selected services."""
    environment = deliver_environment(provider, consumer="ansible-bootstrap", requirements=bootstrap_requirements)
    service_requirements = requirements_for_model(catalog, services, selected_services=selected_services)
    for service in sorted({requirement.service for requirement in service_requirements if requirement.service is not None}):
        requirements = tuple(requirement for requirement in service_requirements if requirement.service == service)
        delivered = deliver_environment(
            provider,
            consumer=f"ansible-service:{service}",
            requirements=requirements,
        )
        for name, value in delivered.items():
            if name in environment and environment[name] != value:
                raise SecretDeliveryError("conflicting secret environment delivery")
            environment[name] = value
    return environment
def redact_environment(environment: Mapping[str, str], secret_names: set[str]) -> dict[str, str]:
    """Return metadata-only environment diagnostics."""
    return {name: "<redacted>" if name in secret_names else value for name, value in environment.items()}


__all__ = [
    "ALL_REQUIREMENTS",
    "BOOTSTRAP_SSH_PRIVATE_KEY_PATH",
    "DEFAULT_REQUIREMENTS",
    "PROVIDER_REQUIREMENTS",
    "PROXMOX_PROVIDER_PATH",
    "DeliveredSecret",
    "SecretDeliveryError",
    "SecretRequirement",
    "deliver",
    "deliver_environment",
    "deliver_services_environment",
    "redact_environment",
    "requirement_index",
    "root_password_requirements",
    "root_password_secret_path",
    "requirements_for_model",
    "provider_requirements",
]
