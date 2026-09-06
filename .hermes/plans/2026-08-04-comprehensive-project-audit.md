# Infra Fabric Comprehensive Project Audit

**Audit date:** 2026-08-04
**Repository:** `infra-fabric`
**Audited ref:** `3fefc1bdc766fc6ae36547889ccd73f03734febd` (`feat/canonical-values-model`)
**Scope:** repository policy, documentation, canonical configuration and projections, public workflows, OpenTofu, Ansible, service catalog, secrets, state/plan controls, tests, CI, container tooling, and supply-chain posture.

## Executive summary

The project has a strong safety architecture: canonical site inputs are separated from generated projections, secret delivery is bounded and transient, plan artifacts are hashed and expire, destructive operations require explicit overrides, OpenTofu and Ansible responsibilities are clearly separated, and a large clean-checkout validation suite passes.

The audit nevertheless found several high-priority safety, recovery, and reproducibility defects. The stateful-destruction classifier reads optional legacy JSON metadata instead of canonical `site.yaml`; canonical service-state backup/restore is broken in normal multi-service sites and omits the verified Ansible vars projection; the documented fresh-site workflow is circular; and multiple runtime artifact paths are not immutable. Additional defects affect secret preflight, teardown plan identity, Tailscale resource creation, Hermes Control readiness, and apply-time TOCTOU protection.

**Priority posture:**

- **Critical:** 0
- **High:** 12
- **Medium:** 18
- **Low:** 8

The repository is structurally healthy, but the high findings should be resolved before relying on canonical batch-destruction classification or deploying Forgejo as a VM.

## Audit method and boundaries

The audit cross-checked documentation against executable recipes and scripts, traced canonical inputs through generated OpenTofu/Ansible projections, reviewed the service registry and plan/apply gates, inspected OpenTofu modules and Ansible orchestration, and ran public-safe validation. Five parallel read-only specialist reviews covered documentation/operator experience, Ansible, OpenTofu, canonical workflows/secrets/state, and CI/tooling/supply chain; material findings were consolidated and key high-severity evidence was re-read directly. No private `values/` data, decrypted secrets, provider-backed plans, applies, live service probes, or production endpoints were inspected.

A clean detached worktree was used to separate repository behavior from ignored local virtual environments and caches.

---

# Findings

## High

### H1. Stateful destructive-change classification does not use the canonical service selection

**Evidence**

- `AGENTS.md:9-14` and `docs/canonical-architecture.md:31-43` define `site.yaml` as the authority for site and service selection.
- `scripts/tfplan-metadata.py:138-166` builds the stateful-address map by loading `ValuesContext.metadata_path`, then falling back to `infra/services.json.default_services`.
- `scripts/values_context.py:56-64` resolves that metadata only from `site.json`, `settings.json`, or `settings.local.json`; it never resolves canonical `site.yaml`.
- `scaffold/sites/dev/site.json:7` independently carries a service list, even though canonical service selection is owned by `site.yaml`.
- `tests/test_tfplan_metadata.py:240-270` exercises the stateful batch gate only with legacy/default service selection; the canonical fixture tests at `tests/test_tfplan_metadata.py:63-136` do not enable a non-default stateful service and verify its classification.
- Audit probe: with canonical `site.yaml` enabling Hermes but `site.json` listing only Technitium and Forgejo, `enabled_stateful_services_by_address()` returned `['forgejo', 'technitium']` and `hermes_detected=False`.

**Impact**

A destructive plan still requires the general `INFRA_ALLOW_DESTROY=1` override, but the additional multi-stateful-service safety gate can fail to identify enabled canonical services such as Hermes, Infisical, SSSF, onramp-host, or onramp workloads. An operator can therefore lose the intended warning and `INFRA_ALLOW_STATEFUL_BATCH=1` gate for a batch affecting multiple stateful services.

**Remediation**

1. In canonical mode, load the selected `CanonicalSite` and derive enabled stateful services from `model.services` plus the catalog.
2. Retain JSON/settings selection only for explicitly legacy contexts.
3. Add tests where canonical `site.yaml` enables two non-default stateful services while `site.json` is absent or stale; assert both are classified and the batch gate blocks.
4. Remove service selection from `site.json`, or document and validate it as lifecycle metadata only.

### H2. Forgejo VM images can be downloaded without checksum verification

**Evidence**

- `infra/opentofu/modules/debian-vm/main.tf:5-15` creates `proxmox_download_file.cloud_image` from a URL but supplies no `checksum` or `checksum_algorithm`.
- `infra/opentofu/modules/debian-vm/variables.tf:39-52` makes internal image creation the default and has no checksum fields or validation.
- `infra/opentofu/forgejo.tf:135-154` invokes this path with `create = !local.onramp_host_enabled`; therefore a Forgejo VM downloads through the unverified module path whenever onramp-host is disabled.
- `infra/opentofu/variables.tf:421-440` calls the URL “pinned” but defines only URL and filename, not a digest.
- In contrast, the shared service image in `infra/opentofu/main.tf:16-28` and the onramp image in `infra/opentofu/onramp-host.tf:1-13` both pass checksums.

