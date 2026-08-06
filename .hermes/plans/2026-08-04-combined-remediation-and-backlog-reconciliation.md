# Combined Backlog Reconciliation and Audit Remediation Plan

**Status:** Approved for source-level execution; infrastructure mutation remains prohibited without separate explicit approval
**Date:** 2026-08-04
**Repository:** `infra-fabric`
**Starting branch:** `feat/canonical-values-model`
**Starting commit:** `f5b4b48192f3ff36771f3c8e14528e6bcd904407`
**Recommended execution model:** `gpt-5.6-terra`

**Implementation progress (2026-08-05):** Packages S2, S3, and O2 are source-complete with focused regression evidence. Package O1 has completed the repository-local HTTPS diagnostics header, structural contract, and role argument-spec work; Hermes Control upstream/repository and live guest acceptance remain separately unverified. O3 now removes the SSSF uv/Pi/Bun remote installers in favor of SHA-256-verified controller-side artifacts, includes managed repository-pin updates, and makes Bun cache acquisition conditional on the visualizer; wider convergence reporting and a unified artifact contract remain open. Q3 now has non-mutating `just update --dry-run` behavior through both repository-owned and canonical update paths; catalog-derived policy/status reporting and end-to-end catalog output coverage remain open. Q1 now derives host-identity root-recovery password salts from canonical site/resource identity; the broader idempotence, tags, and check-mode package remains open. Q2 now validates VM/LXC identity, compute, disk, network, and module-specific extra-disk or mount-path contracts at reusable module boundaries, and constrains the Proxmox provider consistently to the reviewed `~> 0.88` series; projection completeness, aliases, moved-state contracts, and external mapping evidence remain open. S3 includes separate metadata-bound guarded teardown planning/application, immutable execution snapshots, immediate pre-mutation re-verification, local-state snapshot/restore primitives, and single-controller enforcement. External provider/live/recovery acceptance remains unexecuted and is not implied by these source-level statuses.

## Model recommendation

Use **`gpt-5.6-terra`** as the primary execution model. This effort is dominated by repository-scale implementation, shell/Python/Ansible/OpenTofu changes, test repair, evidence tracking, and many cohesive commits. Terra is the better fit for sustained tool-driven engineering execution. This recommendation is based on task fit rather than a repository-specific benchmark of Terra versus Luna.

If a second independent pass is available, use `gpt-5.6-luna` only as a final read-only adversarial reviewer after Terra completes the implementation. Do not split primary ownership between models unless their file scopes and commits are isolated.

## Mission

Complete both of the following as one evidence-gated program:

1. reconcile every outstanding requirement, task, acceptance criterion, deferral, blocker, and open question in the repository's design and implementation documents; and
2. remediate every finding in `.hermes/plans/2026-08-04-comprehensive-project-audit.md`, or record an evidence-backed disposition when a finding requires an operator decision, private-site evidence, provider access, or live/recovery validation.

The result must be one canonical backlog, corrected source and operator workflows, accurate tracker/document statuses, complete regression coverage, and a clean public validation result.

## Required source artifacts

Read these before editing:

- `AGENTS.md`
- `.hermes/plans/2026-08-04-comprehensive-project-audit.md`
- `.hermes/plans/2026-08-04-design-to-implementation-backlog-reconciliation.md`
- `.hermes/plans/canonical-values-model-prd.md`
- `.hermes/plans/canonical-values-model-implementation.md`
- `.hermes/plans/hermes-control-integration.md`
- `.hermes/plans/upstream-capability-adoption.md`
- `.hermes/plans/site-aware-values-migration.md`
- `docs/documentation-inventory.json`
- all current architecture/operator documents referenced by the reconciliation plan

Do not trust the status line or checkboxes in any historical tracker until they have been reconciled against current implementation and evidence.

## Execution authority and stop conditions

### Authorized without further approval

