# Canonical-First Documentation and Service Authoring Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make all maintained operator and contributor documentation canonical-model-only, add a complete canonical site quick start and public just-recipe reference, and establish a public-safe service-authoring workflow plus a non-mutating authoring-wizard design.

**Architecture:** Documentation will name `values/sites/<site>/site.yaml` as the sole non-secret source and `values/sites/<site>/secrets.sops.yaml` as the sole protected source. Routine operations will be expressed only with an explicit selected site. Existing documents that teach root-layout or compatibility authority will be rewritten, retired from the current documentation surface, or deleted when they are purely superseded historical material. The service authoring workflow will be contract-first: catalog, typed schema, projection, OpenTofu, Ansible, secret metadata, state policy, test, and documentation requirements must all be declared before code generation can be considered.

**Tech Stack:** Markdown, Just, Bash, Python 3.12, JSON service catalog, Pydantic canonical models, OpenTofu, Ansible, SOPS/age, Docker Compose tooling.

---

## Scope and decisions

### Explicit documentation contract

- Every current operator instruction uses `VALUES_SITE=<site>` or first exports `VALUES_SITE=<site>`.
- Current documentation teaches only site-scoped canonical inputs:
  - `values/sites/<site>/site.yaml`
  - `values/sites/<site>/.sops.yaml`
  - `values/sites/<site>/secrets.sops.yaml`
  - generated projections as derived private artifacts
- No current operator/contributor document instructs users to author, select services through, or store runtime secrets in root `.env`, `terraform.tfvars`, static inventory, DNS JSON, or `settings.local.json`.
- Secret values, recipient strings, private endpoints, local inventory, and state contents remain absent from tracked documentation and tests.
- Historical implementation/audit documents that primarily teach an obsolete workflow are removed from the current documentation tree rather than kept as discoverable operator guidance. Git history remains the historical record.

### Deliberate boundary

This plan removes legacy **documentation and authoring guidance**. It does not silently remove runtime compatibility code, recovery tooling, or private files. A follow-on code-cutover plan must explicitly decide whether to delete each remaining compatibility branch after tests and recovery guarantees are reviewed. Current docs must not advertise such branches as normal workflows.

## Current evidence driving the work

- `README.md:54-60` begins with root-layout setup, while `README.md:89-98` declares site-scoped canonical authority.
- `justfile:11-35,67-123` exposes public recipes whose canonical operation requires a selected site, but their parameters and side effects are not documented in one place.
- `scripts/site-context.sh:5-35` requires site context for canonical lifecycle commands.
- `scripts/plan-infra.sh:59-205` and `scripts/apply-infra.sh:35-156` use selected-site generated projections and selected-site plan/state paths.
- `scaffold/README.md`, `AGENTS.md`, and several active runbooks still prescribe root-layout configuration.
- `docs/development-environment.md:148-262` is a useful service implementation checklist but names legacy inputs instead of canonical contracts.
- `infra/services.json`, `scripts/canonical_values.py`, `scripts/canonical_projections.py`, OpenTofu service files, Ansible roles, and secret delivery are all required service-extension surfaces. The public focused suite currently passes: 98 tests across canonical values, canonical Ansible compatibility, and secret delivery.

## Task 1: Establish a documentation authority map

**Objective:** Classify every tracked Markdown document as current canonical operator guidance, current canonical contributor guidance, architecture reference, or obsolete historical material.

**Files:**
- Modify: `docs/README.md`
- Modify: `README.md`
- Delete or replace: obsolete canonical phase/audit/migration documents identified by the inventory
- Test: new documentation inventory test, exact path selected during implementation

**Step 1: Build a checked documentation inventory**

Create a deterministic machine-readable list of tracked `README.md`, `AGENTS.md`, `docs/**/*.md`, and `scaffold/README.md`, with one of these classifications:

```text
operator-current
contributor-current
architecture-current
historical-remove
```

The inventory must identify an owner/replacement path for every `historical-remove` document.

**Step 2: Add a failing test for documentation classification**

The test must fail when:

- a current document is unclassified;
- `docs/README.md` links to a removed document;
- a current operator document links to a historical document;
- a historical document remains in the active operator/documentation index.

**Step 3: Implement the inventory and index enforcement**

Keep the inventory public-safe and free of private site names or values. Make `docs/README.md` contain only current canonical documents and a concise path to the root quick start.

**Step 4: Run focused tests**

Run the new documentation inventory test in the container. Expected result: pass after index and inventory align.

## Task 2: Replace the root README with a canonical-first operator entry point

