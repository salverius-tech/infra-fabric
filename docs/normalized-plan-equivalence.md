# Normalized OpenTofu plan-equivalence contract

**Status:** provider adapter implemented; optional and explicitly enforceable plan gate wired, provider-backed acceptance remains site-specific

The report-only boundary is `scripts/report-plan-equivalence.py`. It accepts two saved `tofu show -json` documents, emits only `address`/difference-kind metadata, returns 0 for equivalence, 1 for a semantic difference, and 2 for invalid input. It never invokes OpenTofu, writes plans, or applies infrastructure.

When an operator has a saved prior plan, setting `INFRA_EQUIVALENCE_BEFORE_JSON` while running the existing plan workflow enables the comparison. The current plan is exported to a disposable private-values file, compared, and removed by the existing EXIT cleanup path. A difference stops the workflow with a redacted report. For a canonical site, setting `INFRA_REQUIRE_EQUIVALENCE=true` makes the before-plan artifact mandatory and fails closed when it is absent; leaving that variable unset preserves the ordinary optional review mode.

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

The provider adapter at `scripts/tofu_plan_equivalence.py` owns extraction from `resource_changes`, including provider addresses, nested `change.before`/`change.after` values, unknown and sensitive markers, and provider refresh noise. It outputs the version-1 shape above. Provider-specific normalization is not permitted to silently drop VM identity, runtime type, storage identity/size, placement, endpoint/DNS targets, release pins, or secret-dependent fields. If a value cannot be represented safely, the adapter rejects the input rather than omitting it.

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
invented. A later integration slice needs provider-backed fixtures and tests for
refresh-only differences, exact `resource_changes` mapping, and an approved
report/plan invocation boundary.

This contract is wired into `plan-infra.sh` through `INFRA_EQUIVALENCE_BEFORE_JSON`; `INFRA_REQUIRE_EQUIVALENCE=true` turns the comparison into a required canonical-site planning gate. The gate exports the current plan to a disposable private-values file, compares it, and removes it through the shared projection cleanup trap. It is not wired into `verify_metadata()` or apply, and it does not prove consumer cutover or resource behavior equivalence. A real provider-backed before/after run remains a private-site acceptance step and must use reviewed plan artifacts; it is not fabricated in public fixtures.