- Read tracked public repository files and Git history.
- Create and update public-safe source, tests, documentation, reconciliation artifacts, and trackers.
- Build the tooling image.
- Run public/static validation, unit tests, lint, formatting, schema checks, shell syntax checks, OpenTofu initialization/format/validate without private values, and Ansible syntax/lint against public fixtures.
- Create clean detached worktrees and disposable public-safe fixtures.
- Commit and push cohesive source-level remediation packages to the current feature branch after verification.

### Not authorized without a separate explicit user instruction

- Inspect ignored/private values or decrypted SOPS content.
- Run provider-backed `just plan` or any OpenTofu refresh against a real site.
- Run apply, destroy, import, state surgery, migration apply, secret editing, restore, or live-service mutation.
- Access real endpoints, credentials, identities, state, plans, backups, or private inventory.
- Mark provider, live, idempotence-on-real-host, backup/restore, or recovery acceptance complete without actual evidence.

### Stop only when

- a required product/architecture decision cannot safely be inferred;
- private/provider/live/recovery evidence is required;
- a command would cross the prohibited mutation boundary;
- remote changes create an unresolvable conflict;
- a verification failure cannot be resolved without weakening a safety contract; or
- the complete source-level phase exit gate is satisfied.

Do not stop after a single commit, report, or focused test. Continue through the next unblocked package.

## Operating rules for the executing agent

1. Work in large cohesive packages, not one-field or one-file slices.
2. Before each package, reread the live tracker, affected source, and current Git diff.
3. Include producer, consumers, failure paths, tests, docs, and tracker evidence in the package.
4. Run focused tests before commit and the clean public suite at milestone gates.
5. Review every delegated diff directly; delegate summaries are not evidence.
6. Commit one coherent package at a time with conventional messages.
7. Push after each milestone group, not after every tiny edit.
8. Update reconciliation/tracker statuses only after current evidence exists.
9. Preserve historical provenance through ledger links; do not erase unresolved requirements.
10. Keep all artifacts public-safe and value-free.

## Durable progress artifacts

Create and maintain:

```text
.hermes/reconciliation/source-register.json
.hermes/reconciliation/source-register.md
.hermes/reconciliation/design-implementation-ledger.json
.hermes/reconciliation/extraction-coverage.md
.hermes/reconciliation/contradiction-register.md
.hermes/reconciliation/decision-register.md
.hermes/reconciliation/backlog.json
.hermes/reconciliation/dependency-graph.md
.hermes/reconciliation/waves/*.md
docs/design-implementation-backlog.md
scripts/validate-design-reconciliation.py
tests/test_design_reconciliation.py
```

The ledger schema and invariants are defined in `.hermes/plans/2026-08-04-design-to-implementation-backlog-reconciliation.md` and are mandatory.

## Program phases

# Phase 0 — Baseline, branch safety, and reconciliation scaffolding

**Goal:** Establish a reproducible source baseline and automated reconciliation contract before changing production behavior.

Tasks:

- [ ] Fetch `origin`, confirm the intended branch, and record divergence.
- [ ] Confirm the two 2026-08-04 plans are present; commit them as a documentation-only baseline if still untracked.
- [ ] Enumerate every tracked backlog-bearing document, including linked plans/PRDs/reports not listed in `docs/documentation-inventory.json`.
- [ ] Generate source hashes and authority/status metadata.
- [ ] Implement the ledger schema and validator skeleton.
- [ ] Extract all checkboxes, acceptance criteria, definitions of done, explicit remaining/partial/deferred/blocked statements, open questions, and audit findings.
- [ ] Add extraction coverage tests.
- [ ] Do not assign completion dispositions yet.

Required verification:

- `python3 -B scripts/validate-design-reconciliation.py --check-extraction`
- focused reconciliation tests;
- public-safety check;
- `git diff --check`.

Commit boundary:

```text
docs: establish design reconciliation ledger
```

Exit gate:

- Every source item and all 38 audit findings have stable ledger identities.
- Extraction coverage is complete and reproducible.
- No production behavior changed.

