# Combined Backlog Reconciliation and Audit Remediation Plan

**Status:** Approved for source-level execution; infrastructure mutation remains prohibited without separate explicit approval
**Date:** 2026-08-04
**Repository:** `infra-fabric`
**Starting branch:** `feat/canonical-values-model`
**Starting commit:** `f5b4b48192f3ff36771f3c8e14528e6bcd904407`
**Recommended execution model:** `gpt-5.6-terra`

**Status reconciliation (2026-08-09, compacted by P10-A):** R1, R2, S1, S2, S3, O1, O2, O3, Q1, Q2, Q3, documentation, and CI are source-complete with current production-path and focused verification evidence in the concise [package completion](../reconciliation/package-completion.md) and [original audit dispositions](../reconciliation/audit-dispositions.md) authorities. This plan's package checkboxes are historical implementation records; where they are checked, that means only the public source contract was completed. Separately approved development acceptance is recorded only in the [environment-specific acceptance matrix](../reconciliation/acceptance-matrix.md): it does not establish isolated recovery or production evidence. The remaining gates are infrastructure/controller recovery, upstream Hermes Control compatibility and live operator acceptance, durable external audit storage, Forgejo monitoring pilot acceptance, Onramp handoff and temporary SearXNG retirement, and all production actions. Phase 9 still requires separate approval for each remaining risk boundary. The [explicit decisions](../reconciliation/explicit-decisions.md) authority records D1–D10; no unresolved decision package remains. The frozen lossless per-claim ledger remains available through the immutable Git reference recorded in package completion. Simplification findings are planning evidence only and do not authorize implementation or external action.

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
- private, provider, live, or recovery evidence is required;
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

## Approved decision record — 2026-08-06

These decisions were reviewed interactively in order. They are design authority for
future work; recording them does not authorize implementation, private-values
mutation, provider contact, live changes, or Phase 9 execution.

- **Decision D1 — State and locking policy.** Keep local state under a designated
   single-controller/single-writer policy. All mutation uses the supported wrappers
   and shared site lock. Read-only work may run elsewhere, but a reviewed
   remote-locking backend is required before enabling a second independent mutation
   controller.
- **Decision D2 — Temporary SearXNG ownership.** `infra-fabric` remains the temporary
   owner of
   `searxng_onramp` until `onramp-vNext` proves deployment, secret delivery, proxy,
   health, rollback, backup/restore, Hermes consumption, development cutover, and
   rollback readiness. Retirement is evidence-triggered rather than date-triggered.
- **Decision D3 — Hermes/Forgejo execution semantics.** Hermes may eventually request
   apply only
   through the designated controller's local `scripts/hermes-operator.py` →
   `just apply` path. Forgejo provides validation and monitoring, not infrastructure
   mutation, while state is local. There must not be two apply authorities.
- **Decision D4 — Durable audit contract.** Mutations require a private
   controller-owned,
   append-only, tamper-evident and externally backed-up audit journal. A mutation
   fails closed unless its sanitized pre-execution record is durable; completion or
   failure uses the same correlation ID. Hermes may not edit or delete audit history.
- **Decision D5 — Compatibility retirement.** Normal setup, validate, plan, apply,
   teardown,
   Ansible, and runtime workflows are canonical-only now. Legacy inputs fail
   explicitly. Bounded forensic discovery/recovery tooling remains quarantined until
   canonical rebuild and recovery acceptance passes and the operator separately
   authorizes permanent removal.
- **Decision D6 — Acceptance environments.** Use separate disposable development,
   isolated
   recovery-rehearsal, and production environment roles. Production derives only
   from its own canonical source and never from development. Destructive recovery
   rehearsal does not run against active production.
- **Decision D7 — First Hermes pilot scope.** The initial pilot is read-only: status,
   validate,
   plan, sanitized summaries, and read-only Forgejo monitoring. `/infra-apply` is a
   separately activated extension only after durable audit, trustworthy approval
   identity, development acceptance, and recovery verification. Private-value writes,
   Git publication, teardown, state surgery, restore, and credential mutation are
   excluded.
- **Decision D8 — Onramp substrate handoff.** Expose a versioned, identity-bound,
   non-secret
   contract for one Debian 13 VM shared-host substrate. `infra-fabric` owns Proxmox
   lifecycle, network, storage, host security, rootless Podman prerequisites, and base
   proxy capability; `onramp-vNext` owns application definitions and lifecycle. It
   receives neither Proxmox authority nor generated-file edit authority.
