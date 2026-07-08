---
created: 2026-07-07
status: completed
completed: 2026-07-07
---

# Plan: SearXNG on Podman Onramp Host for Hermes

## Objective

Implement the source-controlled runtime path for a future Hermes-usable SearXNG backend: `homelab-infra` adds an optional Debian 13 Podman onramp-host VM substrate and readiness automation, `onramp-vNext` remains the owner of the SearXNG container service, and Hermes gets a documented private-values-backed endpoint contract.

This plan does **not** claim a live SearXNG URL exists at completion. It must stop before live provisioning, live deployment, sibling-repo mutation, or Hermes plugin implementation unless the operator gives a separate explicit approval outside this plan.

## Context

The archived plan `.specs/archive/onramp-host-pilot/plan.md` established the ownership contract but did not create a runnable SearXNG backend. This plan is the next implementation slice. It should produce infrastructure source, automation, scaffold defaults, and handoff artifacts that make a later reviewed deployment smaller and executable:

1. A future onramp-host VM is declared in `homelab-infra` and enabled through the same service-selection mechanism as other optional services.
2. The onramp host is configured with Podman and enough SSH/runtime prerequisites for Onramp to deploy Docker-compatible app services.
3. SearXNG remains an Onramp app service, not a first-class `homelab-infra` LXC.
4. Hermes gets a documented endpoint variable contract for the `web-searxng` plugin or future Hermes runtime wiring.

## Constraints

- Keep tracked files public-safe. Use placeholders such as `onramp-host.example.internal`, `searxng.apps.example.net`, and RFC 5737 addresses.
- Do not write real domains, IPs, hostnames, credentials, tokens, generated secrets, OpenTofu state, or plan files to tracked files.
- Private values belong in ignored `values/`; scaffold files must remain generic.
- Do not run `just plan`, `just apply`, OpenTofu apply/import/destroy/state surgery, or mutate live services without a separate explicit approval.
- Use public repo entry points for validation: primarily `just validate`.
- Do not invoke private just recipes directly.
- `onramp-vNext` is a separate repository. This plan may perform read-only context inspection if the sibling repo is present, but must not mutate it unless the operator explicitly approves cross-repo edits during execution. If read-only inspection is unavailable, the handoff must be labeled generic and must not claim exact Onramp implementation-file readiness.
- Onramp service `port` fields mean container/service port reachable on the Compose network; do not reinterpret them as host-published ports.
- Podman-in-LXC remains experimental and out of scope for the default implementation.
- This plan runs while previous uncommitted source/docs/spec work may exist. Do not discard or overwrite user work; validate from current repository state.

## Current repo state at plan creation

Uncommitted work exists from the previous execution:

- `README.md`
- `docs/README.md`
- `docs/hermes-operator-pilot-prd.md`
- `docs/onramp-app-platform-contract.md`
- `.specs/archive/onramp-host-pilot/`
- `infra/ansible/roles/forgejo_runner/tasks/main.yml`
- `infra/ansible/roles/hermes/tasks/main.yml`
- `infra/ansible/roles/infisical/tasks/main.yml`
- `infra/opentofu/forgejo.tf`

Executors must not discard or overwrite this work.

## MVP Boundary

In scope:

- Add an optional `onramp_host` service to `homelab-infra` service selection.
- Add OpenTofu declarations for a Debian 13 VM onramp host, including public-safe variables, VM boot-source/template contract, validation, outputs, and scaffold defaults.
- Add Ansible orchestration for Podman installation and onramp-host readiness checks.
- Add private-values scaffolding/migration guidance for onramp-host VMID, IP, hostname, DNS, onramp-host deployment user, and Hermes SearXNG endpoint variables.
- Add a public-safe handoff document that states exactly what `onramp-vNext` must implement for SearXNG when Onramp context is available; otherwise label it a generic handoff.
- Add Hermes-facing endpoint contract documentation and environment variable names, without adding real endpoint values.
- Add a public-safe onramp-host rollback/runbook section for future live deployment planning.
- Validate with task-specific checks, public-safety checks, and `just validate`.

Out of scope:

- Running `just plan` or `just apply`.
- Creating or modifying real `values/` site entries unless the operator explicitly asks for private-value changes.
- Deploying SearXNG to a live host.
- Mutating `C:/Projects/Personal/onramp-vNext` unless explicitly approved during execution.
- Implementing the Hermes `web-searxng` plugin itself.
- Proving live Hermes can query a real SearXNG endpoint.
- Replacing service-local Caddy patterns for existing first-class services.

## Design Direction

### Onramp host resource

Prefer a Proxmox QEMU VM over an LXC for the default onramp host. The implementation must not rely on remembered provider syntax. Before writing final HCL, execution must verify the installed Proxmox provider version/schema from local provider docs/schema output or authoritative provider documentation and record sanitized evidence.