# Phase 1 — Reconcile authority, duplicates, contradictions, and decisions

**Goal:** Establish one canonical requirement graph before implementation begins.

Tasks:

- [ ] Deduplicate overlapping PRD, tracker, audit, and operator statements without losing source provenance.
- [ ] Record supersession chains, especially `site.json` → `site.yaml`, legacy values → generated projections, old secret namespaces → catalog contracts, and temporary onramp ownership.
- [ ] Classify each document as current authority, operator guidance, active tracker, working design, acceptance evidence, historical reference, or superseded.
- [ ] Populate the contradiction register.
- [ ] Populate the decision register for genuinely unresolved product choices.
- [ ] Mark known source-level defects as `outstanding`, not `unreconciled`.
- [ ] Mark provider/live/recovery acceptance items `implemented-unverified` or `evidence-required` as appropriate.
- [ ] Generate the initial canonical backlog and dependency graph.

Decisions that must not be guessed:

- durable local-state single-controller policy versus remote locking backend;
- final ownership/retirement trigger for temporary `searxng_onramp`;
- Hermes operator local apply versus Forgejo workflow semantics;
- required durable audit trail for operator actions;
- compatibility-window end and legacy-removal authorization;
- provider/live/recovery environments used for final acceptance.

If these decisions block source work, stop with options and affected ledger IDs. Otherwise defer only the dependent acceptance package.

Required verification:

- complete ledger/reference validation;
- no duplicate primary records;
- acyclic dependency graph;
- all audit finding IDs mapped;
- `git diff --check`.

Commit boundary:

```text
docs: reconcile design and implementation backlog
```

Exit gate:

- Every source item has a provisional evidence-backed disposition.
- Every finding maps to one remediation package.
- The next implementation frontier is explicit.

# Phase 2 — Recovery and operator-path hotfixes

**Goal:** Repair workflows where current documentation can cause failed or incomplete recovery and fresh-site operation.

## Package R1 — Canonical service-state recovery correctness

Audit coverage: **H4, M12**, parts of **L1**.

Implement as one contract:

- [ ] Emit one canonical enabled service per line.
- [ ] Derive state-capable targets from catalog/state definitions; remove the shell-maintained allowlist.
- [ ] Include SSSF.
- [ ] Consume the verified paired canonical inventory and Ansible vars projection.
- [ ] Ensure Forgejo PostgreSQL backup cannot silently fall back to SQLite.
- [ ] Fail restore when managed services fail to restart, after attempting all required cleanup/restarts.
- [ ] Correct site-context and site-local archive examples.
- [ ] Add CLI tests for multi-service sites, individual selection, `backup all`, disabled services, SSSF, Forgejo PostgreSQL, and restart failures.
- [ ] Add structural coverage proving every catalog state-capable service is reachable or explicitly exempt.

Safety constraints:

- Tests use disposable local fixtures only.
- Do not run a real backup or restore.
- Preserve restrictive archive permissions and path traversal checks.

Commit boundary:

```text
fix: repair canonical service state workflows
```

## Package R2 — Fresh-site validation and scaffold correctness

Audit coverage: **H5, M2, L2, L5, L8**.

Implement as one operator workflow:

- [ ] Add a non-provider canonical render/verify path for fresh sites.
- [ ] Make `just validate` succeed before provider planning when canonical inputs are structurally complete.
- [ ] Keep generated projections private, complete, atomic, and identity-verified.
- [ ] Ensure failed first render removes invalid generated output.
- [ ] Change documentation inventory tests to enumerate tracked Markdown only.
- [ ] Validate links in the installed scaffold destination.
- [ ] Fix scaffold URLs and document host/tool/architecture prerequisites.
- [ ] Add command-level fresh-site setup → validate tests without provider contact.

Safety constraints:

- Validation must not contact Proxmox or decrypt secrets unless explicitly required by a separate protected-input check.
- Do not turn rendered projections into operator-authored inputs.

Commit boundary:

```text
fix: make fresh site validation provider independent
```

