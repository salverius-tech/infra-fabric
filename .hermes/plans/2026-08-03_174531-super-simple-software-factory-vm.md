# Super Simple Software Factory VM Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add the Super Simple Software Factory (SSSF) as a stateful, dedicated Debian VM service in both the development and production canonical sites, with repeatable installation, controlled model credentials, durable factory repositories/traces, optional authenticated observability, backup/restore, and verified operator workflows.

**Architecture:** SSSF is not a single daemon. It is a repository-local Python/`uv` workflow runtime that invokes Pi coding agents, stores raw session artifacts plus a SQLite trace database, and optionally serves a read-only Bun/Vite visualizer. Each site gets one dedicated VM with a non-root service account and isolated workspaces. OpenTofu owns the VM; Ansible owns host bootstrap, dependencies, SSSF installation/configuration, systemd units, secrets delivery, health checks, and state backup/restore. The canonical site model remains the only authoring surface.

**Tech Stack:** Debian 13 cloud image, Proxmox/OpenTofu `debian-vm` module, Ansible, Python/`uv`, Pi coding agent, SQLite WAL, Git, optional Bun/Vite visualizer, SOPS-backed secret metadata and delivery, Caddy or private-network access only if the UI is exposed.

---

## Research evidence and current repository context

- External source reviewed at the pinned upstream commit `de31374882e7a4e3e5b7bb9bd09e69dc2f779356`:
  - https://github.com/disler/super-simple-software-factory/tree/de31374882e7a4e3e5b7bb9bd09e69dc2f779356
  - README: SSSF stamps `.claude/skills/sssf/` into a target repository; the manual prerequisites are `uv`, `pi`, `sqlite3`, Git, and provider API keys. Bun is required only for the visualizer.
  - `.claude/skills/sssf/cookbooks/install.md`: `uv run .../install.py` must run from the target repository root; it creates `adws/`, `.env.sample`, runtime data paths, and requires a Git repository for commit-ending workflows.
  - `.claude/skills/sssf/templates/sssf.config.yaml`: roster/config paths, model provider IDs, protected files, runtime data directory, and SQLite database path are configurable; the starter roster includes planner, builder, scout, reviewer, and documenter.
  - `.claude/skills/sssf/references/observability.md`: runtime truth is raw files plus SQLite; the visualizer polls the database; WAL and `busy_timeout` are expected; runtime data is not repository source.
- This repository already supports `dedicated-vm` as a service archetype, a shared Debian VM image, `infra/ansible/playbooks/site.yml`, canonical projections, SOPS secret delivery, service-state archives, and public-safe scaffold fixtures.
- Current service integration is not generic: `infra/opentofu/services.tf` has a hard-coded runtime-service list and VM-image condition, and `scripts/canonical_values.py` requires every catalog service to have a typed configuration model or explicit exemption. SSSF therefore needs a first-class contract across all surfaces, not only a catalog row.
- Both `values/sites/dev/site.yaml` and `values/sites/prod/site.yaml` exist. Their live values must be inspected and edited only in the separate private values workflow; this plan intentionally contains placeholders and no live addresses, credentials, private keys, or protected values.

## Assumptions to confirm during implementation

1. SSSF should run one isolated VM per site, not on the existing Hermes VM/LXC and not on the shared onramp host.
2. SSSF should execute against explicitly configured Git repositories. The first deployment should not grant it unrestricted access to the infrastructure repository, private values repository, or host filesystem.
3. The visualizer should initially bind to loopback or the private site network and require an existing access boundary; it must not be published anonymously to the Internet.
4. Model/provider API keys are per-site protected runtime secrets. Development and production must not share a credential unless separately authorized.
5. Site-specific SSSF workspaces, sessions, SQLite traces, and prompts are private state and must not be committed to this public repository.
6. The upstream commit is only an implementation baseline. Release/update policy must pin the imported SSSF skill contents and verify upstream changes before updating either site.

## Open decisions required before apply