- **Decision D9 — Future private-values edits.** Hermes and the language model do not
   edit raw
   private files. A post-pilot feature may orchestrate expiring typed proposals whose
   actual values enter through a protected controller-local interface outside
   transcripts. Applying, committing, and pushing the private repository remain
   separate approvals; secret edits remain SOPS-aware protected operations.
- **Decision D10 — Hermes-independent recovery.** Hermes is optional and is recovered
   last. A trusted controller restores reviewed public/private repository identities,
   external identities, state, host trust, audit continuity, and services in
   dependency order, using the same canonical `just` workflows. Primary-audit outage
   requires a protected append-only emergency journal, not unaudited mutation.

Decision-driven follow-up work remains separately authorized:

- document and enforce the single-controller and canonical-only policy boundaries;
- implement durable audit persistence before enabling Hermes apply;
- add read-only Forgejo monitoring and keep the first pilot mutation-disabled;
- define and test the versioned Onramp handoff projection before retiring the
  temporary SearXNG contract;
- design the protected private-values proposal mechanism only after pilot acceptance;
- document and rehearse the Hermes-independent controller recovery procedure; and
- execute the environment-specific evidence sequence only through the separately
  approved Phase 9 gates.

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

- [x] Emit one canonical enabled service per line.
- [x] Derive state-capable targets from catalog/state definitions; remove the shell-maintained allowlist.
- [x] Include SSSF.
- [x] Consume the verified paired canonical inventory and Ansible vars projection.
- [x] Ensure Forgejo PostgreSQL backup cannot silently fall back to SQLite.
- [x] Fail restore when managed services fail to restart, after attempting all required cleanup/restarts.
- [x] Correct site-context and site-local archive examples.
- [x] Add CLI tests for multi-service sites, individual selection, `backup all`, disabled services, SSSF, Forgejo PostgreSQL, and restart failures.
- [x] Add structural coverage proving every catalog state-capable service is reachable or explicitly exempt.

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

- [x] Add a non-provider canonical render/verify path for fresh sites.
- [x] Make `just validate` succeed before provider planning when canonical inputs are structurally complete.
- [x] Keep generated projections private, complete, atomic, and identity-verified.
- [x] Ensure failed first render removes invalid generated output.
- [x] Change documentation inventory tests to enumerate tracked Markdown only.
- [x] Validate links in the installed scaffold destination.
- [x] Fix scaffold URLs and document host/tool/architecture prerequisites.
- [x] Add command-level fresh-site setup → validate tests without provider contact.

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

- [x] Derive stateful address classification from verified canonical `site.yaml` plus catalog.
- [x] Classify disable/removal plans for all state-capable services, including non-default services and shared resources.
- [x] Remove the Tailscale legacy double gate; canonical selection is authoritative.
- [x] Add canonical enabled/disabled tests for every state-capable service and Tailscale runtime type.
- [x] Represent retain/destroy acknowledgement at the strongest practical OpenTofu precondition/resource boundary.
- [x] Document direct OpenTofu execution as unsupported if wrapper-independent enforcement cannot be complete.

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
- [x] Reconcile all Hermes Control tracker items against current source; implement outstanding source-level tasks that do not require live deployment. Typed Control workspace/project-root configuration now has catalog, projection, role-default, argument-spec, rendering, validation, and regression parity.
- [x] Keep live guest and service acceptance explicitly unverified; upstream Hermes Control compatibility, disposable guest lifecycle/plugin/Caddy/DNS/WebSocket smoke checks, and deployed five-state/update verification remain external acceptance gates.

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

- [x] Re-enable `no-changed-when`; add narrow task-level exceptions.
- [x] Replace imperative command paths with modules where practical.
- [x] Correct false `changed_when` reporting.
- [x] Use stable host-specific password hashes/salts and test second-run behavior.
- [x] Establish tags: `validation`, `packages`, `config`, `service`, `health`, `backup`, `restore`.
- [x] Add safe check-mode behavior or explicit skip reasons.
- [x] Fix the static checker to understand `args.creates/removes`.
- [x] Add complete argument specs/default/spec/projection parity tests.
- [x] Document broad provisioning sudo as an intentional trust boundary or narrow it if safely supported.

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
- [x] Reduce compatibility aliases through typed resource/service objects without changing resource addresses.
- [x] Preserve moved blocks and add state-address contract tests.
- [x] Reconcile mapping-matrix source claims against tracked producers and consumers; provider/live equivalence remains explicitly external evidence.

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