Milestone verification:

- focused recovery/operator tests;
- ShellCheck;
- Ansible syntax/lint for changed playbooks;
- documentation contracts;
- clean detached-worktree `scripts/validate-public.sh`;
- `git diff --check`.

# Phase 3 — Canonical authority, secret, and destructive-execution safety

**Goal:** Remove canonical-authority divergence and close pre-mutation safety gaps.

## Package S1 — Canonical service and stateful ownership

Audit coverage: **H1, H6, M15**, relevant mapping/tracker items.

- [ ] Derive stateful address classification from verified canonical `site.yaml` plus catalog.
- [ ] Classify disable/removal plans for all state-capable services, including non-default services and shared resources.
- [ ] Remove the Tailscale legacy double gate; canonical selection is authoritative.
- [ ] Add canonical enabled/disabled tests for every state-capable service and Tailscale runtime type.
- [ ] Represent retain/destroy acknowledgement at the strongest practical OpenTofu precondition/resource boundary.
- [ ] Document direct OpenTofu execution as unsupported if wrapper-independent enforcement cannot be complete.

Commit boundary:

```text
fix: align resource safety with canonical service authority
```

## Package S2 — Unified secret contract and preflight

Audit coverage: **H7, H10, M10, M11, M13, M16**.

- [x] Select and implement one provider namespace and one operator namespace.
- [x] Update catalog, canonical model, migration, fixtures, docs, and consumers atomically.
- [x] Keep legacy aliases only inside explicit migration/import boundaries and fail on conflicts.
- [x] Derive the complete apply-phase required secret set before mutation: provider, SSH identity, operator password, default and host-specific root passwords, selected service requirements.
- [x] Resolve site-local `.sops.yaml` by default and fail closed under `--require-secrets` when exact recipient policy cannot be established.
- [x] Separate bootstrap/host-identity secret environments from ordinary service subprocess environments.
- [x] Mark every sensitive Ansible argument spec `no_log` and test catalog-to-spec parity.
- [x] Replace arbitrary secret-risk override shapes with typed/catalog-declared allowlists where source ownership is known; retain key scanning only as defense in depth.
- [x] Add negative tests proving unauthorized consumers never receive provider/root/operator secrets.

Safety constraints:

- Never inspect or fabricate private secret values or recipients.
- Use public-safe fake SOPS executables and metadata-only fixtures.
- Error messages remain sanitized.

Commit boundary:

```text
fix: unify canonical secret preflight and delivery
```

## Package S3 — Plan/apply/teardown integrity and state protection

Audit coverage: **H8, H12, M3**, parts of **M15**.

- [x] Implement a metadata-bound destroy planner/apply helper using plan hash, age, site, model/projection digest, Git commit, scope, input hashes, destructive summary, and explicit approval.
- [x] Remove raw destroy/apply commands from operator documentation.
- [x] Hold a site-scoped lock from pre-apply verification through storage preparation, OpenTofu apply, and Ansible orchestration.
- [x] Consume an immutable private execution snapshot of plan, metadata, projections, and protected-input identity.
- [x] Make post-apply verification diagnostic rather than the first drift detection.
- [x] Implement source-level local-state backup primitives: restrictive permissions, checksum, atomic snapshot, retention, and tested restore validation against disposable fixtures.
- [x] Do not choose a remote backend without an approved decision.
- [x] Document/enforce single-controller operation until distributed locking is approved.
- [x] Add race/change tests around verification and use boundaries.

Safety constraints:

- No real plan, apply, destroy, state read, or restore.
- State tests use synthetic disposable files containing no real infrastructure data.

Commit boundary:

```text
fix: bind destructive execution to immutable reviewed inputs
```

Milestone verification:

- focused plan metadata, secret, state, projection, and workflow tests;
- bash syntax and ShellCheck;
- OpenTofu format/validate;
- clean detached-worktree public suite;
- fresh disposable adversarial probes for stale/wrong-site/changed-input paths;
- `git diff --check`.