- Service ID and host naming convention (recommended: `sssf` / `sssf-factory`), VMIDs, static addresses, DNS names, and whether the visualizer receives a Caddy name.
- VM sizing and durable storage size. A conservative initial starting point is 4 vCPU, 8 GiB RAM, 40 GiB root disk plus a separate durable data volume; measure actual concurrent-agent workload before increasing it.
- Runtime model roster and provider choice. The upstream starter config names multiple providers; reduce to approved providers and declare only the corresponding environment variables.
- Repository access mechanism: read-only deploy keys, scoped Forgejo tokens, GitHub app/token, or a private mirror. Define which repositories are allowed and where clones are stored.
- Whether SSSF may create commits, branches, or pull requests in target repositories. The upstream workflow can commit, but infrastructure mutation and deployment must remain outside the VM unless explicitly designed and approved.
- Whether traces and workspaces are backed up in full, retained for how long, and whether model prompts/raw outputs contain sensitive source or secrets that require stricter handling.
- Whether to use Pi directly in v1, as upstream currently supports, or to add another coding-agent runtime. Do not model a second runtime until its executable, config, credentials, and security boundary are verified.

---

## Implementation sequence

### Task 1: Freeze the upstream source and define the service contract

**Files:**
- Modify: `infra/services.json`
- Modify: `scripts/canonical_values.py`
- Modify: `docs/canonical-service-authoring.md` only if the generic contract needs clarification
- Add: `scaffold/fixtures/service-configurations.yaml` entry for the new service
- Add: a public-safe service authoring manifest under a temporary review path, then retain only if repository convention requires it

Define service ID, `dedicated-vm` archetype, runtime owner, dependencies, state capability, release source, replacement addresses, inventory names, endpoint contract, required fields, secret metadata, and update/rollback identity. Register `SuperSimpleSoftwareFactoryConfiguration` as a strict typed model, or document a reviewed exemption only if all non-secret configuration is intentionally resource-owned. Keep the upstream commit/ref and checksum as non-secret release metadata.

**Acceptance:** `scripts/service-author.py` generates a manifest; the catalog-wide validator sees the service; configuration contract parity succeeds; no site values or secrets are created.

### Task 2: Add typed canonical configuration and projection mappings

**Files:**
- Modify: `scripts/canonical_values.py`
- Modify: `scripts/canonical_projections.py`
- Modify: `infra/services.json`
- Modify: `scripts/legacy_values_discovery.py` only if compatibility mappings are genuinely needed
- Add/update: `tests/test_canonical_values.py`
- Add/update: projection and cross-projection tests under `tests/`

Model non-secret settings explicitly, likely including:

- runtime user and normalized repository/workspace roots;
- upstream SSSF ref and installation source/checksum;
- Pi executable/version and `uv`/Python constraints;
- agent roster/config path, data directory, SQLite path, poll interval;
- visualizer enablement, loopback bind address, port, and access mode;
- allowed repository list or workspace policy;
- concurrency and process limits;
- state retention/backup policy;
- health-check endpoint/command and systemd unit names.

Secret-bearing fields must be represented only as catalog logical paths and environment names, never in `site.yaml`, generated projections, Terraform variables, plans, Ansible arguments, or logs. Add explicit OpenTofu and Ansible projection mappings rather than inferring names from `sssf`.

**Acceptance:** strict model tests cover defaults, invalid paths/hosts/ports/refs, loopback/public exposure policy, and rejected sensitive configuration; projection identity tests prove dev/prod/service/resource mappings agree.

### Task 3: Add public-safe dev and prod canonical fixtures

**Files:**
- Modify: `scaffold/sites/_template/site.yaml` or the repository’s actual scaffold template path
- Modify: `scaffold/fixtures/service-configurations.yaml`
- Modify: public-safe documentation examples only; do not copy live site values
- Private values repo, separately and only when explicitly authorized: `values/sites/dev/site.yaml`, `values/sites/prod/site.yaml`, corresponding SOPS bundles/policies

Add an explicit `resources.guests.sssf` VM object for each fixture and an enabled `services.sssf` object referencing it. Use RFC 5737/example hostnames, placeholder VMIDs/addresses, a pinned public Debian image, and placeholder upstream ref/checksum values. Keep dev and prod independent; do not derive production from development.

For the private site values implementation, choose real VMIDs, addresses, hostnames, storage, capacity, and endpoints independently for each site. Add separate protected provider credentials and repository-access material. Preserve the private values repository’s uncommitted changes and branch policy.

**Acceptance:** public fixture validation passes and no live endpoint, domain, address, credential, key, state, or plan is added to tracked files.

