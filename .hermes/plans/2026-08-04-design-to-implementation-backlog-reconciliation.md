# Design-to-Implementation Backlog Reconciliation Plan

**Status:** Proposed
**Date:** 2026-08-04
**Repository:** `infra-fabric`
**Baseline branch:** `feat/canonical-values-model`
**Baseline commit:** `f5b4b48192f3ff36771f3c8e14528e6bcd904407`

## Purpose

Create one evidence-backed account of every requirement, task, acceptance criterion, deferral, blocker, and open question in the repository's design and implementation documents. Reconcile each item against current source, tests, operator documentation, and available verification evidence, then publish a prioritized implementation backlog without falsely marking work complete from code presence alone.

This plan produces the reconciliation and backlog. It does not itself authorize infrastructure mutation, private-value inspection, provider planning, apply, destroy, restore, state operations, or live-service changes.

## Desired outcome

At completion, the repository has:

1. one machine-readable reconciliation ledger containing every in-scope design/backlog item;
2. one human-readable current backlog grouped by priority, domain, and dependency;
3. an explicit disposition for every source item;
4. current source documents whose statuses accurately distinguish implemented code from static, provider-backed, live, and recovery evidence;
5. a documentation inventory that distinguishes current authority, working design, superseded material, historical evidence, and operator guidance;
6. no contradictory claims that the same capability is simultaneously complete, partial, deferred, or absent without an explained scope boundary;
7. verification that every source item is represented exactly once in the ledger or explicitly excluded with a reason.

## Non-goals

- Implementing the reconciled backlog.
- Editing private site values or decrypting SOPS bundles.
- Running provider-backed plans, applies, destroys, restores, imports, or state surgery.
- Declaring live acceptance complete from source inspection or public fixtures.
- Deleting historical evidence before its useful decisions and unresolved items are absorbed.
- Converting generated projections or reports into new authoring authorities.
- Rewriting every historical document into current prose; stale documents may instead be classified and retained as historical evidence.

## Safety and evidence rules

1. Follow `AGENTS.md`; all outputs remain public-safe and value-free.
2. Treat document checkboxes and status lines as claims to verify, not evidence.
3. Treat code presence as implementation evidence only; it does not prove provider, live, idempotence, rollback, or recovery acceptance.
4. Use the evidence levels below consistently:
   - `design`: requirement or decision exists;
   - `implemented-static`: production path exists and static/unit/contract evidence passes;
   - `provider-verified`: a provider-backed plan or equivalent external integration was reviewed;
   - `live-verified`: direct service/host acceptance passed;
   - `recovery-verified`: backup/restore or rollback rehearsal passed.
5. Never upgrade an item's evidence level without a cited artifact or freshly executed check.
6. Private/live evidence that cannot be inspected remains `evidence-required`; it is not inferred from documentation.
7. Preserve OpenTofu/Ansible ownership boundaries and canonical `site.yaml` authority.
8. Execute reconciliation in coherent domain waves. Do not update source trackers until the corresponding wave has a complete ledger and verification boundary.

## Known baseline

The initial document scan found several trackers whose status claims are not yet reconciled:

| Document | Lexical tracker state | Important caveat |
| --- | --- | --- |
| `.hermes/plans/canonical-values-model-implementation.md` | 125 checkbox items: 45 open, 27 checked, 53 partial | Last updated 2026-08-02; status still lists migration, equivalence, recovery, cutover, and compatibility work. |
| `.hermes/plans/hermes-control-integration.md` | 31 open items | Status says implementation in progress; current source contains some implementation. |
| `.hermes/plans/upstream-capability-adoption.md` | 29 open items | Status says implementation in progress; current source contains adopted capabilities. |
| `docs/canonical-values-mapping-v1.md` | Status says incomplete/W3 partial | Classified as `architecture-current` despite being a working draft. |
| `docs/normalized-plan-equivalence.md` | Provider adapter implemented; provider-backed acceptance remains site-specific | Must not be interpreted as full equivalence acceptance. |
| `docs/hermes-operator-pilot-prd.md` | Active design with remaining integration and approval scope | Contains outstanding audit persistence, live search validation, and open decisions. |
| `.hermes/plans/site-aware-values-migration.md` | Status says implemented | Describes a legacy `site.json` architecture now partly superseded by canonical `site.yaml`. |

