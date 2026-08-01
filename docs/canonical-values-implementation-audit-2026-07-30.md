# Canonical Site Values Implementation Audit

**Audit date:** 2026-07-30
**Repository:** `infra-fabric`
**Audited commit:** `6bc379e` (`feat: integrate guarded site candidate migration`)
**Scope:** Original Canonical Site Values Model PRD, implementation tracker, current implementation/tests/evidence, and relevant Hermes skills/instruction sets.
**Change boundary:** This audit report and the implementation/deferred-register documentation only. No source, test, skill, or internal instruction file was modified.

## Status reconciliation note

This document is a historical audit baseline, not the current implementation
status. Subsequent commits completed the field-level Ansible inventory parser,
semantic mapping gates, normalized non-secret runtime importer admission,
protected secret delivery, canonical-first operational consumer gating, and
catalog dependency closure. The remaining live boundary is intentionally
narrower: candidate generation still requires selected-source admission without
conflicts, migration and backup/restore acceptance still require private-site
evidence, and semantic pre/post plan equivalence remains report-only. The
current code and focused tests supersede the historical findings below where
they conflict; the PRD acceptance criteria and private-site operational evidence
still supersede both.

## Executive conclusion

The project is **not complete** against the PRD. The current repository contains substantial, tested foundations, but the previous completion framing was not justified because three different evidence layers were treated as equivalent:

1. **Source inventory/classification:** substantially complete. The live checker sees 16 named source files, 182 OpenTofu variables, 9 catalog services, and 378 contextual source identities; 10 are explicitly excluded as generated/operational/retired.
2. **Token-level matrix reconciliation:** currently reports 368 eligible identities matched, 0 unmatched, and 0 ambiguous.
3. **Semantic/runtime implementation:** incomplete. The live checker itself reports `semantic_mapping_status: incomplete`; the mapping matrix has 307 rows; the runtime legacy discovery implementation still treats the complete legacy Ansible inventory as one `<inventory> / unsupported` observation; the default OpenTofu and Ansible consumers remain legacy-authoritative.

The 368/368 result therefore does **not** prove that every source key has a typed canonical owner, normalization/conflict contract, importer path, projection path, and consumer integration. It proves only that the current machine matcher found one matrix-token candidate for each eligible identity.

The corrected baseline is:

- **W0/source inventory and classification:** complete within its explicitly limited scope.
- **W1 canonical model/loader:** partially implemented and tested.
- **W2 secret provider/policy:** partially implemented; operational SOPS/age delivery and consumer-specific delivery remain incomplete.
- **W3 semantic mapping/catalog:** incomplete despite broad token-level reconciliation.
- **W4 importer/migration:** partially implemented; bounded public candidate generation and site integration exist, but complete legacy ingestion, secret-bundle generation, verified backup/restore, and artifact preservation do not.
- **W5 projections/adapters:** partially implemented; canonical projections and opt-in paired Ansible transport exist, but default consumer cutover and parity are not complete.
- **W6 plan/apply/equivalence:** partially implemented; identity and report-only equivalence foundations exist, but full stale-plan and representative plan-equivalence acceptance is not proven.
- **W7/W8 operational cutover/removal:** not started as PRD-complete phases.

## Evidence collected

### Repository state

- `git status --short --branch` was clean before the documentation-only audit edits.
- Latest audited commit was `6bc379e`.
- No infrastructure mutation, migration apply, candidate generation against private values, or consumer cutover was run.

### Live inventory command

Command:

```text
.venv/bin/python scripts/canonical-mapping-inventory.py --repo .
```

Relevant result:

```text
classification_status: classification-complete-with-review-dispositions
inventory_status: complete
semantic_mapping_status: incomplete
consumer_cutover_status: deferred
canonical_projection_authoritative: false
legacy_static_inventory_present: true
legacy_terraform_input_present: true
mapping_matrix.row_count: 307
source_inventory.coverage.opentofu_variables_inventoried: 182
candidate_generation.status: ready
candidate_generation.candidate_generation_allowed: true
```

The `ready` result is a defect in interpretation/contract, not evidence that the project is ready to import all legacy inputs. It is derived from the token-level inventory/matrix gate and does not exercise the runtime discovery adapter or the consumer boundary.

### Focused tests

Command:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest \
  tests.test_legacy_values_discovery \
  tests.test_migrate_values \
  tests.test_migrate_site_values \
  tests.test_migration_backup \
  tests.test_projection_manifest \
  tests.test_secret_provider