**Objective:** Make the repository README a concise canonical operator guide with no root-layout configuration workflow.

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`
- Test: documentation command/reference test from Task 1

**Step 1: Write failing documentation assertions**

Assert that the README includes all of:

```text
just setup "" <site>
export VALUES_SITE=<site>
values/sites/<site>/site.yaml
values/sites/<site>/secrets.sops.yaml
just validate
just plan
just apply
```

Assert that it has no current authoring instructions for root `.env`, root `terraform.tfvars`, root static inventory, root DNS JSON, or `settings.local.json`.

**Step 2: Rewrite README sections**

Use this sequence:

1. What the project manages and its public/private boundary.
2. Canonical source-of-truth statement.
3. Five-minute canonical quick start (Task 3’s detailed document is linked, not duplicated).
4. Daily workflow: validate, reviewed plan, explicitly approved apply.
5. Service lifecycle and update workflow.
6. Links to just-recipe reference, service-authoring guide, security/secret operations, troubleshooting, and architecture docs.

The README must explicitly say generated projections are derived and must not be edited.

**Step 3: Correct selected-site artifact wording**

Describe all plan/state/generated artifacts only beneath `values/sites/<site>/`. Document that plan artifacts are local/private and ephemeral after apply.

**Step 4: Run documentation assertions and link checks**

Expected result: all README/document-index tests pass with no references to removed documents.

## Task 3: Add a complete canonical-site quick start

**Objective:** Give a new operator one safe, end-to-end canonical bootstrap sequence without exposing secrets or implying an apply is routine.

**Files:**
- Create: `docs/canonical-quick-start.md`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/canonical-values-secret-operations.md`
- Test: documentation command/reference test

**Step 1: Write the required command sequence**

The quick start must use public-safe placeholders and explain the purpose and expected local effects of each step:

```bash
just setup "" <site>
export VALUES_SITE=<site>
# establish private site SOPS policy, encrypted bundle, and external age identity
just edit-secrets SITE=<site>
just ssh-initialize SITE=<site>
just validate
just plan
# inspect saved plan; apply only after explicit approval
just apply
```

Do not place recipient values, identities, passwords, tokens, actual domains, or state examples in the document.

**Step 2: Explain source ownership**

Document exactly what an operator edits versus what tooling derives:

```text
Operator-edited: site.yaml, .sops.yaml, secrets.sops.yaml
Derived: generated/*, plan metadata, plan artifacts
External/private: age identities and recipient policy
```

**Step 3: Explain safety gates**

Specify that validate is structural, plan performs local projection refresh and provider-facing read/preflight work, and apply is an infrastructure mutation that requires explicit approval and a reviewed fresh plan.

**Step 4: Add concise first-failure troubleshooting links**

Link to recipe-specific failure contracts rather than putting sensitive command output examples in the quick start.

**Step 5: Run document tests**

Expected result: canonical quick start is indexed from the README and docs index, and all command snippets include a selected-site context.

## Task 4: Create the authoritative public Just recipe reference

**Objective:** Document every public recipe, exact parameters, prerequisites, local side effects, infrastructure side effects, safety acknowledgements, and canonical examples.

**Files:**
- Create: `docs/just-recipes.md`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `AGENTS.md`
- Test: new `tests/test_documented_just_recipes.py` or equivalent

**Step 1: Derive the public recipe list from the Justfile**

Treat `just --list` as the source. Cover:

```text
default
setup remote="" site=""
ssh-initialize SITE=<site>
edit-secrets SITE=<site>
update
validate
plan
apply
```

Private recipes are not listed as supported commands.

**Step 2: Write a recipe table and individual sections**

For every recipe, include:

- canonical invocation;
- required environment/site context;
- inputs and prerequisites;
- changed local/private files;
- whether it contacts external systems;
- whether it mutates infrastructure;
- expected review/approval gate;
- common failure class and next safe action.

**Step 3: Add controlled-rollout guidance**

Document the exact semantics and safety limitations of:

```text
INFRA_TARGET_SERVICE
INFRA_REPLACE_SERVICE
INFRA_ALLOW_DESTROY=1
INFRA_ALLOW_STATEFUL_BATCH=1
```

Make clear that no variable bypasses explicit approval or review of a fresh full plan.

**Step 4: Add an executable documentation contract test**

Parse the Justfile/public recipe list and fail unless every public recipe has a matching heading and canonical example in `docs/just-recipes.md`. Validate that `validate`, `plan`, `apply`, and `update` examples carry `VALUES_SITE` context.

**Step 5: Run the focused test**

Run the recipe-documentation test inside the repository tooling container. Expected result: it passes and detects an intentionally removed heading during its red case.

## Task 5: Rewrite scaffold and contributor instructions around canonical authoring

**Objective:** Ensure fresh values scaffolding and contributor guidance do not direct users toward retired authoring surfaces.