- [x] Expand documentation classifications to current authority, operator guidance, working design, implementation tracker, acceptance evidence, historical reference, and superseded.
- [x] Update status headers and checkboxes from the ledger only after evidence exists.
- [x] Separate implemented source from provider/live/recovery evidence.
- [x] Add one service operations page or generated matrix entry for every first-class service: health, logs, credentials, update/rollback, backup, restore verification, and failure recovery.
- [x] Add executable migration/recovery instructions and explicit compatibility boundaries.
- [x] Add anchor and command-snippet validation.
- [x] Add a diagnostic validation mode or named stage summary while retaining fail-fast CI behavior.
- [x] Clarify supported entry points and prohibit direct `site.yml`/raw OpenTofu lifecycle use.
- [x] Reclassify stale design documents and link successors without deleting useful history.
- [x] Reconcile Hermes operator PRD open questions and retain unresolved decisions in the decision register.

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

- [x] Pin the tooling base image by digest.
- [x] Generate hash-locked Python requirements inputs, including pip bootstrap, and install with hash verification.
- [x] Define apt reproducibility policy or dated snapshot strategy.
- [x] Support `TARGETARCH` with per-architecture checksums or explicitly enforce/document amd64.
- [x] Add SBOM generation and dependency/container advisory scanning with a severity/exception policy.
- [x] Enforce ratcheted Python format, repository-wide fatal lint, and scoped typing gates.
- [x] Generate coverage and establish an observed, ratcheted threshold.
- [x] Direct bytecode/cache output outside the source tree.
- [x] Restrict ownership repair to known public paths; never recurse through private values.
- [x] Add parsed, rendered, and behavioral contracts while retaining useful policy sentinels.
- [x] Add scheduled/manual read-only verification for dependency and build freshness.
- [x] Print validation stage boundaries and an end summary.

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

- [x] Re-run reconciliation extraction against the final source tree.
- [x] Ensure every source item and audit finding has a final disposition.
- [x] Regenerate the canonical backlog and dependency graph.
- [x] Update active trackers and documentation statuses from evidence.
- [x] Mark provider/live/recovery tasks explicitly outstanding where not executed.
- [x] Run all reconciliation validators and documentation contracts.
- [x] Run `scripts/validate-public.sh` in a fresh detached worktree.
- [x] Run public-safety checks and secret-pattern scans.
- [x] Run `git diff --check` and inspect commit history for coherent packages.
- [x] Push the completed source-level branch; local and upstream revisions were verified to match after publication.

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

**Status:** Development gates 1–4 completed under separate approval; remaining gates are not authorized by this plan.

When the operator explicitly approves it in a later session, execute in increasing risk order:

1. ~~provider-backed non-mutating plan/equivalence on a disposable or approved development site~~ — completed for disposable `dev`; semantic equivalence remains unclaimed because no prior normalized baseline was supplied;
2. ~~reviewed development apply~~ — completed with provider and Ansible convergence;
3. ~~direct health and second-run idempotence checks~~ — completed, including Forgejo Runner registration and service activity;
4. ~~service-state backup and restore rehearsal~~ — completed for every enabled disposable stateful service, with archive validation and post-restore health evidence;
5. ~~infrastructure-state recovery rehearsal~~ — completed for disposable `dev` on 2026-08-12: verified a controller-local private state snapshot, restored it through the site lock, revalidated the canonical model, and confirmed a fresh provider-backed plan with zero create/update/replace/delete actions; this is development-only evidence and does not establish isolated-recovery or production acceptance;
6. Hermes operator/live integration validation, including external audit durability and approval identity;
7. production plan and separately approved production apply.

Each step requires its own approval, evidence, rollback plan, and public-safe summary. Do not collapse these into one authorization.

### Development infrastructure-state recovery evidence — 2026-08-12

For disposable `dev`, controller-local execution, state, and audit snapshot roots were
verified private and local. A private audit-journal snapshot and a private state snapshot
were each created, verified, and restored through their guarded paths; state restoration
held the selected-site lock. The restored audit chain had no unresolved correlations, the
restored state remained a regular private file, canonical validation passed, and fresh
provider-backed plans before and after canonical convergence reported zero create, update,
replace, and delete actions. All enabled services converged and redacted direct-service
connectivity passed after recovery. This is development-only controller/infrastructure
recovery evidence: it does not establish independent external audit durability, rollback
acceptance, or production acceptance.