The VM boot source must be explicit. The plan must add one of these public-safe contracts before archive:

- a clone/template contract, such as `onramp_host_vm_template_id` or `onramp_host_vm_template_name`, for an existing Debian 13 cloud-init-capable VM template; or
- a cloud-image upload/download contract if the current provider supports it safely in this repo.

The scaffold must use placeholders only. If no provider-supported Debian 13 VM boot-source path can be implemented safely, stop source implementation, update `## Execution Status`, and do not archive as complete.

The VM should expose the same style of knobs as existing services:

- `onramp_host_enabled` via `enabled_services` / settings service list.
- VMID, hostname, description, cores, memory, disk, datastore, bridge, VLAN, static IPv4 address/gateway, DNS servers, search domain, startup order, started/start-on-boot.
- explicit cloud-init/bootstrap user, SSH public keys, root-login policy, password-auth policy, and sudo/become requirements.
- outputs for onramp-host VMID, address, hostname, and a sanitized Onramp target summary only.

### Podman readiness

Ansible should configure the onramp host as an Onramp deployment target, not as a SearXNG host hardcoded in `homelab-infra`.

Minimum runtime contract:

- Rootless Podman is the default unless the plan update explicitly justifies rootful Podman.
- A dedicated non-root Onramp deploy user is created or documented through private values.
- Password SSH authentication is disabled; root SSH login is disabled unless explicitly justified in the plan and tests.
- Authorized keys have safe ownership/mode.
- Sudo scope is minimal and documented; broad passwordless sudo requires justification.
- Podman installed on Debian 13.
- Exact Compose-compatible command/provider is defined, such as `podman compose` or `podman-compose`, with package/source documented.
- If a Docker API compatibility socket is expected, the socket path, user service, linger behavior, and `DOCKER_HOST` semantics are documented and validated.
- Required packages installed idempotently.
- A non-secret deployment directory exists with safe ownership for the Onramp deploy user.
- SSH reachability, Ansible become behavior, `podman info`, compose provider execution, and directory permissions are verified as the same user Onramp will use.
- A harmless non-secret smoke check or dry-run compose validation is included where it can run locally/non-destructively; live remote smoke tests remain for a later deployment plan.
- No app-specific secrets are printed.

### Credential flow

The onramp-host credential flow must remain private-values-backed and public-safe:

- tracked source defines variable names, policy, validation, and placeholders only.
- SSH public keys, deploy-user details, optional sudo policy inputs, real endpoint URLs, and any onramp-host credentials belong in `values/` or an approved local secret mechanism.
- cloud-init/bootstrap must use those private values without printing them.
- Hermes endpoint settings such as `HERMES_WEB_SEARXNG_URL` belong in private runtime values; tracked scaffold may show only placeholder examples.
- evidence may record key names and pass/fail status, but not real values, SSH targets, URLs, domains, IPs, or tokens.

### Network exposure contract

The onramp host is a future network-facing substrate, so source implementation must define default exposure rules even though live deployment is out of scope:

- Host firewall policy should default to deny inbound.
- SSH ingress source CIDRs must be private values or documented placeholders, never tracked real networks.
- App service host-published ports are forbidden by default except for an approved Onramp-owned reverse proxy binding.
- The handoff must state which component owns app reverse proxy/Caddy rules and which ports may be exposed.
- Validation must inspect the Ansible tasks/docs for default-deny and no-host-published-port language; live firewall verification is deferred to the future deployment plan.

### SearXNG ownership

`homelab-infra` must not add SearXNG as a first-class service resource by default. It should publish the contract Onramp needs:

- onramp-host target name/address comes from private values/inventory.
- SearXNG public/internal URL is supplied through private values or Onramp outputs.
- Caddy/reverse-proxy ownership for app services belongs to Onramp.
- Hermes consumes `HERMES_WEB_SEARXNG_URL` or similarly named private runtime setting, not a tracked real endpoint.

Hermes does not depend on `onramp_host` at settings-validation time. The endpoint may point to any approved SearXNG URL. If this source slice updates Hermes Ansible/runtime templating to pass `HERMES_WEB_SEARXNG_URL`, it must add explicit acceptance checks; otherwise the plan must label Hermes runtime consumption as a follow-up for the plugin/runtime implementation.

## Execution Checklist

This checklist is the durable resume ledger for `/do-it`. `/do-it` must leave items unchecked while in progress, mark each checkbox only after its verification passes, preserve any previously checked state unless a review/plan edit invalidates it, and record sanitized evidence in the item and evidence JSONL before starting dependent work.

### Wave 0 -- Preflight

