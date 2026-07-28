# Normalized OpenTofu plan-equivalence contract

**Status:** report-only, provider adapter deferred

`scripts/plan_equivalence.py` compares a deliberately small, provider-neutral
shape. It is not an OpenTofu JSON parser and is not called by plan or apply.
Provider adapters may be added later, but must map provider output into this
contract before comparison.

## Version 1 shape

```json
{
  "schema_version": 1,
  "resources": [
    {
      "address": "service.forgejo",
      "actions": ["delete", "create"],
      "values": {
        "vmid": 101,
        "runtime": "lxc",
        "storage": {"rootfs": {"size_gb": 32}}
      }
    }
  ]
}
```

The contract is intentionally minimal:

- `schema_version` is required and must be integer `1`.
- `resources` is a list with one entry per exact resource address. Addresses
  must be non-empty and unique; changing an address is a remove plus an add.
- `actions` is a non-empty list containing only `create`, `read`, `update`,
  `delete`, or `no-op`. Replacement is represented explicitly as the ordered
  action list `["delete", "create"]`; it must not be collapsed to `update`,
  `create`, or a boolean replacement hint.
- `values` is required, may contain any JSON value including `null`, and is
  compared as data. Values are never omitted merely because they are provider
  specific. Unknown/computed markers are data too: a known value and an
  unknown marker are different.
- All other top-level fields are outside the comparison contract. Formatting,
  key order, and explicitly path-only metadata may be retained by fixtures but
  must not be used as equivalence inputs.

The comparator reports only `address` and a difference `kind`
(`resource_added`, `resource_removed`, `actions_changed`, or
`values_changed`). It never includes resource values, which keeps public
fixtures and errors safe when a future adapter carries sensitive-dependent
fields.

## Provider-neutral versus provider-specific boundary

A future provider adapter owns extraction from `resource_changes`, including
provider addresses, nested `change.before`/`change.after` values, unknown and
sensitive markers, and provider refresh noise. The adapter must output the
version-1 shape above. Provider-specific normalization is not permitted to
silently drop VM identity, runtime type, storage identity/size, placement,
endpoint/DNS targets, release pins, or secret-dependent fields. If a value
cannot be represented safely, the adapter should reject the input rather than
omit it.

Only a narrowly reviewed allowlist may remove path-only or refresh-only
metadata. There is no generic recursive "ignore provider fields" rule. Exact
saved-plan hashes and canonical model/projection identity remain separate
staleness/source-binding gates; semantic comparison must not weaken either.

## Public fixture policy and deferred work

Fixtures under `tests/fixtures/plan-equivalence/` must use placeholders and RFC
5737 addresses only. They should cover formatting-only equality, known versus
unknown values, changed VMID/runtime/storage/address/DNS/ownership, release or
secret-dependent changes, and update versus replacement actions. No real
`tofu show -json` output is required for this slice, and no provider output is
invented. A later adapter slice needs provider-backed fixtures and tests for
unknown/sensitive encoding, refresh-only differences, and the exact
`resource_changes` mapping.

This contract is intentionally not wired into `verify_metadata()`,
`plan-infra.sh`, or apply. Passing these tests proves normalization semantics
only; it does not prove plan/apply integration, consumer cutover, or resource
behavior equivalence.