### Development Hermes read-only bridge evidence — 2026-08-12

For disposable `dev`, the canonical Ansible convergence installed a root-owned public
operator runtime bundle and a generated non-secret context containing only the selected
site identity and enabled service identifiers. The deployed plugin was invoked as its
runtime user over canonical transport: `status` succeeded using the deployed projection,
and `audit-verify` succeeded against an empty guest-local private journal baseline with
no unresolved correlations. Canonical validation passed, and a fresh provider-backed
plan reported zero create, update, replace, and delete actions. This is development-only
read-only bridge evidence. It does not establish authenticated dashboard/API or WebSocket
acceptance, external audit durability, mutation approval identity, rollback,
isolated-recovery, or production acceptance.

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
4. Never mix private or generated artifacts into a commit.
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

- [x] All backlog-bearing sources are registered and hashed.
- [x] Every extracted item has a stable ledger record.
- [x] Every audit finding has a package and disposition.
- [x] No unresolved duplicate, supersession, contradiction, or dependency remains.
- [x] All authorized source-level packages are implemented and verified.
- [x] All tracked documentation has an accurate authority classification.
- [x] The canonical backlog is generated and validated.
- [x] Public safety passes.
- [x] A fresh detached worktree passes the full public suite.
- [x] No private-value contents, plans, state, credentials, identities, or live endpoints were accessed or emitted; one read-only review traversed private path names without reading contents.
- [x] Provider/live/recovery evidence is clearly separated and remains open unless separately approved.
- [x] The Phase 8 source-level milestone was published and upstream-verified at that
  time; later commits and any future commit or push remain separately gated and are
  not covered by that historical evidence.

# New simplification audit — 2026-08-09

**Status:** Audit complete; the simplification backlog below is proposed source work
only. It does not authorize private-value inspection, provider contact, apply,
teardown, restore, state mutation, production work, or deletion of bounded recovery
tools.

## Audit method and measured baseline

The new audit inspected the current reconciliation generator and tests, generated
artifacts, public `just` surface, lifecycle wrappers, canonical context helpers,
snapshot implementations, documentation statuses, focused test structure, and Git
history/blame. It also reran representative focused suites rather than inferring cost
from file count alone.

Measured observations:

- `.hermes/reconciliation/` contains 25 generated files, 42,144 lines, and
  2,220,059 bytes—38.2% of the tracked repository by bytes.
- The generated ledger contains 919 records, but 807 remain generic
  `evidence-required` source claims even though all 13 implementation packages are
  source-complete. `design-implementation-ledger.json` alone is 1,943,036 bytes.
- Since the reconciliation baseline, generated reconciliation files account for
  53,734 added and 11,590 deleted lines across 106 file touches.
- The generator's frontier rule selects dependency-free packages without considering
  package completion, so it still reports `R2`, `Q3`, and `DECISIONS` as immediate
  source work even though R2/Q3 are source-complete and the decision register contains
  no unresolved question.
- The generator hard-codes every package's external state to `blocked-external`, so it
  cannot represent the completed disposable-development plan/apply/health/idempotence/
  service-restore evidence described by this plan.
- Normal setup, values checking, validation, plan, apply, and container execution still
  contain legacy non-canonical branches despite the approved canonical-only normal
  workflow.
- Bounded legacy discovery/migration implementation and focused tests total about
  8,729 lines. They are intentionally retained until the recovery-removal trigger, but
  should not continue shaping normal runtime paths and should not be refactored merely
  to make them prettier before retirement.
- The three private snapshot implementations total 640 lines and independently
  implement regular-file checks, SHA-256 streaming, private-directory handling,
  atomic staging, manifest writing, and restore/install mechanics.
- An AST-assisted scan identified 165 of 856 tests as candidates that read source text
  and assert strings/order. Not all are defects, but fixed-count reconciliation tests
  and shell-source sentinels duplicate executable behavior coverage and make harmless
  refactors expensive.

## Safety controls that are not over-engineering

The following controls have independent safety value and must not be removed in the
name of simplification:

- one canonical site authoring authority and generated projection identity checks;
- site-scoped locking and the designated single-writer controller boundary;
- saved-plan hash/age/site/model/input verification immediately before mutation;
- immutable execution inputs, pre-apply state snapshots, and separate teardown approval;
- SOPS-aware secret isolation and least-privilege subprocess environments;
- strict host-key verification with independent Proxmox/guest evidence;
- append-only hash-chained operator audit records and fail-closed recovery when audit
  continuity is unavailable; and