- [x] T0: Inspect provider/repo/Onramp patterns and initialize evidence
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] T0b: Generate planned public-safety file list
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] V0: Validate preflight findings and no unsafe mutation
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl

### Wave 1 -- Infrastructure substrate and registry parity

- [x] T1: Add `onramp_host` to service selection, dependency semantics, and settings validation
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] T2: Add OpenTofu onramp-host VM boot-source contract, variables/resources/outputs
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] T3: Update scaffold and migrations for public-safe onramp-host defaults
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] T4: Add minimal onramp-host inventory mapping and playbook stub for registry parity
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] V1: Validate OpenTofu/service-selection/inventory substrate
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl

### Wave 2 -- Ansible onramp-host readiness

- [x] T5: Implement Ansible onramp-host role for Podman, SSH hardening, and network defaults
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] V2: Validate Ansible syntax/lint and onramp-host targeting
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl

### Wave 3 -- SearXNG/Hermes contract and rollback runbook

- [x] T6: Add Onramp SearXNG handoff artifact
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] T7: Add Hermes endpoint contract docs/scaffold variables
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] T8: Add public-safe onramp-host rollback and future deployment runbook
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] V3: Validate SearXNG ownership boundary, docs navigation, and rollback runbook
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl

### Final Gates

- [x] F1: Task-specific acceptance complete
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] F2: Public-safety and whitespace checks complete
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] F3: Repo-wide validation complete
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] F4: Manual validation complete or not required
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] F5: Deployment validation complete or not required
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] F6: Archive criteria/preflight complete
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl
- [x] F7: Archive completed
  - Status: completed
  - Evidence: 2026-07-07 passed; see evidence/validation.jsonl

## Task Breakdown

| # | Task | Files | Type | Model | Depends On |
|---|------|-------|------|-------|------------|
| T0 | Inspect provider/repo/Onramp patterns and initialize evidence | `.specs/searxng-podman-runtime/evidence/validation.jsonl` | research | medium | -- |
| T0b | Generate planned public-safety file list | `.specs/searxng-podman-runtime/evidence/public-safety-files.txt` | mechanical | small | T0 |
| V0 | Validate preflight findings and no unsafe mutation | evidence only | validation | small | T0,T0b |
| T1 | Add `onramp_host` to service selection, dependency semantics, and settings validation | `scripts/settings.py`, `settings.example.json`, tests | feature | medium | V0 |
| T2 | Add OpenTofu onramp-host VM boot-source contract, variables/resources/outputs | `infra/opentofu/*.tf` | feature | large | T1 |
| T3 | Update scaffold and migrations for public-safe onramp-host defaults | `scaffold/`, `scripts/migrate-values.py`, tests, docs as needed | feature | medium | T2 |
| T4 | Add minimal onramp-host inventory mapping and playbook stub for registry parity | `infra/ansible/inventory/tfvars.py`, `infra/ansible/playbooks/onramp-host.yml`, `infra/ansible/roles/onramp_host/`, tests | feature | medium | T1,T2 |
| V1 | Validate OpenTofu/service-selection/inventory substrate | commands only | validation | medium | T1,T2,T3,T4 |
| T5 | Implement Ansible onramp-host role for Podman, SSH hardening, and network defaults | `infra/ansible/roles/onramp_host/`, `infra/ansible/playbooks/onramp-host.yml` | feature | medium | V1 |
| V2 | Validate Ansible syntax/lint and onramp-host targeting | commands only | validation | medium | T5 |
| T6 | Add Onramp SearXNG handoff artifact | `docs/onramp-searxng-handoff.md` or similar | docs | small | V2 |
| T7 | Add Hermes endpoint contract docs/scaffold variables | `docs/`, `scaffold/.env.example`, Hermes role only if endpoint env wiring is in scope | docs/config | small | T6 |
| T8 | Add public-safe onramp-host rollback and future deployment runbook | `docs/`, README/docs index as needed | docs | small | T7 |
| V3 | Validate SearXNG ownership boundary, docs navigation, and rollback runbook | commands only | validation | small | T6,T7,T8 |
| F1-F7 | Final gates | plan/evidence | validation/archive | small/medium | V3 |

## Execution Waves

### Wave 0 -- Preflight

**T0: Inspect provider/repo/Onramp patterns and initialize evidence**

Acceptance criteria:

1. Evidence file exists without truncating prior records.
   - Verify: `mkdir -p .specs/searxng-podman-runtime/evidence && test -f .specs/searxng-podman-runtime/evidence/validation.jsonl || : > .specs/searxng-podman-runtime/evidence/validation.jsonl; test -f .specs/searxng-podman-runtime/plan.md && test -f .specs/searxng-podman-runtime/evidence/validation.jsonl`
2. Current repo state is captured without exposing private values.
   - Verify: `git status --short --branch`