**Files:**
- Modify: `scaffold/README.md`
- Modify: `AGENTS.md`
- Modify: `docs/development-environment.md`
- Modify: `docs/canonical-values-secret-operations.md`
- Modify: `scripts/values.sh` help strings only if wording is user-facing and misleading
- Test: documentation inventory/reference tests

**Step 1: Rewrite scaffold README layout and initialization sections**

Describe the canonical site directory, setup command with site parameter, mandatory SOPS setup, selected-site lifecycle, and derived artifacts. Remove all root-layout configuration snippets and root secret-variable lists.

**Step 2: Update AGENTS.md doctrine and workflow**

Replace root-value source-of-truth instructions with canonical equivalents. List every public recipe but classify `ssh-initialize` and `edit-secrets` as explicit secret-mutating operations. Preserve the prohibitions against private data in public tracked source and unapproved apply/destructive operations.

**Step 3: Rewrite service development guidance**

Replace the legacy mapping section in `docs/development-environment.md` with the canonical extension checklist designed in Task 6. Correct bootstrap behavior: canonical setup does not run SSH initialization automatically.

**Step 4: Narrow secret-operations language to current canonical behavior**

Keep key lifecycle/recovery safety guidance, but remove claims that selected-site normal lifecycle is merely a deferred or validation-only cutover.

**Step 5: Run docs checks**

Expected result: no current document has root-layout authoring instructions or bare operational lifecycle commands.

## Task 6: Publish a canonical service-authoring guide and contract checklist

**Objective:** Make the full first-class-service implementation contract explicit before adding a service.

**Files:**
- Create: `docs/canonical-service-authoring.md`
- Modify: `docs/development-environment.md`
- Modify: `docs/README.md`
- Test: new contract-completeness tests under `tests/`

**Step 1: Define supported service archetypes**

Document these explicit, non-overlapping choices:

```text
dedicated LXC service
dedicated VM service
shared-host service
no-runtime integration
```

For each, document placement, network/ingress expectations, supported resource ownership, and when a bespoke OpenTofu implementation is mandatory.

**Step 2: Publish the required extension matrix**

The guide must map each service concern to the exact code surface:

```text
Catalog: infra/services.json
Schema: scripts/canonical_values.py
Projection: scripts/canonical_projections.py
OpenTofu: infra/opentofu/services.tf, variables.tf, per-service files, outputs.tf
Ansible: playbook, role, inventory mapping, handlers, health checks
Secrets: catalog declaration, secret_provider.py, secret_delivery.py
State: infra/ansible/vars/service-state.yml
Scaffold/fixtures: scaffold/sites/dev and fixtures
Tests: catalog, canonical values, projections, Ansible, secret delivery, state, OpenTofu bindings
Docs: operator runbook, service-specific maintenance/rollback guidance
```

**Step 3: Define acceptance gates**

Separate static/public gates from site-local/live gates. Require all of:

```text
schema/catalog/projection parity
OpenTofu and Ansible static validation
secret delivery contract coverage
state backup/restore contract for stateful services
provider-backed reviewed plan
host identity readiness
service smoke test
repeat-plan / drift check
recovery rehearsal where stateful
```

**Step 4: Add a failing catalog-service contract test**

For a fixture catalog service, assert a precise error when a required contract surface is absent. The test must check typed configuration registration, projection declaration, secret metadata completeness, and state contract when stateful.

**Step 5: Implement minimum test support only**

Do not refactor the entire service system in this documentation change. Add a testable manifest/checklist registry only if needed for the test and the upcoming authoring wizard.

**Step 6: Run focused canonical extension tests**

Run:

```bash
scripts/python.sh -m unittest -v \
  tests.test_service_catalog \
  tests.test_canonical_values \
  tests.test_ansible_canonical_compat \
  tests.test_secret_delivery \
  tests.test_service_state \
  tests.test_opentofu_output_bindings
```

Expected result: all pass in the containerized repository environment.

## Task 7: Design and implement a non-mutating service-author manifest wizard

**Objective:** Provide a supported way to design a complete new service before implementation, without creating secrets, site configuration, state, plans, or provider resources.

**Files:**
- Create: `scripts/service-author.py`
- Create: `docs/service-author-manifest.schema.json` or an equivalent typed Python schema
- Create: `tests/test_service_author.py`
- Modify: `docs/canonical-service-authoring.md`
- Modify: `docs/just-recipes.md` only if a public recipe is explicitly approved in a separate decision

**Step 1: Define the command as generate-only**

Initial CLI shape:

```bash
scripts/python.sh scripts/service-author.py \
  --service-id <id> \
  --archetype dedicated-lxc \
  --output /tmp/<id>-authoring-manifest.json
```

Do not add a new public Just recipe unless explicitly approved. The initial command must default to no repository writes other than the requested output path.

