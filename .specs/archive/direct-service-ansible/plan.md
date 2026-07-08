---
created: 2026-07-07
status: completed
completed: 2026-07-07
---

# Plan: Convert Service Ansible to Direct Service Access

## Context & Motivation

The operator model for this homelab is direct service access: agents and operators should use each service's LAN DNS/IP, SSH user, and HTTPS endpoint for normal diagnostics and steady-state configuration. The user corrected a bad assumption that Hermes should be accessed by SSHing to Proxmox and using `pct enter`; the correct model is direct SSH to the service endpoint, e.g. `ssh <user>@hermes.example.internal`.

`AGENTS.md` now says direct service SSH/HTTPS is the normal path and Proxmox `pct` access is reserved for lifecycle diagnostics, bootstrap, console recovery, or explicit operator instruction. The existing Ansible implementation only partially matches that doctrine: `onramp-host.yml` already targets `onramp_host` directly, but most LXC playbooks still target `pve`, and several roles perform steady-state service configuration through `pct exec`/`pct push`.

Current evidence from the repo:

- Direct already: `infra/ansible/playbooks/onramp-host.yml` targets `hosts: onramp_host`.
- Proxmox-targeted service playbooks include `technitium.yml`, `caddy-proxy.yml`, `forgejo.yml`, `forgejo-runner.yml`, `infisical.yml`, `hermes.yml`, and `tailscale-client.yml`.
- Roles with steady-state `pct` usage include `caddy_proxy`, `forgejo`, `forgejo_runner`, `infisical`, and `hermes`; Technitium also has `pct` tasks and must be reviewed directly, even if an earlier quick count missed it.
- `caddy-proxy.yml` is not a separate service host. It is configured on the Technitium/DNS LXC and currently uses `technitium_vmid`; there is no `caddy_proxy` dynamic inventory group.
- Forgejo Runner includes both in-runner configuration and Proxmox-host SSH/trust/authorization work; it must be split along that boundary rather than moved wholesale into the runner LXC.
- Empirical direct-access probe after review: enabled LXCs and the Onramp host have TCP/22 open; direct Ansible ping succeeds for enabled services when host-key checking is bypassed; default strict host-key checking currently blocks the LXCs until known_hosts is refreshed. Effective direct user is root in the current inventory. This means the immediate operational gap is host-key trust management, not SSH daemon absence, for the already-provisioned services. Fresh-service conversion must still keep a bootstrap/recovery boundary if SSH/Python/become fails.

This plan rolls out the direct-service doctrine to all repo-managed services while preserving the Proxmox boundary for lifecycle readiness, known_hosts/SSH trust setup, minimal direct-SSH bootstrap/recovery, storage prep, and other Proxmox-owned host operations.

## Constraints

- Platform: Windows host with Git Bash/MSYS (`MINGW64_NT-10.0-26200`), commands run through Bash and repo Docker Compose tooling.
- Shell: `/usr/bin/bash`.
- Public tracked files must remain generic/public-safe; no real domains, IPs, hostnames, tokens, keys, or private inventory in tracked files.
- Private values stay in ignored `values/`; do not commit `values/`, `settings.local.json`, state, plans, or credentials.
- Use public Just workflow commands for normal validation, especially `just validate`.
- Do not run `just apply`, OpenTofu apply/destroy/import/state surgery, or destructive operations without explicit user approval.
- Steady-state service configuration should use direct Ansible SSH to service hosts.
- Proxmox access remains valid for OpenTofu/provisioning adjacency, LXC readiness, host-key discovery/refresh when direct SSH host keys change, minimal direct-SSH/Python bootstrap when explicitly needed, storage prep, first-boot recovery, console recovery, and situations where direct service access is unavailable.
- Preserve idempotence, `no_log` on secret tasks, service-local Caddy pattern, and existing service behavior.
- Do not broaden SSH exposure as part of this migration. If a service lacks direct SSH/become access, diagnose and block or use an explicit approval-gated bootstrap path; do not silently enable root SSH or widen firewall access.
- The final design must work for both existing deployments and fresh/new-user setups starting from `just setup` → `just plan` → approved `just apply`. Fresh LXCs may not have local known_hosts entries yet and may rely on OpenTofu-injected LXC SSH keys plus a bootstrap check before direct Ansible can run.
- The bootstrap handoff must be an explicit reusable implementation boundary, not just validation prose. Add a `direct_access_ready`-style playbook/role/helper boundary with explicit execution contexts: Proxmox-side readiness/minimal bootstrap on `pve`, host-key trust management on the controller/infra container, and direct SSH/Python/root-or-become probes on the service host only after trust is established. Do not implement it as a direct-host role that must connect before it can repair trust.
- Convert service roles incrementally with validation gates; do not perform live service reconfiguration as part of plan archive unless separately approved. Source-only validation may archive without live services when private live values/resources are unavailable; existing-live deployments must run live direct probes when values/resources are present; approved fresh rollouts must run the direct-access handoff after LXC creation and before service roles.
- DRY up repeated patterns where it directly reduces risk in this migration: direct-access handoff, settings-derived validation, direct template/copy semantics, and shared Caddy/Docker primitives. Do not create broad abstractions for app-specific secrets, registration flows, or DNS sync until behavior is preserved and tests cover the shared surface. DRY checks must be concrete structure/policy checks, not subjective abstraction scoring.
- Host-key trust is a security boundary. Use a persistent gitignored managed known_hosts file under `values/` (for example `values/ansible/known_hosts`) via explicit `UserKnownHostsFile`; derive expected fingerprints through an authenticated Proxmox/LXC boundary where possible; classify states as `absent-added`, `unchanged-verified`, or `changed-conflict-blocked`; fail closed on changed/conflicting existing keys unless the user explicitly approves replacement.
- Root direct SSH is accepted only with compensating controls for this migration: scoped local deployment keys, no agent forwarding, strict host-key checking, managed known_hosts, sanitized logs, and documented follow-up/deferral for dedicated non-root service users.

## Risk & Manual Gate Decision

Manual gates are exceptional. Decide based on blast radius and rollback, not generic confidence. Be conservative for work/shared systems and data/resources that cost money; treat personal/local GitHub repos as localized-to-user when changes are reversible and validated.

- **Risk level:** Medium-high
- **Blast radius:** Local/home-lab infrastructure repository and multiple live homelab services if deployed
- **Rollback:** Known for source changes via Git; known for live config if prior role is restored and re-applied; no destructive infrastructure mutation required for MVP
- **Manual approval before action:** Not required for source edits, unit tests, syntax checks, static regression checks, read-only direct SSH/become probes, or check-mode dry runs. Required before `just apply`, approval-gated Proxmox bootstrap mutations, replacing an existing trusted host key, or any live service reconfiguration.
- **Manual validation after action:** Not required for MVP archive. Automated validation, direct connectivity/become checks, syntax checks, and check-mode/dry-run evidence are sufficient.
- **Decision reason:** The MVP is a source-level Ansible architecture refactor plus validation with clear execution modes. Source-only/archive validation uses public fixtures, syntax/policy/unit checks, and no live service mutation. Existing-live validation uses private values and direct probes when services already exist. Fresh rollout validation runs only after explicit apply/deployment approval. Live deployment affects multiple services and therefore needs explicit approval, but deployment is not required to complete/archive the source-level plan.