3. Provider/resource shape for a Proxmox VM is verified locally or from authoritative docs before HCL implementation.
   - Verify: run a non-mutating provider schema/documentation check through the repo tooling, such as `just validate` provider initialization plus an approved containerized `tofu providers schema`/provider-doc inspection command if available, then record sanitized evidence naming provider version/schema source and whether `proxmox_virtual_environment_vm` supports the selected boot-source/cloud-init approach.
4. Existing repo parity constraints are identified before ordering implementation.
   - Verify: inspect `tests/test_service_registry_parity.py`, `scripts/settings.py`, and `infra/ansible/inventory/tfvars.py`; record sanitized summary that `onramp_host` must be added consistently across service registry, inventory hosts, and playbook paths before parity validation.
5. Optional read-only Onramp context is checked without storing raw sibling-repo content.
   - Verify: `test -d C:/Projects/Personal/onramp-vNext && echo onramp-context-present || echo onramp-context-absent-generic-handoff`; if present, inspect only enough public-safe structure to name expected Onramp handoff terms and record a sanitized summary.

**T0b: Generate planned public-safety file list**

Acceptance criteria:

1. `.specs/searxng-podman-runtime/evidence/public-safety-files.txt` exists before any `--tracked-files` public-safety scan.
   - Verify: `test -f .specs/searxng-podman-runtime/evidence/public-safety-files.txt`
2. The file list includes every touched tracked file and planned untracked source/spec/evidence artifact, including README/docs/scaffold/scripts/infra/test files and this plan.
   - Verify: compare against `git diff --name-only` plus planned untracked files; update the list before each final public-safety scan.
3. The list itself contains only repo-relative paths and no private values paths except generic scaffold files.
   - Verify: `if rg -n '(^|/)values/|settings.local.json|terraform.tfstate|tfplan|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+' .specs/searxng-podman-runtime/evidence/public-safety-files.txt; then exit 1; fi`

**V0: Validate preflight findings and no unsafe mutation**

Checks:

- Run T0 and T0b acceptance criteria.
- Confirm no `just plan`, `just apply`, apply/import/destroy/state commands, or live service mutation were run.
- Confirm current uncommitted work is not discarded.
- Confirm provider feasibility is either actionable for source implementation or the plan is updated to blocked before any archive attempt.

### Wave 1 -- Infrastructure substrate and registry parity

**T1: Add `onramp_host` to service selection, dependency semantics, and settings validation**

Acceptance criteria:

1. `onramp_host` is accepted by settings validation and included in `settings.example.json`.
   - Verify: `python scripts/settings.py --settings settings.example.json validate && python scripts/settings.py --settings settings.example.json services | rg -q 'onramp_host'`
2. Existing services still validate and dependency behavior is unchanged except for explicit `onramp_host` semantics.
   - Verify: run settings unit tests, including missing/default settings and duplicate/unknown service cases.
3. Hermes does **not** require `onramp_host` in settings validation because `HERMES_WEB_SEARXNG_URL` may point at any approved SearXNG endpoint.
   - Verify: add/update tests proving `hermes` alone remains valid and `onramp_host` can be selected independently.
4. Service registry parity is maintained with OpenTofu enabled-services validation and inventory service hosts.
   - Verify: `python -m unittest tests.test_service_registry_parity tests.test_settings` or the current equivalent tests.

**T2: Add OpenTofu onramp-host VM boot-source contract, variables/resources/outputs**

Acceptance criteria:

1. HCL contains an optional onramp-host VM resource gated by `local.onramp_host_enabled` or equivalent.
   - Verify: static inspection confirms `count` or `for_each` is directly tied to `local.onramp_host_enabled`; grep alone is not sufficient.
2. The VM boot source/template contract is explicit and public-safe.
   - Verify: variables and scaffold include placeholder Debian 13 template/image identifiers, datastore/cloud-init requirements, and validation; provider schema evidence from T0 matches the chosen implementation.
3. Variables cover VM shape and include validation for static IP/CIDR, VMID, hostname, DNS servers, VLAN, startup settings, deployment user, and SSH policy. MAC validation is required only if a MAC variable is added.
   - Verify: targeted HCL inspection plus `just validate`.
4. App-host VMID and non-DHCP address are checked for uniqueness against other service VMIDs and addresses in available tfvars/scaffold validation tooling.
   - Verify: unit tests or helper validation fail on duplicate onramp-host VMID/IP and pass on scaffold defaults.
5. Outputs expose only non-secret onramp-host connection facts.
   - Verify: `rg -n 'onramp_host_.*(vmid|address|hostname|ssh|onramp)' infra/opentofu/outputs.tf` and inspect that no secrets or real values are emitted.

