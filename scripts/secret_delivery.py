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


@dataclass(frozen=True)
class DeliveredSecret:
    path: str
    consumer: str
    environment_name: str
    value: str


# Environment names are explicit policy, never inferred from logical paths.
DEFAULT_REQUIREMENTS: tuple[SecretRequirement, ...] = (
    SecretRequirement(
        "secrets.bootstrap.technitium.root_password",
        "bootstrap",
        frozenset({"ansible-bootstrap"}),
        "TF_VAR_container_root_password",
    ),
)


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


def redact_environment(environment: Mapping[str, str], secret_names: set[str]) -> dict[str, str]:
    """Return metadata-only environment diagnostics."""
    return {name: "<redacted>" if name in secret_names else value for name, value in environment.items()}


__all__ = [
    "DEFAULT_REQUIREMENTS",
    "DeliveredSecret",
    "SecretDeliveryError",
    "SecretRequirement",
    "deliver",
    "deliver_environment",
    "redact_environment",
    "requirement_index",
]
