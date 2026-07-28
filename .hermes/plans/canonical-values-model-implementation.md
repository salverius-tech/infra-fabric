# Canonical Site Values Model — Implementation Plan

**Status:** In progress — Phase 1 foundation slice verified; migration and consumer cutover remain
**Branch:** `feat/canonical-values-model`
**PRD:** [`canonical-values-model-prd.md`](./canonical-values-model-prd.md)
**Repository:** `infra-fabric`
**Last updated:** 2026-07-27

## Purpose

This document is the implementation companion to the Canonical Site Values Model PRD. It decomposes the PRD into reviewable work packages and is the progress tracker for this branch. Checkboxes, phase status, decision records, and verification evidence must be updated as work lands; do not mark a phase complete from code inspection alone.

## Scope and guardrails

- Canonical operator-edited inputs become `values/sites/<site>/site.yaml` and encrypted `secrets.sops.yaml`.
- Existing OpenTofu, Ansible, DNS, service-role, and public `just` interfaces remain compatible during migration.
- The public repository remains generic/public-safe; real values, credentials, state, and private remotes remain under the ignored private values repository.
- Migration is additive, dry-run by default, reversible, and conflict-failing.
- No automatic production apply, destructive migration, state surgery, or infrastructure mutation is part of implementation without explicit approval.
- No phase may silently discard an unmapped legacy value or secret.

## Progress legend

- `[ ]` not started
- `[~]` in progress or partially complete
- `[x]` implemented and verified
- `[!]` blocked or requires a product decision

Phase status is meaningful only when its exit gate has evidence recorded in this document.

## Definition of done

The implementation is complete when all of the following are true:

- [ ] Canonical schema and strict loader cover every supported service, runtime, shared host, resource, and required secret contract.
- [ ] Mapping matrix classifies every current supported Terraform, Ansible, migration, DNS, and dotenv input.
- [ ] SOPS/age loading, secret classification, redaction, cleanup, and key-management procedures are implemented and tested.
- [ ] Import works for both legacy root and site-aware values layouts, is idempotent, dry-run by default, conflict-failing, backed up, and reversible.
- [ ] OpenTofu, Ansible, runtime dotenv, and DNS projections are generated from one normalized snapshot and carry verified identity metadata.
- [ ] Plan/apply refuses wrong-site, stale-model, stale-secret, stale-projection, and altered-plan execution.
- [ ] Plan-equivalence evidence demonstrates no unintended resource changes for representative existing sites.
- [ ] Canonical workflow is used by setup, validate, plan, apply, backup, restore, update, and operator tooling.
- [ ] Legacy surfaces are compatibility-only, warn during the compatibility window, and have documented removal criteria.
- [ ] Documentation and public-safe scaffold describe the canonical architecture as the normal operating model.
- [ ] Required unit, contract, integration, migration, rollback, and operational validation passes are recorded.

## Workstream map

| ID | Workstream | Depends on | Status |
| --- | --- | --- | --- |
| W0 | Implementation design and repository inventory | PRD | `[~]` |
| W1 | Canonical schema, strict YAML loader, normalization, digests | W0 | `[~]` |
| W2 | Secret provider, SOPS/age policy, transport and cleanup | W0, W1 | `[~]` |
| W3 | Service catalog and mapping matrix | W0, W1 | `[~]` |
| W4 | Legacy importer and reversible migration | W1, W2, W3 | `[~]` |
| W5 | Consumer projections and compatibility adapters | W1, W2, W3 | `[~]` |
| W6 | Plan/apply identity binding and equivalence oracle | W5 | `[~]` |
| W7 | Operational cutover and compatibility window | W4, W5, W6 | `[ ]` |
| W8 | Compatibility removal and final validation | W7 | `[ ]` |

## Phase 0 — Implementation design and inventory

**Goal:** Resolve implementation-design questions for the phase being started and inventory the current contracts before changing consumers.