The committed comprehensive audit at `.hermes/plans/2026-08-04-comprehensive-project-audit.md` is a seed source for defects and improvement opportunities, not a replacement for source-item reconciliation.

## Source universe

### Primary decision and implementation sources

- `.hermes/plans/canonical-values-model-prd.md`
- `.hermes/plans/canonical-values-model-implementation.md`
- `.hermes/plans/site-aware-values-migration.md`
- `.hermes/plans/hermes-control-integration.md`
- `.hermes/plans/upstream-capability-adoption.md`
- `.hermes/plans/2026-08-03_071330-canonical-cutover-audit.md`
- `.hermes/plans/2026-08-03_071330-canonical-cutover-audit-report.md`
- `.hermes/plans/2026-08-03_135649-canonical-first-documentation-and-authoring.md`
- `.hermes/plans/2026-08-03_174531-super-simple-software-factory-vm.md`
- `docs/canonical-values-mapping-v1.md`
- `docs/canonical-values-model-blockers.md`
- `docs/canonical-values-migration.md`
- `docs/normalized-plan-equivalence.md`
- `docs/hermes-operator-pilot-prd.md`

### Current authority and contract sources

- `AGENTS.md`
- `README.md`
- `docs/README.md`
- `docs/documentation-inventory.json`
- `docs/canonical-architecture.md`
- `docs/canonical-service-authoring.md`
- `docs/canonical-readiness.md`
- `docs/service-catalog.md`
- `infra/services.json`
- `scripts/canonical_values.py`
- `scripts/canonical_projections.py`
- `scripts/service_catalog.py`
- `scripts/verify-projections.py`
- `scripts/tfplan-metadata.py`
- `scripts/plan-infra.sh`
- `scripts/apply-infra.sh`
- `scripts/apply-ansible-services.py`
- `scripts/service-state.sh`
- `infra/opentofu/`
- `infra/ansible/`
- `tests/`
- `.github/workflows/validate.yml`

### Source-discovery rule

Before extraction, enumerate all tracked Markdown and structured planning files and identify references among them. Add any document containing a decision, requirement, checklist, acceptance criterion, deferral, blocker, or open question to the source register. Do not assume the list above is exhaustive.

## Reconciliation ledger contract

Create a machine-readable ledger at:

```text
.hermes/reconciliation/design-implementation-ledger.json
```

Each record must contain:

```json
{
  "id": "stable-domain-id",
  "source": {
    "path": ".hermes/plans/example.md",
    "section": "Exact heading",
    "line": 123,
    "kind": "requirement|task|acceptance|decision|deferral|blocker|open-question|finding"
  },
  "summary": "Value-free normalized statement",
  "domain": "canonical-model|catalog|projection|migration|secrets|opentofu|ansible|state|service|documentation|tooling|ci|operator",
  "scope": "repository|site-specific|service-specific|provider-specific|live-only",
  "disposition": "verified-implemented|implemented-unverified|partial|outstanding|blocked-external|intentionally-deferred|superseded|duplicate|not-applicable|stale-claim",
  "evidence_level": "design|implemented-static|provider-verified|live-verified|recovery-verified",
  "evidence": [
    {"path": "path/to/code-or-test", "lines": "10-20", "claim": "what this evidence proves"}
  ],
  "missing_evidence": ["specific acceptance still required"],
  "superseded_by": ["other-ledger-id"],
  "duplicates": ["other-ledger-id"],
  "dependencies": ["other-ledger-id"],
  "priority": "critical|high|medium|low|none",
  "recommended_action": "implement|verify|document|decide|archive|none",
  "target_artifact": "file, issue, or acceptance evidence to produce",
  "notes": "scope distinction or contradiction explanation"
}
```

### Ledger invariants

- IDs are stable across reruns and derived from domain plus normalized requirement identity, not line number alone.
- Every in-scope source item maps to exactly one primary ledger record.
- Duplicate source statements link to one primary record rather than becoming independent backlog items.
- `verified-implemented` requires cited production code and passing relevant verification.
- `implemented-unverified` is used when code exists but the required provider/live/recovery evidence does not.
- `superseded` requires a cited replacement decision or contract.
- `not-applicable` requires a reason; it must not be used to hide unfinished work.
- `stale-claim` marks status prose that contradicts current evidence; it is not a capability disposition.
- No record contains private values, endpoints, identities, state, plan contents, or decrypted material.