## Alternatives Considered

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Convert all repo-managed service configuration to the direct-service pattern, preserving Proxmox only for readiness/bootstrap/storage/recovery | Aligns implementation with doctrine everywhere; prevents future agents from defaulting to Proxmox; establishes one consistent pattern | Larger cross-cutting Ansible refactor; must preserve service-specific secrets, direct access, and idempotence | **Selected** |
| Convert Hermes only first | Lower risk and faster; proves pattern on immediate problem | Leaves other service playbooks contradicting the new doctrine; user explicitly asked why this half measure was chosen | Rejected for this revised plan |
| Keep Proxmox-mediated Ansible and only update `AGENTS.md` | Minimal implementation work | Documentation and code remain inconsistent; agents will keep using `pct exec` | Rejected |
| Add a fake `caddy_proxy` inventory group | Makes one assertion easy | Invents a service that does not exist; risks OpenTofu/inventory churn | Rejected; caddy-proxy targets Technitium |
| Move every role wholesale to direct service hosts | Simple mental model | Incorrect for Forgejo Runner and any Proxmox-host-boundary task | Rejected; split pve-boundary tasks explicitly |
| Extract broad generic roles for every repeated task immediately | Could reduce line count | High risk of hiding service-specific semantics during an access-pattern migration | Rejected for MVP; extract only low-risk shared primitives first |

The opposite pattern, Proxmox-mediated `pct exec`, remains correct when direct SSH is unavailable, when waiting for an LXC to boot, for approved bootstrap/recovery, for Proxmox-host storage/trust operations, or for console recovery. That exception must be explicit, minimal, and isolated from steady-state service roles.

## Objective

Refactor Ansible so all first-class service configuration uses direct service inventory targets by default, while Proxmox-targeted plays remain only for lifecycle readiness, explicit bootstrap/recovery, storage prep, and Proxmox-host-boundary operations.

## MVP Boundary

The smallest user-visible outcome is: every enabled normal service playbook has an explicit reusable direct-access handoff before steady-state configuration, then a direct service configuration play; service roles no longer use Proxmox `pct` for steady-state configuration; repeated migration-critical patterns are centralized where safe; YAML-aware tests prevent regression; validation commands derive targets from settings/inventory instead of hard-coded service lists; and the flow works for fresh/new-user setups where LXCs have just been created and no service host keys are trusted locally yet.

Services in scope:

- Technitium service configuration, direct on `technitium`
- Caddy proxy configuration, direct on `technitium` because it is Technitium/DNS LXC-local, not a `caddy_proxy` host
- Forgejo service configuration, direct on `forgejo`
- Forgejo Runner in-runner configuration, direct on `forgejo_runner`, with Proxmox-host trust/authorization split into an explicit pve-boundary play/role if still required
- Infisical service configuration, direct on `infisical`
- Hermes service configuration, direct on `hermes`
- Tailscale client configuration, direct on `tailscale_client` if enabled/supported
- Onramp host remains as-is except for regression tests because it already uses direct service targeting

Infrastructure/lifecycle in scope only as boundaries:

- Keep `lxc_ready` on `pve`.
- Keep storage prep on `pve`.
- Keep `technitium-dns.yml` on `localhost` because it orchestrates DNS API sync, not in-guest steady-state service config.
- Allow an explicit, approval-gated pve bootstrap/recovery path only when direct SSH/Python/become is missing.

## Explicit Deferrals

- Live `just apply` deployment unless separately approved.
- Creating new non-root operator users on each service. This plan verifies current direct SSH/become posture and must not broaden root SSH exposure; dedicated accounts are a separate design/deployment task.
- Reworking OpenTofu resource shape, DNS records, hostnames, IPs, firewalls, or service ports.
- Deploying Menos or adding Menos/Hermes integration.
- Removing Proxmox recovery tooling.
- Rewriting all shell snippets into perfect Ansible modules where it would change semantics; prefer modules where practical, but preserve behavior first.
- Full genericization of every service role. This plan should extract only proven repeated primitives: direct-access handoff, settings-derived validation, direct file/template handling, and optionally shared Caddy/Docker includes where semantics are already identical.

## Project Context

- **Language**: Infrastructure repo with Justfile, Bash/Python helper scripts, OpenTofu HCL, Ansible YAML, and Python unit tests.
- **Test command**: `just validate`
- **Lint command**: Included in `just validate` via public-safety checks, OpenTofu validation/TFLint, ShellCheck, Python tests, Ansible syntax, and ansible-lint.
- **Focused commands**: `scripts/python.sh -m unittest ...`; `scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; ... ansible-playbook --syntax-check ...'`.
- **Existing specs**: `.specs/archive/onramp-host-pilot`, `.specs/archive/searxng-podman-runtime`, `.specs/direct-hermes-ansible`. This plan uses `.specs/direct-service-ansible`.

## Automation Plan

| Operation | Command/wrapper | Credentials | Evidence |
|-----------|-----------------|-------------|----------|
| Preflight inventory/status | `git status --short --untracked-files=all && rg -n "pct|hosts: pve" infra/ansible/playbooks infra/ansible/roles -g '*.yml'` | None | Terminal-only baseline; do not archive raw private inventory |
| Build validation helper | Create `scripts/check-direct-service-ansible.py` plus tests; invoke with `scripts/python.sh scripts/check-direct-service-ansible.py --help` | None | Helper usage output; unit tests |
| Extract shared migration primitives | Add `direct_access_ready` boundary and, where safe, shared task includes for direct template/copy validation and Caddy/Docker repeated setup | None | Reduced repeated role boilerplate with tests proving semantics are unchanged |
| Fresh setup bootstrap implementation | Add reusable `direct_access_ready` boundary and validate with `scripts/python.sh scripts/check-direct-service-ansible.py bootstrap-plan --settings settings.example.json --redacted` | None for public check; private values/SSH keys for live use | Public-safe proof and implementation path: LXC ready → minimal SSH/Python bootstrap if approved/needed → persistent host-key trust → direct SSH/Python/root-or-become probe → direct role |
| Direct host-key trust | `INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; export ANSIBLE_SSH_COMMON_ARGS="-o UserKnownHostsFile=/workspace/values/ansible/known_hosts -o StrictHostKeyChecking=yes -o ForwardAgent=no"; python scripts/check-direct-service-ansible.py known-hosts --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted'` | Existing private values and SSH keys through approved local mechanisms | Sanitized checked/skipped/absent-added/unchanged-verified/changed-conflict-blocked summary only; no raw host keys, hostnames, IPs, or domains |
| Direct access matrix | `INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; export ANSIBLE_SSH_COMMON_ARGS="-o UserKnownHostsFile=/workspace/values/ansible/known_hosts -o StrictHostKeyChecking=yes -o ForwardAgent=no"; python scripts/check-direct-service-ansible.py connectivity --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted'` | Existing private values and SSH keys through approved local mechanisms | Sanitized checked/skipped/fail group summary only; no hostnames/IPs/domains |
| Direct become/Python probe | Same helper command with `become-probe`, expecting root UID through Ansible become or explicit root posture where the direct service role uses `become: true` | Existing private values and SSH keys | Sanitized group/status/error-class summary |
| Implement direct playbook targeting | Targeted edits to service playbooks and `site.yml` if needed | None | Git diff and helper validation |
| Implement direct role execution | Targeted edits under service roles; split pve-boundary tasks where required | None | Git diff, YAML-aware policy tests, syntax/check-mode evidence |
| Regression tests | `scripts/python.sh -m unittest tests.test_ansible_safety tests.test_tfvars_inventory tests.test_settings tests.test_service_registry_parity` | None | Tests exit 0 |
| Syntax/check-mode validation | `scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; python scripts/check-direct-service-ansible.py syntax --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --redacted; python scripts/check-direct-service-ansible.py check-mode --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --redacted'` | Private inventory only; no mutation intended | Sanitized pass/fail summary; check-mode exception budget with task path, reason, idempotence guard, and compensating evidence |
| Repo-wide validation | `just validate` | Existing local private values and Docker tooling | Exits 0 |
| Deployment | Not required for MVP. If explicitly approved: `just plan`, review output, then serial service rollout via `just apply` or approved narrower playbook execution | Private values/API/SSH credentials through approved mechanisms | Apply output and post-apply direct service matrix; not required for archive |
| Rollback | Before commit: `git restore --source=HEAD -- <changed files>`; after commit: `git revert <commit>`; if live rollout approved, per-service backups and rollback steps must be written before applying | None for source rollback | Git status/revert commit; live rollback evidence only if deployment occurs |