**Impact**

A mutable or compromised upstream artifact at the configured URL can become the base disk of the Forgejo VM without content verification. HTTPS and a dated filename do not provide immutable artifact identity.

**Remediation**

Prefer one verified top-level image resource and pass only its `file_id` into every VM module. If module-local download remains supported, require checksum and algorithm whenever `image.create=true`, add validation, and add an OpenTofu contract test proving every `proxmox_download_file` has digest verification.

### H3. Parallel Ansible waves do not serialize services that share one host

**Evidence**

- `scripts/apply-ansible-services.py:84-101` computes waves only from service dependencies.
- `scripts/apply-ansible-services.py:523-561` runs every service in a ready wave concurrently.
- `infra/services.json:264-296`, `457-500`, and `503-555` map `infisical_onramp`, `onramp_host`, and `searxng_onramp` to the same `onramp_host_vm`; both application services become ready after `onramp_host` completes.
- The roles operate package/container/service/Caddy surfaces on that shared host, so dependency completion is not equivalent to host-level concurrency safety.

**Impact**

Two playbooks can contend for package-manager locks, Podman state, systemd reloads, shared deployment directories, or Caddy configuration on the same machine. Failures are timing-dependent and can leave partial shared-host convergence.

**Remediation**

Add a scheduler resource key (canonical resource ID or inventory host) and permit at most one service per resource in a parallel wave. Continue parallelism only across distinct hosts. Add a test showing both onramp applications are serialized while unrelated dedicated guests remain parallel.

### H4. Canonical service-state backup and restore is broken across selection, inputs, and documentation

**Evidence**

- `scripts/service-state.sh:101-120` emits all canonical enabled services as one space-separated line, then tests that whole line as a single service; normal multi-service sites therefore yield no enabled supported services.
- `scripts/service-state.sh:22-30` omits `sssf`, although `infra/ansible/vars/service-state.yml:37-44` defines it and `docs/service-state-backup.md:56-72` documents it.
- `scripts/service-state.sh:150-175` invokes backup/restore with the generated inventory but not the verified `generated/ansible-vars.json`. Service-state definitions require projected values at `infra/ansible/vars/service-state.yml:10,28,43-44,52,61-64,73-76`.
- Forgejo backup falls back to SQLite when `forgejo_database` is absent (`infra/ansible/playbooks/service-state-backup.yml:46-80`), so a PostgreSQL deployment can produce an archive without a database dump.
- Operator examples omit required `VALUES_SITE` context and show non-site-local archive paths (`docs/service-state-backup.md:7-35`, `docs/hermes-state-backup.md:8-46`, `docs/sssf.md:74-88`).

**Impact**

`backup all` and individual operations can reject enabled services; SSSF is unreachable; shared-host paths can be undefined; and Forgejo PostgreSQL state can be silently omitted. The documented recovery story is therefore not executable.

**Remediation**

Emit one enabled service per line, derive targets from the catalog/state definition rather than a shell allowlist, consume the manifest-verified inventory/vars pair, require site-aware documented commands, and add CLI tests for every state-capable service, multi-service sites, PostgreSQL selection, backup, and restore acceptance.

### H5. Fresh-site onboarding has a circular validation dependency

**Evidence**

- `README.md:26-37` and `docs/canonical-quick-start.md:59-73` direct operators to validate before planning.
- Setup creates `site.yaml` but no generated projections (`scripts/values.sh:69-85`).
- Validation requires all five generated files and instructs the operator to run plan when any is absent (`scripts/validate-values.sh:14-22`).
- Planning is what first renders and installs those projections (`scripts/plan-infra.sh:59-85`).

**Impact**

A correctly initialized site cannot pass the advertised safety gate without first contacting the provider through planning. The documented sequence is impossible on a fresh site.

**Remediation**

Add a non-provider render/verify command, or render to a private temporary directory during validation as `scripts/workspace-preflight.py:139-175` already does. Validation must not require plan-created persistent artifacts.

### H6. Tailscale canonical enablement is silently double-gated

**Evidence**

- `infra/opentofu/services.tf:10-17` requires both membership in canonical `enabled_services` and `var.tailscale_client_enabled`.
- The legacy boolean defaults to false (`infra/opentofu/variables.tf:1415-1418`).
- Canonical rendering emits `enabled_services` and resource/runtime values (`scripts/canonical_projections.py:218-266`) but never emits `tailscale_client_enabled`.

**Impact**

Canonical inventory and Ansible can target Tailscale while OpenTofu creates no Tailscale guest, violating canonical authority and causing post-apply convergence failure.

**Remediation**

Remove the legacy second gate and derive enablement solely from canonical service selection. Add an end-to-end test proving enabled Tailscale produces both the resource and inventory target.

### H7. Pre-mutation secret preflight omits required host-identity secrets

**Evidence**