- [ ] Record current values-context entry points and invariants from `values_context.py`, `site-context.sh`, `migrate-values.py`, and `migrate-site-values.py`.
- [ ] Inventory current OpenTofu inputs from `infra/opentofu/variables.tf`, modules, scripts, and all invocation paths.
- [ ] Inventory Ansible inventory and variable consumers, including `infra/ansible/inventory/tfvars.py`, static inventory, playbooks, roles, and `apply-ansible-services.py`.
- [ ] Inventory DNS, dotenv, service-state, backup/restore, update, setup, validate, plan, and apply contracts.
- [ ] Enumerate every entry in `infra/services.json`, supported runtime, resource type, dependency, state, configuration, endpoint, release, and secret requirement.
- [ ] Define the complete version-one mapping matrix and its review/report format.
- [ ] Define the exact projection lifecycle: temporary path, ignored path, mode, ownership, cleanup, and invocation boundary.
- [ ] Define SOPS/age executable discovery, key-file discovery, recipient policy, and failure behavior.
- [ ] Identify all secrets currently entering OpenTofu state and document the required state protection before enabling those paths.
- [ ] Define service-specific typed override keys and configuration-schema ownership.
- [ ] Define compatibility-window warning text, owner, duration, and removal release criteria.

**Exit gate:** The design decisions affecting W1–W3 are recorded below, the mapping matrix is complete enough to classify every current input, and no phase-starting ambiguity remains.

## Phase 1 — Canonical schema and loader

**Goal:** Add a strict, platform-neutral model without changing OpenTofu or Ansible consumers.

- [~] Add strict Pydantic models for `schema_version`, `site`, `platform`, `resources`, and `services`. Initial public model exists; service-specific schemas remain.
- [~] Add typed LXC, VM, shared-host, storage, network, image/template, runtime, endpoint, release, state, configuration, and override models. Initial common models exist; complete catalog coverage remains.
- [x] Reject unknown fields, duplicate YAML keys, unsafe aliases/anchors, invalid types, unsupported schema versions, and path traversal at the canonical loader boundary.
- [x] Implement defaults and one-way platform → resource merge semantics for network and root storage fields.
- [x] Validate site/path/`VALUES_SITE` identity and site lifecycle safety constraints.
- [x] Validate resource identity, VMID uniqueness, address uniqueness, DHCP/static rules, runtime-specific fields, storage constraints, and non-overlapping IPv4 networks.
- [~] Validate service catalog membership, dependencies, resource references, supported runtime/resource combinations, required fields, and state policy. Catalog membership/dependencies are implemented; complete per-service requirements remain.
- [x] Implement normalized canonical representation and stable `model_digest`.
- [x] Implement redacted model summaries and path-specific non-secret errors.
- [~] Add public-safe schema fixtures covering all supported services, runtimes, shared hosts, stateful/stateless services, and invalid cases. A public `scaffold/sites/dev/site.yaml` fixture and common invalid-case suite exist; full service/runtime fixture coverage remains.

**Exit gate:** Strict schema and loader tests pass; a valid fixture loads with stable identity across formatting-only changes; consumers are unchanged.

## Phase 2 — Secret model and controlled loading boundary

**Goal:** Load one encrypted logical secret bundle per site without exposing values.

- [~] Add structural `secrets.sops.yaml` model with logical namespaces and required-secret classification. Initial validated `SecretBundle` and required-path contract exist; full catalog-driven classification remains.
- [~] Add provider-neutral `SecretProvider` boundary and version-one `SopsAgeProvider`. In-memory decryption, logical resolution, identity hashing, and sanitized failures are implemented; key discovery policy remains.
- [ ] Implement SOPS/age recipient policy and `.sops.yaml` rules without committing private keys.
- [~] Define external age-key discovery, missing-key errors, recipient checks, and provider availability checks. External key-file discovery, sanitized missing/unreadable/permission failures, public SOPS age-recipient matching, and metadata-only executable/bundle availability checks exist; plan/preflight policy wiring remains.
- [ ] Validate required secrets after service enablement/configuration evaluation.
- [x] Implement `secret_digest` over resolved logical values and `ciphertext_hash` over committed ciphertext.
- [ ] Ensure provider, bootstrap, runtime, recovery, and generated secrets are delivered only to permitted consumers.
- [ ] Add protected temporary directory/file creation with modes `0700`/`0600` and cleanup on success, validation failure, renderer failure, OpenTofu failure, Ansible failure, interruption, and termination.
- [~] Add redaction tests proving secret values do not appear in provider errors/metadata. Execution-boundary and generated-artifact cleanup tests remain.
- [ ] Document key creation, recipient rotation/revocation, backup, offline recovery, and disposable restore testing.

**Exit gate:** Secret-loading and cleanup tests pass, no plaintext secret is persisted outside the controlled boundary, and key-management documentation is complete.

## Phase 3 — Service catalog and mapping matrix

**Goal:** Make service capability and legacy translation explicit and testable.

