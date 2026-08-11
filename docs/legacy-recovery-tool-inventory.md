# Bounded legacy recovery-tool inventory

**Status:** Source inventory complete; retirement is blocked by isolated controller/infrastructure recovery acceptance and separate operator authorization.

This document records the P10-E compatibility boundary without deleting or refactoring it. The normal operator lifecycle is canonical-only. The artifacts below remain solely for explicit recovery/forensics, historical mapping evidence, or public static fixtures until the recovery-removal trigger is met.

## Authority and prohibition

Decision D5 keeps bounded forensic discovery/recovery tooling quarantined until canonical rebuild and isolated recovery acceptance pass. P10-E additionally requires an exact caller inventory and separate permanent-removal authorization. This inventory is not that authorization.

Do not use these tools as a fallback from `setup`, `validate`, `plan`, `apply`, teardown, Ansible orchestration, or runtime service workflows. Do not delete them before the trigger. Until retirement, make only correctness or security fixes.

## Entrypoint and call-edge inventory

| Artifact | Current caller or entrypoint | Retained recovery purpose | Normal lifecycle edge |
| --- | --- | --- | --- |
| `just recover-legacy-values-forensics` | Explicit private recipe in `justfile` | Emits a value-redacted, read-only legacy discovery report; mutation requires a separately invoked recovery CLI | None; operational cutover tests prohibit calls from normal recipes |
| `scripts/migrate-values.py` | Direct recovery CLI; dynamically loaded by the two discovery modules; parsed by mapping inventory | Inspect/normalize old dotenv, tfvars, inventory, and generated-secret-era layouts; backup/restore helpers support bounded repair | None |
| `scripts/migrate-site-values.py` | Direct recovery CLI/tests; parsed by mapping inventory | Plan or explicitly apply movement of old root-layout values and operational artifacts into a selected site directory with backup metadata | None |
| `scripts/legacy-values-discovery.py` | Thin CLI over `legacy_values_discovery.py`; called by the explicit forensic recipe | Read-only report for old private-value layouts | None |
| `scripts/legacy_values_discovery.py` | Legacy discovery CLI, site-layout migration, semantic discovery, and focused tests | Value-redacted field classification, conflict reporting, candidate refusal, and ancillary-artifact metadata | None |
| `scripts/ansible_semantic_discovery.py` | Direct report CLI/tests | Static inventory-consumer evidence for legacy Ansible input identities | None |
| `scripts/migration_backup.py` | `migrate-values.py`, `migrate-site-values.py`, focused tests | Restrictive, manifest-bound backup and restore of explicitly selected migration files | None |
| `scripts/migrate-secret-bundle.py` | Direct protected recovery CLI documented in secret operations | Dry-run-by-default migration of encrypted logical secret paths | None |
| `scripts/secret_bundle_migration.py` | Secret-bundle CLI, canonical secret recovery, reconciliation validation, tests | SOPS-aware encrypted-bundle transformation primitives; shared canonical recovery use means it is not automatically deletable with layout migration | None |
| `scripts/discover-values-remote.sh` | No production caller; a regression test proves setup does not invoke it | Historical remote discovery only | None |
| `scripts/canonical-mapping-inventory.py` | Mapping documentation and direct tests; reconciliation records cite its test evidence | Historical source-to-canonical mapping evidence and retirement/exclusion accounting | No mutation edge; public validation directly exercises its contracts through whole-suite test discovery |

## Public scaffold and mapping surfaces tied to retirement

These tracked files are not normal operator inputs, but they remain active public static fixtures or historical mapping sources:

- `scaffold/terraform.tfvars`
- `scaffold/dns-records.local.json`
- `scaffold/ansible/inventory/local.yml`
- legacy input and exclusion sections in `docs/canonical-values-mapping-v1.md`
- legacy-source parsing/classification in `scripts/canonical-mapping-inventory.py`