**Step 2: Write failing validation tests**

Cover rejection of:

- unknown service archetype;
- service ID outside the repository naming rules;
- guest/shared-host service without declared provisioning contract;
- missing typed configuration-model declaration;
- stateful service without a state contract;
- secret path lacking classification/consumer/environment binding;
- projection field lacking explicit consumer mapping;
- any request to create a site, SOPS bundle, age identity, plan, inventory, or resource.

**Step 3: Implement manifest generation**

Emit public-safe metadata only:

```text
service identity and archetype
catalog candidate requirements
required schema/projection/OpenTofu/Ansible/state/secret contract work
files to create or modify
fixture/test/documentation checklist
manual/site-local/live acceptance gates
unsupported requested behavior
```

No guessed Terraform variable names or secret values may appear.

**Step 4: Add fixture-driven tests**

Test all four archetypes and intentional rejection cases. Ensure output contains no secret-like values and is stable/deterministic.

**Step 5: Run tests**

Run `tests/test_service_author.py` plus the focused canonical extension suite. Expected result: all pass.

## Task 8: Retire obsolete documentation and enforce canonical wording

**Objective:** Remove remaining documentation that teaches compatibility/root-layout operation and prevent regression.

**Files:**
- Delete: superseded historical documents determined by Task 1
- Modify: `docs/README.md`
- Modify: documentation inventory/test files
- Test: full documentation contract test

**Step 1: Remove superseded documents from the active tree**

Delete documents that have no continuing architectural value and whose instructions are contradicted by current canonical behavior. Do not alter Git history.

**Step 2: Replace durable architecture references where needed**

If a document contains reusable architecture decisions but obsolete lifecycle instructions, rewrite it into a canonical architecture reference rather than retaining compatibility prose.

**Step 3: Add banned-pattern checks for current docs**

The check should reject current documentation patterns that instruct operators to use root-layout values as authority, including authoring examples based on root `.env`, `terraform.tfvars`, static inventory, DNS JSON, or `settings.local.json`.

Allow literal mentions only in a narrowly scoped public safety statement if absolutely required by source layout; the preferred result is no current-doc occurrence.

**Step 4: Run full documentation validation**

Run link checking, documentation contract tests, and public-safe scans. Expected result: no broken links, no stale current-workflow commands, and no root-layout authoring guidance.

## Task 9: Repository-wide verification and review

**Objective:** Verify documentation accuracy against the implementation and protect public-safety boundaries.

**Files:**
- Review: all modified tracked files
- Test: existing repository validation suite and newly added docs tests

**Step 1: Run targeted tests**

Run all new docs/wizard tests and the focused canonical service tests.

**Step 2: Run repository validation**

Run:

```bash
VALUES_SITE=dev just validate
```

Use a valid disposable/development canonical site and external identity only. Do not use production values, plan, or apply for documentation verification.

**Step 3: Run static safety checks**

Run:

```bash
git diff --check
git diff --name-only
git status --short --branch
```

Inspect diffs for public-safe placeholders only. Confirm no value files, SOPS identities, decrypted data, plans, state, or generated private artifacts are staged in the public repository.

**Step 4: Manual command/doc reconciliation**

Run `just --list` and compare every public recipe, signature, and command example to `docs/just-recipes.md`.

**Step 5: Review without committing**

Present the exact changed-file list, validation evidence, and remaining site-local/live acceptance gates. Do not commit, push, plan against production, or apply without separate authorization.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Removing historical docs loses useful design rationale | Retain only canonical architecture references; Git history preserves superseded implementation artifacts. |
| Documentation promises behavior the code does not support | Derive recipe content from Justfile/script behavior and add automated recipe-doc parity tests. |
| A generic wizard creates misleading partial services | Generate a manifest only; reject catalog-only or incomplete contracts; do not provision or write secrets. |
| Documentation change leaks private information | Use public-safe placeholders only; run repository public-safety checks and inspect diffs. |
| Removing legacy documentation while compatibility code remains confuses recovery users | Keep recovery strictly out of routine docs; make any residual code removal a separately reviewed code-cutover decision. |
| New documentation tests become brittle | Test semantic headings/required fields and recipe derivation rather than prose wording. |

## Open questions to settle during implementation

1. Should obsolete historical Markdown files be deleted outright, or moved outside the documentation index into a non-operator archive directory? This plan defaults to deletion because the stated requirement is to remove legacy mentions from documentation.
2. Should `service-author` remain a direct Python tool initially, or should a public `just service-author` recipe be added? This plan defaults to no new public recipe until the tool contract stabilizes.
3. Is removal of runtime legacy compatibility code authorized after documentation is canonical-only? This plan deliberately does not perform that destructive compatibility-removal work without explicit approval.