## Execution Checklist

This checklist is the durable resume ledger for `/do-it`. Every executable task, validation gate, and final completion gate has exactly one matching checkbox. Checked means verified complete; unchecked means pending, in-progress, blocked, or invalidated.

`/do-it` must mark each item `[x]` immediately after that item passes its required verification and before starting any dependent or next sequential step. `/review-it` must preserve checked state, add unchecked items for new executable work, and never mark implementation or validation work complete.

### Wave 1

- [x] T2: Add settings-aware direct-service validation helper, reusable direct-access bootstrap handoff, and policy guardrails
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] V1: Validate wave 1
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record

### Wave 2

- [x] T1: Determine execution mode and verify direct inventory/SSH/Python/become posture when live services are in scope
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] V2: Validate wave 2
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record

### Wave 3

- [x] T3: Convert service playbooks to lifecycle-plus-direct-service structure and shared handoff usage
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] T4: Convert Technitium/Caddy/Hermes/Infisical direct role execution and extract safe shared Caddy/file primitives
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] T5: Convert Forgejo and Forgejo Runner with explicit pve-boundary split
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] T6: Review/convert Tailscale and preserve already-direct Onramp behavior
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] V3: Validate wave 3
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record

### Wave 4

- [x] T7: Update site orchestration, docs, and migration notes for the new access pattern
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] T8: Add final regression coverage, DRY-boundary checks, and sanitized evidence enforcement
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] V4: Validate wave 4
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record

### Final Gates

- [x] F1: Task-specific verification complete
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] F2: Repo-wide validation complete
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] F3: Manual validation not required or completed
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] F4: Deployment validation complete or not required
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record
- [x] F5: Archive preflight complete
  - Status: completed
  - Evidence: see Execution Status and Workflow Eval Record

## Task Breakdown

| # | Task | Files | Type | Model | Agent | Depends On |
|---|------|-------|------|-------|-------|------------|
| T2 | Add settings-aware direct-service validation helper, reusable direct-access bootstrap handoff, and policy guardrails | 3-6 | feature | medium | qa-engineer | -- |
| V1 | Validate wave 1 | -- | validation | medium | validation-lead | T2 |
| T1 | Determine execution mode and verify direct inventory/SSH/Python/become posture when live services are in scope | 0-2 | research | medium | ansible-specialist | V1 |
| V2 | Validate wave 2 | -- | validation | medium | validation-lead | T1 |
| T3 | Convert service playbooks to lifecycle-plus-direct-service structure and shared handoff usage | 8-10 | architecture | large | ansible-specialist | V2 |
| T4 | Convert Technitium/Caddy/Hermes/Infisical direct role execution and extract safe shared Caddy/file primitives | 8-14 | architecture | large | engineering-lead | V2 |
| T5 | Convert Forgejo and Forgejo Runner with explicit pve-boundary split | 6-10 | architecture | large | ansible-specialist | V2 |
| T6 | Review/convert Tailscale and preserve already-direct Onramp behavior | 3-6 | feature | medium | ansible-specialist | V2 |
| V3 | Validate wave 3 | -- | validation | large | validation-lead | T3, T4, T5, T6 |
| T7 | Update site orchestration, docs, and migration notes for the new access pattern | 3-6 | feature | medium | docs-specialist | V3 |
| T8 | Add final regression coverage, DRY-boundary checks, and sanitized evidence enforcement | 2-5 | feature | medium | qa-engineer | V3 |
| V4 | Validate wave 4 | -- | validation | large | validation-lead | T7, T8 |

## Execution Waves

### Wave 1

**T2: Add settings-aware direct-service validation helper, reusable direct-access bootstrap handoff, and policy guardrails** [medium] -- qa-engineer
- Note: This task must run before T1 because T1 uses the helper/handoff created here.
- Description: Add a tracked helper, likely `scripts/check-direct-service-ansible.py`, plus tests and an explicit reusable `direct_access_ready`-style boundary. The helper must derive enabled services and playbooks from `scripts/settings.py`/dynamic inventory, map `caddy-proxy.yml` to the `technitium` group, skip disabled services explicitly, and produce sanitized checked/skipped/fail evidence. The reusable handoff must implement the fresh/new-user sequence with explicit host contexts: after OpenTofu creates an LXC, use Proxmox only for readiness/minimal direct-management bootstrap, manage persistent host-key trust on the controller, verify direct SSH/Python/root-or-become, and only then allow direct service roles. Helper subcommands must have a CLI contract: exit 0 only when required checks pass; nonzero for enabled-service failure, parse errors, redaction breach, changed host-key conflict, or missing required inputs; live subcommands must invoke real Ansible/SSH operations and propagate failure.
- Files: `scripts/check-direct-service-ansible.py`, required wrapper playbook `infra/ansible/playbooks/direct-access-ready.yml`, optional supporting role/includes under `infra/ansible/roles/direct_access_ready/**`, committed public fixture inventory/settings for non-live helper tests, `tests/test_ansible_safety.py`, possibly `tests/test_service_registry_parity.py`.
- Acceptance Criteria:
  1. [ ] Helper derives targets from settings/inventory rather than hard-coded loops.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py inventory --settings settings.example.json --redacted`
     - Pass: Output is public-safe and shows enabled public example services mapped to expected groups; caddy proxy maps to Technitium.
     - Fail: Helper hard-codes private enabled services or prints private endpoints.
  2. [ ] YAML-aware tests detect forbidden steady-state `pct` usage, including argv-list forms.
     - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety`
     - Pass: Tests pass and include service roles/playbooks in the assertion, with an explicit allowlist for `lxc_ready`, storage prep, approved bootstrap/recovery, and Proxmox-host-boundary tasks.
     - Fail: Grep-only checks or comment/string-only checks remain.
  3. [ ] Helper exposes and tests a fresh/new-user bootstrap plan backed by a reusable implementation boundary.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py bootstrap-plan --settings settings.example.json --redacted`
     - Pass: Public-safe output shows the ordered path for each enabled example service: `lxc_ready`/approved minimal bootstrap, persistent host-key trust refresh, direct SSH/Python/root-or-become probe, direct service role. It must not require pre-existing known_hosts entries, and it must reference the reusable `direct_access_ready` boundary rather than prose-only sequencing.
     - Fail: Add bootstrap-plan behavior and reusable handoff implementation before direct-access verification depends on it.
  4. [ ] The reusable direct-access handoff has syntax/test coverage and does not become a steady-state configuration backdoor.
     - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety && scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; ansible-playbook --syntax-check infra/ansible/playbooks/direct-access-ready.yml'`
     - Pass: `infra/ansible/playbooks/direct-access-ready.yml` exists and syntax-checks; it may delegate to roles/includes, but it is the required stable wrapper for `/do-it`. Tests verify the handoff only performs allowlisted readiness/bootstrap/known-hosts/probe behavior and fail when the wrapper or included paths are missing.
     - Fail: Split or constrain the handoff so it cannot perform arbitrary service configuration through Proxmox.
  5. [ ] Host-key trust handling is persistent, scoped, and fail-closed.
     - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety && scripts/python.sh scripts/check-direct-service-ansible.py known-hosts --settings settings.example.json --known-hosts-file .specs/direct-service-ansible/evidence/test-known-hosts --check --redacted`
     - Pass: Tests cover `absent-added`, `unchanged-verified`, and `changed-conflict-blocked`; changed existing keys fail unless an explicit approval flag is supplied; updates are atomic; public/example tests use a temp path; live commands use `values/ansible/known_hosts`.
     - Fail: Fix trust-state handling before live probes depend on it.
  6. [ ] Helper exposes public fixtures and exit-code contracts for every non-live subcommand.
     - Verify: `scripts/python.sh -m unittest tests.test_service_registry_parity tests.test_ansible_safety && scripts/python.sh scripts/check-direct-service-ansible.py --help`
     - Pass: Public fixture inventory/settings exercise inventory, bootstrap-plan, playbooks, policy, pve-boundary, structure, and redaction paths; enabled-service failures, parse errors, and redaction breaches produce nonzero exits.
     - Fail: Add fixture coverage and explicit exit-code behavior.
  7. [ ] Tests no longer depend on stale Proxmox task names for secret assertions.
     - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety`
     - Pass: Tests assert semantic no-log/idempotence/mode guarantees, not task names like “Push ... into LXC”.
     - Fail: Update tests to avoid preserving stale Proxmox wording.