`validate-public.sh` still uses the scaffold tfvars and inventory for OpenTofu formatting and Ansible static validation. They therefore cannot be deleted until equivalent canonical-only public fixtures replace every static consumer.

## Tests coupled to the bounded subsystem

Direct retirement candidates include:

- `tests/test_migrate_values.py`
- `tests/test_migrate_site_values.py`
- `tests/test_legacy_values_discovery.py`
- `tests/test_ansible_semantic_discovery.py`
- `tests/test_migration_backup.py`
- `tests/test_secret_bundle_migration.py`, but only for behavior no longer shared by canonical recovery
- legacy-source portions of `tests/test_canonical_mapping_inventory.py`
- the recovery-entrypoint/no-normal-call-edge assertions in `tests/test_operational_cutover.py` and `tests/test_plan_projection_lifecycle.py`

Security tests for traversal, symlinks, exclusive creation, restrictive permissions, redaction, encrypted output, and no-normal-workflow fallback must remain until the corresponding implementation is deleted. Equivalent guards must cover any retained canonical recovery primitive.

## Recovery scenarios that currently justify retention

1. **Old root-layout private values recovery.** A protected backup contains `.env`, `terraform.tfvars`, static inventory, DNS JSON, state, plans, backups, or known-hosts material that predates selected-site layout.
2. **Field provenance and conflict investigation.** An operator must identify how a legacy scalar or inventory identity maps—or refuses to map—to the canonical model without printing protected values.
3. **Encrypted logical-path migration.** A valid SOPS bundle uses an obsolete logical namespace and must be transformed while remaining encrypted and rollback-capable.
4. **Migration rollback.** A bounded recovery move must be reversed from a restrictive manifest-bound backup.
5. **Historical audit resolution.** A canonical mapping or exclusion must remain explainable until the frozen reconciliation history and recovery rehearsal prove that the source family is no longer needed.

## Confirmed normal-workflow isolation

The public `justfile` exposes a read-only legacy discovery report as the private `recover-legacy-values-forensics` recipe. Mutating recovery importers remain direct, explicit CLIs. Normal setup, site validation, planning, apply, teardown, update, and Ansible execution require an explicit canonical site and do not invoke the importer or remote-discovery helper. `tests/test_operational_cutover.py` and `tests/test_plan_projection_lifecycle.py` guard this boundary.

Whole-suite public test discovery and static OpenTofu/DNS/Ansible scaffold checks are normal-validation edges, not runtime lifecycle edges. They still prevent deletion until replacement canonical-fixture and test contracts are defined.

## Triggered deletion manifest

After isolated recovery acceptance and explicit permanent-removal authorization, prepare one reviewed retirement package in this order:

1. Replace legacy scaffold participation in `validate-public.sh` with canonical-only public fixtures.
2. Remove mapping-inventory source families, compatibility exclusions, and historical scaffold claims that no longer serve active validation.
3. Delete the root-layout importer, site-layout migration, legacy discovery CLIs/modules, remote discovery helper, and migration-only backup code whose callers are gone.
4. Delete their focused tests and update operational-cutover guards to assert that no legacy entrypoint exists.
5. Retain or split `secret_bundle_migration.py` and its security tests if canonical encrypted-bundle recovery still consumes them.
6. Remove the `recover-legacy-values-forensics` recipe last, after proving no caller remains.
7. Run canonical public validation, documentation/link checks, public-safety checks, and `git diff --check` before considering the source retirement complete.

Do not leave forwarding shims, deprecated aliases, or hidden auto-detection that recreates a second normal workflow.

## Exit conditions

Permanent retirement remains blocked until all are true:

- isolated infrastructure/controller recovery is accepted and recorded;
- each retained recovery scenario above is either exercised through the canonical recovery path or explicitly abandoned;
- source and test caller searches show no remaining dependency;
- canonical-only public fixtures cover OpenTofu and Ansible static validation;
- the operator separately authorizes permanent compatibility removal; and
- deletion is implemented and verified as one cohesive package.
