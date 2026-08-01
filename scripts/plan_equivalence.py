"""Compare OpenTofu/Terraform JSON plans for semantic equivalence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class PlanEquivalenceError(ValueError):
    """Raised when a plan document is malformed."""


def _load_document(value: Mapping[str, Any] | Path) -> Mapping[str, Any]:
    if isinstance(value, Path):
        try:
            value = json.loads(value.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PlanEquivalenceError(f"could not read plan JSON: {value}") from error
    if not isinstance(value, Mapping):
        raise PlanEquivalenceError("plan JSON must be an object")
    entries = value.get("resource_changes", value.get("resources", []))
    if not isinstance(entries, list):
        raise PlanEquivalenceError("plan resource_changes must be a list")
    return value


def _resource_identity(change: Mapping[str, Any]) -> str:
    address = change.get("address")
    if not isinstance(address, str) or not address:
        raise PlanEquivalenceError("plan resource change has no address")
    return address


def _semantic_resource_change(change: Mapping[str, Any]) -> dict[str, Any] | None:
    details = change.get("change")
    if not isinstance(details, Mapping):
        raise PlanEquivalenceError(f"plan resource change is malformed: {_resource_identity(change)}")
    actions = details.get("actions")
    if not isinstance(actions, list) or not all(isinstance(action, str) for action in actions):
        raise PlanEquivalenceError(f"plan resource actions are malformed: {_resource_identity(change)}")
    if actions == ["no-op"] or actions == ["read"]:
        return None
    return {
        "actions": actions,
        "before": details.get("before"),
        "after": details.get("after"),
        "replace_paths": details.get("replace_paths", []),
    }


def _semantic_output_changes(plan: Mapping[str, Any]) -> dict[str, Any]:
    outputs = plan.get("output_changes", {})
    if not isinstance(outputs, Mapping):
        raise PlanEquivalenceError("plan output_changes must be an object")
    result: dict[str, Any] = {}
    for name, change in outputs.items():
        if not isinstance(name, str) or not isinstance(change, Mapping):
            raise PlanEquivalenceError("plan output change is malformed")
        actions = change.get("actions", [])
        if actions in ([], ["no-op"], ["read"]):
            continue
        result[name] = {
            "actions": actions,
            "before": change.get("before"),
            "after": change.get("after"),
        }
    return result


def _semantic_changes(plan: Mapping[str, Any]) -> dict[str, Any]:
    resources: dict[str, Any] = {}
    entries = plan.get("resource_changes", plan.get("resources", []))
    for raw_change in entries:
        if not isinstance(raw_change, Mapping):
            raise PlanEquivalenceError("plan resource change must be an object")
        address = _resource_identity(raw_change)
        if address in resources:
            raise PlanEquivalenceError(f"plan contains duplicate resource address: {address}")
        if "change" in raw_change:
            semantic = _semantic_resource_change(raw_change)
        else:
            actions = raw_change.get("actions")
            if not isinstance(actions, list) or not all(isinstance(action, str) for action in actions):
                raise PlanEquivalenceError(f"plan resource actions are malformed: {address}")
            semantic = None if actions in (["no-op"], ["read"]) else {
                "actions": actions,
                "before": None,
                "after": raw_change.get("values"),
                "replace_paths": [],
            }
        if semantic is not None:
            resources[address] = semantic
    return {"resources": resources, "outputs": _semantic_output_changes(plan)}


def compare_plans(before: Mapping[str, Any] | Path, after: Mapping[str, Any] | Path) -> dict[str, Any]:
    """Return a stable semantic comparison of two plan JSON documents."""
    before_semantic = _semantic_changes(_load_document(before))
    after_semantic = _semantic_changes(_load_document(after))
    if before_semantic == after_semantic:
        return {"equivalent": True, "differences": []}
    differences: list[dict[str, Any]] = []
    before_resources = before_semantic["resources"]
    after_resources = after_semantic["resources"]
    for address in sorted(set(before_resources) | set(after_resources)):
        if address not in before_resources:
            differences.append({"kind": "new-resource-change", "address": address, "after": after_resources[address]})
        elif address not in after_resources:
            differences.append({"kind": "removed-resource-change", "address": address, "before": before_resources[address]})
        elif before_resources[address] != after_resources[address]:
            before_actions = before_resources[address]["actions"]
            after_actions = after_resources[address]["actions"]
            kind = "replacement" if "delete" in after_actions and "create" in after_actions else "resource-change"
            differences.append({"kind": "values_changed" if kind == "resource-change" else kind, "address": address})
    before_outputs = before_semantic["outputs"]
    after_outputs = after_semantic["outputs"]
    for name in sorted(set(before_outputs) | set(after_outputs)):
        if before_outputs.get(name) != after_outputs.get(name):
            differences.append({"kind": "output-change", "address": name, "before": before_outputs.get(name), "after": after_outputs.get(name)})
    return {"equivalent": False, "differences": differences}


__all__ = ["PlanEquivalenceError", "compare_plans"]