```

Result: **87 tests passed**.

This verifies the bounded discovery, migration, backup-helper, projection-manifest, and secret-provider slices. It does not prove PRD-wide importer completion, encrypted secret import, durable backup/restore, consumer cutover, or plan equivalence.

## Findings

### Finding 1 — High: token-level “candidate ready” is inconsistent with semantic incompleteness

**Evidence**

- `scripts/canonical-mapping-inventory.py` reports `candidate_generation_allowed: true` and `semantic_mapping_status: incomplete` in the same output.
- The mapping matrix contains 307 rows while the report describes 378 source identities and 368 eligible inputs.
- `docs/canonical-values-model-blockers.md` previously described canonical mapping as complete and candidate generation as authorized.
- The implementation tracker records historical evidence where candidate generation was blocked, followed by later bounded candidate-generation work, but did not clearly replace the broad status with a current semantic/runtime gate.

**Impact**

A reader can reasonably infer that all eligible legacy inputs are safe to turn into canonical candidates, even though the runtime importer does not consume every classified source key and the semantic gate remains incomplete.

**Correction**

The tracker and deferred register now state that token-level reconciliation is complete only as an inventory result. Candidate generation is limited to the bounded public observation path over an operator-approved canonical base; it is not a complete importer readiness or migration authorization gate.

### Finding 2 — High: the runtime importer does not consume the classified Ansible inventory keys

**Evidence**

- `scripts/legacy_values_discovery.py:264-272` discovers `ansible/inventory/local.yml` but emits exactly one observation: `key: "<inventory>"`, `classification: "unsupported"`, `value_type: "yaml"`.
- The same module’s `DiscoveryReport.candidate_ready` at lines 40-43 rejects any `unknown` or `unsupported` observation.
- `build_candidate_site()` at lines 323-340 overlays only observations classified as `mapped` and skips secrets; it cannot apply the individual inventory fields listed by the inventory/classification report.
- The live inventory report’s Ansible section lists inventory field contracts, but that metadata is not equivalent to a YAML parser/adapter used by legacy discovery.

**Impact**

The broad inventory/classification work is useful design evidence but does not establish an importer path. Treating it as importer coverage was the direct source of the earlier W0 overclaim.

**Required next evidence**

Before inventory-related importer work can be marked complete, each relevant YAML key must have an exact `(source, key, canonical path/owner, normalization, conflict rule, secret rule, consumer projection, test)` record and must be exercised through the actual discovery/importer boundary.

### Finding 3 — High: the deferred register contradicts both the live report and the code boundary

**Evidence**

The former register stated:

- “Canonical mapping complete.”
- “Candidate generation is authorized.”
- “All eligible identities are matched and classified.”

But it also stated that no remaining identity had an approved owner plus verified projection transport and that secret delivery, migration, and cutover remained blocked. Those statements cannot be presented under one unqualified “mapping complete” status.

**Impact**

The document hid the important distinction between classification, matrix-token matching, typed semantic ownership, importer support, and projection/cutover evidence.

**Correction**

The register now uses separate statuses and calls out the semantic/runtime gap explicitly.

### Finding 4 — High: the PRD’s importer acceptance criteria are not met

The PRD requires the importer to support both root and site-aware layouts, produce `site.yaml` and `secrets.sops.yaml`, fail closed on conflicts, preserve unknown values, generate persistent secrets idempotently, create and verify backups before mutation, roll back safely, preserve operational artifacts, prevent cross-site copying, and provide fixtures for idempotence/conflict/dry-run/backup/rollback.

**Current evidence**

- Report-only discovery exists for selected dotenv, tfvars, JSON, and artifact metadata.
- Root/site-aware report-only parity tests exist.
- Bounded public candidate generation overlays mapped public observations onto an approved base and omits secrets.
- Site migration performs pre-mutation discovery/candidate construction and can write a mode-0600 `site.yaml`.
- Existing migration rollback restores moved files and root settings after an apply failure.

**Missing or incomplete**

- Complete field-level Ansible inventory ingestion.
- Complete semantic mapping coverage and importer support.
- Encrypted `secrets.sops.yaml` generation and operational recipient/key policy.
- Verified durable backup creation/restore integrated into the migration caller.
- Full preservation/migration semantics for state, known hosts, plans, backups, and private artifacts.
- Complete both-layout acceptance evidence against the PRD’s backup/restore and idempotence requirements.

### Finding 5 — High: PRD consumer cutover and plan-equivalence success criteria are not met

The PRD requires Ansible inventory, OpenTofu inputs, DNS records, and runtime delivery to derive from one normalized identity-bound snapshot, with exact plan/apply binding and semantic pre/post migration equivalence.

**Current evidence**

- Canonical model, projection, manifest, and identity helpers exist.
- Canonical DNS transport and opt-in paired Ansible inventory/vars transport have been implemented with fail-closed mixed-authority checks.
- The live report explicitly says `canonical_projection_authoritative: false`, `cutover_status: deferred`, and legacy static inventory/Terraform inputs remain present.

**Missing or incomplete**

- Default OpenTofu and Ansible invocation cutover.
- Complete runtime dotenv projection and delivery.
- Full canonical secret delivery to permitted consumers.
- Representative pre/post migration plan-equivalence evidence under the PRD oracle.
- Stale-plan rejection for every relevant source, secret, renderer, projection, and tool change.
- Operational validation using the selected-site `just validate`, reviewed plan, approved apply, repeat plan, health, backup/restore, rollback, and cleanup process.

### Finding 6 — Medium: the tracker contains historical evidence that is individually useful but misleading in aggregate

The tracker preserves a long evidence history with changing counts: 387, 368, 365/19/1, 370/14/1, and finally 378/368/0/0. This is valuable history, but the current status did not clearly label older counts as superseded or distinguish report shape changes from implementation completion.

**Impact**

A reader can mistake the latest aggregate count for proof that all prior blockers were implemented rather than reclassified.

**Correction**

The tracker now adds an audit baseline and a status-authority note: current live evidence must be rerun; historical counts are not current status; token-level matching cannot close W3/W4/W5.

### Finding 7 — Medium: several design decisions are documented, but the tracker’s `[x]` decision status can be mistaken for operational implementation

The PRD requires exact implementation-design decisions for SOPS/age integration, key discovery, temporary paths/cleanup, secret inventory/state exposure, caller cutover, backup transport, and compatibility removal criteria before the affected phase. The tracker records these decisions, which is good, but `[x]` in the decision table means “decision recorded,” not “the corresponding implementation is complete.”

The tracker now states this distinction explicitly. W2/W4/W5/W6 implementation statuses remain partial where the code or operational evidence is partial.

## PRD-to-tracker alignment

| PRD requirement | Tracker representation | Current evidence | Correct status |
| --- | --- | --- | --- |
| One authoritative `site.yaml` and encrypted `secrets.sops.yaml` per site | Scope, definition of done, W4/W7 | Public canonical fixture and bounded `site.yaml` candidate path; no complete encrypted secret import | Partial |
| Strict canonical schema and loader | W1 | Strict validation, digest, redaction, identity tests | Partial: full service/runtime/catalog fixture coverage remains open |
| SOPS/age secret model and delivery | W2 | Provider boundary, metadata checks, logical paths, protected temporary helpers | Partial/blocked: no complete operational secret delivery contract exercised |
| Both legacy root and site-aware importer | W4 | Report-only discovery and migration helpers for bounded inputs/layouts | Partial: complete field ingestion, artifact semantics, backup/restore, and encrypted secrets remain open |
| Conflict failure, normalization, unknown preservation, idempotence | W3/W4 | Narrow conflict tests and report-only artifact metadata | Partial: not proven for the complete source set and mutation workflow |
| OpenTofu projection | W5 | Non-secret projection and selected plan refresh | Partial: full invocation authority and secret/state boundary remain open |
| Ansible projection from canonical model | W5 | Canonical inventory/vars helpers and opt-in paired invocation | Partial: default remains legacy and parity/cutover evidence is incomplete |
| Runtime dotenv projection | W5 | No PRD-complete runtime delivery evidence | Not complete |
| DNS projection/provider path | W5 | Canonical DNS model/projection and selected Ansible transport | Partial: provider delivery and full cutover remain open |
| Identity-bound plan/apply | W6 | Model/projection manifest identity checks at selected boundaries | Partial: complete stale-plan and both-consumer enforcement not proven |
| Semantic plan equivalence | W6 | Report-only normalized comparator/fixtures | Not complete as acceptance evidence |
| Verified backup/restore and rollback | W4/W7 | Backup manifest helper and file-move rollback | Partial: durable verified backup/restore not integrated/rehearsed |
| Operational cutover | W7 | Explicitly unchecked | Not started |
| Compatibility removal | W8 | Explicitly unchecked | Not started |

## What is genuinely complete or strongly evidenced

These are bounded claims, not project-completion claims:

- Canonical schema foundations, strict YAML/model checks, site identity/path protection, normalization, digesting, and redacted summaries.
- Public-safe service catalog/dependency validation foundations.
- Value-free secret-provider metadata and logical-path boundaries; no claim of complete operational SOPS/age delivery.
- Public-safe report-only legacy discovery and CLI restrictions.
- Fail-closed conflict handling for the currently mapped discovery subset.
- Artifact metadata discovery with containment and symlink rejection.
- Projection manifest integrity and selected canonical preflight.
- Canonical DNS model/projection foundations and selected transport verification.
- Opt-in paired Ansible compatibility transport with mixed-authority rejection; default legacy authority remains active.
- Bounded public candidate generation from an approved canonical base, with secret omission and mode-0600 output.
- Site migration’s pre-mutation candidate construction and existing file-move rollback behavior.

## Current blockers and missing acceptance evidence

1. Exact source-key reconciliation through the runtime importer, especially legacy Ansible inventory.
2. Complete typed catalog/schema/projection coverage for all PRD-supported service/runtime/resource contracts.
3. Operational SOPS/age executable, recipient, key transport, encrypted bundle generation, and consumer-delivery evidence.
4. Durable verified backup/restore integrated with migration and rehearsed in a disposable restore.
5. Complete artifact/state/known-host/plan migration policy and tests.
6. Runtime dotenv generation and cleanup across all failure paths.
7. Default OpenTofu/Ansible canonical authority and same-snapshot enforcement.
8. Representative plan-equivalence and stale-plan acceptance evidence.
9. W7 operational workflow and W8 compatibility-removal evidence.

## Hermes skills and instruction-set audit

### Instructions that likely contributed to circular confusion

The relevant skills contain valuable safeguards, but they also contain tensions that can produce oscillation or false progress if not resolved:

1. **Proceed-through-backlog versus decision-gate language.** The canonical-values skill says not to turn scope boundaries into a work stoppage and to continue through safe batches, but elsewhere requires stopping after bounded assessments for an explicit decision gate. Without an explicit mode switch, this can alternate between “keep implementing” and “stop for policy.”
2. **Classification versus candidate-readiness language.** The skill correctly says a classification pass does not close the matrix, but it also contains candidate-readiness guidance that can be interpreted as allowing a candidate when all identities have dispositions. The repository’s live report exposes the same ambiguity: token-level readiness is `true` while semantic status is `incomplete`.
3. **Historical/session-specific corrections embedded as durable procedure.** The skill contains numerous lessons from prior sessions, including repeated-verification and backlog-continuation corrections. These are useful, but their density can cause current evidence to be interpreted through old assumptions instead of establishing a fresh authority order.
4. **Repeated verification guidance can compete with substantive audit work.** The fresh-probe rules are appropriate after implementation edits, but an audit request with documentation-only scope should not trigger implementation-style probe loops or imply that a passing bounded probe validates the whole program.
5. **Tracker evidence and live evidence are not given a strict authority hierarchy.** The skills say to inspect the live tracker and inventory, but they do not force a single rule that current code/tests outrank historical tracker prose and that machine token matching cannot override runtime adapter evidence.

### Recommended instruction additions

These additions should be made to the relevant skill/instruction set in a separate, explicitly authorized change; they were **not** applied in this audit because the allowed change scope excludes skill files.

```text
AUDIT MODE