### Wave 1 -- Validation Gate

**V1: Validate wave 1** [medium] -- validation-lead
- Blocked by: T2
- Checks:
  1. Run all T2 acceptance criteria.
  2. `scripts/python.sh -m unittest tests.test_ansible_safety tests.test_settings tests.test_service_registry_parity` -- exits 0.
  3. Confirm `scripts/python.sh scripts/check-direct-service-ansible.py --help` exits 0.
- On failure: create a fix task, re-validate after fix.

### Wave 2

**T1: Determine execution mode and verify direct inventory/SSH/Python/become posture when live services are in scope** [medium] -- ansible-specialist
- Blocked by: V1
- Description: First classify the run as `source-only`, `existing-live`, or `approved-fresh-rollout` and record that mode in evidence. Confirm dynamic inventory provides direct service groups/hosts for every enabled service. In `existing-live` or `approved-fresh-rollout` mode, verify the reusable direct-access handoff can establish/verify host-key trust, direct SSH, Python, and root/become posture for roles that will use direct Ansible. In `source-only` mode, do not run live probes; instead run public fixture/static helper checks and record why live probes are out of scope. Do not use Proxmox fallback as success; Proxmox is allowed only inside the explicit handoff for readiness/minimal bootstrap.
- Files: Read-only expected; potential tracked fixes in `infra/ansible/inventory/tfvars.py` or tests only if direct host mapping is missing.
- Acceptance Criteria:
  1. [ ] Execution mode is explicit and inventory exposes direct groups for all enabled service roles in scope.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py execution-mode --settings settings.example.json --redacted && scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; python scripts/check-direct-service-ansible.py inventory --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --redacted'`
     - Pass: Evidence states `source-only`, `existing-live`, or `approved-fresh-rollout`; sanitized output lists enabled services, mapped inventory groups, and checked/skipped status; disabled services are explicit skips; no hostnames/IPs/domains are printed. If private values/resources are absent, public fixture inventory proves source-only mapping instead.
     - Fail: Fix dynamic inventory or document an explicit blocker; do not replace direct groups with `pve`.
  2. [ ] In `existing-live` or `approved-fresh-rollout` mode, direct SSH host-key trust is current and persisted for every enabled direct-service group.
     - Verify: `INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; export ANSIBLE_SSH_COMMON_ARGS="-o UserKnownHostsFile=/workspace/values/ansible/known_hosts -o StrictHostKeyChecking=yes -o ForwardAgent=no"; python scripts/check-direct-service-ansible.py known-hosts --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted' && INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; export ANSIBLE_SSH_COMMON_ARGS="-o UserKnownHostsFile=/workspace/values/ansible/known_hosts -o StrictHostKeyChecking=yes -o ForwardAgent=no"; python scripts/check-direct-service-ansible.py known-hosts --check --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted'`
     - Pass: Enabled groups report `absent-added` only for new keys, `unchanged-verified` on the second container run, and never replace an existing key silently; disabled groups are skipped; no raw keys/endpoints are printed.
     - Fail: Changed/conflicting keys must report `changed-conflict-blocked`; investigate as a safety event and require explicit user approval before replacement.
  3. [ ] In `existing-live` or `approved-fresh-rollout` mode, direct SSH and Python work for every enabled direct-service group with normal host-key checking enabled.
     - Verify: `INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; export ANSIBLE_SSH_COMMON_ARGS="-o UserKnownHostsFile=/workspace/values/ansible/known_hosts -o StrictHostKeyChecking=yes -o ForwardAgent=no"; python scripts/check-direct-service-ansible.py connectivity --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted'`
     - Pass: Enabled groups return sanitized success; disabled groups are skipped; absent enabled groups fail.
     - Fail: Resolve SSH/user/firewall/inventory/host-key issue or mark plan blocked on private direct access.
  4. [ ] In `existing-live` or `approved-fresh-rollout` mode, direct root/become posture is explicit and works for every enabled service play.
     - Verify: `INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; export ANSIBLE_SSH_COMMON_ARGS="-o UserKnownHostsFile=/workspace/values/ansible/known_hosts -o StrictHostKeyChecking=yes -o ForwardAgent=no"; python scripts/check-direct-service-ansible.py become-probe --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted'`
     - Pass: Enabled groups either connect as root by design with compensating controls (`ForwardAgent=no`, managed known_hosts, scoped key) or can become root through the configured user; the helper reports only sanitized posture/status, not usernames/endpoints.
     - Fail: Block before Wave 3 unless the user explicitly approves a bootstrap/recovery path.
  5. [ ] In `source-only` mode, live probes are explicitly skipped and replaced by public/static evidence.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py bootstrap-plan --settings settings.example.json --redacted && scripts/python.sh scripts/check-direct-service-ansible.py structure --settings settings.example.json --check handoff --redacted`
     - Pass: Evidence records that live resources are absent or deployment is out of scope, public fixture/static checks pass, and no live direct probe is required for archive.
     - Fail: Do not proceed until either live mode is selected and probes run, or source-only substitute evidence passes.

### Wave 2 -- Validation Gate

**V2: Validate wave 2** [medium] -- validation-lead
- Blocked by: T1
- Checks:
  1. Run all T1 acceptance criteria for the selected execution mode.
  2. In `existing-live` or `approved-fresh-rollout` mode, confirm no plan-blocking enabled service lacks direct SSH/Python/become. If one does, record the sanitized blocker and stop before Wave 3 unless the user explicitly approves bootstrap/recovery work.
  3. In `source-only` mode, confirm live probes were not attempted, the skip reason is recorded, and public/static substitute evidence passed.
- On failure: create a fix task, re-validate after fix.

### Wave 3

**T3: Convert service playbooks to lifecycle-plus-direct-service structure and shared handoff usage** [large] -- ansible-specialist
- Blocked by: V2
- Description: For each service playbook, include the reusable direct-access handoff as explicit preliminary plays before the direct service role, then run the service role on the direct service group with `become: true`. The handoff may call Proxmox `lxc_ready` or approved minimal bootstrap where needed in a `pve` play, must manage known_hosts on `localhost`/controller before any direct-host play connects, and must run direct probes in a service-host play with `gather_facts: false` until Python is verified. Steady-state service roles must run directly. Caddy proxy targets `technitium`, not `caddy_proxy`. Preserve `storage-prep.yml` on `pve` and `technitium-dns.yml` on `localhost`. Update `site.yml` orchestration to include the direct playbooks without routing service configuration through `pve`. Avoid duplicated handoff boilerplate by using the same role/include shape for each LXC service.
- Files: `infra/ansible/playbooks/{technitium,caddy-proxy,forgejo,forgejo-runner,infisical,hermes,tailscale-client,onramp-host,site}.yml`.
- Acceptance Criteria:
  1. [ ] Service playbooks structurally separate pve lifecycle/bootstrap from direct service roles.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py playbooks --settings settings.example.json --redacted`
     - Pass: YAML-aware output confirms pve plays contain only the reusable direct-access handoff or other allowlisted lifecycle/bootstrap/pve-boundary roles/tasks and service roles run in direct plays. `caddy-proxy.yml` uses direct group `technitium`.
     - Fail: A pve play still runs a steady-state service role or caddy proxy targets a nonexistent group.
  2. [ ] Syntax checks pass for settings-derived service playbooks in the selected execution mode.
     - Verify existing-live/approved-fresh-rollout: `scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; python scripts/check-direct-service-ansible.py syntax --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --redacted'`
     - Verify source-only: `scripts/python.sh scripts/check-direct-service-ansible.py syntax --settings settings.example.json --fixture-public --redacted`
     - Pass: Enabled service playbooks syntax-check successfully in live modes; source-only mode checks public fixture/example playbook resolution without requiring private hosts; disabled service playbooks are skipped or checked only in public-all mode without requiring private hosts.
     - Fail: Fix inventory, variables, or YAML structure.