- [ ] Extend or formalize `infra/services.json` as the capability/schema registry.
- [ ] Add required canonical fields, required logical secret paths, configuration schema identifiers, supported release forms, and allowed consumer overrides.
- [ ] Add the versioned mapping matrix covering Terraform, Ansible, inventory, DNS, dotenv, migration scripts, scaffold, and current service inputs.
- [~] Define normalization for HCL quoting, CIDR/bare addresses, `null`, `dhcp`, booleans, lists, checksums, hostnames, generated names, and derived DNS records. Forgejo public-name aliases now normalize scalar hostnames to canonical lowercase lists; broader normalization remains open.
- [ ] Classify every current input as canonical, derived, Ansible-only, OpenTofu-only, deprecated, or unsupported.
- [ ] Define conflict/default/destructive-impact behavior for every mapping row.
- [ ] Add automated coverage checks so new current inputs cannot bypass the matrix.
- [ ] Preserve unknown legacy values in a review report rather than dropping them.

**Exit gate:** Matrix coverage check passes against all named source files and every enabled service has a schema/fixture contract.

## Phase 4 — Legacy importer and reversible migration

**Goal:** Produce canonical files from both supported legacy layouts safely.

- [ ] Import legacy root layout: `.env`, `terraform.tfvars`, static inventory, DNS JSON, state, and settings metadata.
- [ ] Import current site-aware layout: `site.json`, site `.env`, site `terraform.tfvars`, inventory, known hosts, DNS JSON, state, plans, backups, and artifacts.
- [ ] Reuse existing values-context and migration contracts; do not create a competing path resolver.
- [x] Add report-only legacy discovery for dotenv, tfvars, settings, DNS, and inventory inputs. Secret/unknown values are redacted, all reads are non-mutating, candidate generation refuses incomplete mapping, and a restricted JSON CLI report is available.
- [ ] Generate candidate `site.yaml` and encrypted `secrets.sops.yaml` in dry-run mode by default.
- [~] Detect and report conflicts after semantic normalization; narrow mapped dotenv/tfvars conflict detection is covered, while the complete matrix remains open.
- [ ] Generate missing persistent secrets idempotently through an explicit policy, without logging values.
- [ ] Preserve unknown values and source paths in a migration report.
- [ ] Create and verify a backup before mutation; record source/destination hashes, schema/renderer versions, site, decisions, generated-secret actions, and backup ID in a manifest.
- [ ] Support explicit apply only, refuse overwrite without explicit migration mode, and roll back completed moves if later work fails.
- [ ] Preserve or deliberately migrate state, known hosts, plans, backups, and private artifact references.
- [ ] Prevent production credentials/state/backups from being copied into development sites.
- [ ] Add idempotence, conflict, dry-run, backup, rollback, and both-layout fixtures/tests.

**Exit gate:** Both legacy layouts migrate in disposable fixtures with verified backup/restore, idempotent rerun, conflict failure, and no secret leakage.

## Phase 5 — Consumer projections and compatibility adapters

**Goal:** Generate all consumer inputs from one normalized snapshot while preserving existing interfaces.

### OpenTofu projection

- [~] Render site-scoped OpenTofu variables using existing names. Pure projection rendering and a restricted-output CLI exist; plan/apply wiring remains.
- [~] Exclude Ansible-only, runtime-only, and unnecessary secret values. Projections reject recursively detected sensitive field names in arbitrary service maps and fail closed on non-empty opaque runtime `cloud_init`/`users`; explicit allow-listed schemas and consumer-specific exclusions remain.
- [~] Update every OpenTofu invocation path to consume exactly the generated projection. The primary plan boundary now refreshes canonical non-secret projections into the selected site's generated directory; consumer argument cutover remains.
- [ ] Bind projection to site, model, secret, source, and renderer identities.
- [ ] Keep generated inputs temporary or ignored and never operator-editable.

### Ansible projections

- [~] Render `ansible-inventory.json` from resources with existing groups, hosts, connection data, VMIDs, service domains, storage, and runtime variables. Initial resource/service inventory contract exists; full parity remains.
- [x] Render `ansible-vars.json` from enabled services with non-secret placement, runtime, endpoint, release, configuration, allow-listed overrides, and catalog metadata.
- [ ] Replace or reduce `tfvars.py` to a compatibility adapter over the canonical snapshot.
- [ ] Reduce static `ansible/inventory/local.yml` to genuine Ansible-only overrides.
- [ ] Update validation, plan, apply, and `apply-ansible-services.py` to consume the same snapshot/projection set.
- [ ] Inject secrets separately and only into tasks that require them.