- `scripts/workspace-preflight.py:178-207` validates catalog service paths, the bootstrap SSH key, and the Proxmox token.
- The apply path later resolves `secrets.operator.password` and resource-specific root-password requirements (`scripts/secret_delivery.py:57-112`; `scripts/apply-ansible-services.py:264-307,704-709`).

**Impact**

OpenTofu can mutate infrastructure successfully before Ansible fails because operator or host root-password secrets are missing.

**Remediation**

Derive and validate the complete selected apply-phase secret set before `tofu apply`: provider token, SSH identity, operator password, default and host-specific root passwords, and selected service requirements. Add tests that remove each class and prove apply is never invoked.

### H8. Documented teardown bypasses saved-plan identity and freshness controls

**Evidence**

- `docs/canonical-teardown.md:19-41` creates a raw destroy plan.
- The apply procedure at `docs/canonical-teardown.md:50-69` checks only file existence before applying it.
- It does not create or verify `tfplan` metadata, canonical/projection identity, plan hash, age, Git commit, selected-site scope, input hashes, or stateful-change summary, and it does not verify projections before planning/apply.

**Impact**

The documented destructive path bypasses the repository's strongest reviewed-plan guarantees and can apply a stale or wrong-authority destroy plan.

**Remediation**

Implement a guarded teardown helper using the same metadata create/verify path as normal plan/apply, with explicit destroy scope and acknowledgement. Remove the raw `tofu apply` procedure.

### H9. Hermes Control authenticated readiness always sends a malformed bearer token

**Evidence**

- `infra/ansible/roles/hermes/tasks/main.yml:577-598` sends the literal header `Authorization: Bearer *** hermes_control_api_token }}`.
- The internal diagnostics task uses the real templated token correctly (`infra/ansible/roles/hermes_control/tasks/main.yml:254-265`).

**Impact**

When Hermes Control is enabled, the HTTPS diagnostics readiness task should repeatedly fail despite a healthy service, blocking convergence.

**Remediation**

Use the correctly templated variable while retaining `no_log: true`, and add a structural/rendered-task test that confirms the header references the variable without exposing its value.

### H10. Canonical secret namespaces and migration targets contradict runtime consumers

**Evidence**

- The canonical model and quick start use `secrets.providers.cloudflare.api_token` (`scripts/canonical_values.py:166-175`; `docs/canonical-quick-start.md:24-31`).
- Catalog requirements use `services.providers.cloudflare.secrets.api_token` (`infra/services.json:29-31,75-95,472-474`).
- Runtime delivery requires `secrets.operator.password` (`scripts/secret_delivery.py:57-64`), but migration writes top-level `operator.password` (`scripts/secret_bundle_migration.py:22-48`).

**Impact**

A bundle following the documented model can fail catalog preflight, and the migration can successfully produce a path that Ansible never consumes.

**Remediation**

Choose one provider namespace and one operator namespace, update model/catalog/docs/fixtures/migration atomically, retain legacy aliases only inside importers, and fail on conflicting values.

### H11. Runtime artifact installation is not consistently immutable

**Evidence**

- Infisical uses mutable `postgres:16-alpine` and `redis:7-alpine` images in both deployment modes (`infra/ansible/roles/infisical/templates/docker-compose.yml.j2:1-25`; `infra/ansible/roles/infisical_onramp/templates/docker-compose.yml.j2:1-29`).
- Tailscale executes an unpinned root installer (`infra/ansible/roles/tailscale_client/tasks/main.yml:9-16`).
- SSSF executes unpinned remote installers for uv, Pi, and Bun (`infra/ansible/roles/sssf/tasks/main.yml:130-156,228-241`).
- Several of these mutation paths report `changed_when: false`.

**Impact**

Redeployment can silently change stateful database/cache versions or execute changed network scripts as root/service users. Rollback and convergence evidence is unreliable.

**Remediation**

Use digest-pinned database/cache images, signed repositories or checksum-pinned artifacts for tools, managed update contracts, and accurate change detection. Add a test that every production image and network installer has immutable identity.

### H12. Apply verification has a mutation-time TOCTOU window

**Evidence**

- Plan metadata is verified at `scripts/apply-infra.sh:57-62`.
- Storage and guest preflights then run before provider credentials are re-resolved and the saved plan is applied at `scripts/apply-infra.sh:89-134`.
- A second metadata verification occurs only after infrastructure mutation at `scripts/apply-infra.sh:136-141`.

**Impact**

The plan, metadata, projections, ciphertext, source inputs, or credentials can change after verification but before use. Late detection can stop Ansible after OpenTofu has already succeeded or partially mutated infrastructure.

**Remediation**

Hold a site-scoped lock across verification, storage preparation, apply, and orchestration. Consume an immutable private snapshot of the verified plan, metadata, projections, and ciphertext identity; treat post-apply verification as diagnostic rather than the first chance to detect drift.

## Medium

### M1. `site.yml` is a misleading, incomplete, unconditional orchestration surface

**Evidence**