**T4: Convert Technitium/Caddy/Hermes/Infisical direct role execution and extract safe shared Caddy/file primitives** [large] -- engineering-lead
- Blocked by: V2
- Description: Convert Technitium, Caddy proxy, Hermes, and Infisical roles from Proxmox-mediated commands/file pushes to direct Ansible modules and direct commands. Use `apt`, `template`, `copy`, `file`, and `systemd` where practical. Use `command`/`shell` only when an idempotent module is not practical, with explicit `changed_when`/`failed_when` and check-mode behavior. Secret-bearing files must be templated/copied directly to final paths with `owner`, `group`, `mode`, and `no_log: true`; non-secret managed files/directories must also set explicit owner/group/mode. Do not stage secrets in `/tmp` on the controller or service host. Preserve handler semantics: changed templates notify exactly the intended handler, unit changes run daemon reload before restart, and Caddy config is validated before reload/restart. Extract safe shared primitives when they are behaviorally identical, especially direct template/copy-with-mode/no_log patterns and repeated Caddy validation/restart setup. Do not abstract app-specific env schemas or unique service configs.
- Files: `infra/ansible/roles/{technitium,caddy_proxy,hermes,infisical}/**`.
- Acceptance Criteria:
  1. [ ] These roles contain no forbidden steady-state `pct` commands.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py policy --roles technitium caddy_proxy hermes infisical --redacted`
     - Pass: YAML-aware check finds no forbidden `pct` argv/list/string forms outside allowlisted bootstrap/recovery boundaries.
     - Fail: Convert remaining task or move it to an explicit lifecycle/bootstrap role with justification.
  2. [ ] Managed files are copied directly to final paths with explicit permissions and no logging where secret-bearing.
     - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety`
     - Pass: Tests cover Hermes/Caddy/Infisical secret env files and any Technitium secret-bearing files for `no_log`, final destination, owner/group/mode, and no secret `/tmp` staging; tests also require explicit owner/group/mode for non-secret direct-managed systemd units, Caddyfiles, app configs, SSH snippets, runner configs, and service directories.
     - Fail: Restore secure and explicit file handling.
  3. [ ] Safe repeated Caddy/file patterns are centralized or explicitly left local with justification.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py structure --roles caddy_proxy hermes infisical forgejo --check shared-primitives --redacted`
     - Pass: Output objectively identifies shared Caddy/template/file primitives in use, or lists service-specific exceptions with a reason. It must not require abstraction of app-specific secret schemas.
     - Fail: Extract the low-risk repeated primitive or document why it is intentionally service-local.
  4. [ ] Handler/idempotence behavior is preserved for direct module conversion.
     - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety`
     - Pass: Tests assert template/copy changes notify only the intended handlers, systemd unit/override changes trigger daemon reload before restart, Caddy config validates before reload/restart, and command tasks have explicit idempotence guards.
     - Fail: Restore handler/idempotence safeguards before check-mode validation.
  5. [ ] Direct check-mode/dry-run is attempted or explicitly exempted for unsupported tasks in the selected execution mode.
     - Verify existing-live/approved-fresh-rollout: `scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; python scripts/check-direct-service-ansible.py check-mode --groups technitium infisical hermes --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --redacted'`
     - Verify source-only: `scripts/python.sh scripts/check-direct-service-ansible.py check-mode --groups technitium infisical hermes --settings settings.example.json --fixture-public --redacted`
     - Pass: Sanitized summary shows check-mode pass or a bounded exception list with task path, reason, idempotence guard (`creates`/probe/`changed_when`), secret logging posture, handler notification behavior, and compensating evidence. Source-only mode must not require private inventory or live SSH.
     - Fail: Fix check-mode failures or document why a task cannot safely support check mode.