## Work plan

### Phase 0 — Freeze scope and establish reproducible inventory

**Goal:** Create a complete, immutable source register at the selected commit.

Tasks:

1. Record branch, commit, upstream divergence, and clean/dirty state.
2. Enumerate tracked Markdown, JSON inventories, and planning artifacts.
3. Parse document links to discover referenced plans, PRDs, reports, and trackers.
4. Record each document's stated status, last-updated date, authority classification, checkbox counts, and linked successor/predecessor.
5. Classify each document provisionally as:
   - current authority;
   - current operator guidance;
   - active implementation tracker;
   - working design;
   - acceptance evidence;
   - superseded design;
   - historical report.
6. Add a source-register manifest with SHA-256 hashes so later edits cannot silently change the extraction baseline.

Outputs:

- `.hermes/reconciliation/source-register.json`
- `.hermes/reconciliation/source-register.md`

Verification gate:

- Every tracked document with status/checklist/decision language is included or explicitly excluded.
- Every path in `docs/documentation-inventory.json` is represented.
- Every link from a primary tracker to a PRD or implementation plan resolves.
- Source hashes reproduce from the baseline commit.

### Phase 1 — Extract every backlog-bearing statement

**Goal:** Produce a lossless normalized inventory before deciding current status.

Tasks:

1. Extract:
   - Markdown checkboxes;
   - workstream/phase status rows;
   - definition-of-done and success criteria;
   - acceptance criteria;
   - `remaining`, `partial`, `deferred`, `blocked`, and `outstanding` prose;
   - open questions and unresolved decisions;
   - audit findings and remediation requirements;
   - compatibility-removal and migration exit gates.
2. Split compound checklist lines only when they have independently verifiable outcomes.
3. Preserve source location and original scope while writing a value-free normalized summary.
4. Assign provisional domain and source kind.
5. Generate a coverage report showing source item counts by document and extraction method.
6. Manually review documents with prose-only backlogs, especially PRDs and audit reports.

Outputs:

- Initial `.hermes/reconciliation/design-implementation-ledger.json`
- `.hermes/reconciliation/extraction-coverage.md`

Verification gate:

- Every literal checkbox is represented.
- Every definition-of-done/success/acceptance criterion is represented.
- Every explicit deferral, blocker, and open question is represented.
- A manual review sample from every source document matches source text and scope.
- No status/disposition beyond `unreconciled` is assigned during extraction.

### Phase 2 — Normalize identity, duplicates, and supersession

**Goal:** Turn overlapping documents into one requirement graph without losing provenance.

Tasks:

1. Group records by semantic identity, not wording.
2. Choose one primary record for each capability or decision.
3. Link duplicate statements from PRDs, implementation plans, audits, and operator docs.
4. Identify supersession chains, including:
   - `site.json` design versus canonical `site.yaml`;
   - legacy settings/tfvars/inventory authority versus projections;
   - early secret namespaces versus catalog-owned current paths;
   - temporary onramp/SearXNG ownership versus target app-platform ownership;
   - report-only or optional plan equivalence versus required acceptance.
5. Flag contradictory status claims for adjudication rather than selecting the newest statement automatically.
6. Record unresolved product decisions separately from implementation tasks.

Outputs:

- Deduplicated ledger with `duplicates` and `superseded_by`
- `.hermes/reconciliation/contradiction-register.md`

Verification gate:

- No duplicate is deleted; all source provenance remains reachable.
- Every superseded item cites its replacement.
- Contradictions are explicit and value-free.
- Stable IDs remain unchanged after line movement.

### Phase 3 — Evidence reconciliation by domain waves

**Goal:** Assign dispositions using current implementation and verification evidence.

Each wave must finish production-path tracing, failure-path tracing, tests, docs, and evidence-level classification before moving to the next wave.

#### Wave 3A — Canonical model, catalog, mappings, and projections

Trace:

- schema/model coverage;
- catalog service coverage and dependencies;
- configuration/override ownership;
- canonical-to-OpenTofu/Ansible/DNS projection parity;
- manifest identity and permissions;
- mapping-matrix completeness;
- stale compatibility names and silent defaults.