- `infra/ansible/playbooks/site.yml:2-19` imports a fixed set of services unconditionally.
- It omits catalog services such as `forgejo_runner`, `infisical_onramp`, and `searxng_onramp` while including optional services regardless of canonical enablement.
- The real apply path uses registry-driven playbooks through `scripts/apply-ansible-services.py:466-490` and `589-717`.
- `scripts/validate-public.sh:33-37` syntax-checks `site.yml`, which can make it appear supported even though it is not the canonical execution path.

**Impact**

A conventional filename implies “configure the site,” but direct execution can configure the wrong set and bypass catalog selection, dependency scheduling, projection pairing, secret delivery, and readiness sequencing.

**Remediation**

Remove the wrapper, rename it clearly as a non-executable syntax aggregation fixture, or make it fail with guidance to use `just apply`. Do not attempt to encode dynamic catalog selection in static imports when the Python orchestrator is already authoritative.

### M2. Public validation is sensitive to ignored local Markdown files

**Evidence**

- `tests/test_documentation_contract.py:11-20` calls `ROOT.rglob('*.md')` and excludes only `.git`, `.hermes`, `.specs`, and `values`.
- Common ignored directories such as `.venv`, `.tmp`, and `infra/opentofu/.terraform` are not excluded.
- In the current workspace, `scripts/validate-public.sh` ran 691 tests and failed only because Markdown bundled in ignored virtual environments/provider caches was treated as project documentation.
- The same validation in a genuinely clean detached worktree passed all 691 tests and the remaining validation stages.

**Impact**

The documented validation command can fail after normal local tool installation or audit work even when tracked source is valid. This creates false negatives and discourages local verification.

**Remediation**

Build the documentation set from `git ls-files '*.md'`, or centralize a repository-file enumerator that respects Git tracking. Add a regression test with ignored Markdown under `.venv` and `.terraform`.

### M3. Local OpenTofu state has no locking or documented single-writer control

**Evidence**

- `scripts/plan-infra.sh:170-176` and `scripts/apply-infra.sh:120-134` use explicit local `-state` paths under the selected private values directory.
- `infra/opentofu/versions.tf:1-10` declares no backend.
- `docs/canonical-architecture.md:68-79` explains state privacy but not concurrent-writer exclusion, locking, or ownership.

**Impact**

Two operators or automation runs against the same private state can race, produce stale plans, or overwrite state. Plan metadata protects source/input identity but is not a distributed state lock.

**Remediation**

Document an explicit single-writer operating model immediately. Longer term, use a locking-capable encrypted remote backend or add a robust site-scoped lock around plan/apply and state backup operations. State migration must be an explicit, separately reviewed operation.

### M4. Ansible lint globally disables the principal command-idempotence rule

**Evidence**

- `.ansible-lint:2-5` globally skips `no-changed-when`.
- The Ansible tree contains more than 200 `ansible.builtin.command` sites and numerous manually forced `changed_when: true/false` declarations.
- `scripts/validate-public.sh:39-48` otherwise runs the production lint profile over the full Ansible tree.

**Impact**

New command tasks can silently report changes every run or hide real changes. A narrow legacy exception has become a repository-wide blind spot.

**Remediation**

Re-enable `no-changed-when`, add task-level `# noqa no-changed-when` only to commands that are deliberately always-mutating, and prefer modules or explicit result predicates. Add repeat-convergence tests for the highest-risk roles.

### M5. Operator password hashing is not idempotent and root salts are globally reused

**Evidence**

- `infra/ansible/roles/host_identity/tasks/main.yml:61-67` hashes the operator password without an explicit salt and sets `update_password: always`; the generated hash can vary on each run.
- Root credential hashing is deterministic, but `infra/ansible/roles/host_identity/defaults/main.yml:17` and `infra/ansible/roles/root_credentials/defaults/main.yml:2` use the same public salt, `infraFabricRoot`, across every host/site.
- `infra/ansible/roles/root_credentials/tasks/main.yml:17-22` rotates the account on every execution.

**Impact**

The operator account can be reported changed on every apply, obscuring real drift. Global salt reuse enables cross-host hash correlation and avoids the defense normally provided by unique salts.

**Remediation**

Derive stable, host-specific salts from a non-secret site/resource identity, or precompute and deliver a protected password hash. Test second-run idempotence for both operator and root credential roles.

### M6. OpenTofu validation is inconsistent across service-specific inputs

**Evidence**

- Many early variables validate CIDRs, VLANs, and MAC addresses, e.g. `infra/opentofu/variables.tf:60-68`, `90-99`, and `267-275`.
- SSSF inputs at `infra/opentofu/variables.tf:492-538` define address, gateway, MAC, and VLAN values without equivalent validation.
- Module inputs in `infra/opentofu/modules/debian-lxc/variables.tf:11-45`, `69-89`, and `107-135`, and `infra/opentofu/modules/debian-vm/variables.tf:11-18`, `55-80`, and `93-127` lack general positive-size/VMID/network validation.

**Impact**

Invalid canonical projections can reach provider evaluation and fail late, inconsistently by service/runtime. Module reuse does not carry a uniform safety contract.

**Remediation**