**T3: Update scaffold and migrations for public-safe onramp-host defaults**

Acceptance criteria:

1. `scaffold/terraform.tfvars` includes public-safe onramp-host defaults using placeholder hostnames and RFC 5737/example addresses.
   - Verify: `rg -n 'onramp_host' scaffold/terraform.tfvars && python scripts/public-safety-check.py --tracked-files .specs/searxng-podman-runtime/evidence/public-safety-files.txt`
2. Existing values repos can be migrated idempotently without printing secrets or private topology.
   - Verify: migration tests cover onramp_host enabled in `settings.local.json`, onramp_host absent, and second-run idempotence.
3. Migration stdout contains only key names/generic labels, not URL, hostname, IP, token, generated secret, or private value contents.
   - Verify: unit tests assert migration output redaction for onramp-host/Hermes SearXNG endpoint additions.
4. Documentation says private `values/terraform.tfvars` remains the source of truth for onramp-host VM shape.
   - Verify: `rg -n 'onramp_host|values/terraform.tfvars' README.md docs scaffold`

**T4: Add minimal onramp-host inventory mapping and playbook stub for registry parity**

Acceptance criteria:

1. Enabled `onramp_host` maps to an Ansible playbook in `scripts/settings.py` and the playbook path exists before service-registry parity validation.
   - Verify: `python scripts/settings.py --settings settings.example.json ansible-playbooks | rg -q 'onramp-host.yml' && test -f infra/ansible/playbooks/onramp-host.yml`
2. Inventory derives the onramp-host target from tfvars rather than duplicating private values by hand.
   - Verify: unit tests or targeted inventory tests cover `onramp_host` hostvars from tfvars, including ansible user/become variables.
3. The onramp-host playbook is included in all-playbooks syntax validation.
   - Verify: `python scripts/settings.py ansible-playbooks --all | rg -q 'onramp-host.yml'`
4. The minimal stub does not install services until T5, but it is syntactically valid and keeps registry/inventory/playbook tests green.
   - Verify: `python -m unittest tests.test_service_registry_parity` and targeted syntax check if available.

**V1: Validate OpenTofu/service-selection/inventory substrate**

Checks:

- T1-T4 acceptance criteria.
- `python scripts/public-safety-check.py --tracked-files .specs/searxng-podman-runtime/evidence/public-safety-files.txt`
- `git diff --check -- infra/opentofu infra/ansible scripts tests settings.example.json scaffold README.md docs .specs/searxng-podman-runtime/plan.md`
- Use targeted tests during repair loops, then run full `just validate` before final gates.

### Wave 2 -- Ansible onramp-host readiness

**T5: Implement Ansible onramp-host role for Podman, SSH hardening, and network defaults**

Acceptance criteria:

1. App-host role installs Podman and the exact Compose-compatible tooling idempotently on Debian 13.
   - Verify: inspect tasks for package/module idempotence and run ansible syntax/lint through validation.
2. Role defines and validates deployment user semantics.
   - Verify: role variables/tasks cover non-root Onramp deploy user, authorized keys ownership/mode, root/password SSH policy, sudo/become policy, deployment directory ownership, and no secret logging.
3. Role validates runtime readiness as the Onramp deploy user.
   - Verify: tasks check SSH/become preflight, `podman info`, compose provider execution, socket/user service if used, directory permissions, and a harmless non-secret smoke/dry-run where safe.
4. Role defines default network exposure policy.
   - Verify: tasks/docs include default-deny host firewall intent, allowed SSH/reverse-proxy ports/source-CIDR variables, and explicit no-host-published-service-ports-by-default language.
5. No SearXNG-specific container is deployed by `homelab-infra` runtime code.
   - Verify: `if rg -n 'searxng|searx' infra/ansible/roles/onramp_host infra/opentofu; then exit 1; fi`; docs/scaffold references outside runtime roles are allowed only for contracts.
6. Evidence/logging is sanitized.
   - Verify: task output does not print private hostnames/IPs, URLs, tokens, or raw inventory; use `no_log` where needed.

**V2: Validate Ansible syntax/lint and onramp-host targeting**

Checks:

- T5 acceptance criteria.
- `python scripts/settings.py ansible-playbooks --all | rg -q 'infra/ansible/playbooks/onramp-host.yml'`
- Ansible syntax/lint through `just validate`; targeted syntax/lint may be used during repair loops, but full `just validate` is still required before completion.

### Wave 3 -- SearXNG/Hermes contract and rollback runbook

**T6: Add Onramp SearXNG handoff artifact**

Acceptance criteria:

1. A handoff doc exists and states that `onramp-vNext` owns the SearXNG container definition.
   - Verify: `rg -n 'onramp-vNext owns|SearXNG|Podman|onramp_host|HERMES_WEB_SEARXNG_URL' docs`
