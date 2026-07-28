"""Report-only comparison of normalized public plan fixtures.

This module deliberately does not parse provider-specific OpenTofu JSON or gate
plan/apply. Its input is a small normalized shape that can be adopted by a
future provider adapter after the equivalence policy is reviewed.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class PlanEquivalenceError(ValueError):
    """Raised when a normalized plan fixture is malformed."""


def _resources(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    resources = plan.get("resources")
    if not isinstance(resources, list):
        raise PlanEquivalenceError("normalized plan resources must be a list")
    result: dict[str, dict[str, Any]] = {}
    for resource in resources:
        if not isinstance(resource, dict):
            raise PlanEquivalenceError("normalized plan resources must be objects")
        address = resource.get("address")
        actions = resource.get("actions")
        if not isinstance(address, str) or not address:
            raise PlanEquivalenceError("normalized plan resource address is required")
        if address in result:
            raise PlanEquivalenceError("normalized plan resource addresses must be unique")
        if not isinstance(actions, list) or not all(isinstance(action, str) for action in actions):
            raise PlanEquivalenceError("normalized plan resource actions must be strings")
        result[address] = {
            "actions": actions,
            "values": resource.get("values"),
        }
    return result


def compare_plans(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """Return a redacted structural equivalence report for normalized plans."""
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise PlanEquivalenceError("normalized plans must be objects")
    before_resources = _resources(before)
    after_resources = _resources(after)
    differences: list[dict[str, str]] = []
    for address in sorted(set(before_resources) | set(after_resources)):
        if address not in before_resources:
            differences.append({"address": address, "kind": "resource_added"})
            continue
        if address not in after_resources:
            differences.append({"address": address, "kind": "resource_removed"})
            continue
        before_resource = before_resources[address]
        after_resource = after_resources[address]
        if before_resource["actions"] != after_resource["actions"]:
            differences.append({"address": address, "kind": "actions_changed"})
        if before_resource["values"] != after_resource["values"]:
            differences.append({"address": address, "kind": "values_changed"})
    return {"equivalent": not differences, "differences": differences}