Move generic invariants into modules: positive VMID/CPU/memory/disk, valid CIDR-or-DHCP, gateway compatibility, MAC, VLAN, unique disk interfaces, and safe mount paths. Keep service-specific checks only at the root/canonical layer.

### M7. The OpenTofu root contract remains a large compatibility surface

**Evidence**

- `infra/opentofu/variables.tf` is 1,599 lines and mixes generic resource data, service configuration, compatibility aliases, defaults, storage, and Ansible-only-looking values.
- `infra/opentofu/variables.tf:400-440` retains Forgejo-specific runtime/image compatibility fields alongside the generic service runtime and image contract.
- Several descriptions still tell contributors to edit `terraform.tfvars` or `values/.env`, e.g. `infra/opentofu/variables.tf:1-3`, `8-19`, and `443-445`, contrary to canonical-only authoring in `AGENTS.md:55-63`.

**Impact**

The projection layer must maintain a broad legacy-shaped interface, increasing mapping and test burden and making ownership unclear. Stale inline descriptions invite bypasses even though operator docs are canonical-first.

**Remediation**

Create a phased internal contract: generic resource objects/maps, explicit service runtime inputs, and sharply bounded compatibility locals. Deprecate and then remove service-specific aliases only after projection and state-address compatibility tests. Update all HCL descriptions now so they describe generated inputs rather than operator authoring.

### M8. Supply-chain controls stop short of immutable base/container inputs and automated scanning

**Evidence**

- `tools/Dockerfile:1` uses mutable `debian:bookworm-slim` without a digest.
- `tools/Dockerfile:17-30` installs unpinned Debian packages; downloaded OpenTofu, TFLint, and SOPS artifacts are correctly checksum-verified at `31-46`.
- Python dependencies are exactly pinned in `tools/requirements.txt:1-40`.
- `.github/workflows/validate.yml:11-19` has a single public validation job; it does not generate an SBOM or run dependency/image vulnerability scanning.

**Impact**

Tooling builds are reproducible only within the moving Debian image/repository snapshot, and known vulnerable dependencies can enter without an automated evidence path.

**Remediation**

Pin the base image digest, record a controlled refresh process, add SBOM generation and dependency/container scanning, and make high-severity findings visible without granting workflows write permissions.

### M9. Canonical update behavior contradicts update policy

**Evidence**

- `docs/service-update-policy.md:33-37` says `just update` manages OpenTofu and TFLint.
- Canonical execution skips targets without `canonical_path`, including those public tool pins (`scripts/update.py:376-390`).
- Output still describes Technitium as unmanaged despite catalog release/version/checksum requirements (`scripts/update.py:463-469`; `infra/services.json:10-13,39-42`).

**Impact and remediation**

Operators can receive a successful update report while repository-owned tooling was skipped and stale guidance was printed. Process public tool targets independently of site mode, derive service status from the catalog, and add end-to-end output-contract tests.

### M10. Site-local SOPS recipient policy verification can fail open

**Evidence**

- `scripts/workspace-preflight.py:100-134` defaults policy discovery to repository-root `.sops.yaml` and reports recipient policy as unavailable when absent.
- Canonical policy is site-local, and the normal wrapper does not supply an explicit policy override.

**Impact and remediation**

Normal plan/apply can omit the promised exact-site recipient equality check. Default to the selected context's `.sops.yaml`; under `--require-secrets`, require the file, exact site scope, and recipient equality.

### M11. Every service subprocess receives the bootstrap root password

**Evidence**

- `scripts/secret_delivery.py:224-246` starts service delivery with `ansible-bootstrap` requirements before adding service-specific secrets.
- Tests explicitly encode this broad delivery (`tests/test_secret_delivery.py:148-160,194-199`).

**Impact and remediation**

Ordinary service playbooks receive a root credential outside their declared service requirements, expanding exposure if a role or subprocess is compromised. Separate bootstrap/host-identity environments from service environments and assert root/operator/provider secrets are absent unless explicitly authorized.

### M12. Restore can report success after service restart failures

**Evidence**

- `infra/ansible/playbooks/service-state-restore.yml:275-282` suppresses system-service restart failures.
- The play reports restoration success immediately afterward (`infra/ansible/playbooks/service-state-restore.yml:284-288`).

**Impact and remediation**

A restore can exit successfully while the service remains down. Attempt all restarts, collect results, then fail with the affected unit list; suppress failures only during rescue cleanup.

### M13. Sensitive Ansible role arguments are inconsistently protected

**Evidence**

- Forgejo marks its database password `no_log` (`infra/ansible/roles/forgejo/meta/argument_specs.yml:62-66`).
- Comparable Infisical, Forgejo Runner, Tailscale, and Hermes secrets lack `no_log` in their argument specs (`infra/ansible/roles/infisical/meta/argument_specs.yml:14-33`; `infra/ansible/roles/forgejo_runner/meta/argument_specs.yml:22-25`; `infra/ansible/roles/tailscale_client/meta/argument_specs.yml:22-25`; `infra/ansible/roles/hermes/meta/argument_specs.yml:102-113`).