### Runtime and DNS projections

- [ ] Render restricted `runtime.env` only for declared process-environment keys and secrets.
- [ ] Retain restricted dotenv parsing and escaping; reject duplicates, unknown keys, invalid quoting, and newline violations.
- [~] Render `dns-records.json` from service endpoint intent and resolved resource addresses. Initial A-record projection exists; provider/schema parity remains.
- [ ] Feed DNS projection through the existing `DNS_RECORDS_FILE` path during migration.
- [~] Add projection manifest with names, hashes, lifecycle, site/model/secret identity, schema version, and renderer version. Stable content hashes, identity verification, and restricted-output CLI exist; lifecycle wiring remains.
- [x] Add read-only canonical projection preflight at the workspace validation boundary. Selected canonical sites render and verify non-secret projections in a temporary restricted directory; legacy-only workspaces retain the existing validation path.
- [ ] Reject stale, altered, wrong-site, or cross-site projections.

**Exit gate:** Projection contract tests and integration tests pass for OpenTofu, Ansible, DNS, and runtime delivery; no generated artifact is treated as canonical input.

## Phase 6 — Plan/apply identity binding and equivalence

**Goal:** Make reviewable plan/apply operations exact and prove migration equivalence.

- [~] Record `schema_version`, loader/renderer version, source commit, selected site, `model_digest`, secret identity, ciphertext hash, projection digest, enabled services, ownership, and tool versions in plan metadata. Canonical model/projection identity recording and verification now exist for sites with persistent generated manifests; plan-path rendering and consumer integration remain.
- [~] Verify site/model/secret/projection identity before OpenTofu and again before Ansible. Existing metadata verification runs before OpenTofu and is repeated after OpenTofu before Ansible; secret-bearing and full consumer wiring remain.
- [ ] Ensure Ansible uses the same normalized snapshot or an identity-verified re-render.
- [ ] Reject stale plans after relevant source, secret, renderer, projection, or tool changes.
- [ ] Implement semantic plan-equivalence comparison for pre/post migration plans.
- [ ] Ignore only formatting/path/key-order/comments, refresh-only provider differences, and semantically equal computed values.
- [ ] Flag creates, destroys, replacements, address/VMID/runtime/storage changes, service placement changes, DNS target changes, and secret-dependent changes.
- [ ] Add wrong-site, stale-plan, changed-secret, altered-projection, and plan-equivalence failure tests.

**Exit gate:** A reviewed plan cannot be applied against a different site/model/secret/projection, and representative legacy-to-canonical plans meet the PRD equivalence criteria.

## Phase 7 — Operational cutover and compatibility window

**Goal:** Make canonical files the normal workflow while retaining safe compatibility support.

- [ ] Route `setup`, `validate`, `plan`, `apply`, `backup`, `restore`, `update`, and operator tooling through the canonical loader.
- [ ] Keep public `just` command names stable unless an explicit decision changes them.
- [ ] Make `VALUES_SITE` mandatory for site-scoped operations and preserve existing site-context safety checks.
- [ ] Update backup/restore and state paths to site-local state, generated artifacts, and encrypted backups.
- [ ] Emit documented warnings for direct legacy-file use during the compatibility window.
- [ ] Make canonical files the only documented operator-edited configuration inputs.
- [ ] Add selected-site, separate-dev/prod, direct-service-health, backup/restore, and repeat-plan operational checks.
- [ ] Update README, AGENTS, scaffold docs/site fixture, migration plan, development docs, setup help, and private values contract tests.

**Exit gate:** A representative site can validate, plan, apply (only with explicit approval), backup, restore, and repeat-plan using canonical inputs with identity checks and no unexpected changes.

## Phase 8 — Compatibility removal and release validation

**Goal:** Remove permanent duplicate configuration surfaces after evidence-backed cutover.

- [ ] Confirm the compatibility window and removal release criteria have passed.
- [ ] Stop treating root `.env`, `terraform.tfvars`, inventory, and DNS JSON as authoritative.
- [ ] Remove permanent duplicate knobs and direct consumer parsing paths.
- [ ] Retain a time-bounded legacy migration command, rollback documentation, and rollback tests.
- [ ] Verify public repository safety and absence of private values/state/generated secrets.
- [ ] Run the complete validation suite and record results.
- [ ] Run `just validate` for representative selected sites.
- [ ] Run reviewed plan, approved apply where authorized, repeat plan, service health/direct-access checks, backup/restore, rollback rehearsal, secret rotation, and generated-artifact cleanup.