Primary sources:

- Canonical PRD and implementation W1/W3/W5 items.
- Mapping matrix.
- Service-authoring and catalog contracts.
- Comprehensive audit H1, H6, M6, M7, M16.

Required evidence:

- source paths;
- catalog/model/projection tests;
- projection key-set and consumer parity checks;
- explicit `implemented-unverified` where live consumer evidence is absent.

#### Wave 3B — Secrets, SOPS policy, migration, and protected delivery

Trace:

- logical namespace authority;
- provider/operator/bootstrap/service secret paths;
- SOPS recipient policy;
- preflight completeness;
- service-scoped delivery;
- migration transformations, conflict handling, and rollback;
- no-log/redaction/cleanup behavior.

Primary sources:

- PRD secret contract.
- Implementation W2/W4.
- Cutover audit and report.
- Secret operations documentation.
- Comprehensive audit H7, H10, M10, M11, M13.

Required evidence:

- exact path-contract parity tests;
- negative delivery tests;
- dry-run migration tests;
- private/live evidence left as explicit acceptance backlog.

#### Wave 3C — OpenTofu, plan/apply, state, destruction, and equivalence

Trace:

- provider/version and artifact integrity;
- resource enablement and address stability;
- variable completeness and module validation;
- saved-plan identity and TOCTOU boundaries;
- destructive/stateful gates;
- teardown workflow;
- local state locking, backup, and recovery;
- normalized plan equivalence and provider-backed acceptance.

Primary sources:

- Implementation W5/W6/W7/W8.
- Normalized plan-equivalence contract.
- Site-aware migration.
- Comprehensive audit H1, H2, H6, H8, H12, M3, M6, M15, L7.

Required evidence:

- static/unit/contract tests and OpenTofu validation;
- no claim of provider equivalence without reviewed provider artifacts;
- no claim of recovery completion without restore rehearsal.

#### Wave 3D — Ansible, service orchestration, identity, and recovery

Trace:

- direct-service ownership and inventory/vars pairing;
- service dependency and shared-host serialization;
- host identity, sudo, SSH key rotation, password hashing, and root-recovery boundaries;
- idempotence, handlers, tags, and check mode;
- role argument specs and secret annotations;
- service-state backup/restore reachability and acceptance;
- runtime installer and image integrity;
- disabled/retained service behavior.

Primary sources:

- Host contract and implementation W5/W7.
- Upstream capability adoption plan.
- SSSF plan.
- Hermes Control plan.
- Comprehensive audit H3, H4, H9, H11, M1, M4, M5, M12, M13, M14, M18.

Required evidence:

- role/playbook/catalog mapping;
- syntax/lint/focused tests;
- second-run and recovery items remain unverified without live evidence.

#### Wave 3E — Operator experience, documentation, updates, and Hermes operator pilot

Trace:

- setup/edit-secrets/SSH initialize/validate/plan/apply sequence;
- fresh-site bootstrapping;
- update target parity and output;
- migration/recovery documentation;
- service operations coverage;
- Hermes operator actions, approval semantics, audit persistence, and backend validation;
- temporary onramp ownership and handoff criteria;
- documentation authority and discoverability.

Primary sources:

- Documentation/authoring plan.
- Hermes operator PRD.
- Hermes Control integration plan.
- Canonical migration docs.
- Comprehensive audit H5, H8, M1, M2, M9, L1, L2, L5, L6, L8.

Required evidence:

- command/help tests;
- installed-scaffold link tests;
- source versus rendered documentation checks;
- product questions retained as decisions, not implementation defects.

#### Wave 3F — CI, tooling, quality, and supply chain

Trace:

- clean-checkout reproducibility;
- base image/package/Python lock integrity;
- architecture support;
- SBOM/advisory scanning;
- Python format/lint/type/coverage gates;
- generated cache/ownership side effects;
- source-text versus behavioral tests;
- scheduled/manual verification.

Primary sources:

- Upstream capability adoption plan.
- Development environment docs.
- Comprehensive audit M8, M17, L3, L4, L8.

Required evidence:

- clean detached-worktree validation;
- exact CI workflow coverage;
- clear distinction between static CI and private/live acceptance.

Wave output:

- Ledger records with final evidence-backed dispositions for the completed domain.
- One wave report under `.hermes/reconciliation/waves/` containing decisions, evidence, unresolved items, and verification commands.

Wave verification gate:

- Every assigned disposition has cited evidence.
- Every `verified-implemented` item passes the relevant current verification.
- Missing provider/live/recovery evidence is retained explicitly.
- Source trackers are not edited until all six waves are complete.

### Phase 4 — Adjudicate contradictions and outstanding decisions

**Goal:** Resolve status conflicts that cannot be settled by implementation evidence alone.

Tasks:

1. Separate factual implementation discrepancies from product/architecture decisions.
2. Prepare a decision register for questions such as:
   - target ownership and retirement of temporary `searxng_onramp`;
   - Hermes operator apply/Forgejo workflow semantics;
   - minimum durable audit trail;
   - supported tooling architectures;
   - local-state single-controller policy versus remote backend;
   - compatibility-window end criteria;
   - provider-backed acceptance sites and evidence retention.
3. For each decision, provide options, trade-offs, default recommendation, affected ledger IDs, and blocking relationships.
4. Obtain operator decisions before marking dependent records actionable.
5. Record decisions in the authoritative design document and ledger; do not bury them only in chat or an audit report.

Outputs:

- `.hermes/reconciliation/decision-register.md`
- Updated ledger dependencies/dispositions

Verification gate:

- Every unresolved product question is either decided, intentionally deferred with owner/trigger, or marked blocked.
- No implementation task depends on an unstated decision.

### Phase 5 — Produce the canonical backlog and dependency graph

**Goal:** Convert the reconciled ledger into executable implementation packages.

Tasks:

1. Filter records whose recommended action is `implement`, `verify`, `document`, or `decide`.
2. Prioritize using:
   - safety/data-loss/secret exposure;
   - broken documented workflows;
   - canonical-authority violations;
   - blockers to provider/live/recovery acceptance;
   - reliability and reproducibility;
   - maintainability and documentation quality.
3. Group work into cohesive packages containing producer, consumers, failure paths, tests, docs, and verification.
4. Define dependencies and a frontier of immediately actionable packages.
5. Keep acceptance-only work separate from source implementation.
6. For each package record:
   - objective;
   - included ledger IDs;
   - affected files/contracts;
   - completion criteria;
   - required evidence level;
   - verification commands;
   - rollback/safety constraints;
   - explicit non-goals.
7. Ensure the comprehensive audit's findings are either represented in the backlog or dispositioned with evidence.

Outputs:

- `docs/design-implementation-backlog.md`
- `.hermes/reconciliation/backlog.json`
- `.hermes/reconciliation/dependency-graph.md`

Verification gate:

- Every outstanding/partial/blocked/evidence-required ledger item appears in exactly one package or decision.
- Every audit finding has a linked disposition.
- No package is an arbitrary file slice; each is a complete contract boundary.
- The dependency graph is acyclic.

### Phase 6 — Update and classify source documents

**Goal:** Make repository documentation tell one coherent story after reconciliation.

Tasks:

1. Expand `docs/documentation-inventory.json` classifications to include:
   - `operator-current`;
   - `contributor-current`;
   - `architecture-current`;
   - `working-design`;
   - `implementation-tracker`;
   - `acceptance-evidence`;
   - `historical-reference`;
   - `superseded`.
2. Update status headers in active trackers from ledger evidence.
3. Replace stale checkbox states only after cited evidence exists.
4. Add a reconciliation link to each active source document.
5. Mark superseded documents and point to their successor; preserve useful decision history.
6. Remove contradictory completion prose or narrow it to the verified scope/evidence level.
7. Update `docs/README.md` with clearly separated current operations, current architecture, active designs, trackers, and historical evidence.
8. Add documentation-contract tests for classification completeness and forbidden ambiguous states.

Outputs:

- Updated source trackers/statuses
- Updated `docs/documentation-inventory.json`
- Updated `docs/README.md`
- Documentation contract tests

Verification gate:

- Every tracked Markdown file has exactly one authority classification.
- No incomplete tracker is labeled unqualified `architecture-current`.
- Status headers agree with ledger dispositions.
- Working designs remain discoverable but cannot be mistaken for operator truth.