**T5: Convert Forgejo and Forgejo Runner with explicit pve-boundary split** [large] -- ansible-specialist
- Blocked by: V2
- Description: Convert Forgejo service configuration and Forgejo Runner in-runner configuration to direct Ansible operations. Split any Proxmox-host SSH trust/authorization, storage-adjacent, or other host-boundary task into an explicit pve-boundary play/role that is allowed by policy tests and documented as not in-guest steady-state configuration.
- Files: `infra/ansible/roles/forgejo/**`, `infra/ansible/roles/forgejo_runner/**`, possible new pve-boundary role/playbook fragments, related playbooks/tests.
- Acceptance Criteria:
  1. [ ] Forgejo service and in-runner tasks contain no forbidden steady-state `pct` commands.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py policy --roles forgejo forgejo_runner --redacted`
     - Pass: YAML-aware check finds no forbidden steady-state `pct` argv/list/string forms.
     - Fail: Convert remaining task or explicitly split it into an allowlisted pve-boundary task.
  2. [ ] Proxmox-host-boundary tasks are isolated and documented.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py pve-boundary --settings settings.example.json --redacted`
     - Pass: Output lists only approved pve-boundary tasks/roles, including any Forgejo Runner SSH trust/authorization task that must remain on Proxmox.
     - Fail: Boundary task is hidden in service role or lacks explicit allowlist/docs.
  3. [ ] Forgejo Runner registration remains idempotent and secret-protected.
     - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety`
     - Pass: Tests cover runner registration, UUID resolution, config file protection, no-log semantics, explicit file ownership/mode, command idempotence guards, and handler notification behavior without relying on Proxmox-specific task names.
     - Fail: Fix role or tests without exposing secrets.

**T6: Review/convert Tailscale and preserve already-direct Onramp behavior** [medium] -- ansible-specialist
- Blocked by: V2
- Description: Convert Tailscale client service configuration to direct service targeting if enabled/supported. Keep Onramp host direct behavior as a reference and ensure new guardrails do not regress it. Do not change Onramp infrastructure/resource shape.
- Files: `infra/ansible/roles/tailscale_client/**`, `infra/ansible/playbooks/tailscale-client.yml`, `infra/ansible/playbooks/onramp-host.yml`, related tests.
- Acceptance Criteria:
  1. [ ] Tailscale service configuration runs against the direct `tailscale_client` group when enabled.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py playbooks --settings settings.example.json --include-disabled --redacted`
     - Pass: Tailscale playbook has a direct service play or is explicitly marked unsupported/disabled without pve steady-state service role execution.
     - Fail: Add direct service play or document disabled/unsupported handling.
  2. [ ] Onramp host remains direct and does not gain Proxmox-mediated service configuration.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py policy --roles onramp_host --redacted`
     - Pass: Onramp host remains direct with no forbidden pve service config.
     - Fail: Revert unintended Onramp changes.

### Wave 3 -- Validation Gate

**V3: Validate wave 3** [large] -- validation-lead
- Blocked by: T3, T4, T5, T6
- Checks:
  1. Run all T3-T6 acceptance criteria.
  2. `scripts/python.sh -m unittest tests.test_ansible_safety tests.test_tfvars_inventory tests.test_settings tests.test_service_registry_parity` -- exits 0.
  3. In live modes, `scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; python scripts/check-direct-service-ansible.py syntax --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --redacted; python scripts/check-direct-service-ansible.py check-mode --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --redacted'` exits 0 or reports only bounded documented check-mode exceptions with compensating evidence. In `source-only` mode, run `scripts/python.sh scripts/check-direct-service-ansible.py syntax --settings settings.example.json --fixture-public --redacted && scripts/python.sh scripts/check-direct-service-ansible.py check-mode --settings settings.example.json --fixture-public --redacted`.
  4. In `existing-live` or `approved-fresh-rollout` mode, direct connectivity and become probes from T1 still pass. In `source-only` mode, confirm the source-only substitute evidence remains current.
  5. Cross-task integration: no direct role relies on files staged under `/tmp` on Proxmox, and pve-boundary tasks are explicit/allowlisted.
- On failure: create a fix task, re-validate after fix.

### Wave 4

**T7: Update site orchestration, docs, and migration notes for the new access pattern** [medium] -- docs-specialist
- Blocked by: V3
- Description: Update docs and repo instructions so operators and agents understand that direct service access is normal, Proxmox is lifecycle/bootstrap/storage/recovery, and `just apply` still orchestrates approved service configuration. Keep examples generic.
- Files: `AGENTS.md`, `README.md`, `docs/README.md`, service runbooks as needed, `scripts/settings.py` only if playbook listing logic needs updates.
- Acceptance Criteria:
  1. [ ] Docs contain generic direct-service guidance and no real local endpoints.
     - Verify: `rg -n "direct service access|ssh <user>@|Proxmox.*recovery|bootstrap" AGENTS.md README.md docs -g '*.md' && scripts/public-safety-check.sh`
     - Pass: Guidance is present; public safety passes.
     - Fail: Sanitize examples or add missing guidance.
  2. [ ] `settings.py` service playbook listing still reflects the correct playbooks.
     - Verify: `scripts/python.sh scripts/settings.py ansible-playbooks --settings settings.example.json`
     - Pass: Lists public-safe playbook paths without errors.
     - Fail: Fix service registry/listing logic.

**T8: Add final regression coverage, DRY-boundary checks, and sanitized evidence enforcement** [medium] -- qa-engineer
- Blocked by: V3
- Description: Strengthen tests so future service roles cannot reintroduce Proxmox-mediated steady-state configuration, stale Proxmox-specific assertions, raw private evidence persistence, a fake `caddy_proxy` group, or copy-pasted direct-access boilerplate that bypasses the reusable handoff. The allowlist must keep `lxc_ready`, storage prep, explicit bootstrap/recovery, and Proxmox-host-boundary paths legal.
- Files: `tests/test_ansible_safety.py`, `tests/test_service_registry_parity.py`, `scripts/check-direct-service-ansible.py` tests as needed.
- Acceptance Criteria:
  1. [ ] Regression test covers all service roles in scope with YAML-aware forbidden-command detection.
     - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety`
     - Pass: Tests pass and include service roles in the assertion.
     - Fail: Add missing roles or fix test logic.
  2. [ ] Concrete structure tests verify the reusable handoff is used and unsafe over-abstraction is avoided.
     - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py structure --settings settings.example.json --check handoff --check shared-primitives --redacted`
     - Pass: Output confirms service playbooks use the shared direct-access handoff and objective low-risk primitives, while app-specific env/registration/DNS logic remains service-local or explicitly justified.
     - Fail: Replace copy-pasted handoff logic with the shared boundary or remove unsafe generic abstractions.
  3. [ ] Validation helper redacts private endpoints in evidence output using fixtures, not brittle literal greps.
     - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety && scripts/public-safety-check.sh`
     - Pass: Tests inject representative private RFC1918/link-local/IPv6 addresses, private domains, hostnames, usernames, SSH fingerprints where disallowed, token/password/key-shaped strings, and Ansible stderr into helper outputs; documented placeholders such as `example.internal` remain allowed.
     - Fail: Fix redaction/sanitization.

### Wave 4 -- Validation Gate

**V4: Validate wave 4** [large] -- validation-lead
- Blocked by: T7, T8
- Checks:
  1. Run all T7/T8 acceptance criteria.
  2. `just validate` -- exits 0.
  3. In `existing-live` or `approved-fresh-rollout` mode, direct connectivity and become probes pass for enabled service groups with redacted output. In `source-only` mode, source-only substitute evidence remains current and no command requires `values/terraform.tfvars`, `settings.local.json`, or private inventory.
  4. `git diff --check` -- exits 0.
  5. Cross-task integration: docs, tests, helper script, and role/playbook structure describe the same direct-service policy.
- On failure: create a fix task, re-validate after fix.

## Dependency Graph

```text
Wave 1: T2 → V1
Wave 2: T1 (after V1) → V2
Wave 3: T3 playbook/handoff skeleton after V2 → T4, T5, T6 role cohorts in parallel → V3 integration
Wave 4: T7, T8 (parallel after V3) → V4
Final Gates: V4 → F1 → F2 → F3 → F4 → F5
```

## Success Criteria

1. [ ] All enabled normal service playbooks use the reusable direct-access handoff followed by direct service configuration plays, with Proxmox limited to lifecycle/bootstrap/storage/pve-boundary plays, and the ordering supports fresh/new-user setups without duplicated handoff boilerplate.
   - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py playbooks --settings settings.example.json --include-disabled --redacted`
   - Pass: YAML-aware summary confirms direct service roles, Technitium-targeted caddy proxy, and allowlisted pve plays only.
2. [ ] Fresh/new-user bootstrap sequencing is explicit, reusable, and public-safe.
   - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py bootstrap-plan --settings settings.example.json --redacted`
   - Pass: Output shows new services can progress through the reusable handoff from LXC readiness/minimal bootstrap to host-key trust to direct Ansible probes without assuming pre-existing known_hosts entries.
3. [ ] No service role uses Proxmox `pct` for steady-state configuration, including argv-list forms.
   - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py policy --redacted`
   - Pass: No forbidden steady-state `pct` usage; any allowed pve-boundary/bootstrap tasks are listed explicitly.
4. [ ] Direct Ansible host-key trust, SSH/Python, and root/become posture work for enabled service groups without raw private evidence output in `existing-live` or `approved-fresh-rollout` mode.
   - Verify: `INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; export ANSIBLE_SSH_COMMON_ARGS="-o UserKnownHostsFile=/workspace/values/ansible/known_hosts -o StrictHostKeyChecking=yes -o ForwardAgent=no"; python scripts/check-direct-service-ansible.py known-hosts --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted; python scripts/check-direct-service-ansible.py connectivity --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted; python scripts/check-direct-service-ansible.py become-probe --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted'`
   - Pass: Enabled groups return sanitized success; disabled groups are explicit skips; absent enabled groups fail; changed host-key conflicts block rather than refresh silently.
5. [ ] Repeated migration-critical patterns are centralized where safe and app-specific logic remains explicit.
   - Verify: `scripts/python.sh scripts/check-direct-service-ansible.py structure --settings settings.example.json --check handoff --check shared-primitives --redacted`
   - Pass: Output confirms the shared direct-access handoff and safe shared primitives are used; app-specific exceptions are documented.
6. [ ] Helper evidence and redaction contracts are fixture-tested.
   - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety tests.test_service_registry_parity && scripts/public-safety-check.sh`
   - Pass: Public fixture tests cover non-live helper modes, exit codes, redaction, and allowed placeholders.
7. [ ] Repo-wide validation passes.
   - Verify: `just validate`
   - Pass: Exits 0.

## Validation Contract

`/do-it` must satisfy this contract before reporting the plan complete or archiving it.

### Automation completeness

- Required: yes
- `/do-it` must run all validation/deployment-independent checks through documented commands, scripts, playbooks, or wrappers.
- Credentials are expected through existing approved local mechanisms: private `values/`, SSH keys copied into the infra container via `INFRA_COPY_SSH_KEYS=true`, Docker Compose tooling, and a gitignored managed known_hosts file at `values/ansible/known_hosts` when live direct probes run.
- Execution modes must be explicit in evidence: `source-only` for public/static validation without live services, `existing-live` when private values/resources are present and probes can run, and `approved-fresh-rollout` only after explicit deployment approval. Source-only mode may archive the source refactor if all static/fixture/syntax/policy checks pass and live deployment is out of scope. Existing-live mode must run direct probes. Approved fresh rollout must run the direct-access handoff after LXC creation and before service roles.
- Manual-only steps are not required for source-level MVP completion. If direct service SSH/Python/become is missing for an enabled existing-live service, mark blocked with the failing sanitized command and either fix private access or ask for explicit approval for a Proxmox bootstrap/recovery path. Do not treat Proxmox fallback as success.

### Required automated validation

Execution-mode matrix for commands below:

| Mode | When used | Live/private commands required | Source-only substitute |
|------|-----------|--------------------------------|------------------------|
| `source-only` | No live services/private resources are available or deployment is out of scope | No | Use `settings.example.json`, committed fixture inventory, `--fixture-public`, static syntax/policy/structure checks, helper exit-code/redaction tests, and `just validate` |
| `existing-live` | Private values point at already-existing services | Yes | Not applicable; live known_hosts/connectivity/become/syntax/check-mode must pass |
| `approved-fresh-rollout` | User explicitly approved apply/deployment that creates/configures services | Yes, after creation/handoff | Not applicable; live direct-access handoff and probes must pass before service roles/archive |

1. [ ] Run repo-wide validation.
   - Command: `just validate`
   - Pass: exits 0 with no failed validation stages.
   - Fail: do not archive; update execution status with the failing command and next fix.

2. [ ] Run task-specific verification from every acceptance criterion above.
   - Command: see each task's `Verify:` command.
   - Pass: every acceptance criterion passes as written.
   - Fail: create/fix a task, rerun affected checks, then rerun repo-wide validation.

3. [ ] Run direct service known_hosts, connectivity, and root/become posture probes when in `existing-live` or `approved-fresh-rollout` mode; run source-only substitutes otherwise.
   - Live command: `INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; export ANSIBLE_SSH_COMMON_ARGS="-o UserKnownHostsFile=/workspace/values/ansible/known_hosts -o StrictHostKeyChecking=yes -o ForwardAgent=no"; python scripts/check-direct-service-ansible.py known-hosts --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted; python scripts/check-direct-service-ansible.py connectivity --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted; python scripts/check-direct-service-ansible.py become-probe --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --known-hosts-file values/ansible/known_hosts --redacted'`
   - Source-only command: `scripts/python.sh scripts/check-direct-service-ansible.py bootstrap-plan --settings settings.example.json --redacted && scripts/python.sh scripts/check-direct-service-ansible.py structure --settings settings.example.json --check handoff --fixture-public --redacted`
   - Pass: live modes return sanitized success; disabled services are explicitly skipped; changed host-key conflicts block; source-only mode records live probes skipped and fixture/static substitute evidence passed; no private endpoints are persisted.
   - Fail: block live/archive in existing-live mode unless the user explicitly narrows scope or approves bootstrap/recovery; do not fall back to Proxmox `pct` as a success path.

4. [ ] Run Ansible syntax and direct check-mode checks for settings-derived service playbooks in the selected execution mode.
   - Live command: `scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=values/terraform.tfvars INFRA_SETTINGS_FILE=settings.local.json; python scripts/check-direct-service-ansible.py syntax --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --redacted; python scripts/check-direct-service-ansible.py check-mode --inventory values/ansible/inventory/local.yml --inventory infra/ansible/inventory/tfvars.py --settings settings.local.json --redacted'`
   - Source-only command: `scripts/python.sh scripts/check-direct-service-ansible.py syntax --settings settings.example.json --fixture-public --redacted && scripts/python.sh scripts/check-direct-service-ansible.py check-mode --settings settings.example.json --fixture-public --redacted`
   - Pass: syntax checks exit 0; check mode passes or reports only bounded documented task exceptions with task path, reason, idempotence guard, secret logging posture, handler impact, and compensating evidence; source-only mode requires no private values.
   - Fail: fix playbook/role/inventory errors.

5. [ ] Run fresh-setup bootstrap sequencing and concrete structure checks.
   - Command: `scripts/python.sh scripts/check-direct-service-ansible.py bootstrap-plan --settings settings.example.json --redacted && scripts/python.sh scripts/check-direct-service-ansible.py structure --settings settings.example.json --check handoff --check shared-primitives --redacted`
   - Pass: public-safe output documents correct new-user sequencing and appropriate shared primitive usage without unsafe broad genericization.
   - Fail: update helper/playbook ordering or structure boundary before archive.

6. [ ] Run policy checks for no forbidden steady-state Proxmox usage.
   - Command: `scripts/python.sh scripts/check-direct-service-ansible.py policy --settings settings.example.json --redacted && scripts/python.sh scripts/check-direct-service-ansible.py pve-boundary --settings settings.example.json --redacted`
   - Pass: no forbidden `pct` argv/string forms; all pve-boundary tasks are explicit/allowlisted.
   - Fail: convert task or explicitly move it to lifecycle/bootstrap/pve-boundary with justification.

7. [ ] Run helper CLI contract and redaction fixture tests.
   - Command: `scripts/python.sh -m unittest tests.test_ansible_safety tests.test_service_registry_parity && scripts/public-safety-check.sh`
   - Pass: non-live helper modes run against committed fixtures; exit codes fail on parse/check/redaction errors; allowed placeholders are not rejected.
   - Fail: fix helper contract or sanitizer before archive.

### Manual validation

Manual validation is exceptional. It should be `Required: no` unless the plan includes destructive operations, data-loss risk, irreversible external side effects, shared/work production impact, paid/billing/data-costing resources, secret exposure risk, hardware/physical checks, or genuinely subjective user judgment that cannot be replaced by safe automation.

- Required: no
- Justification: Automated static checks, fixture-backed helper tests, syntax checks, check-mode/dry-run checks, unit tests, ansible-lint through `just validate`, and public safety checks are sufficient for source-only archive. Direct Ansible SSH/Python/become probes are required in existing-live or approved-fresh-rollout modes. Live apply, Proxmox bootstrap mutations, or replacing a changed trusted host key requires explicit approval but is not required for source-only archive.
- Steps:
  1. None.

If manual validation is not required, `/do-it` may mark the manual gate complete after recording why automated evidence is sufficient.

### Deployment validation

- Required: no for MVP archive.
- Procedure: None for archive. If the user explicitly approves live deployment, first write/update a serial rollout note listing each service, expected changed files/services, pre-change backups for env/Caddyfile/systemd/app config, health checks, and rollback commands. Then run `just plan`, summarize creates/updates/replaces/deletes, request approval, and only then run `just apply` or an approved narrower serial playbook run. After deployment, run direct connectivity/become probes and `just plan` to verify no drift.

If deployment is skipped, the plan may still archive because the MVP is a source-level Ansible access-pattern migration with direct connectivity and repo validation. If deployment is attempted and fails, `/do-it` must not archive until resolved or deployment is explicitly removed from active execution scope.

### Archive rule

`/do-it` may archive this plan only after all required automated validation, task-specific verification, syntax/check-mode checks, policy checks, helper CLI/redaction fixture tests, and repo-wide validation pass. In `existing-live` or `approved-fresh-rollout` mode, direct service host-key/connectivity/become verification must also pass. In `source-only` mode, record why live probes are skipped and which public/static evidence replaces them. Do not require manual validation merely to increase confidence in non-destructive behavior that automated checks already cover.

## Telemetry & Evidence Contract

Future `/do-it` runs should record non-secret evidence in terminal output and, if using durable artifacts, under `.specs/direct-service-ansible/evidence/`. Do not record secrets, private IPs/domains, SSH keys, tokens, unredacted private inventory, SSH banners, or raw Ansible inventory dumps.

The preferred evidence format is the redacted output from `scripts/check-direct-service-ansible.py`, containing only service names, group names, checked/skipped/fail status, and sanitized error classes. Do not persist raw `ansible-inventory --graph` output from private values.

Machine-readable evidence records should use JSON Lines with these fields:

```json
{"episode_id":"direct-service-ansible","phase_id":"wave-1","task_id":"T1","validation_command":"scripts/check-direct-service-ansible.py connectivity --redacted","status":"pending|pass|fail|blocked","archive_status":"not-ready|ready|archived","started_at":"ISO-8601","completed_at":"ISO-8601","evidence":"non-secret terminal summary or artifact path"}
```

Required fields:

- `episode_id`: `direct-service-ansible`
- `phase_id`: `wave-1`, `wave-2`, `wave-3`, `wave-4`, or `final-gates`
- `task_id`: one of `T2`, `V1`, `T1`, `V2`, `T3`, `T4`, `T5`, `T6`, `V3`, `T7`, `T8`, `V4`, `F1`, `F2`, `F3`, `F4`, `F5`
- `validation_command`: exact command or short label for non-command checks
- `status`: `pending`, `pass`, `fail`, or `blocked`
- `archive_status`: `not-ready`, `ready`, or `archived`
- `started_at`: ISO-8601 timestamp
- `completed_at`: ISO-8601 timestamp or `null` while in progress
- `evidence`: non-secret command summary or artifact path

### Plan review data contract

- `plan_profile`: `ansible-direct-service-access-migration`
- `review_panel_decision`: reviewed in `.specs/direct-service-ansible/review-1/synthesis.md`
- `expected_reviewer_count`: 7
- `selected_reviewer_personas`: `reviewer`, `security-reviewer`, `product-manager`, `devops-pro`, `qa-engineer`, `python-pro`, `terraform-pro`
- `selection_reasons`: Cross-service Ansible migration; live service access boundaries; secret/no-log protection; dynamic inventory/settings tooling; OpenTofu/Proxmox boundary preservation
- `complexity_score`: 8/10
- `risk_score`: 6/10
- `expected_high-risk areas`: preserving idempotence, not leaking secrets, keeping lifecycle Proxmox usage available, direct SSH/become assumptions, avoiding accidental live mutation, Caddy/service restart behavior if deployed later, pve-boundary tasks such as Forgejo Runner trust setup

## Handoff Notes

- This supersedes the Hermes-only plan at `.specs/direct-hermes-ansible/plan.md` for the broader doctrine rollout.
- Do not treat Proxmox `pct` fallback as a successful validation path for service configuration. A direct SSH/Python/become failure is a blocker or private values/access issue to fix, unless the user explicitly approves a bootstrap/recovery path.
- Keep `lxc_ready`, storage prep, and explicit pve-boundary tasks on `pve`; those are lifecycle/host-boundary operations, not normal service configuration.
- `caddy-proxy.yml` targets Technitium; do not invent a `caddy_proxy` inventory group unless a separate design adds it intentionally.
- `technitium-dns.yml` should remain localhost/API orchestration unless a separate design changes DNS management.
- `onramp_host` already follows the direct-service model; keep it as the reference pattern.
- Do not run `just apply` without explicit approval.

## Execution Status

- completion_classification: completed-and-archived
- archive_status: archived
- archive_path: `.specs/archive/direct-service-ansible/plan.md`
- date: 2026-07-07
- execution_mode: source-only
- last_completed_gate: F5 archive preflight
- next_gate: none
- implemented:
  - Added `scripts/check-direct-service-ansible.py` for source/static direct-service validation, redaction checks, policy checks, pve-boundary reporting, source-only syntax/check-mode checks, and direct-access evidence summaries.
  - Added `infra/ansible/playbooks/direct-access-ready.yml` as the stable reusable direct-access handoff wrapper.
  - Converted service playbooks to pve lifecycle readiness plus direct service plays for Technitium, Caddy proxy on Technitium, Forgejo, Forgejo Runner, Infisical, Hermes, and Tailscale client.
  - Converted steady-state service roles and handlers away from Proxmox `pct` usage; `pct` remains only in the allowlisted `lxc_ready` lifecycle boundary.
  - Updated tests for YAML-aware no-`pct` policy, direct-service helper behavior, service registry parity, secret/no-log checks, and direct final destination file management.
  - Updated README/docs direct-service guidance.
- validation_passed:
  - `scripts/python.sh -m unittest tests.test_ansible_safety tests.test_settings tests.test_service_registry_parity tests.test_direct_service_ansible` -> pass
  - `scripts/python.sh -m unittest discover -s tests -p 'test_*.py'` -> pass
  - `scripts/python.sh scripts/check-direct-service-ansible.py execution-mode --settings settings.example.json --redacted` -> pass, source-only
  - `scripts/python.sh scripts/check-direct-service-ansible.py inventory --settings settings.example.json --redacted` -> pass
  - `scripts/python.sh scripts/check-direct-service-ansible.py bootstrap-plan --settings settings.example.json --redacted` -> pass
  - `scripts/python.sh scripts/check-direct-service-ansible.py playbooks --settings settings.example.json --include-disabled --redacted` -> pass
  - `scripts/python.sh scripts/check-direct-service-ansible.py policy --settings settings.example.json --redacted` -> pass
  - `scripts/python.sh scripts/check-direct-service-ansible.py pve-boundary --settings settings.example.json --redacted` -> pass
  - `scripts/python.sh scripts/check-direct-service-ansible.py structure --settings settings.example.json --check handoff --check shared-primitives --redacted` -> pass
  - `scripts/python.sh scripts/check-direct-service-ansible.py known-hosts --settings settings.example.json --known-hosts-file .specs/direct-service-ansible/evidence/test-known-hosts --check --redacted` -> pass
  - `scripts/python.sh scripts/check-direct-service-ansible.py syntax --settings settings.example.json --fixture-public --redacted` -> pass
  - `scripts/python.sh scripts/check-direct-service-ansible.py check-mode --settings settings.example.json --fixture-public --redacted` -> pass
  - Ansible source syntax command using scaffold inventory/settings -> pass
  - `scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; ansible-lint infra/ansible'` -> pass
  - `scripts/public-safety-check.sh` -> pass
  - `git diff --check` -> pass
  - `just validate` -> pass
- manual_validation: not required; source-only mode uses static/fixture/syntax/policy/unit/repo validation and no live service mutation.
- deployment_validation: not required; no `just apply`, OpenTofu apply, or live service reconfiguration was run.
- remaining_user_steps: none for source-level completion. Live rollout remains explicitly deferred and requires separate approval.
- rerun_do_it: false

## Workflow Eval Record

- outcome: completed-and-archived
- archive_status: archived
- archive_path: `.specs/archive/direct-service-ansible/plan.md`
- validation_commands_results: all required source-only task-specific checks, syntax/check-mode checks, public safety, ansible-lint, full unit discovery, `git diff --check`, and `just validate` passed.
- manual_deployment_gate_decisions: manual validation not required; deployment not required for MVP archive; live apply remains deferred.
- checklist_completion_state: all executable checklist items and final gates marked completed.
- blocker_reason: none
- friction:
  - category: edit-scope-control; severity: low; evidence: broad YAML formatting touched unrelated lifecycle/storage files and was corrected with targeted `git restore`; impact: extra cleanup during execution; recommended_change: use narrower file sets or format only changed service role/playbook files; candidate_test: compare changed file set against plan file list before final validation.
- missing_evidence: none for source-only completion.
- improvement_candidates:
  - category: helper-live-depth; severity: low; evidence: source-only archive did not run live direct SSH probes by design; impact: live rollout still needs direct probe evidence before apply; recommended_change: run existing-live helper probes during a separately approved deployment session.
- eval_confidence: medium
- post_run_reviewers: deterministic self-check only; no blocking friction triggers after repair and successful archive preflight.
- execution_outcome: completed
- panel_quality_label: right-sized
- panel_quality_reason: review identified source-only/live-mode separation and reusable handoff requirements that were implemented.
- panel_quality_confidence: medium