**Exit gate:** All PRD success criteria and acceptance criteria are evidenced; no undocumented authoritative duplicate remains.

## Design decisions and records

These are implementation decisions required by the PRD. Record the decision, alternatives considered, rationale, and affected workstreams before starting the affected phase.

| ID | Decision | Required before | Status | Record |
| --- | --- | --- | --- | --- |
| D1 | Python package/module location and public CLI boundary for the values loader | W1 | `[ ]` | |
| D2 | Exact schema models and per-service configuration schema strategy | W1/W3 | `[ ]` | |
| D3 | Complete mapping matrix format and automated coverage check | W3 | `[ ]` | |
| D4 | SOPS/age executable and external key-file discovery contract | W2 | `[ ]` | |
| D5 | Projection temp/ignored paths, ownership, modes, and cleanup implementation | W2/W5 | `[ ]` | |
| D6 | Secret inventory and state-exposure policy | W2/W5 | `[ ]` | |
| D7 | Exact dynamic-inventory caller and compatibility-adapter cutover | W5 | `[ ]` | |
| D8 | Allowed service override keys and catalog metadata format | W3/W5 | `[ ]` | |
| D9 | Local state permissions, encryption-at-rest, and backup transport | W4/W7 | `[ ]` | |
| D10 | Compatibility warning owner, release window, and removal criteria | W7/W8 | `[ ]` | |

## Verification evidence

Update this table with real command output, fixture names, or review links. Do not replace evidence with a claim.