**Impact and remediation**

Malformed secret inputs can appear in argument-validation diagnostics even where tasks use `no_log`. Mark every sensitive spec field and add catalog-to-spec secret parity tests.

### M14. Check-mode and task-tag contracts are absent, and the static checker is inaccurate

**Evidence**

- No Ansible task/play declares `check_mode:` or operational tags.
- `scripts/check-direct-service-ansible.py:237-248` looks for idempotence keys only at task top level, so it misses valid `args.creates/removes`; `infra/ansible/roles/hermes_control/tasks/main.yml:47-55` is a demonstrated false positive.

**Impact and remediation**

Operators lack reliable validation/configuration/recovery slices and the nominal static checker does not prove real check-mode behavior. Establish a small tag taxonomy, explicitly model mutation-only tasks in check mode, fix nested-argument parsing, and run representative containerized `--check` fixtures.

### M15. Stateful retention policy exists only in wrappers

**Evidence**

- Stateful resource removal is driven directly by service `count` expressions (`infra/opentofu/services.tf:10-17` and service modules).
- No resource uses `prevent_destroy`; retention gates exist in shell/Python metadata verification rather than resource lifecycle.

**Impact and remediation**

Direct OpenTofu use bypasses `disable_policy: retain` intent. Project retention acknowledgement into OpenTofu preconditions/lifecycle where feasible and explicitly document direct CLI execution as unsupported.

### M16. Arbitrary override maps rely on secret-looking key names

**Evidence**

- Service overrides allow arbitrary nested scalar values (`scripts/canonical_values.py:1171-1179`).
- Catalog validation restricts namespaces but projection rejection recognizes sensitive-looking keys rather than value semantics (`scripts/service_catalog.py:246-250`; `scripts/canonical_projections.py:18-36`).

**Impact and remediation**

A credential under an innocuous key can enter projections, plans, or logs. Replace opaque overrides with typed allow-listed schemas or explicitly declared catalog fields; retain key scanning only as defense in depth.

### M17. Python quality and coverage are largely ungated

**Evidence**

- `scripts/validate-public.sh:20-27` performs byte compilation and `unittest`, but not formatting, linting, typing, or coverage enforcement.
- Black is installed (`tools/requirements.txt:8`) but not run.
- Byte compilation writes ignored `__pycache__` content into the checkout, and `tools/docker-entrypoint.sh:31-32` recursively changes workspace ownership.

**Impact and remediation**

Static defects and coverage regressions can merge, while validation leaves invisible residue and can touch ignored private paths. Add `black --check`, a Python linter, observed/ratcheted coverage, and direct bytecode output to `/tmp`; restrict ownership repair to known public paths.

### M18. Role interface contracts are incomplete

**Evidence**

- `hermes_control`, `host_identity`, and `root_credentials` have defaults/tasks but no `meta/argument_specs.yml` despite security-sensitive inputs.
- The parent Hermes role dynamically includes Hermes Control, but its argument spec does not cover the subrole variables.

**Impact and remediation**

Type, requirement, and sensitivity validation can drift from defaults and canonical projections. Add argument specs for reusable subroles and test defaults/spec/projection parity.

## Low

### L1. Documentation lacks a complete service-by-service operations matrix

**Evidence**

- `docs/README.md:15-28` provides strong general and selected-service runbooks, but dedicated operational guides are concentrated on Hermes, SSSF, and onramp.
- `infra/services.json:6-556` declares ten services with differing health, state, secret, runtime, and dependency contracts.

**Impact**

Operators must infer health, logs, credentials, backup/restore, rollback, and failure isolation for Technitium, Forgejo, Forgejo Runner, Infisical, and Tailscale from roles and general documents.

**Remediation**

Add a generated or maintained service-operations matrix keyed from the catalog. For each service link health, logs, direct endpoint, credentials/rotation, update, backup, restore verification, rollback, and recovery.

### L2. Documentation link checks validate paths but not anchors or executable snippets

**Evidence**

- `tests/test_documentation_contract.py:29-36` checks only linked file existence from the docs index.
- The audit link probe found no missing relative files, but heading fragments and command examples are not mechanically exercised.

**Impact**

Section renames and command drift can pass while links remain syntactically valid.

**Remediation**

Validate Markdown anchors and add focused command/help contract tests for public snippets (`just --list`, service-author CLI, setup argument shape).

### L3. CI validates only main pushes and pull requests

**Evidence**

- `.github/workflows/validate.yml:3-6` runs on pull requests and pushes to `main` only.

**Impact**

There is no scheduled detection of upstream image, provider, or dependency drift and no explicit manual workflow for reproducibility checks.

**Remediation**

Add a read-only scheduled/manual workflow for lockfile freshness, vulnerability scanning, and tooling rebuild evidence. Keep provider-backed/live infrastructure checks outside public CI unless a safe disposable environment exists.

### L4. Aggregate local validation gives little failure-stage summary

**Evidence**