- separate approvals for private edits, provider planning, apply, teardown, restore,
  commit, push, production, and recovery actions.

## Simplification findings

### SIMP-H1 — Lossless reconciliation became a permanent shadow system

Evidence: `scripts/validate-design-reconciliation.py:22-108,224-274,363-388`,
`tests/test_design_reconciliation.py:231-315`, and the measured generated-artifact
footprint above.

The lossless ledger was useful while reconciling competing historical trackers, but it
now duplicates Git history, the source register, the package backlog, wave documents,
the audit registry, and the human backlog. Every documentation edit causes broad
generated churn while most records remain generic source claims rather than actionable
work.

Simpler target: freeze the final lossless ledger at its closing commit and remove it
from continuous regeneration. Keep one concise package registry, the 38-finding audit
disposition registry, the explicit decision register, and an environment-specific
acceptance matrix. Git history retains the frozen per-claim provenance. Generate one
short human backlog; remove per-wave files and giant membership lists.

Risk: **CAREFUL**. Preserve a verifiable archival commit and audit-ID mapping before
removing generated files from the active contract.

### SIMP-H2 — Reconciliation status cannot represent the actual frontier

Evidence: `scripts/validate-design-reconciliation.py:265-271`,
`.hermes/reconciliation/dependency-graph.md:43`,
`.hermes/reconciliation/decision-register.md:5-11`, and Phase 9 above.

The current model conflates source completeness with all external environments. It
reports completed dependency-free packages as the frontier and reports all external
states as blocked even after disposable-development evidence passed. This creates a
large, precise-looking status system that is less accurate than the plan prose.

Simpler target: compute source frontier from incomplete source packages only and
replace package-wide `external_status` with a small explicit matrix whose rows are
development, isolated recovery rehearsal, and production and whose columns are plan,
apply, health/idempotence, service restore, infrastructure recovery, Hermes integration,
and rollback. Never infer one environment from another.

Risk: **SAFE** for correcting the generated frontier; **CAREFUL** for replacing the
schema because historical evidence links must remain resolvable.

### SIMP-H3 — Canonical-only policy is not yet canonical-only code

Evidence: `justfile:11-31`, `scripts/values.sh:9-16,59-90,119-128`,
`scripts/validate-values.sh:11-40`, `scripts/run-infra.sh:9-38`,
`scripts/plan-infra.sh:24-26,88-112,133-141`, and
`scripts/apply-infra.sh:29-33,71-107,159-187`.

Normal commands still branch between canonical and legacy values, inventories,
provider environments, and Ansible invocation. That doubles paths through the most
sensitive workflows, preserves obsolete setup choices, and forces tests to protect
behavior the approved clean-rebuild strategy no longer uses.

Simpler target: require `VALUES_SITE` plus `values/sites/<site>/site.yaml` for every
normal command; make `just setup "" <site>` the only setup shape; use only generated
canonical projections in validate/plan/apply/Ansible; and fail explicitly when legacy
inputs appear. Keep any forensic importer behind a separately named recovery-only
entry point with no call edge from normal recipes.

Risk: **CAREFUL**. This is a deliberate compatibility removal and must preserve public
fixtures needed for static validation without presenting them as operator inputs.

### SIMP-M1 — Legacy migration code should be retired, not modernized

Evidence: the bounded discovery/migration files and tests measured above, Decision D5,
and the approved clean-rebuild strategy.

The legacy subsystem is large, but refactoring its 8,729 lines into newer abstractions
would spend effort on a path with an explicit removal trigger. Its continued existence
is justified only as bounded forensic/recovery tooling until canonical rebuild and
recovery acceptance pass.

Simpler target: first remove all normal call edges and inventory the exact recovery
scenarios still requiring each tool. After isolated recovery acceptance and separate
operator authorization, delete unused importers, migration helpers, legacy scaffold
authoring surfaces, mapping exclusions, and their tests as one retirement package.
Until that trigger, fix correctness/security defects only—no architectural cleanup.

Risk: **RISKY / TRIGGERED**. Do not delete before recovery evidence and explicit
authorization.

### SIMP-M2 — Lifecycle scripts repeat canonical context and projection assembly