# Phase 4 — Runtime correctness, orchestration, and immutable artifacts

**Goal:** Fix deterministic runtime failures and unsafe/unreproducible installation paths.

## Package O1 — Hermes Control readiness and role contracts

Audit coverage: **H9, M18**, Hermes Control tracker.

- [x] Correct the HTTPS diagnostics authorization header.
- [x] Add a non-secret structural/render test proving variable use without exposing token contents.
- [x] Add `argument_specs` for Hermes Control and reconcile parent-role inputs.
- [ ] Reconcile all Hermes Control tracker items against current source; implement outstanding source-level tasks that do not require live deployment.
- [ ] Keep live guest and service acceptance explicitly unverified.

Commit boundary:

```text
fix: complete hermes control source contract
```

## Package O2 — Host-aware Ansible scheduling

Audit coverage: **H3, M1**.

- [x] Add a canonical execution-resource key using resource ID/inventory host.
- [x] Serialize services sharing the same execution resource while retaining parallelism across distinct hosts.
- [x] Test onramp applications, independent guests, failures, and dependency ordering.
- [x] Remove, guard, or clearly quarantine `site.yml` so it cannot act as a competing orchestration authority.

Commit boundary:

```text
fix: serialize ansible services by managed host
```

## Package O3 — Immutable runtime and image supply chain

Audit coverage: **H2, H11, M8**, parts of **L3**.

- [x] Require checksum fields whenever the generic VM module downloads an image.
- [x] Prefer verified top-level image acquisition and pass immutable file IDs to modules.
- [x] Ensure Forgejo VM creation always verifies image content.
- [x] Pin Infisical PostgreSQL and Redis images by digest in both deployment modes.
- [x] Replace Tailscale/uv/Pi/Bun network installers with signed repositories or immutable checksum-pinned artifacts.
- [x] Report changes accurately.
- [x] Add an integrity contract test covering every production image and network installer.
- [x] Add managed update paths for newly pinned artifacts.

Commit boundary:

```text
fix: enforce immutable runtime artifacts
```

Milestone verification:

- focused Ansible/catalog/integrity tests;
- rendered Compose validation;
- OpenTofu format/validate;
- Ansible syntax/lint;
- clean public suite;
- `git diff --check`.

# Phase 5 — Convergence, interfaces, and maintainability

**Goal:** Make static validation meaningfully enforce idempotence and typed contracts.

## Package Q1 — Ansible idempotence, credentials, tags, and check mode

Audit coverage: **M4, M5, M14**, parts of **M18**.

- [ ] Re-enable `no-changed-when`; add narrow task-level exceptions.
- [ ] Replace imperative command paths with modules where practical.
- [ ] Correct false `changed_when` reporting.
- [ ] Use stable host-specific password hashes/salts and test second-run behavior.
- [ ] Establish tags: `validation`, `packages`, `config`, `service`, `health`, `backup`, `restore`.
- [ ] Add safe check-mode behavior or explicit skip reasons.
- [ ] Fix the static checker to understand `args.creates/removes`.
- [ ] Add complete argument specs/default/spec/projection parity tests.
- [ ] Document broad provisioning sudo as an intentional trust boundary or narrow it if safely supported.

Commit boundary:

```text
refactor: strengthen ansible convergence contracts
```

## Package Q2 — OpenTofu module and canonical projection contracts

Audit coverage: **M6, M7, L7**, outstanding W1/W3/W5 items.

- [x] Add reusable module validation for VMID, CPU, memory, disk, address/gateway, MAC, VLAN, mount paths, and unique disk interfaces.
- [x] Add projection completeness checks for conditionally required root variables.
- [x] Align the provider compatibility constraint to the reviewed pre-1.0 series.
- [x] Update stale HCL descriptions that direct edits to generated/legacy files.
- [ ] Reduce compatibility aliases through typed resource/service objects without changing resource addresses.
- [x] Preserve moved blocks and add state-address contract tests.
- [ ] Reconcile all mapping-matrix claims against live producers and consumers; do not mark provider/live equivalence complete.