| Date | Scope | Command/test/evidence | Result | Notes |
| --- | --- | --- | --- | --- |
| 2026-07-27 | Branch setup | `git status --short --branch` | `[x]` | Branch created from synchronized `main`; worktree clean before plan creation. |
| 2026-07-27 | Phase 1 foundation slice | `docker compose run --rm -T infra python -m unittest -v tests/test_canonical_values.py tests/test_service_catalog.py` | `[x]` | 15 tests passed; strict YAML/model invariants, stable digest, redacted summary, CLI, and service catalog dependency validation. |
| 2026-07-27 | Phase 2 secret-provider slice | `docker compose run --rm -T infra python -m unittest -v tests/test_secret_provider.py tests/test_canonical_values.py tests/test_service_catalog.py` | `[x]` | 20 tests passed; provider boundary, in-memory logical resolution, secret/ciphertext identities, and sanitized failure paths. |
| 2026-07-27 | Projection/manifest slice | `docker compose run --rm -T infra python -m unittest -v tests/test_projection_manifest.py tests/test_secret_provider.py tests/test_canonical_values.py tests/test_service_catalog.py` | `[x]` | 25 tests passed; non-secret OpenTofu/Ansible/DNS projections and stale/altered identity rejection. |
| 2026-07-27 | Public scaffold fixture | `docker compose run --rm -T infra python scripts/canonical-values.py --site-file scaffold/sites/dev/site.yaml validate` | `[x]` | Canonical `dev` scaffold validates and produces a redacted model digest. |
| 2026-07-27 | Projection renderer CLI | `docker compose run --rm -T infra python -m unittest -v tests/test_canonical_values.py tests/test_projection_manifest.py` | `[x]` | 17 tests passed; renderer writes the non-secret projection set, manifest, and mode-0700 output directory. |
| 2026-07-27 | Phase 1 syntax/diff checks | `docker compose run --rm -T infra python -m py_compile scripts/canonical_values.py scripts/service_catalog.py scripts/canonical-values.py tests/test_canonical_values.py tests/test_service_catalog.py`; `git diff --check` | `[x]` | Python compilation and whitespace checks passed. |
| 2026-07-27 | Full repository unittest discovery | `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'` | `[x]` | 275 tests collected and passed in the repository tooling image. |
| 2026-07-27 | Phase 1 network/defaults slice | `docker compose run --rm -T infra python -m unittest -v tests/test_canonical_values.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `git diff --check` | `[x]` | 16 focused tests and 279 full repository tests passed; platform defaults, IPv4 validity, and overlapping-network rejection are covered. |
| 2026-07-27 | Phase 1 catalog-boundary slice | `docker compose run --rm -T infra python -m unittest -v tests/test_canonical_values.py tests/test_service_catalog.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `git diff --check` | `[x]` | 23 focused tests and 286 full repository tests passed; complete canonical service-map membership and catalog-owned dependency checks are covered. |
| 2026-07-27 | Phase 2 secret-boundary slice | `docker compose run --rm -T infra python -m unittest -v tests/test_canonical_values.py tests/test_service_catalog.py tests/test_secret_provider.py tests/test_projection_manifest.py` | `[x]` | 37 focused tests passed; structural bundle discovery, required logical paths, external age-key-file discovery, redacted metadata, private modes, and cleanup are covered. Execution-boundary integration and recipient policy remain open. |
| 2026-07-27 | Phase 2 catalog/key-policy slice | `.venv/bin/python -m unittest -v tests/test_secret_provider.py tests/test_service_catalog.py tests/test_canonical_values.py tests/test_projection_manifest.py`; `.venv/bin/python -m py_compile scripts/secret_provider.py scripts/service_catalog.py tests/test_secret_provider.py tests/test_service_catalog.py`; `git diff --check` | `[x]` | 39 tests passed; catalog-driven required-secret path derivation, logical-path validation, age-key permission checks, redacted structural metadata, and existing projection identity regressions verified. Recipient checks, provider availability policy, and execution-boundary cleanup remain open. |
| 2026-07-27 | Phase 2 recipient-policy slice | `docker compose run --rm -T infra python -m unittest -v tests/test_secret_provider.py tests/test_service_catalog.py`; `python3 -m py_compile scripts/secret_provider.py scripts/service_catalog.py tests/test_secret_provider.py tests/test_service_catalog.py`; `git diff --check` | `[x]` | 21 focused tests passed; public SOPS age-recipient metadata matching, mismatch rejection, malformed/missing metadata failures, catalog path derivation, and key-file permission checks verified. Provider availability policy, `.sops.yaml` rules, and execution-boundary cleanup remain open. |
| 2026-07-27 | Ansible variables projection slice | `docker compose run --rm -T infra python -m unittest -v tests/test_canonical_values.py tests/test_projection_manifest.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `python3 -m py_compile scripts/canonical_projections.py scripts/canonical-render.py tests/test_canonical_values.py`; `git diff --check` | `[x]` | 20 focused tests and 290 full repository tests passed; `ansible-vars.json` renders non-secret service placement/configuration and is included in the projection manifest. |
| 2026-07-27 | Projection manifest integrity slice | `docker compose run --rm -T infra python -m unittest -v tests/test_projection_manifest.py tests/test_canonical_values.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `python3 -m py_compile scripts/projection_manifest.py tests/test_projection_manifest.py`; `git diff --check` | `[x]` | 22 focused tests and 292 full repository tests passed; manifest self-tampering and projection-set mismatch now fail closed in addition to stale/altered payload checks. |
| 2026-07-27 | Canonical projection preflight slice | `docker compose run --rm -T infra python -m unittest -v tests/test_workspace_preflight.py tests/test_canonical_values.py tests/test_projection_manifest.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `docker compose run --rm -T infra python -m py_compile scripts/workspace-preflight.py tests/test_workspace_preflight.py`; `git diff --check` | `[x]` | 29 focused tests and 294 full repository tests passed; selected canonical sites render and verify non-secret projections in a temporary restricted directory, invalid canonical input fails closed, and no generated directory is left behind. |
| 2026-07-27 | Legacy discovery report-only slice | `docker compose run --rm -T infra python -m unittest -v tests/test_legacy_values_discovery.py tests/test_migrate_values.py tests/test_values_context.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `docker compose run --rm -T infra python -m py_compile scripts/legacy_values_discovery.py tests/test_legacy_values_discovery.py`; `git diff --check` | `[x]` | 32 focused tests and 297 full repository tests passed; legacy reads are byte-for-byte non-mutating, secret and unknown values are redacted, inventory is reported as unsupported, and incomplete mapping refuses candidate generation. |
| 2026-07-27 | Legacy discovery CLI slice | `docker compose run --rm -T infra python -m unittest -v tests/test_legacy_values_discovery.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `docker compose run --rm -T infra python -m py_compile scripts/legacy_values_discovery.py scripts/legacy-values-discovery.py tests/test_legacy_values_discovery.py`; `git diff --check` | `[x]` | 5 focused discovery/CLI tests and 299 full repository tests passed; stdout and restricted-file JSON reporting are redacted, invalid directories return sanitized errors, and no migration mutation is invoked. |
| 2026-07-27 | Legacy discovery normalization/conflict slice | `docker compose run --rm -T infra python -m unittest -v tests/test_legacy_values_discovery.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `docker compose run --rm -T infra python -m py_compile scripts/legacy_values_discovery.py scripts/legacy-values-discovery.py tests/test_legacy_values_discovery.py`; `git diff --check` | `[x]` | 6 focused discovery/CLI tests and 300 full repository tests passed; lowercase Terraform and uppercase dotenv aliases now share a canonical path, differing values are reported as conflicts, and candidate generation remains blocked. |
| 2026-07-28 | Legacy discovery CLI safety slice | `docker compose run --rm -T infra python -m unittest -v tests/test_legacy_values_discovery.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `docker compose run --rm -T infra python -m py_compile scripts/legacy_values_discovery.py scripts/legacy-values-discovery.py tests/test_legacy_values_discovery.py`; `git diff --check` | `[x]` | 8 focused discovery/CLI tests and 302 full repository tests passed; report output inside the legacy values directory is rejected, malformed JSON produces no output artifact, and restricted output behavior remains covered. |
| 2026-07-28 | Public SOPS policy contract | `docker compose run --rm -T infra python -m unittest -v tests/test_sops_policy.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `docker compose run --rm -T infra python -m py_compile tests/test_sops_policy.py`; `git diff --check` | `[x]` | 1 focused policy test and 315 full repository tests passed; `.sops.yaml` matches only canonical site secret bundles and contains an explicit non-operational placeholder recipient. Preflight/key transport wiring remains deferred. |
| 2026-07-28 | Technitium `SERVER_NAME` mapping slice | `docker compose run --rm -T infra python -m unittest -v tests/test_legacy_values_discovery.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `docker compose run --rm -T infra python -m py_compile scripts/legacy_values_discovery.py tests/test_legacy_values_discovery.py`; `git diff --check` | `[x]` | 13 focused discovery tests and 315 full repository tests passed; scalar `SERVER_NAME` maps to normalized Technitium public names, conflicting values remain fail-closed, and DNS/inventory ownership remains incomplete. |
| 2026-07-28 | Canonical service endpoint schema slice | `docker compose run --rm -T infra python -m unittest -v tests/test_canonical_values.py tests/test_service_catalog.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `docker compose run --rm -T infra python -m py_compile scripts/canonical_values.py tests/test_canonical_values.py`; `git diff --check` | `[x]` | 28 focused canonical/catalog tests and 312 full repository tests passed; endpoint protocols normalize case and reject duplicates, while endpoint ports are restricted to 1–65535. |
| 2026-07-28 | Non-secret projection leakage guard | `docker compose run --rm -T infra python -m unittest -v tests/test_canonical_values.py tests/test_workspace_preflight.py tests/test_secret_provider.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `docker compose run --rm -T infra python -m py_compile scripts/canonical_projections.py tests/test_canonical_values.py`; `git diff --check` | `[x]` | 37 focused projection/preflight/secret tests and 310 full repository tests passed; sensitive field names are rejected in arbitrary service maps and non-empty opaque runtime cloud-init/users maps fail closed before non-secret artifact generation. |
| 2026-07-28 | Forgejo legacy endpoint-name mapping slice | `docker compose run --rm -T infra python -m unittest -v tests/test_legacy_values_discovery.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `docker compose run --rm -T infra python -m py_compile scripts/legacy_values_discovery.py tests/test_legacy_values_discovery.py`; `git diff --check` | `[x]` | 14 focused discovery tests and 309 full repository tests passed; Forgejo domain/server-name aliases map to `services.forgejo.endpoints.public_names`, scalar hostnames normalize to lowercase one-item lists, equivalent values do not conflict, and different values remain fail-closed. |
| 2026-07-28 | Persistent plan projection boundary | `bash -n scripts/plan-infra.sh`; `bash -n scripts/apply-infra.sh`; `docker compose run --rm -T infra python -m unittest -v tests/test_tfplan_metadata.py tests/test_workspace_preflight.py tests/test_projection_manifest.py`; `docker compose run --rm -T infra python -m unittest discover -s tests -p 'test_*.py'`; `docker compose run --rm -T infra python -m py_compile scripts/tfplan-metadata.py tests/test_tfplan_metadata.py`; `git diff --check` | `[x]` | 30 focused plan/projection tests and 305 full repository tests passed; canonical plans atomically refresh non-secret projections into the selected generated directory, metadata binds their verified identity, and apply re-verifies identity before Ansible. Legacy-only plan behavior remains unchanged. |
| 2026-07-27 | Host-only unittest discovery | `.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v` | `[!]` | Host run was not authoritative: missing declared dependencies and `/workspace` assumptions caused environment failures. |

