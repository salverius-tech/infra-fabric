# Canonical Cutover Audit Plan

> **For Hermes:** Conduct this as a read-only audit first. Do not restore, generate, rotate, commit, push, plan, apply, or mutate private values until the audit report has been reviewed and the operator authorizes a remediation phase.

**Goal:** Produce an evidence-backed, public-safe audit that maps every active configuration and secret interface to exactly one authoritative canonical source, identifies every remaining legacy or dual-read path, and defines a complete non-destructive remediation sequence.

**Architecture:** Reconcile four layers: private source-of-truth material, canonical model/projections, consumer contracts, and execution workflows. Treat SOPS logical paths and values as private: report names, classifications, presence, source location, and hashes/status only—never values, tokens, IPs, domains, hostnames, or credentials.

**Tech stack:** Python helpers, OpenTofu/Ansible orchestration scripts, SOPS/age provider metadata and logical-path enumeration, Git private-values history, repository unit tests.

---

## Verified starting evidence

- Main repository: `/devdata/repos/infra-fabric`, branch `feat/canonical-values-model`; many uncommitted public implementation changes.
- Private values repository: `/devdata/repos/infra-fabric/values`, branch `feat/canonical-values-cutover`; substantial uncommitted canonical-cutover and generated/state changes. Preserve all of them.
- Provider recreate has completed and a subsequent OpenTofu plan reported zero resource drift. Do not repeat teardown or apply during this audit.
- The current `values/sites/dev/migration-manifest.json` says `adoption: existing-canonical-site-no-legacy-moves`, `operations: []`, and `secret_values_included: false`.
- Legacy dev inputs are deleted in the working tree but exist in private Git `HEAD`, including `sites/dev/.env`, `sites/dev/terraform.tfvars`, `sites/dev/ansible/inventory/local.yml`, `sites/dev/site.json`, and `sites/dev/dns-records.local.json`.
- The current SOPS bundle has bootstrap/operator/provider logical values and Hermes values under `services.hermes.secrets.*`; do not assume absence from this bundle means absence from legacy private history.
- `infra/services.json` declares Hermes runtime paths as `services.hermes.secrets.*`, which match the SOPS bundle.
- `scripts/secret_delivery.py` currently builds service paths as `secrets.services.<service>.<key>`, which does not match the Hermes catalog/SOPS path convention.
- The current SOPS bundle has not imported the non-Hermes runtime values needed by the delivery helper. Those values are recoverable from private legacy source, but their target canonical paths and consumer interfaces must be audited before any mutation.
- Repository docs currently state that broader runtime consumer cutover remains deferred (`docs/canonical-values-secret-operations.md`). Reconcile this declared scope with code that now attempts runtime service secret delivery.

## Audit constraints

1. Read-only audit first; do not alter `values/`, `.env`, SOPS ciphertext, Git branches, state, known_hosts, or infrastructure.
2. Never print decrypted secret values, private keys, tokens, passwords, domains, IPs, hostnames, SOPS recipients, plan contents, or state contents.
3. Inspect the direct source before using Git/session history. Git private history may be used only to establish file/key presence and migration provenance.
4. Do not inspect Hermes-container repositories; that is separately operator-gated.
5. Do not commit, push, `tofu apply`, or run live service mutations.
6. Treat generated projections and private state as derived artifacts, not primary inputs.

## Required deliverable

Create a public-safe audit report at `.hermes/plans/` containing an ASCII table for each configuration family with these columns:

```text
canonical domain | source locations | canonical target | actual consumer paths |
writer/generator | lifecycle (setup/validate/plan/apply) | status |
classification | remediation action | regression test
```

Classify every row as exactly one of:

```text
canonical-only | legacy-only | dual-read | dual-write | canonical path mismatch |
missing migration | orphaned legacy | generated derived artifact | intentionally deferred
```

## Audit tasks

### Task 1: Freeze and inventory source boundaries

**Objective:** Record all source files, Git state, and generated artifacts without changing them.

**Files to inspect:**
- `values/sites/dev/site.yaml`
- `values/sites/dev/secrets.sops.yaml` (logical path names only)
- `values/sites/dev/migration-manifest.json`
- `values/sites/dev/generated/*`
- `values` Git status and `HEAD` tree entries for deleted legacy files
- `values/sites/prod/*` only to identify shared implementation conventions; do not expose values

**Verification:**
- Produce a value-free file-presence and logical-path inventory.
- Confirm which deleted working-tree files are still recoverable from private Git `HEAD`.

### Task 2: Establish canonical interface definitions

**Objective:** Identify the authoritative model definitions for every non-secret and secret path.

**Files to inspect:**
- `infra/services.json`
- `scripts/canonical_values.py`
- `scripts/canonical_projections.py`
- `scripts/secret_delivery.py`
- `scripts/secret_provider.py`
- `scripts/service_catalog.py`
- `docs/canonical-values-mapping-v1.md`
- `docs/canonical-values-secret-operations.md`