Evidence: the repeated projection file lists, inventory/variable path selection,
provider command branching, and target assembly across `scripts/plan-infra.sh`,
`scripts/apply-infra.sh`, `scripts/teardown-infra.sh`, and
`scripts/validate-values.sh` (537 lines total). A fresh plan render is also verified at
`scripts/plan-infra.sh:77-80` and then immediately rechecked at `:92-98`.

The duplication is partly a result of the dual legacy/canonical path. Creating a new
general workflow framework would repeat the same mistake at a higher abstraction
level.

Simpler target: perform SIMP-H3 first, then extend the existing
`scripts/values_context.py` boundary to expose one canonical runtime-context command or
small importable API for site path, generated paths, required projection set, inventory,
OpenTofu vars, state, plan, and metadata paths. Keep plan/apply/teardown as visibly
separate top-level commands and keep mutation gates local and explicit. Verify installed
projections exactly once per plan path: after a fresh atomic install or, when no render
occurred, before consumption.

Risk: **CAREFUL**. Consolidate data/path derivation only; do not hide approval,
verification, snapshot, or mutation boundaries inside a generic framework.

### SIMP-M3 — Private snapshot tools duplicate mechanics and expose an awkward import boundary

Evidence: `scripts/execution-snapshot.py:33-73,88-148`,
`scripts/state-snapshot.py:33-48,67-115`, and
`scripts/hermes-audit-snapshot.py:17-67,70-142`.

Each snapshot type needs a distinct schema and semantic validator, but all three
reimplement low-level private-file operations. The audit snapshot additionally loads
the hyphenated operator CLI dynamically to reach audit-chain functions.

Simpler target: extract only proven low-level primitives—regular non-symlink open,
stream hash, private directory creation, fsynced atomic copy/install, and restrictive
manifest write—into one small importable module. Move audit-chain parsing to an
importable module consumed by both the CLI shim and snapshot tool. Keep the three
snapshot schemas and domain validators separate.

Risk: **CAREFUL**. Require adversarial symlink, TOCTOU, permission, tamper, interrupted
install, retention, and restore tests before deleting duplicate implementations.

### SIMP-M4 — Structural sentinel tests overfit implementation text

Evidence: `tests/test_design_reconciliation.py:231-315`,
`tests/test_plan_projection_lifecycle.py:21-78`,
`tests/test_state_snapshot.py:128-134`, and representative source-order assertions in
the Ansible/tooling contract tests.

Some source sentinels appropriately prohibit unsafe constructs, but fixed ledger
counts, exact command fragments, task labels, and source-order checks often duplicate
behavioral tests and couple harmless refactors to broad test rewrites.

Simpler target: inventory the 165 candidates and classify each as security invariant,
schema/semantic contract, generated-artifact check, or implementation-text assertion.
Retain security prohibitions; replace parseable YAML/HCL/JSON assertions with semantic
parsers; replace shell-source sequencing checks with disposable command-level tests at
the pre-mutation boundary; remove fixed totals such as `919` in favor of invariants.

Risk: **SAFE** for removing fixed counts after invariant coverage exists; **CAREFUL**
for mutation-boundary tests.

### SIMP-M5 — Status prose has drifted from verified evidence

Evidence: the former Phase 9 gate-4 status, `docs/hermes-operator-pilot-prd.md:3`, and
the generated decision register reporting no unresolved questions.

Several status lines still describe service-state rehearsal or unresolved decisions
as open after evidence or decisions were recorded. The source-hash ledger detects that
text changed, but not that two current documents contradict each other.

Simpler target: make the concise acceptance matrix and decision register the only
machine-checked status authorities. Current documents should link to those authorities
instead of copying long status sentences. Historical plans retain dated claims without
being regenerated as current status.

Risk: **SAFE** documentation consolidation.

### SIMP-M6 — Saved-plan validity is redundantly bound to unrelated commits

Evidence: `scripts/tfplan-metadata.py:32-46,71-87,350-364,455-471`.

Saved-plan metadata records both a Git revision and SHA-256 hashes of OpenTofu,
Ansible, every script, the public service catalog, tool definitions, compose/Just
configuration, and selected site inputs. Verification requires both sets to remain
unchanged. Consequently, a documentation- or test-only commit invalidates a reviewed
plan even when the plan bytes, canonical identity, scope, expiry, and every operational
input hash are unchanged.

