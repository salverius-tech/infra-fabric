#!/usr/bin/env python3
"""Fail-closed consumer delivery for canonical logical secrets.

This module deliberately keeps resolved values in memory. It does not write
secret projections, command-line arguments, logs, or persistent dotenv files.
"""
from __future__ import annotations

from dataclasses import dataclass
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


# Environment names are explicit policy, never inferred from logical paths.
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
        "secrets.operator.systemboss_password",
        "operator",
        frozenset({"ansible-host-identity"}),
        "INFRA_SYSTEMBOSS_PASSWORD",
        state_exposure="forbidden",
    ),
)


def _service_requirement(service: str, key: str, environment_name: str) -> SecretRequirement:
    return SecretRequirement(
        f"secrets.services.{service}.{key}",
        "runtime",
        frozenset({f"ansible-service:{service}"}),
        environment_name,
        service,
        "forbidden",
    )


SERVICE_REQUIREMENTS: tuple[SecretRequirement, ...] = (
    _service_requirement("forgejo", "bootstrap_admin_password", "FORGEJO_ADMIN_PASSWORD"),
    _service_requirement("forgejo", "bootstrap_owner_password", "FORGEJO_REPO_OWNER_PASSWORD"),
    _service_requirement("forgejo", "internal_token", "FORGEJO_INTERNAL_TOKEN"),
    _service_requirement("forgejo", "lfs_jwt_secret", "FORGEJO_LFS_JWT_SECRET"),
    _service_requirement("forgejo", "oauth2_jwt_secret", "FORGEJO_OAUTH2_JWT_SECRET"),
    _service_requirement("forgejo", "postgres_password", "FORGEJO_POSTGRES_PASSWORD"),
    _service_requirement("forgejo", "secret_key", "FORGEJO_SECRET_KEY"),
    _service_requirement("forgejo_runner", "registration_secret", "FORGEJO_RUNNER_REGISTRATION_SECRET"),
    _service_requirement("hermes", "control_api_token", "HERMES_CONTROL_API_TOKEN"),
    _service_requirement("hermes", "control_bridge_token", "HERMES_CONTROL_BRIDGE_TOKEN"),
    _service_requirement("hermes", "dashboard_basic_auth_password_hash", "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH"),
    _service_requirement("hermes", "dashboard_basic_auth_secret", "HERMES_DASHBOARD_BASIC_AUTH_SECRET"),
    _service_requirement("infisical", "auth_secret", "INFISICAL_AUTH_SECRET"),
    _service_requirement("infisical", "encryption_key", "INFISICAL_ENCRYPTION_KEY"),
    _service_requirement("infisical", "postgres_password", "INFISICAL_POSTGRES_PASSWORD"),
    _service_requirement("searxng_onramp", "secret_key", "SEARXNG_SECRET_KEY"),
    _service_requirement("tailscale_client", "auth_key", "TS_AUTHKEY"),
    _service_requirement("caddy", "cloudflare_api_token", "CLOUDFLARE_API_TOKEN"),
)

ALL_REQUIREMENTS = DEFAULT_REQUIREMENTS + OPERATOR_REQUIREMENTS + SERVICE_REQUIREMENTS


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


def requirements_for_services(services: list[str] | tuple[str, ...]) -> tuple[SecretRequirement, ...]:
    selected = set(services)
    return DEFAULT_REQUIREMENTS + tuple(requirement for requirement in SERVICE_REQUIREMENTS if requirement.service in selected)


def requirement_index(
    requirements: tuple[SecretRequirement, ...] = DEFAULT_REQUIREMENTS,
) -> dict[str, SecretRequirement]:
    index: dict[str, SecretRequirement] = {}
    for requirement in requirements:
        if requirement.path in index:
            raise SecretDeliveryError("duplicate logical secret delivery requirement")
        if not requirement.path or not requirement.consumers or not requirement.environment_name:
            raise SecretDeliveryError("secret delivery requirement is incomplete")
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
    return DeliveredSecret(path, consumer, requirement.environment_name or "", value)


def deliver_environment(
    provider: SecretProvider,
    *,
    consumer: str,
    requirements: tuple[SecretRequirement, ...] = DEFAULT_REQUIREMENTS,
) -> dict[str, str]:
    """Return a transient environment mapping for one approved consumer."""
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
    services: list[str] | tuple[str, ...],
    *,
    bootstrap_requirements: tuple[SecretRequirement, ...] = DEFAULT_REQUIREMENTS,
) -> dict[str, str]:
    """Resolve bootstrap plus only the runtime secrets required by selected services."""
    environment = deliver_environment(provider, consumer="ansible-bootstrap", requirements=bootstrap_requirements)
    for service in services:
        delivered = deliver_environment(
            provider,
            consumer=f"ansible-service:{service}",
            requirements=requirements_for_services([service]),
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
    "DEFAULT_REQUIREMENTS",
    "SERVICE_REQUIREMENTS",
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
    "requirements_for_services",
]