**Verification:**
- Build a path matrix from service catalog requirements, SOPS logical paths, and delivery helper paths.
- Explicitly identify whether `infra/services.json`, mapping documentation, and delivery code agree for each service.

### Task 3: Trace every legacy reader, writer, and generator

**Objective:** Find all code paths that consume, generate, delete, or transform legacy configuration.

**Files to inspect:**
- `scripts/migrate-values.py`
- `scripts/migrate-secret-bundle.py`
- `scripts/parse-env.py`
- `scripts/values.sh`
- `scripts/site-context.sh`
- `scripts/settings.py`
- `scripts/ssh-initialize.py`
- `scripts/canonical-secret-set.py`
- `scripts/workspace-preflight.py`
- `justfile`

**Verification:**
- For each legacy env/tfvars/inventory/DNS value family, record source, conversion target, generation behavior, and whether canonical-site mode bypasses that conversion.
- Distinguish intentional legacy migration compatibility from active production dual-read behavior.

### Task 4: Trace all runtime consumers and execution workflows

**Objective:** Determine exactly which values are consumed during setup, validate, plan, apply, bootstrap, and service convergence.

**Files to inspect:**
- `scripts/apply-ansible-services.py`
- `scripts/apply-infra.sh`
- `scripts/plan-infra.sh`
- `scripts/run-infra.sh`
- `scripts/canonical-provider-env.py`
- `infra/ansible/playbooks/*.yml`
- affected Ansible roles under `infra/ansible/roles/`
- `infra/opentofu/*.tf`

**Verification:**
- Map each execution stage to value reads/writes and secret delivery boundaries.
- Identify any runtime consumer that reads legacy environment variables while canonical mode is enabled.
- Identify every apply-only failure not detected by `just validate`.

### Task 5: Audit tests against the real contract

**Objective:** Identify why current tests/validation allowed an incomplete cutover to reach live apply.

**Files to inspect:**
- `tests/test_secret_delivery.py`
- `tests/test_apply_ansible_services.py`
- `tests/test_canonical_mapping_inventory.py`
- `tests/test_canonical_values.py`
- `tests/test_operational_cutover.py`
- `tests/test_migrate_values.py`
- `tests/test_workspace_preflight.py`
- `tests/test_ansible_canonical_compat.py`

**Verification:**
- Record missing test assertions for catalog-to-delivery path equality, canonical bundle completeness for enabled consumers, legacy-to-SOPS migration preservation, and no-live-apply preflight.

### Task 6: Produce a remediation design, not implementation

**Objective:** Recommend one coherent cutover design based on evidence.

**Required remediation decisions:**
1. Select the authoritative canonical logical-path namespace and make catalog, SOPS bundle, migration, and delivery helper agree.
2. Preserve existing private legacy values by importing/reconciling them; do not generate replacement credentials when recoverable values exist.
3. Define an idempotent canonical-site migration path that does not skip legacy import solely because `site.yaml` already exists.
4. Define a safe transition for deleted legacy files: restore only as an input to migration if needed, then remove only after canonical completeness verification.
5. Add fail-closed validation that checks every enabled service’s required canonical secret path before a live apply reaches service roles.
6. Define migration backup, rollback, SOPS recipient preservation, and tests.

**Do not implement this task in the audit session unless the operator explicitly authorizes remediation after reviewing the report.**

## Audit acceptance criteria

The audit is complete only when it provides:

1. A complete source-to-consumer matrix for enabled services and all infrastructure identity/provider inputs.
2. Evidence that each legacy value is either preserved, migrated, intentionally retained, or explicitly orphaned.
3. A precise explanation of every namespace/path mismatch with exact source file references.
4. A lifecycle matrix for setup, validate, plan, and apply, distinguishing generated, validated, decrypted/delivered, and ignored values.
5. A test-gap list explaining why `just validate` passed while service convergence failed.
6. A remediation plan that requires no new secret values unless no recoverable source exists.
7. No values or sensitive private topology in the report.

## Post-audit verification for the later remediation phase

After a separately authorized implementation:

```text
1. Run focused migration/path-contract tests.
2. Run the complete unit suite and just validate.
3. Produce a non-mutating plan and confirm no unexpected resource changes.
4. Verify required secret logical-path availability for enabled consumers without printing values.
5. Only with explicit approval, run just apply and capture per-service convergence evidence.
6. Run a final no-drift plan.
```

## Likely files to modify in the later remediation phase

- `scripts/secret_delivery.py`
- `scripts/migrate-values.py`
- `scripts/migrate-secret-bundle.py`
- `scripts/workspace-preflight.py`
- `scripts/apply-ansible-services.py`
- `infra/services.json`
- `docs/canonical-values-mapping-v1.md`
- `docs/canonical-values-secret-operations.md`
- targeted files under `tests/`
- private `values/sites/dev/secrets.sops.yaml` and legacy input files only under explicit private-values mutation authorization