- `scripts/validate-public.sh:7-48` executes many strong gates under `set -e`, but reports no final matrix and stops at the first failing stage.

**Impact**

Operators must infer which checks were not executed, and a noisy unit-suite failure can hide later syntax/lint status.

**Remediation**

Keep fail-fast behavior for CI, but print named stage boundaries and an end summary; optionally provide a non-gating diagnostic mode that runs independent stages and preserves all exit codes.

### L5. Copied scaffold README links resolve outside the private values repository

`scaffold/README.md:30,57` uses `../docs/...` links, but setup copies the file to the private repository root (`scripts/values.sh:69-71`). Generate destination-aware links or use stable absolute public documentation URLs, and test the installed scaffold rather than only its source location.

### L6. Documentation inventory conflates active truth with unfinished design material

`docs/documentation-inventory.json:34-38` marks incomplete migration/mapping/blocker documents as `architecture-current`, while `docs/README.md:30-36` intentionally hides most of them. One mapping document still carries superseded Technitium release gaps. Introduce `working-design` and `historical-reference` states, index active designs clearly, and archive superseded implementation status.

### L7. Provider compatibility is broader than the reviewed pre-1.0 series

`infra/opentofu/versions.tf:4-8` allows `~> 0.88`, while the lockfile resolves `0.111.1`. The lock protects normal initialization, but an intentional upgrade can cross many pre-1.0 minor releases. Align the constraint to the reviewed series and keep the lock/hashes committed.

### L8. Tooling architecture and host prerequisites are not declared

`tools/Dockerfile:3-9,31-45` hardcodes Linux amd64 downloads, while `README.md:15-24` and `docs/canonical-quick-start.md:5-14` begin with setup without documenting Git, just, Docker/Compose, daemon permissions, supported architecture, or age/SOPS identity prerequisites. Add a prerequisite table and either support `TARGETARCH` with per-architecture checksums or explicitly constrain builds to amd64.

---

# Documentation improvement plan

1. **Repair the executable operator path first.** Make fresh-site validation possible before provider planning; fix all service-state examples to include site context and site-local archives; replace raw teardown commands with a guarded helper.
2. **Correct authority language in code-facing documentation.** Replace HCL descriptions that instruct edits to `terraform.tfvars`, `.env`, or settings files with generated-input language.
3. **Add state ownership, locking, backup, and recovery guidance.** Explain single-writer requirements, durable state backup/restore, service-state versus infrastructure state, and migration boundaries.
4. **Publish a service operations matrix.** Generate as much as possible from `infra/services.json`; link health, logs, credential rotation, update/rollback, backup, restore verification, and failure recovery.
5. **Clarify supported entry points.** Remove or explicitly mark `infra/ansible/playbooks/site.yml` unsupported; state that direct playbook/OpenTofu execution bypasses canonical gates.
6. **Separate current truth from design history.** Add `working-design` and `historical-reference` inventory statuses and index them explicitly.
7. **Document prerequisites and platform support.** Cover Git, just, Docker/Compose, daemon permissions, age/SOPS identity, and supported CPU architectures.
8. **Expand docs tests.** Validate installed-scaffold links, anchors, tracked-file inventory, public command behavior, and catalog-to-operations coverage.

# Ansible improvement plan

1. Repair service-state selection, vars projection consumption, SSSF reachability, restart failure handling, and documented CLI behavior.
2. Fix the malformed Hermes Control authorization header.
3. Serialize by canonical resource/inventory host while retaining cross-host parallelism.
4. Pin runtime installers and all stateful container images by immutable identity.
5. Separate host-identity/bootstrap secret environments from service environments.
6. Re-enable `no-changed-when`, narrow exceptions, and add second-run idempotence tests.
7. Add complete argument specs and `no_log` parity for sensitive inputs.
8. Establish tags and check-mode contracts; repair the static checker.
9. Use stable host-specific password hashes/salts.
10. Remove or quarantine `site.yml` as a non-production wrapper.

# OpenTofu and canonical workflow improvement plan

1. Derive stateful plan classification from canonical `site.yaml` and test every state-capable service.
2. Fix the checksum-less Forgejo VM image path and enumerate every download resource in integrity tests.
3. Remove the Tailscale legacy double gate.
4. Validate the complete apply-phase secret set before mutation and unify provider/operator namespaces.
5. Replace raw teardown with a metadata-bound destroy workflow.
6. Close the apply TOCTOU window with a site lock and immutable execution snapshot.
7. Introduce durable state backup and locking or a documented/enforced single-controller model.
8. Make state retention visible at the resource/precondition layer where practical.
9. Move reusable input validation into `debian-lxc` and `debian-vm` modules.
10. Replace arbitrary overrides and flat compatibility variables with typed, catalog-declared contracts without changing resource addresses.

# Strengths