2. The handoff names expected Onramp inputs/outputs without real values.
   - Verify: public-safety scan and placeholder examples only.
3. If read-only Onramp context was available in T0, the handoff uses exact public-safe Onramp terms/commands discovered there. If not, it explicitly says the handoff is generic and requires Onramp-side confirmation before implementation.
   - Verify: doc inspection.
4. The doc includes a copy/paste implementation checklist for the sibling repo, but does not mutate that repo unless separately approved.
   - Verify: doc inspection and `git -C C:/Projects/Personal/onramp-vNext status --short` only if the sibling repo exists and inspection is needed; do not save raw output in this repo.
5. The handoff preserves Onramp service-port semantics and forbids default host-published app ports except through approved Onramp proxying.
   - Verify: `rg -n 'port.*Compose network|host-published|reverse proxy|Caddy' docs/onramp-searxng-handoff.md`

**T7: Add Hermes endpoint contract docs/scaffold variables**

Acceptance criteria:

1. `scaffold/.env.example` documents a placeholder Hermes SearXNG endpoint variable such as `HERMES_WEB_SEARXNG_URL=https://searxng.apps.example.net` if Hermes runtime will consume environment values from `values/.env`.
   - Verify: `rg -n 'HERMES_WEB_SEARXNG_URL|searxng.apps.example.net' scaffold docs`
2. README/docs navigation point operators from Hermes and Onramp contract docs to the SearXNG handoff.
   - Verify: `rg -n 'onramp-searxng|SearXNG' README.md docs/README.md docs`
3. The docs state whether Hermes runtime env templating is implemented in this slice.
   - Verify: if implemented, add acceptance checks for the Hermes Ansible/runtime file that passes the env var; if not implemented, docs and success criteria say endpoint consumption is a follow-up for Hermes plugin/runtime implementation.
4. `hermes` remains independently selectable without `onramp_host`.
   - Verify: settings tests from T1 still pass.

**T8: Add public-safe onramp-host rollback and future deployment runbook**

Acceptance criteria:

1. A docs/runbook section explains how to disable `onramp_host` service selection in settings and what a future reviewed `just plan` should be expected to show.
   - Verify: `rg -n 'disable.*onramp_host|just plan|destroy|retention|rollback' docs README.md`
2. The runbook distinguishes VM deletion versus retention, DNS cleanup ownership, Onramp app cleanup, and private values follow-up.
   - Verify: targeted doc inspection with public-safe placeholders only.
3. The runbook states no state surgery, import, destroy, or live mutation may happen without explicit approval.
   - Verify: `rg -n 'state surgery|import|destroy|explicit approval' docs README.md`
4. The runbook includes future deployment validation requirements: reviewed `just plan`, explicit approval, `just apply`, SSH reachability, Podman readiness, Onramp SearXNG deployment, and Hermes endpoint smoke validation.
   - Verify: targeted doc inspection.

**V3: Validate SearXNG ownership boundary, docs navigation, and rollback runbook**

Checks:

- T6-T8 acceptance criteria.
- Confirm runtime roles do not deploy SearXNG directly from `homelab-infra` using the failing check from T5.
- Public-safety and whitespace checks for all touched docs/scaffold/spec files.

## Dependency Graph

```text
Wave 0: T0 -> T0b -> V0
Wave 1: V0 -> T1 -> T2 -> T3; T1,T2 -> T4; T1,T2,T3,T4 -> V1
Wave 2: V1 -> T5 -> V2
Wave 3: V2 -> T6 -> T7 -> T8 -> V3
Final: V3 -> F1 -> F2 -> F3 -> F4 -> F5 -> F6 -> F7
```

## Success Criteria

1. `onramp_host` is a first-class optional service in `homelab-infra` settings, OpenTofu, scaffold defaults, outputs, inventory mapping, and Ansible playbook selection.
   - Verify: targeted tests plus `python scripts/settings.py --settings settings.example.json validate`.
2. The onramp-host substrate is specified as a Debian 13 Podman VM target with an explicit boot-source/template contract, not an LXC and not a SearXNG-specific service.
   - Verify: HCL/resource inspection, provider schema evidence, scaffold placeholders, and docs checks.
3. The onramp-host runtime contract is specific enough for Onramp: deploy user, SSH policy, Podman mode, Compose provider, socket/API semantics if used, deployment directory, and default network exposure are documented and validated at source level.
   - Verify: Ansible role/playbook inspection, syntax/lint, and `just validate`.
4. Onramp has a precise public-safe handoff for deploying SearXNG under Podman, or the handoff is explicitly labeled generic when sibling repo context was unavailable.
   - Verify: handoff doc acceptance checks.
