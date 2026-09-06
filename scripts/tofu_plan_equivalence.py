#!/usr/bin/env python3
"""Normalize OpenTofu JSON plans for the provider-neutral equivalence contract."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plan_equivalence import PlanEquivalenceError


class TofuPlanError(PlanEquivalenceError):
    """Raised when OpenTofu JSON cannot be normalized safely."""


def _marker_tree(value: Any, markers: Any, *, marker: str) -> Any:
    if markers is True:
        return {marker: True}
    if isinstance(markers, Mapping):
        if isinstance(value, Mapping):
            return {
                key: _marker_tree(child, markers.get(key), marker=marker)
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [
                _marker_tree(child, markers.get(str(index)), marker=marker)
                for index, child in enumerate(value)
            ]
    if isinstance(value, Mapping):
        return {key: _marker_tree(child, None, marker=marker) for key, child in value.items()}
    if isinstance(value, list):
        return [_marker_tree(child, None, marker=marker) for child in value]
    return value


def _change_values(change: Mapping[str, Any]) -> Any:
    actions = change.get("actions")
    if not isinstance(actions, list) or not actions or not all(isinstance(item, str) for item in actions):
        raise TofuPlanError("OpenTofu resource change actions are invalid")
    after = change.get("after")
    before = change.get("before")
    values = after if after is not None else before
    if values is None:
        values = {}
    values = _marker_tree(values, change.get("after_unknown"), marker="unknown")
    values = _marker_tree(values, change.get("after_sensitive"), marker="sensitive")
    return values


def normalize_tofu_plan(document: Mapping[str, Any]) -> dict[str, Any]:
    """Convert ``tofu show -json`` output into normalized plan version 1.

    The adapter retains exact resource addresses and action sequences. Unknown
    and sensitive values become explicit markers; they are never omitted or
    replaced with guessed values. Provider metadata and formatting are dropped.
    """
    if not isinstance(document, Mapping):
        raise TofuPlanError("OpenTofu plan must be an object")
    changes = document.get("resource_changes")
    if not isinstance(changes, list):
        raise TofuPlanError("OpenTofu plan resource_changes must be a list")
    resources: list[dict[str, Any]] = []
    for change in changes:
        if not isinstance(change, Mapping):
            raise TofuPlanError("OpenTofu resource changes must be objects")
        address = change.get("address")
        if not isinstance(address, str) or not address:
            raise TofuPlanError("OpenTofu resource change address is required")
        resources.append(
            {
                "address": address,
                "actions": list(change.get("change", {}).get("actions", []))
                if isinstance(change.get("change"), Mapping)
                else [],
                "values": _change_values(change.get("change", {}))
                if isinstance(change.get("change"), Mapping)
                else _change_values({}),
            }
        )
    return {"schema_version": 1, "resources": resources}


__all__ = ["TofuPlanError", "normalize_tofu_plan"]