### Phase 7 — Reconciliation verification and publication

**Goal:** Prove the reconciliation is complete, reproducible, and internally consistent.

Tasks:

1. Add a validator, for example `scripts/validate-design-reconciliation.py`, that checks:
   - source-register paths and hashes;
   - source-item coverage;
   - stable unique IDs;
   - valid disposition/evidence enums;
   - evidence paths and line ranges;
   - duplicate/supersession/dependency references;
   - no dependency cycles;
   - backlog coverage of actionable records;
   - audit-finding coverage;
   - documentation classification coverage.
2. Run focused reconciliation tests.
3. Run public-safety scanning.
4. Run documentation contract tests and relative-link/anchor validation.
5. Run `scripts/validate-public.sh` in a clean detached worktree.
6. Run `git diff --check` and inspect the final diff.
7. Commit reconciliation artifacts in coherent commits by phase or domain wave.

Final acceptance criteria:

- 100% of source items are covered or explicitly excluded with a reason.
- 100% of actionable items appear in the canonical backlog.
- 100% of dispositions have evidence or an explicit missing-evidence statement.
- No unresolved duplicate, contradiction, or dangling dependency remains.
- All current documentation classifications are valid and complete.
- Public validation passes in a clean checkout.
- No private or live values appear in any artifact.
- The final summary distinguishes implemented code, static verification, provider acceptance, live acceptance, and recovery acceptance.

## Proposed implementation packages after reconciliation

The exact backlog must come from the ledger, but the current audit indicates this likely first frontier:

1. **Service-state recovery correctness:** canonical service selection, vars projection, SSSF reachability, restart failures, docs, and recovery tests.
2. **Canonical safety alignment:** stateful destruction classification, Tailscale enablement, complete pre-apply secret validation, and secret namespace unification.
3. **Destructive execution integrity:** metadata-bound teardown, apply lock, immutable execution snapshot, and state backup/locking policy.
4. **Runtime correctness and supply chain:** Hermes Control header, verified Forgejo image, immutable database/cache images, and pinned installers.
5. **Fresh-site operator workflow:** render-before-provider validation, installed scaffold correctness, and executable migration/recovery guidance.
6. **Ansible convergence:** shared-host serialization, idempotence enforcement, credential hashing, argument specs, tags/check mode, and role contract parity.
7. **Contract simplification:** module validation, typed overrides, compatibility surface reduction, and update-policy parity.
8. **Acceptance evidence:** provider equivalence, live convergence, second-run drift, backup/restore rehearsal, and operational cutover evidence.

These are hypotheses until Phase 3 evidence reconciliation and Phase 4 decisions are complete.

## Execution strategy

- Use one branch for reconciliation artifacts; do not mix source fixes into the same commits.
- Complete one domain wave end to end before updating tracker status.
- Commit each completed wave with its ledger changes, wave report, tests, and verification evidence.
- Rebase/fetch before each wave if remote changes land and rerun affected extraction/evidence checks.
- After reconciliation is merged, execute backlog packages through evidence-gated implementation waves; do not reopen the historical trackers as competing backlogs.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Treating checkbox counts as truth | Reconcile every item against code, tests, and evidence levels. |
| Losing provenance during deduplication | Preserve every source link and use one primary ledger record with duplicate edges. |
| Marking code as operationally complete | Separate static, provider, live, and recovery evidence. |
| Reconciliation becoming another stale tracker | Add a validator, stable schema, source hashes, and one canonical backlog output. |
| Expanding into implementation | Keep fixes out of reconciliation commits; record them as packages. |
| Private data leakage | Use value-free summaries and public fixtures only; do not inspect private values. |
| Historical documents remaining misleading | Classify and label them explicitly, with successor links. |
| Product questions blocking technical work invisibly | Maintain a decision register and dependency edges. |
| Remote work invalidating evidence | Rebase/fetch between waves and rerun only affected reconciliation checks plus the final clean suite. |

## Completion handoff

The final handoff must report:

- baseline and final commits;
- source documents and extracted item counts;
- disposition totals;
- evidence-level totals;
- outstanding backlog packages by priority;
- unresolved or deferred decisions;
- documents reclassified or superseded;
- checks run and exact boundaries not verified;
- confirmation that no infrastructure or private values were mutated.