5. Hermes has a documented endpoint variable/contract for consuming SearXNG, with runtime/env templating status explicitly marked implemented or follow-up.
   - Verify: scaffold/docs checks for `HERMES_WEB_SEARXNG_URL` or final chosen variable.
6. Source-only completion is not misrepresented as a live SearXNG backend.
   - Verify: docs and plan state no live SearXNG URL exists until a later approved deployment plan runs.
7. Full repo validation passes.
   - Verify: `scripts/values.sh check && just validate`.

## Validation Contract

Required automated validation:

1. Task-specific acceptance criteria from every wave.
2. Planned-file list freshness:
   - Command: refresh `.specs/searxng-podman-runtime/evidence/public-safety-files.txt` from all touched tracked files plus planned untracked docs/spec/evidence files before public-safety scans.
3. Public-safety scan for tracked and planned untracked files:
   - Command: `python scripts/public-safety-check.py` and `python scripts/public-safety-check.py --tracked-files .specs/searxng-podman-runtime/evidence/public-safety-files.txt`
4. Whitespace validation:
   - Command: `git diff --check`
5. Settings/inventory/migration tests:
   - Command: run the relevant `python -m unittest ...` tests, including `tests.test_service_registry_parity`, settings tests, inventory tests, and migration tests that are added/updated for `onramp_host`.
6. Repo-wide validation:
   - Command: `scripts/values.sh check && just validate`

Manual validation:

- Required for this source-only implementation: no.
- Required before live provisioning: yes, but live provisioning is out of scope. A later `just plan` review and explicit approval are required before `just apply`.
- Required before mutating `onramp-vNext`: yes, but sibling-repo mutation is out of scope. Read-only inspection is allowed when available and must be sanitized.

Deployment validation:

- Required for this plan: no, because this plan must not run `just plan`, `just apply`, deploy SearXNG, or perform live service mutation.
- A future deployment plan must run `just plan`, summarize creates/changes/destroys, obtain explicit approval, run `just apply`, verify SSH and Podman readiness on the live onramp host, deploy SearXNG through Onramp, and smoke-test the Hermes endpoint.

Archive rule:

- Archive only after all source changes and required automated validation pass.
- Do not archive if provider boot-source feasibility is unresolved, `just validate` fails, public-safety fails, planned-file list is missing/stale, onramp-host service selection is incomplete, service-registry parity fails, or the plan accidentally deploys SearXNG from `homelab-infra` runtime roles.
- F7 is complete only after `/do-it` moves the plan and sibling review/evidence artifacts to `.specs/archive/searxng-podman-runtime/` and updates evidence with `archive_status: archived`.
- Do not archive if tracked evidence contains real hostnames, real IPs, private inventory, raw `values/` content, tokens, credentials, or unredacted Onramp/private repo output.

## Telemetry & Evidence Contract

Record sanitized JSONL evidence in `.specs/searxng-podman-runtime/evidence/validation.jsonl` with these fields:

```json
{"episode_id":"searxng-podman-runtime","phase_id":"wave-1","task_id":"T1","validation_command":"...","status":"pending|passed|failed|blocked","archive_status":"not_ready|ready|archived","started_at":"ISO-8601","completed_at":"ISO-8601","evidence":"sanitized summary"}
```

Allowed tracked evidence:

- pass/fail status
- command names
- repo-relative artifact paths
- placeholder hostnames/domains such as `onramp-host.example.internal` and `searxng.apps.example.net`
- generic summaries such as `provider schema supports selected VM boot-source` or `onramp-context-present`

Forbidden tracked evidence:

- raw private `values/` content
- real hostnames, domains, IPs, DNS records, SSH targets, URLs, or inventory
- tokens, credentials, generated secrets, private keys, or raw command logs containing them
- raw sibling-repo file listings or content when those names reveal private deployment structure

When evidence must mention onramp-host address, hostname, inventory, SSH target, or Onramp URL, redact to placeholders before writing tracked evidence. Raw logs may remain only in ignored local locations and must not be archived in this public repo.

## Risk & Manual Gate Decision

- Risk level for source implementation: medium, because it adds new infrastructure resource definitions and orchestration paths.
- Risk level for live deployment: high enough to require explicit approval, because it creates a new Proxmox VM and network/DNS-facing substrate.
- Blast radius for this plan: tracked source/scaffold/docs/tests only; no live mutation.
- Rollback for this plan: normal Git revert before any future apply.
- Rollback after future apply: must follow the reviewed onramp-host rollback/runbook and explicit operator approval; no state surgery/import/destroy without approval.
- Manual approval before source edits: not required.
- Manual validation after source edits: not required if automated validation passes.
- Manual approval before `just plan` / `just apply`: required and out of scope for this plan.
- Manual approval before sibling-repo mutation: required and out of scope for this plan.
- Decision reason: source edits are reversible and validated; live provisioning, external repo mutation, and deployment have larger blast radius and are deferred.