- **Clear canonical ownership:** `AGENTS.md:9-16` and `docs/canonical-architecture.md:29-45` sharply separate canonical inputs, generated projections, secrets, OpenTofu, and Ansible.
- **Strong plan binding:** `scripts/tfplan-metadata.py:310-337` records plan hash, expiry, commit, site, canonical identity, summary, scope, and input hashes; `401-457` verifies them before apply and gates destruction.
- **Projection integrity:** `scripts/verify-projections.py:29-50` checks model/catalog loading, permissions, cross-projection identity, and the manifest digest.
- **Safe plan installation:** `scripts/plan-infra.sh:34-85` renders to temporary storage, verifies, atomically replaces generated projections, and restores the prior set on failure.
- **No OpenTofu provisioner misuse:** the audit found no `local-exec`, `remote-exec`, or provisioner-based service configuration.
- **Secret hygiene:** secret-bearing Ansible tasks use extensive `no_log`; `scripts/run-infra.sh:24-39` uses a private temporary directory and `umask 077`; canonical Ansible vars are written mode `0600` and removed in `scripts/apply-ansible-services.py:395-416,713-715`.
- **Typed service contracts:** `infra/services.json` centralizes ten services, dependencies, state capability, runtime ownership, Terraform addresses, playbooks, secret classification/environment mapping, and inventory projection metadata.
- **Validation depth:** a clean detached worktree passed 691 unit tests, OpenTofu initialization/format/validate, TFLint, ShellCheck, service-contract validation, inventory generation, Ansible syntax checks, and production-profile ansible-lint over 154 files.
- **Public safety:** the public-safety check passed, `docker compose config --quiet` passed, and the service-contract validator validated all ten services.
- **Supply-chain positives:** OpenTofu/TFLint/SOPS downloads are checksum-verified, Python dependencies are exact-pinned, the provider lockfile is tracked, and the GitHub checkout action is pinned to a full commit SHA.

# Verification performed

| Check | Result | Boundary |
| --- | --- | --- |
| `git status --short --branch` before audit | Clean | Source worktree only |
| Relative Markdown link/file probe | Pass; no missing relative files | File existence, not anchors/HTTP targets |
| `docker compose config --quiet` | Pass | Static Compose rendering |
| `scripts/public-safety-check.sh` | Pass | Tracked public-safety policy |
| `python3 -B scripts/validate-service-contracts.py --repo .` | Pass; 10 services | Public catalog/contracts |
| Host Python unit suite | Blocked/failed due missing host `pydantic`, `PyYAML`, and `python-hcl2` | Host environment, not repository verdict |
| `scripts/validate-public.sh` in current workspace | 691 tests with one failure caused by ignored virtualenv/provider Markdown | Demonstrates M2 |
| `scripts/validate-public.sh` in clean detached worktree | Pass; 691 tests OK; OpenTofu/TFLint/ShellCheck/Ansible checks passed | Clean-checkout static validation |
| Canonical stateful-classification probe | `hermes_detected=False` with stale JSON metadata | Demonstrates H1 without private values |
| `git diff --check` before report | Pass | Existing tracked source |

## Unexecuted evidence

- Provider-authenticated `just plan` and any OpenTofu refresh.
- `just apply`, destroy, import, state changes, migrations, or secret editing.
- Live Ansible convergence, second-run idempotence, service health, DNS/HTTPS, or recovery rehearsal.
- Private `values/` content, decrypted SOPS bundles, state, plans, credentials, identities, or live endpoints.

# Recommended remediation sequence

1. **Recovery hotfixes:** H4 service-state selection/input correctness and M12 restart-failure propagation.
2. **Canonical safety hotfixes:** H1 stateful classification, H6 Tailscale double gate, H7 complete secret preflight, and H10 namespace unification.
3. **Destructive workflow:** H8 metadata-bound teardown and H12 apply locking/immutable execution snapshot.
4. **Runtime correctness:** H9 Hermes Control header and H3 host-aware Ansible scheduling.
5. **Supply-chain hotfixes:** H2 verified Forgejo VM image and H11 immutable runtime dependencies/installers.
6. **Operator workflow:** H5 non-provider fresh-site render/validate path, site-aware recovery docs, and service operations matrix.
7. **State resilience:** M3 durable state backup plus locking or enforced single-controller operation.
8. **Validation/idempotence:** M2 tracked-file documentation inventory, M4 lint narrowing, M5 stable hashes, M13/M18 argument specs, and M14 check-mode/tag evidence.
9. **Contract simplification:** M1 `site.yml`, M6 module validation, M7/M16 typed canonical interfaces, and M9 update-policy parity.
10. **Engineering maturity:** M8/M17 reproducible tooling, SBOM/advisory scans, Python quality/coverage, and platform support.

## Bottom line

The repository has unusually strong canonical-model, projection, secret, and reviewed-plan controls for a homelab infrastructure project, and its clean-checkout validation is substantial. However, the canonical cutover is not operationally complete: service-state recovery is broken in normal multi-service sites, fresh-site validation is circular, several canonical selections or secret paths diverge from their consumers, and the documented teardown path bypasses plan-identity protections. Resolve the recovery and canonical-safety findings before relying on the system for stateful production workloads; then address execution locking, immutable runtime artifacts, host-aware orchestration, and validation/idempotence quality.