Simpler target: retain `git_commit` as provenance in metadata and reports, but make
validity depend on plan hash, site/canonical identity, operation/scope, age, and the
complete operational-input hash set. Add a test proving docs-only commits do not
invalidate a plan and tests proving every mutation-relevant tracked input still does.

Risk: **CAREFUL**. Before relaxing the commit comparison, prove the operational input
set covers all code/configuration read by plan, apply, teardown, and Ansible execution.

## Proposed Phase 10 — Simplification without weakening safety

This phase is not authorized merely by recording it. Implement one package at a time,
with a separate review before any compatibility deletion.

### Package P10-A — Close and compact reconciliation

**Status: complete (2026-08-09).** Active reconciliation now consists only of concise package/source completion, the 38 original audit finding dispositions/evidence, explicit approved decisions, and the environment-specific acceptance matrix. The final lossless per-claim ledger is preserved through the immutable Git reference in package completion rather than regenerated on documentation edits.

- [x] Record the historical ledger Git reference and verify all 38 original audit findings retain a
  package, disposition, production citation, and focused verification citation.
- [x] Add the environment-specific acceptance matrix and migrate Phase 9 development evidence into
  it without promoting development evidence to isolated recovery or production.
- [x] Correct frontier generation so only incomplete source packages appear; no unresolved decisions
  means `DECISIONS` is absent.
- [x] Replace continuously generated per-claim/wave artifacts with concise package/source completion,
  audit disposition, explicit decision, and acceptance authorities.
- [x] Remove the synonymous `--check-extraction` mode and dormant historical decision-word map.
- [x] Remove the fixed lossless-record count test and validate compact invariants plus archival provenance.

Exit gate: met — active reconciliation is concise, names only external acceptance work, and retains a
verifiable Git reference to frozen lossless history.

### Package P10-B — Finish canonical-only operational cutover

**Status: complete (2026-08-11).** Normal setup and lifecycle commands now require an
explicit selected canonical site. The private legacy forensics recipe emits only the
value-redacted discovery report and has no normal lifecycle caller; mutating recovery
CLIs remain separately invoked behind the P10-E retention boundary.

- [x] Make site selection and `site.yaml` mandatory for every normal public command.
- [x] Remove legacy branches from setup, values check, validation, run, plan, apply, and
  Ansible orchestration.
- [x] Expose the still-required forensic discovery only through a recovery-only name and prove no
  normal recipe imports or invokes mutating legacy recovery.
- [x] Preserve public-safe static fixtures without presenting them as normal authoring
  files.
- [x] Add command-level tests proving legacy inputs fail with one explicit canonical
  recovery message.

Exit gate: met — each normal workflow has one canonical path from `site.yaml` through verified
projections; legacy inputs cannot silently select a second path.

### Package P10-C — Consolidate path and private-file mechanics

**Status: complete (2026-08-10).** Canonical path and projection-set consolidation,
audit-chain imports, and Git-provenance simplification are implemented. Snapshot,
restore, and operator-audit paths now retain descriptor authority through validation,
copy, publication, cleanup, pruning, append, and durability operations. An independent
adversarial review approved all 13 filesystem behavior gates after reproducing the
former execution ancestor-swap exploit and verifying that the corrected path rejects it.

- [x] Retain `values_context.py` as the Python selected-site path boundary and centralize
  shared shell site/projection-set derivation in `site-context.sh`.
- [x] Remove repeated projection filename lists and derive lifecycle paths from the one
  selected `INFRA_VALUES_DIR` root.
- [x] Retain one projection verification per plan path instead of verifying a fresh
  atomic install twice.
- [x] Extract the minimal shared private-file primitives proven by all snapshot tools,
  including held-FD audit append/source validation and race-safe failure cleanup.
- [x] Expose audit-chain parsing through an importable module with a thin CLI wrapper.
- [x] Keep Git revision as saved-plan provenance, but remove it as a second validity
  gate only after complete operational-input coverage is proven.
- [x] Keep execution, state, and audit snapshot schemas and validators separate.

Exit gate: met — shared descriptor-safe mechanics are behaviorally proven while site
locks, saved-plan verification, distinct snapshot schemas, audit continuity, and
explicit approvals remain visible and tested.

### Package P10-D — Replace brittle sentinels with behavior and semantic checks