## Risks and stop conditions

- Stop before consumer cutover if the mapping matrix has an unclassified current input or unresolved conflict semantics.
- Stop before secret integration if any required secret would be logged, passed as a command-line argument, or persisted in an uncontrolled artifact.
- Stop before plan/apply cutover if source, model, secret, or projection identities cannot be verified at both execution boundaries.
- Stop before migration mutation if backup verification and disposable restore have not passed.
- Stop before production readiness if plan equivalence, rollback, repeat-plan, and secret cleanup evidence is incomplete.
- Treat any discovered product-level decision as a PRD update requirement before proceeding.

## Change log

- 2026-07-27 — Created implementation tracker on `feat/canonical-values-model` from the synchronized `main` branch.
- 2026-07-27 — Added the initial strict canonical site loader, stable model digest/redacted summary helpers, service catalog validation adapter, focused tests, and the pinned Pydantic tooling dependency.
- 2026-07-27 — Added the provider-neutral SOPS/age secret boundary with logical resolution, secret identities, sanitized errors, and focused tests.
- 2026-07-27 — Added non-secret OpenTofu/Ansible/DNS projection helpers and stable projection-manifest identity verification with focused tests.
- 2026-07-27 — Added the public-safe canonical `dev` scaffold fixture and CLI validation evidence.
- 2026-07-27 — Added the restricted non-secret projection renderer CLI and output-directory lifecycle test.
- 2026-07-27 — Added IPv4 semantic validation, non-overlapping resource-network checks, and one-way platform defaults for resource network/root-storage fields.
- 2026-07-27 — Added canonical service-map membership and catalog-owned dependency validation, including disabled-service and override mismatch failures.
- 2026-07-27 — Added the initial validated secret bundle, required logical-path checks, external age-key-file discovery, redacted metadata, and private temporary secret-material cleanup helpers.
- 2026-07-27 — Added catalog-driven required-secret path metadata/derivation and age-key-file permission enforcement; recipient checks, provider availability policy, and execution-boundary cleanup remain open.
- 2026-07-27 — Added read-only canonical projection preflight to workspace validation, with temporary restricted output, manifest verification, legacy fallback, and cleanup tests.
- 2026-07-27 — Added report-only legacy values discovery with source classification, redaction, non-mutation checks, and fail-closed candidate gating.
- 2026-07-27 — Added the restricted JSON CLI for report-only legacy discovery with sanitized errors and output-file permissions.
- 2026-07-27 — Added lowercase/uppercase legacy alias normalization and conflict reporting for the initial mapped endpoint subset.
- 2026-07-28 — Hardened the discovery CLI against output-path overwrite of legacy inputs and malformed-input artifact creation.
- 2026-07-28 — Bound canonical site/model/projection/renderer/source identity into plan metadata verification while preserving explicit legacy-site compatibility.
- 2026-07-28 — Plan now atomically refreshes canonical non-secret projections in the selected generated directory, and apply re-verifies plan identity before Ansible execution.
- 2026-07-28 — Added Forgejo legacy domain/server-name aliases with hostname normalization to canonical public-name lists; incomplete mappings remain fail-closed.
- 2026-07-28 — Added metadata-only SOPS/age availability checks for encrypted bundle, executable, external key-file, and optional recipient policy prerequisites; no decryption or secret delivery occurs.
- 2026-07-28 — Added recursive sensitive-field rejection to non-secret projections so obvious password/token/secret/key/credential fields fail closed before artifact generation.
- 2026-07-28 — Extended the projection boundary to fail closed on non-empty opaque runtime cloud-init/users maps while preserving ordinary scaffold service configuration.
- 2026-07-28 — Added canonical service endpoint schema validation: protocols normalize to lowercase and must be unique; ports must be within 1–65535.
- 2026-07-28 — Added report-only `SERVER_NAME` discovery mapping to normalized Technitium public names; conflicts remain fail-closed and no candidate generation is enabled.
- 2026-07-28 — Added public `.sops.yaml` path policy for canonical site bundles with an explicit non-operational recipient placeholder; preflight does not yet consume it.