### Task 4: Extend OpenTofu runtime ownership for the dedicated VM

**Files:**
- Modify: `infra/opentofu/services.tf`
- Add: `infra/opentofu/sssf.tf`
- Modify: `infra/opentofu/variables.tf` only where canonical projections need a new generic field
- Modify: `infra/opentofu/outputs.tf` if service host/IP outputs are not covered by generic outputs
- Modify: `infra/opentofu/main.tf` or image download locals if the current shared service VM image condition omits SSSF
- Review: `infra/opentofu/modules/debian-vm/{main.tf,variables.tf,outputs.tf}`
- Add/update: OpenTofu binding and lifecycle tests

Use the existing `modules/debian-vm` contract: pinned cloud image, explicit VMID/name, cores/memory, root and durable data disk ownership, network bridge/VLAN/static address, cloud-init bootstrap key, startup order, and `stop_on_destroy` behavior. Add SSSF to the allowed runtime service set and VM-image enablement. Ensure replacement addresses and `terraform_data`/state dependencies are correct. Do not add `local-exec` for service configuration.

If the current VM module cannot represent a separate durable data volume or guest filesystem sizing required by SSSF, extend the module generically and test it; do not add an SSSF-specific imperative workaround.

**Acceptance:** `tofu fmt -check`, `tofu validate`, static output-binding checks, service-runtime validation, and a selected-site non-mutating plan show exactly the expected VM/resource/storage changes with no unrelated replacement.

### Task 5: Implement Ansible VM preparation and SSSF installation role

**Files:**
- Add: `infra/ansible/playbooks/sssf.yml`
- Modify: `infra/ansible/playbooks/site.yml`
- Add: `infra/ansible/roles/sssf/{defaults/main.yml,handlers/main.yml,tasks/main.yml,meta/argument_specs.yml}`
- Add: `infra/ansible/roles/sssf/templates/` for systemd units, environment allow-list, and optional visualizer service
- Add: `infra/ansible/roles/sssf/files/` only for small audited helper scripts
- Modify: `scripts/canonical_projections.py`/inventory mapping as required
- Add: role syntax, argument-spec, idempotency, and direct-service tests

The role should:

1. converge the dedicated VM host identity and operator access using existing host-identity/direct-access contracts;
2. install only pinned OS packages and required tools (`git`, `sqlite3`, Python/`uv`, Pi, and optionally Bun) with checksums/signature verification where upstream provides them;
3. create a dedicated non-root runtime user and separate service/operator accounts as required by repository policy;
4. create a controlled workspace root, repo allow-list, runtime data root, SQLite parent directory, logs, and backup staging paths with restrictive ownership/modes;
5. clone or materialize SSSF from the pinned upstream commit without running an unreviewed remote install script as root;
6. run the upstream installer from each explicitly approved target repository root, or provide a deterministic repo-stamping mechanism if the service is intended to manage multiple workspaces;
7. render the SSSF config from canonical non-secret values and protected transient environment values;
8. install separate systemd units/timers or a deliberately operator-invoked unit for ADW execution and optional visualizer serving; prevent accidental boot-time arbitrary workflow execution;
9. set resource, process, timeout, and network restrictions appropriate to an agent runner;
10. provide an explicit service health command that checks the executable, config, workspace permissions, SQLite open/WAL behavior, and visualizer only when enabled.

Do not place API keys in static templates, command-line arguments, generated inventory, or persistent world-readable environment files. Use the repository’s secret-delivery mechanism and transient protected material.

**Acceptance:** Ansible check mode is clean after first convergence; second convergence is idempotent; systemd units are syntax-valid and disabled/enabled exactly as designed; the health check fails closed when credentials or required model configuration are missing.

### Task 6: Add secret catalog and protected delivery

**Files:**
- Modify: `infra/services.json`
- Modify: `scripts/secret_provider.py` and/or `scripts/secret_delivery.py` only through existing service abstractions
- Modify: private SOPS bundle/policy outside the public repo, only when authorized
- Add/update: secret path/classification/environment and delivery tests

Declare only the required logical paths, for example provider API keys, repository access tokens/deploy keys, and any visualizer authentication secret if the chosen access layer requires one. Use service-scoped paths such as `services.sssf.secrets.<key>`, catalog-owned environment names, and runtime-only delivery. Choose one secret provider mechanism per site and explicitly document whether a key is allowed for one repository, all factory repositories, or an environment tier.