When the user asks for a PRD/tracker/codebase audit:
- freeze implementation and infrastructure mutation;
- modify only files explicitly authorized by the user, normally the audit report and tracker documentation;
- establish the evidence baseline before proposing or applying implementation work;
- do not treat a historical tracker entry, session summary, delegated report, or aggregate inventory count as current completion evidence.

EVIDENCE AUTHORITY

Use this order for completion claims:
1. current PRD acceptance criteria;
2. current code path exercised by the relevant test/probe;
3. current test and command output;
4. current machine-readable inventory, interpreted only within its declared scope;
5. tracker/documentation history;
6. prior assistant summaries or delegated reports.

SEPARATE GATES

Maintain separate gates for:
- source discovery;
- classification/disposition;
- semantic mapping;
- runtime importer support;
- projection support;
- consumer authority/cutover;
- operational backup/secret/rollback evidence.

A gate may not be closed by evidence from a different gate. In particular, token-level matrix matching cannot authorize candidate generation when the runtime importer lacks the corresponding source adapter or when semantic status is incomplete.

COMPLETION CLAIMS

Before saying “complete,” name the exact PRD requirement, code path, tests, command result, and scope. If a report says both “ready” and “semantic incomplete,” preserve the contradiction and default the project-level claim to incomplete until the gate semantics are corrected.
```

## Documentation changes made by this audit

- Added this report: `docs/canonical-values-implementation-audit-2026-07-30.md`.
- Corrected `.hermes/plans/canonical-values-model-implementation.md` to distinguish W0 inventory/classification completion from W3 semantic mapping, W4 importer, and W5 cutover completion; added the current audit baseline and explicit evidence authority.
- Corrected `docs/canonical-values-model-blockers.md` so it no longer presents token-level matching as complete semantic mapping or complete importer authorization.

No source, tests, PRD, skills, or internal instruction files were changed.

## Recommended next decision

Do not begin another implementation slice from the old W0 completion premise. First review and accept this re-baselined audit. The next technical work should be selected from the corrected W3/W4 boundary: exact source-key reconciliation through the actual importer, beginning with the Ansible inventory adapter, while keeping secrets and consumer cutover outside that slice.