**Status: complete (2026-08-10).** The source-reading inventory was classified and normal
fail-closed workflow checks were converted. Caller-level regressions now exercise held
source identity, destination appearance, root and ancestor swaps, no-replace collisions,
recursive cleanup and pruning, audit syscall ordering, concurrent writers, and
missing/malformed history. The integrated focused boundary contains 76 passing tests and
received an independent adversarial approval. Focused timing was 0.78 seconds before and
0.96 seconds after the original conversion. Full public validation was 87.84 seconds
before and 138.19 seconds after; no cache or second validation mode was added.

- [x] Classify all source-reading tests before deleting any.
- [x] Replace fixed totals and source-order/string assertions where an executable or
  parser-backed contract exists.
- [x] Retain narrowly scoped tests that forbid secret leakage, raw mutation commands,
  unsafe host-key acceptance, unverified downloads, or bypass of approval gates.
- [x] Measure focused and full validation time before and after; do not add caching or a
  second validation mode unless measured cost justifies it.

Exit gate: met — behavioral and semantic checks cover the affected callers and retained
security sentinels remain narrowly scoped to controls unsafe to exercise through live
mutation paths.

### Package P10-E — Triggered legacy retirement

**Status: complete (2026-08-12).** The recorded disposable-development
controller/infrastructure recovery rehearsal satisfied the development recovery-evidence
gate for evaluation, and the authorized removal scope retired the bounded legacy
compatibility surface as one package. This source retirement is not isolated-recovery or
production acceptance.

- [x] Record development controller/infrastructure recovery acceptance evidence.
- [x] Inventory the legacy callers before removal and retain the historical inventory as provenance.
- [x] Replace static legacy public fixtures with rendered, verified temporary canonical projections.
- [x] Delete legacy import/discovery/forensics, mapping, fixture, entrypoint, and focused-test surfaces together; retain only canonical encrypted-bundle recovery primitives.

Exit gate: met — no caller depends on legacy tooling, public validation consumes only
generated canonical projections, and normal operation has no compatibility fallback.

Retained-boundary evidence (2026-08-11): `just validate-public` passed all stages with
948 tests and 74% aggregate script coverage; the integrated audit/forensics suite passed
208 tests, and a fresh `hermes-verify-integrated-*` probe exercised strict audit semantics
plus real read-only/no-network recipe execution without changing its public fixture tree.

### Package P10-F — Historical source-only Onramp handoff projection

**Status: source-complete (2026-08-11); removed from the active reconciliation frontier
on 2026-08-12.** The generated projection has no corresponding consumer requirement or
implementation in the authorized `onramp-vNext` repository. It is not an accepted
cross-repository contract, does not create a consumer cutover obligation, and cannot
justify temporary workload retirement. Any future consumer integration requires its own
consumer-owned requirement and separately authorized implementation.
Canonical rendering now emits a manifest-bound, non-secret `onramp-handoff.json` artifact.
Disabled sites emit an explicit disabled state. Enabled sites bind the handoff to canonical
site, service, shared-host resource, non-provider VM identity, hostname, address, Debian 13
rootless Podman/Caddy capabilities, and ownership exclusions. Provider IDs and temporary
workload definitions remain outside the handoff.

- [x] Define a stable `infra-fabric.onramp-handoff/v1` consumer contract.
- [x] Generate it from the canonical model rather than a second values source.
- [x] Include it in render, verification, apply-preflight, Forgejo monitor, execution
  snapshot, shell lifecycle, and dynamic inventory projection sets.
- [x] Reject non-VM or non-shared-host placement, sensitive key names, and identity drift.
- [x] Add public-safe enabled, disabled, tamper, placement, manifest, and monitor coverage.
- [x] Document ownership, consumption, and evidence boundaries without claiming live
  Onramp or SearXNG cutover acceptance.

Exit gate: met for the historical source artifact only. No consumer deployment, verification,
rollback, or temporary SearXNG retirement gate is tracked by this reconciliation plan.

Verification evidence (2026-08-11): `just validate-public` passed all stages with
925 unit/contract tests and 73% aggregate script coverage after the source-contract review;
the focused handoff/catalog/canonical/projection suite passed 106 tests, and compilation
plus `git diff --check` passed.

## Simplification verification strategy

For every proposed package:

1. capture a before/after inventory of files, lines, generated bytes, public commands,
   and affected tests;
2. run focused tests at the changed contract boundary;
3. run `just validate-public` and `git diff --check`;
4. use only disposable public-safe fixtures for negative and recovery-path tests;
5. inspect the final diff for accidental weakening of the controls listed above; and
6. report source completion separately from provider, live, recovery, and production
   evidence.