**Acceptance:** secret coverage checks pass; non-secret projections reject all declared sensitive paths; logs, plans, generated files, and test fixtures contain names/metadata only, never secret values.

### Task 7: Implement durable state backup, restore, and disable behavior

**Files:**
- Modify: `infra/ansible/vars/service-state.yml`
- Add: `infra/ansible/playbooks/sssf-state-backup.yml`
- Modify: generic state backup/restore playbooks only where target-specific hooks are needed
- Modify: `scripts/service-state.sh` if the target catalog requires explicit registration
- Add: state archive and capacity/restore tests
- Add: operator documentation under `docs/sssf.md` and link from `docs/README.md`

Classify the following as private state: cloned target repositories and local branches, `.env`/provider runtime material if persisted, `adws/adw_data/` sessions and raw outputs, `sssf.db`, prompts/config that are site-specific, visualizer/runtime logs, and any generated workspace metadata. Prefer separate durable mounts for workspace and trace state. Define backup order, service stop/start units, checksum/manifest validation, capacity preflight, retention, restore-if-present behavior, and disable policy. Decide whether raw prompts/output require encryption or exclusion because they may contain proprietary source.

**Acceptance:** backup produces a private checksum-validated archive; restore is explicit, capacity-aware, and reversible; first boot with no archive is a successful no-op where intended; a failed preflight makes no guest state change.

### Task 8: Add access, observability, and security runbook

**Files:**
- Add/update: `docs/sssf.md`
- Modify: `docs/README.md`
- Add/update: `docs/canonical-troubleshooting.md` if cross-links are needed
- Add: security-focused tests or static checks for bind addresses, service users, protected paths, and unit permissions

Document direct SSH diagnostics, service health, how to launch a named ADW, how to inspect phases/processes/SQLite traces, how to stop a stuck run safely, how to update the pinned upstream ref, how to rotate provider/repository credentials, and how to access the visualizer. State clearly that SSSF agents can execute shell commands and modify authorized workspaces; do not expose the visualizer or agent runner publicly without an approved authentication and network boundary. Document that infrastructure apply remains an external, separately approved operation.

**Acceptance:** operator can diagnose install, missing model/provider credentials, stale sessions, stuck processes, SQLite lock/capacity issues, and failed updates without reading secrets.

### Task 9: Add complete service contract and regression coverage

**Files:**
- Add/update: `tests/test_service_catalog.py`
- Add/update: `tests/test_canonical_values.py`
- Add/update: `tests/test_cross_projection_identity.py`
- Add/update: `tests/test_opentofu_output_bindings.py`
- Add/update: `tests/test_direct_service_ansible.py`
- Add/update: `tests/test_secret_delivery.py`
- Add/update: `tests/test_service_state.py`, `tests/test_service_state_capacity.py`
- Add/update: `tests/test_documentation_contract.py`
- Add fixture coverage under `tests/fixtures/` or existing scaffold fixture locations

Cover catalog registration, dependency ordering, typed configuration, dev/prod independent fixtures, VM runtime mapping, image/checksum metadata, resource/storage mapping, inventory identity, secret environment binding, first-run/repeat-run behavior, unauthorized workspace/path rejection, systemd health contract, state backup/restore, and public-safety scans.

**Acceptance:** focused tests pass, catalog-wide service validation passes, public validation passes, and `git diff --check` is clean.

### Task 10: Execute non-mutating validation and staged plans for both sites

**Commands:**

```bash
scripts/python.sh scripts/validate-service-contracts.py --repo .
just validate-public
VALUES_SITE=dev just validate
VALUES_SITE=prod just validate
VALUES_SITE=dev just plan
VALUES_SITE=prod just plan
git diff --check
```

Review both plans for creates, changes, replacements, destroys, VM image downloads, storage changes, DNS records, and Ansible host/service changes. Verify the plan metadata and projection identity for each site. Do not apply, rebuild, mutate private SOPS values, or modify production until the plans and private-site values have been reviewed and explicitly approved.

### Task 11: Dev deployment and smoke verification

After explicit authorization for live mutation, apply only the development plan through the repository’s normal workflow. Then verify:

- VM is reachable through the canonical non-root provisioning path;
- host identity/operator convergence is correct;
- SSSF health command passes;
- pinned upstream commit and tool versions match the canonical model;
- a minimal read-only ADW completes and writes a valid envelope;
- SQLite contains a successful session and events are visible while a longer test runs;
- a controlled repository write test stays inside the allow-listed workspace;
- the visualizer is reachable only through the approved access boundary;
- repeat Ansible convergence and repeat plan show no unexpected drift;
- backup and restore rehearsal succeeds on development before production.

Keep raw outputs and private state out of the public repository and final reports.

### Task 12: Production deployment and smoke verification

After dev evidence is reviewed and production apply is separately authorized, repeat the same workflow against `VALUES_SITE=prod`. Do not copy dev values or credentials. Verify production independently, including endpoint/DNS/HTTPS checks if enabled, credential scoping, repository allow-list, resource limits, backup archive, restore procedure, and acceptable repeat-plan drift.

---

## Expected implementation surface summary

Likely public repository changes:

- `infra/services.json`
- `scripts/canonical_values.py`
- `scripts/canonical_projections.py`
- `scripts/service_catalog.py` only if generic validation needs a safe extension
- `infra/opentofu/services.tf`, `infra/opentofu/sssf.tf`, possibly `main.tf`, `variables.tf`, `outputs.tf`
- `infra/ansible/playbooks/site.yml`, new `sssf.yml`, new `roles/sssf/`
- `infra/ansible/vars/service-state.yml`
- scaffold fixtures and public-safe site template
- focused tests across catalog/model/projection/OpenTofu/Ansible/secrets/state/docs
- `docs/sssf.md` and `docs/README.md`

Likely private values changes, only under explicit authorization:

- `values/sites/dev/site.yaml` and `values/sites/prod/site.yaml`
- each site’s SOPS secret bundle and private SOPS/age policy
- generated projections, inventories, known-hosts, plans, state, and backups

Never track: API keys, repository tokens/deploy keys, private SSH material, decrypted environment files, real endpoints/addresses/domains in public fixtures, generated private projections, Terraform/OpenTofu state/plans, raw SSSF sessions, or trace databases.

## Verification gates

### Static/public gates

- catalog dependency and configuration-contract parity;
- strict canonical schema and public-safe placeholder validation;
- projection and cross-projection identity;
- OpenTofu format/validate and output bindings;
- Ansible syntax, argument specs, lint/idempotency checks;
- release/ref/checksum validation;
- secret metadata and delivery coverage;
- service-state archive/restore/capacity checks;
- documentation contract and `git diff --check`.

### Private/live gates

- site-specific SOPS paths and policy;
- provider-backed reviewed plan for dev and prod;
- host readiness/direct SSH and guest health;
- minimal read-only SSSF workflow;
- controlled repository access/write test;
- visualizer access-boundary verification;
- backup/restore rehearsal;
- repeat convergence and repeat plan;
- explicit approval before every infrastructure mutation.

## Risks and mitigations

- **Agent execution is high risk:** isolate each site in a dedicated VM, use a non-root runtime account, limit repositories and filesystem paths, restrict network access, and make infrastructure credentials unavailable to the runtime user.
- **Provider/API credentials can leak through prompts or traces:** use transient delivery, scoped credentials, redact/avoid secret-bearing prompts, and treat raw SSSF state as private backup material.
- **Upstream installer drift:** pin a commit, review release changes, verify checksums where possible, and update through the normal update/validate/plan workflow.
- **SQLite and workspace growth:** separate durable storage, add capacity preflight/monitoring, and define retention before production use.
- **Unbounded concurrency/processes:** configure limits and systemd resource controls; test stuck-run termination and child-process cleanup.
- **Public exposure of the visualizer:** default loopback/private access; require an approved authenticated ingress path before DNS/Caddy publication.
- **Two sites diverge accidentally:** keep canonical dev/prod values separate, verify each selected-site projection and plan independently, and never use dev as a production baseline.

## Completion criteria

The service is complete only when both sites have independently validated canonical values and reviewed non-mutating plans, the public contract passes all static gates, the VM/Ansible implementation is idempotent, SSSF executes a verified smoke workflow in each site after authorized apply, the visualizer access policy is proven, and backup/restore has been rehearsed at least in dev before production. No claim of live readiness should be made from static validation or a plan alone.