Commit boundary:

```text
refactor: tighten canonical opentofu contracts
```

## Package Q3 — Update workflow parity

Audit coverage: **M9**.

- [x] Process repository-owned tool pins regardless of canonical site mode.
- [x] Derive service release/update status from the catalog.
- [x] Remove stale Technitium output.
- [x] Add end-to-end update dry-run/output tests.
- [x] Ensure newly immutable runtime dependencies participate in managed update policy.

Commit boundary:

```text
fix: align update behavior with declared policy
```

Milestone verification:

- focused Ansible/OpenTofu/update tests;
- full Ansible lint with no broad `no-changed-when` skip;
- OpenTofu format/validate/TFLint;
- clean public suite;
- `git diff --check`.

# Phase 6 — Documentation authority and day-two operations

**Goal:** Ensure operator and contributor documentation accurately reflects implemented and verified behavior.

Audit coverage: **L1-L8**, documentation portions of all high/medium findings.

Tasks:

- [ ] Expand documentation classifications to current authority, operator guidance, working design, implementation tracker, acceptance evidence, historical reference, and superseded.
- [ ] Update status headers and checkboxes from the ledger only after evidence exists.
- [ ] Separate implemented source from provider/live/recovery evidence.
- [ ] Add one service operations page or generated matrix entry for every first-class service: health, logs, credentials, update/rollback, backup, restore verification, and failure recovery.
- [ ] Add executable migration/recovery instructions and explicit compatibility boundaries.
- [ ] Add anchor and command-snippet validation.
- [ ] Add a diagnostic validation mode or named stage summary while retaining fail-fast CI behavior.
- [ ] Clarify supported entry points and prohibit direct `site.yml`/raw OpenTofu lifecycle use.
- [ ] Reclassify stale design documents and link successors without deleting useful history.
- [ ] Reconcile Hermes operator PRD open questions and retain unresolved decisions in the decision register.

Commit boundary:

```text
docs: align operator guidance with verified implementation
```

Exit gate:

- Every tracked Markdown document has one authority classification.
- No unfinished design is labeled unqualified current architecture.
- All public commands and installed scaffold links are tested.
- Every service has discoverable day-two guidance.

# Phase 7 — Tooling, CI, and quality gates

**Goal:** Make clean-checkout validation reproducible, architecture-aware, and capable of detecting dependency and Python quality regressions.

Audit coverage: **M8, M17, L3, L4, L8**.

Tasks:

- [ ] Pin the tooling base image by digest.
- [ ] Generate a hash-locked Python requirements input and install with hash verification.
- [ ] Define apt reproducibility policy or dated snapshot strategy.
- [ ] Support `TARGETARCH` with per-architecture checksums or explicitly enforce/document amd64.
- [ ] Add SBOM generation and dependency/container advisory scanning with a severity/exception policy.
- [ ] Enforce Python format and lint; add typing where practical.
- [ ] Generate coverage and establish an observed, ratcheted threshold.
- [ ] Direct bytecode/cache output outside the source tree.
- [ ] Restrict ownership repair to known public paths; never recurse through private values.
- [ ] Replace critical source-text tests with parsed/rendered/behavioral contracts while retaining useful policy sentinels.
- [ ] Add scheduled/manual read-only verification for dependency and build freshness.
- [ ] Print validation stage boundaries and an end summary.

Commit boundary:

```text
ci: strengthen reproducibility and quality gates
```

Verification:

- no-cache tooling build for supported architecture;
- SBOM/advisory workflow dry run where locally possible;
- Python format/lint/type/coverage;
- full clean public suite;
- workflow syntax review;
- `git diff --check`.

# Phase 8 — Tracker closure and source-level acceptance

**Goal:** Close the source-level program without overstating external acceptance.

Tasks:

- [ ] Re-run reconciliation extraction against the final source tree.
- [ ] Ensure every source item and audit finding has a final disposition.
- [ ] Regenerate the canonical backlog and dependency graph.
- [ ] Update active trackers and documentation statuses from evidence.
- [ ] Mark provider/live/recovery tasks explicitly outstanding where not executed.
- [ ] Run all reconciliation validators and documentation contracts.
- [ ] Run `scripts/validate-public.sh` in a fresh detached worktree.
- [ ] Run public-safety checks and secret-pattern scans.
- [ ] Run `git diff --check` and inspect commit history for coherent packages.
- [ ] Push the completed source-level branch.

Required final report:

- commits and package mapping;
- audit finding disposition table;
- design/backlog item disposition totals;
- static test commands and results;
- provider/live/recovery evidence still missing;
- unresolved decisions and blockers;
- confirmation that no private values or infrastructure were mutated.

Exit gate:

- All source-level remediation packages are complete and green.
- Every audit finding is fixed, superseded, decided, or explicitly evidence-required.
- Every historical backlog item has one ledger disposition.
- The repository exposes one canonical backlog rather than competing trackers.
- External acceptance remains open unless separately authorized and executed.

# Phase 9 — Separately approved external acceptance

**Status:** Not authorized by this plan.

When the operator explicitly approves it in a later session, execute in increasing risk order:

1. provider-backed non-mutating plan/equivalence on a disposable or approved development site;
2. reviewed development apply;
3. direct health and second-run idempotence checks;
4. service-state backup and restore rehearsal;
5. infrastructure-state recovery rehearsal;
6. Hermes operator/live integration validation;
7. production plan and separately approved production apply.

Each step requires its own approval, evidence, rollback plan, and public-safe summary. Do not collapse these into one authorization.

## Audit finding coverage matrix

| Package | Findings |
| --- | --- |
| R1 | H4, M12, part of L1 |
| R2 | H5, M2, L2, L5, L8 |
| S1 | H1, H6, M15 |
| S2 | H7, H10, M10, M11, M13, M16 |
| S3 | H8, H12, M3, part of M15 |
| O1 | H9, M18 |
| O2 | H3, M1 |
| O3 | H2, H11, M8, part of L3 |
| Q1 | M4, M5, M14, part of M18 |
| Q2 | M6, M7, L7 |
| Q3 | M9 |
| Documentation phase | L1, L2, L3, L4, L5, L6, L7, L8 and documentation portions of H/M findings |
| Tooling/CI phase | M8, M17, L3, L4, L8 |

The reconciliation validator must assert that H1-H12, M1-M18, and L1-L8 are all mapped to at least one package and have a final ledger disposition.

## Commit and push strategy

1. Commit the two planning documents first if untracked.
2. Commit Phase 0 and Phase 1 reconciliation artifacts separately from production fixes.
3. Use one commit per coherent package unless a package requires a small follow-up repair after verification.
4. Never mix private/generated artifacts into a commit.
5. Before every commit:
   - inspect the full diff;
   - run relevant focused tests;
   - run `git diff --check`;
   - confirm public safety.
6. Before every milestone push:
   - fetch/reconcile remote changes;
   - run the milestone gate;
   - verify branch/upstream state after push.

## Final definition of done

Source-level remediation is complete only when all of the following are true:

- [ ] All backlog-bearing sources are registered and hashed.
- [ ] Every extracted item has a stable ledger record.
- [ ] Every audit finding has a package and disposition.
- [ ] No unresolved duplicate, supersession, contradiction, or dependency remains.
- [ ] All authorized source-level packages are implemented and verified.
- [ ] All tracked documentation has an accurate authority classification.
- [ ] The canonical backlog is generated and validated.
- [ ] Public safety passes.
- [ ] A clean detached worktree passes the full public suite.
- [ ] No private values, plans, state, credentials, identities, or live endpoints were accessed or emitted.
- [ ] Provider/live/recovery evidence is clearly separated and remains open unless separately approved.
- [ ] All completed work is committed and pushed, with a clean worktree and matching upstream revision.