## Handoff Notes

- This plan intentionally moves farther than the archived contract plan, but still stops before live infrastructure mutation.
- If implementation discovers that the current Proxmox provider cannot safely provision the desired Debian 13 VM through HCL, stop and update `## Execution Status` with provider evidence and an alternative, such as a documented image/template prerequisite. Do not archive as complete.
- If `onramp-vNext` changes are approved during execution, create a separate commit/validation trail in that repository and do not mix its private or generated artifacts into this public repo.
- If private values are missing, complete source edits that do not need them, but block final repo-wide validation/archive until `scripts/values.sh check` passes or the operator approves setup.
- Do not treat grep-only checks as sufficient where unit tests or parser-backed validation exist in this repo.

## Review Update Notes

Review findings from `.specs/searxng-podman-runtime/review-1/` were applied before execution. The main changes were: explicit VM boot-source contract, planned-file-list generation, stronger settings/inventory/migration tests, SSH/user/network hardening, Onramp context handling, runtime contract specificity, rollback runbook requirements, and clearer source-only completion scope.

## Execution Status

- Status: completed-and-archived
- Last updated: 2026-07-07
- Last completed wave/gate: F7 archive completed
- Next wave/gate to run: none
- Implemented: optional onramp_host service selection, Proxmox VM boot-source contract, scaffold/migration/inventory/playbook support, onramp_host Ansible Podman readiness role, SearXNG Onramp handoff, Hermes endpoint contract, and rollback runbook.
- Validation passed:
  - `scripts/python.sh -m unittest tests.test_settings tests.test_tfvars_inventory tests.test_migrate_values tests.test_service_registry_parity tests.test_onramp_host_contract`
  - `python scripts/public-safety-check.py --tracked-files .specs/searxng-podman-runtime/evidence/public-safety-files.txt`
  - `git diff --check`
  - `scripts/validate-public.sh`
  - `scripts/values.sh check && just validate`
- Manual validation: not required for this source-only implementation. Live provisioning, `just plan`, `just apply`, sibling-repo mutation, and SearXNG deployment remain out of scope and require a later reviewed approval gate.
- Deployment validation: not required for this plan.
- Archive status: archived to `.specs/archive/searxng-podman-runtime/`.

## Workflow Eval Record

- outcome: completed-and-archived
- archive_status: archived
- archive_path: `.specs/archive/searxng-podman-runtime/plan.md`
- validation_commands:
  - `scripts/python.sh -m unittest tests.test_settings tests.test_tfvars_inventory tests.test_migrate_values tests.test_service_registry_parity tests.test_onramp_host_contract` -- passed
  - `python scripts/public-safety-check.py --tracked-files .specs/searxng-podman-runtime/evidence/public-safety-files.txt` -- passed
  - `git diff --check` -- passed
  - `scripts/validate-public.sh` -- passed after formatting repair
  - `scripts/values.sh check && just validate` -- passed
- manual_gate_decisions: source-only manual validation not required; live provisioning and sibling-repo mutation deferred.
- deployment_gate_decisions: deployment validation not required; `just plan`, `just apply`, Onramp SearXNG deploy, and Hermes smoke test are future-plan work.
- checklist_completion_state: all checklist items checked before archive.
- friction:
  - category: validation-repair; severity: low; evidence: `tofu fmt -check` initially reported onramp-host HCL/scaffold formatting; impact: delayed validation; recommended_change: run formatter before first aggregate validation; candidate_test: keep `tofu fmt -check` in validate-public.
  - category: private-values-migration; severity: low; evidence: `just validate` ran the documented migration path and reported a placeholder Hermes SearXNG key addition in private values; impact: validation can mutate ignored private values during source-plan execution; recommended_change: future source-only plans should state whether validation migrations are permitted or should be run in a temporary values fixture; candidate_test: add dry-run support for migrate-values.
- missing_evidence: none for source completion; live endpoint evidence intentionally absent and out of scope.
- improvement_candidates:
  - category: provider-schema; severity: low; evidence: host `tofu` binary unavailable, containerized `tofu` later validated provider v0.111.0; impact: preflight evidence had to use lock file plus authoritative docs before container validation; recommended_change: document provider schema inspection through the tooling container; candidate_test: add a read-only provider schema helper script.
- eval_confidence: high
- post_run_reviewers: deterministic-checks-only
- execution_outcome: completed
- panel_quality_label: right-sized
- panel_quality_reason: review findings anticipated boot-source, public-safety, migration, and ownership-boundary risks; validation found only formatting and workflow-friction issues.
- panel_quality_confidence: medium
