---
created: 2026-07-06
status: completed
completed: 2026-07-07
---

# Plan: Onramp Host Pilot Contract

## Context & Motivation

The operator wants to use Hermes as a cockpit for managing this homelab infrastructure while keeping `homelab-infra` and `onramp-vNext` as separate repositories with a united product model. The selected architecture from the discussion is option 3: `homelab-infra` remains the durable infrastructure substrate, `onramp-vNext` becomes the Docker application platform, and Hermes operates across both through their native workflows.

This was triggered by the next Hermes plugin need: a `web-searxng` plugin likely needs a SearXNG service reachable from Hermes. The conversation rejected making every plugin backend a first-class infrastructure service by default. Web research also found that running Docker Compose files with Podman is possible, including through `podman compose` providers and Debian 13 `podman-compose`, but Podman inside Proxmox LXC requires nested-container trade-offs. The recommended default for the Onramp app substrate is a Debian 13 VM running Podman, with Podman-in-LXC treated as an experimental lightweight option.

A PRD draft already exists at `docs/hermes-operator-pilot-prd.md`. This plan turns the discussion into a durable, public-safe contract and implementation handoff without provisioning live infrastructure yet.

## Constraints

- Platform: Windows Git Bash/MSYS2 detected as `MINGW64_NT-10.0-26200`.
- Shell: `/usr/bin/bash`.
- Repository markers detected: `justfile`, `.gitattributes`, `AGENTS.md`, `README.md`, `settings.example.json`.
- This repository must remain public-safe. Use placeholders such as `example.internal` and RFC 5737 addresses; do not write real domains, IPs, hostnames, tokens, credentials, state, or plans to tracked files.
- Private site values and OpenTofu state remain in ignored `values/`; this plan must not edit `values/`, `settings.local.json`, state files, or generated secrets.
- Normal workflow remains `just setup`, `just validate`, `just plan`, `just apply`; do not invoke private just recipes directly.
- No live mutation is in scope for this MVP. Do not run `just plan`, `just apply`, OpenTofu plan/apply/import/state commands, state surgery, router/firewall changes, or direct service mutation unless the user makes a separate explicit request outside this plan.
- `homelab-infra` owns durable infrastructure resources and first-class services. Onramp owns general Docker app services. Hermes is the operator cockpit, not a separate source of truth.
- Service-local Caddy remains the default for first-class infrastructure services. Do not turn Technitium into a general ingress proxy.
- Onramp/Caddy convention: a service `port` field means the container/service port reachable on the Compose network; do not reinterpret it as a host-published port unless explicitly requested.
- Current uncommitted state at plan creation: untracked `docs/hermes-operator-pilot-prd.md` and this `.specs/` plan. No tracked file modifications were present when this plan was written.

## Risk & Manual Gate Decision

Manual gates are exceptional. Decide based on blast radius and rollback, not generic confidence. Be conservative for work/shared systems and data/resources that cost money; treat personal/local GitHub repos as localized-to-user when changes are reversible and validated.

- **Risk level:** low
- **Blast radius:** personal-local-repo documentation only
- **Rollback:** easy by reviewing/reverting uncommitted Git diffs; executor must not discard user work without explicit approval
- **Manual approval before action:** not required for this MVP because it only edits public documentation and plan artifacts
- **Manual validation after action:** not required
- **Decision reason:** The MVP does not provision infrastructure, mutate `values/`, run deploy/apply commands, call external APIs, or change paid/shared resources. Automated public-safety, diff, and repo validation are sufficient.

## Alternatives Considered

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Put SearXNG directly on the Hermes LXC | Fastest and keeps the plugin backend local to Hermes | Makes Hermes a mini onramp host and sets a precedent for piling plugin dependencies into the management LXC | Rejected for default: acceptable only when a dependency is truly Hermes-only |
| Add SearXNG as a first-class `homelab-infra` LXC | Matches existing first-class service pattern with OpenTofu, Ansible, Caddy, and DNS | Encourages service sprawl and makes every small plugin backend an infra resource | Rejected for default: use only for durable platform services |
| Use the existing Onramp deployment immediately | Fastest way to test a reachable SearXNG endpoint | Risks encoding legacy Onramp assumptions instead of vNext contracts | Deferred: useful as a temporary smoke target, not the target architecture |
| Provision an Onramp onramp host with `homelab-infra`, then let `onramp-vNext` deploy SearXNG | Clean infra/app boundary, dogfoods vNext, keeps plugin services out of infra | Requires explicit DNS, Caddy, secrets, and state contracts before runtime work | **Selected** |
| Run Podman and Compose inside an unprivileged Proxmox LXC | Lower overhead and fits current LXC-heavy repo patterns | Requires nesting/fuse/keyctl style configuration, weaker isolation, more host-kernel coupling, and app-specific compatibility testing | Rejected for default; keep as an experimental alternative |
| Use an Arch or CachyOS VM for the onramp host | Newer Podman and faster access to runtime changes | Rolling-release churn is a poor default for a durable onramp host; CachyOS performance tuning is less relevant to server stability | Rejected for default; use only if a specific Podman/kernel feature requires it |

Trend-bias check: this plan converges on a platform split and service-catalog direction. The opposite approach is correct when a service is core infrastructure with strict lifecycle needs, static DNS, secrets bootstrap, or disaster recovery requirements. In that scenario, it should remain a first-class `homelab-infra` service rather than an Onramp app.

## Objective

Produce a durable, public-safe documentation contract that defines how option 3 works: `homelab-infra` provisions and owns the onramp-host substrate, `onramp-vNext` owns Docker app services such as SearXNG, and Hermes operates across both without bypassing approved workflows.

## MVP Boundary

The smallest user-visible outcome is a reviewed documentation and handoff package in this repository that answers where `homelab-infra` ends, where `onramp-vNext` begins, why Debian 13 VM plus Podman is the default onramp-host direction, and how the first SearXNG pilot should be classified.

This is sufficient for the current plan because runtime implementation spans infrastructure, Onramp, and Hermes. Codifying the contract first prevents premature service sprawl and makes the later provisioning plan smaller and safer. The MVP can be implemented and validated in one focused session.

## Explicit Deferrals

- Provisioning a Debian 13 VM in OpenTofu.
- Adding private tfvars, DNS records, or inventory values for an onramp host.
- Running `just plan`, `just apply`, OpenTofu plan/apply/import/state commands, or any live infrastructure mutation.
- Implementing Onramp SearXNG catalog entries or deploying SearXNG.
- Wiring the Hermes `web-searxng` plugin to a live SearXNG endpoint.
- Migrating or modifying the existing Onramp deployment.
- Runtime telemetry implementation for Hermes, Onramp, or Pi workflows.
- Arch/CachyOS VM experiments and Podman-in-LXC compatibility tests.

Deferred work is not required for archive.

## Project Context

- **Language**: Infrastructure runbook with OpenTofu, Ansible, shell, and Python helpers. No `pyproject.toml`, `package.json`, `go.mod`, or `Cargo.toml` marker was detected in this checkout.
- **Test command**: `just validate` is the repo-wide validation command. Task-specific checks include `python scripts/public-safety-check.py` and `git diff --check`.
- **Lint command**: `just validate` is the repo entry point for linting and validation; it includes public-safety, OpenTofu, ShellCheck, Python, DNS JSON, Ansible syntax, and ansible-lint checks per repo docs.
- **Command dependency**: acceptance checks use `rg`/ripgrep. If `rg` is unavailable in the agent shell, install/use the repo tooling environment or convert the exact checks to equivalent `grep -E` commands before marking criteria complete.

## Automation Plan

List every operational step required to complete this plan and how it is automated. Prefer scripts, playbooks, wrappers, and repeatable commands over manual steps. Any manual-only step must include why it cannot be safely automated.

| Operation | Command/wrapper | Credentials | Evidence |
|-----------|-----------------|-------------|----------|
| Preflight | `git status --short --branch && test -f .specs/onramp-host-pilot/plan.md` | none | terminal output showing current branch and plan path |
| Values preflight for repo-wide validation | `scripts/values.sh check` | approved local `values/` mechanism | exit 0 means `just validate` can run; nonzero means block and run `just setup` only if appropriate |
| Initialize evidence | `mkdir -p .specs/onramp-host-pilot/evidence && test -f .specs/onramp-host-pilot/evidence/validation.jsonl || : > .specs/onramp-host-pilot/evidence/validation.jsonl` | none | evidence file exists; existing evidence is not truncated |
| Optional Onramp context availability | `test -d C:/Projects/Personal/onramp-vNext/docs/prd && echo optional-onramp-context-present || echo optional-onramp-context-absent-using-embedded-plan-context` | none | sanitized availability signal only; do not archive raw filenames or file content |
| Update docs | Create or edit `docs/hermes-operator-pilot-prd.md`, create `docs/onramp-app-platform-contract.md`, and update `README.md` plus `docs/README.md` | none | Git diff of public-safe documentation |
| Planned-file public-safety scan | `mkdir -p .specs/onramp-host-pilot/evidence && printf '%s\n' README.md docs/README.md docs/hermes-operator-pilot-prd.md docs/onramp-app-platform-contract.md .specs/onramp-host-pilot/plan.md .specs/onramp-host-pilot/evidence/validation.jsonl > .specs/onramp-host-pilot/evidence/public-safety-files.txt && python scripts/public-safety-check.py --tracked-files .specs/onramp-host-pilot/evidence/public-safety-files.txt` | none | exit code 0; covers planned untracked files as well as tracked files |
| Task-specific validation | `git diff --check -- README.md docs .specs/onramp-host-pilot/plan.md` plus every task acceptance command | none | exit code 0 and sanitized summary |
| Repo-wide validation | `just validate` after `scripts/values.sh check` passes | local ignored `values/` repo only; no credentials required for docs edits; do not save raw output | exit code 0 and sanitized summary only |
| Deployment | not applicable | none | deployment validation gate marked not required |
| Rollback | Review diff and, only with explicit user approval, revert unwanted documentation edits through normal Git tools; delete or redact `.specs/onramp-host-pilot/evidence/` if it contains rejected or sensitive data | none | clean or expected `git status --short` |
| Archive preflight | `scripts/values.sh check && python scripts/public-safety-check.py && python scripts/public-safety-check.py --tracked-files .specs/onramp-host-pilot/evidence/public-safety-files.txt && git diff --check` | local ignored `values/` repo only for values check | exit code 0 and list of remaining intentional files |

## Execution Checklist

This checklist is the durable resume ledger for `/do-it`. Every executable task, validation gate, and final completion gate has exactly one matching checkbox. Checked means verified complete; unchecked means pending, in-progress, blocked, or invalidated.

`/do-it` must mark each item `[x]` immediately after that item passes its required verification and before starting any dependent or next sequential step. `/review-it` must preserve checked state, add unchecked items for new executable work, and never mark implementation or validation work complete.

### Wave 0

- [x] T0: Run preflight and initialize sanitized evidence
  - Status: completed
  - Evidence: 2026-07-07: plan/evidence present; values-preflight=ok
- [x] V0: Validate preflight and evidence setup
  - Status: completed
  - Evidence: 2026-07-07: T0 acceptance rerun passed; evidence file retained

### Wave 1

- [x] T1: Create or update Hermes operator PRD with option 3 decisions
  - Status: completed
  - Evidence: 2026-07-07: PRD acceptance checks passed
- [x] T2: Add Onramp app-platform contract document
  - Status: completed
  - Evidence: 2026-07-07: contract acceptance checks passed
- [x] V1: Validate wave 1 documentation package
  - Status: completed
  - Evidence: 2026-07-07: T1/T2 acceptance, public-safety, whitespace, and integration checks passed

### Wave 2

- [x] T3: Add README and docs navigation for the contract
  - Status: completed
  - Evidence: 2026-07-07: README/docs navigation acceptance checks passed
- [x] V2: Validate wave 2 documentation navigation
  - Status: completed
  - Evidence: 2026-07-07: navigation public-safety and whitespace checks passed

### Final Gates

- [x] F1: Task-specific verification complete
  - Status: completed
  - Evidence: 2026-07-07: all task-specific acceptance criteria passed
- [x] F2: Repo-wide validation complete
  - Status: completed
  - Evidence: 2026-07-07: `scripts/values.sh check && just validate` exited 0 after repair loop
- [x] F3: Manual validation complete or not required
  - Status: completed
  - Evidence: 2026-07-07: not required for docs-only public-safe MVP
- [x] F4: Deployment validation complete or not required
  - Status: completed
  - Evidence: 2026-07-07: not required; no live provisioning or deployment in scope
- [x] F5: Archive preflight complete
  - Status: completed
  - Evidence: 2026-07-07: archive preflight public-safety and whitespace checks passed

## Task Breakdown

| # | Task | Files | Type | Model | Agent | Depends On |
|---|------|-------|------|-------|-------|------------|
| T0 | Run preflight and initialize sanitized evidence | 1: `.specs/onramp-host-pilot/evidence/validation.jsonl` | mechanical | small | coding-light | -- |
| V0 | Validate preflight and evidence setup | -- | validation | small | qa-engineer | T0 |
| T1 | Create or update Hermes operator PRD with option 3 decisions | 1: `docs/hermes-operator-pilot-prd.md` | feature | medium | planner | V0 |
| T2 | Add Onramp app-platform contract document | 1: `docs/onramp-app-platform-contract.md` | feature | medium | planner | V0 |
| V1 | Validate wave 1 documentation package | -- | validation | medium | qa-engineer | T1, T2 |
| T3 | Add README and docs navigation for the contract | 2: `README.md`, `docs/README.md` | mechanical | small | coding-light | V1 |
| V2 | Validate wave 2 documentation navigation | -- | validation | small | qa-engineer | T3 |
| F1 | Task-specific verification complete | -- | final-gate | small | qa-engineer | V2 |
| F2 | Repo-wide validation complete | -- | final-gate | medium | qa-engineer | F1 |
| F3 | Manual validation complete or not required | -- | final-gate | small | qa-engineer | F2 |
| F4 | Deployment validation complete or not required | -- | final-gate | small | qa-engineer | F3 |
| F5 | Archive preflight complete | -- | final-gate | small | qa-engineer | F4 |

## Execution Waves

### Wave 0

**T0: Run preflight and initialize sanitized evidence** [small] -- coding-light
- Description: Confirm the plan path and repository status, create the evidence directory, initialize `validation.jsonl` only if it does not already exist, and record whether private values are available for later repo-wide validation. Missing private values do not block documentation edits, but they do block F2 and archive until resolved.
- Files: `.specs/onramp-host-pilot/evidence/validation.jsonl`
- Acceptance Criteria:
  1. [ ] Preflight runs without truncating existing evidence.
     - Verify: `mkdir -p .specs/onramp-host-pilot/evidence && test -f .specs/onramp-host-pilot/evidence/validation.jsonl || : > .specs/onramp-host-pilot/evidence/validation.jsonl; test -f .specs/onramp-host-pilot/plan.md && test -f .specs/onramp-host-pilot/evidence/validation.jsonl && git status --short --branch`
     - Pass: command exits 0 and evidence file exists
     - Fail: missing plan path, missing evidence file, or git status failure; fix path/state before continuing
  2. [ ] Values availability is recorded for later F2 validation.
     - Verify: `scripts/values.sh check >/dev/null 2>&1 && echo values-preflight=ok || echo values-preflight=blocked`
     - Pass: command prints one of the two allowed sanitized statuses; if blocked, continue docs tasks but mark F2 blocked until values are repaired
     - Fail: command prints anything else or exposes private values; stop and fix evidence handling

### Wave 0 -- Validation Gate

**V0: Validate preflight and evidence setup** [small] -- qa-engineer
- Blocked by: T0
- Checks:
  1. Run all T0 acceptance criteria.
  2. Confirm `.specs/onramp-host-pilot/evidence/validation.jsonl` was not truncated if it already contained records.
- On failure: fix preflight/evidence setup and rerun V0 before starting Wave 1.

### Wave 1 (parallel after V0)

**T1: Create or update Hermes operator PRD with option 3 decisions** [medium] -- planner
- Blocked by: V0
- Description: Create `docs/hermes-operator-pilot-prd.md` if it is absent, or update it if present. The PRD must record the selected option 3 architecture, the `homelab-infra` versus `onramp-vNext` boundary, the SearXNG pilot classification, and the Podman host recommendation from this plan. Keep it public-safe and avoid real site identifiers.
- Files: `docs/hermes-operator-pilot-prd.md`
- Acceptance Criteria:
  1. [ ] PRD states the selected architecture and ownership split using explicit required statements.
     - Verify: `for pattern in "option 3" "homelab-infra remains the durable infrastructure substrate" "onramp-vNext owns Docker app services" "Hermes operates across both" "SearXNG" "Debian 13 VM running Podman" "Podman-in-LXC is experimental"; do rg -qi "$pattern" docs/hermes-operator-pilot-prd.md || { echo "missing: $pattern"; exit 1; }; done`
     - Pass: every required pattern is found and no private values appear
     - Fail: command prints a missing pattern or public-safety validation fails; revise the PRD and rerun
  2. [ ] PRD clearly marks live provisioning and deployment as deferred.
     - Verify: `for pattern in "No live mutation is in scope" "Provisioning a Debian 13 VM" "Deploying SearXNG" "Wiring the Hermes web-searxng plugin"; do rg -qi "$pattern" docs/hermes-operator-pilot-prd.md || { echo "missing: $pattern"; exit 1; }; done`
     - Pass: every deferred live-mutation topic is present
     - Fail: command prints a missing pattern; update requirements, non-goals, or deferrals and rerun

**T2: Add Onramp app-platform contract document** [medium] -- planner
- Blocked by: V0
- Description: Create a focused boundary contract, distinct from the PRD, that explains operational ownership. The contract must define ownership, DNS wildcard direction, Caddy ownership, secrets ownership, state ownership, approval boundaries, onramp-host runtime choice, how to classify future Hermes plugin backends, and the future provisioning gate. It must be useful to both this repo and `onramp-vNext`, but must only mutate this repository in this MVP.
- Files: `docs/onramp-app-platform-contract.md`
- Acceptance Criteria:
  1. [ ] Contract document exists with required sections.
     - Verify: `test -f docs/onramp-app-platform-contract.md && for pattern in "^## Purpose" "^## Ownership" "^## DNS Contract" "^## Caddy Contract" "^## Secrets Contract" "^## State Contract" "^## Approval Contract" "^## Onramp Host Runtime" "^## SearXNG Pilot" "^## Future Provisioning Gate"; do rg -qi "$pattern" docs/onramp-app-platform-contract.md || { echo "missing: $pattern"; exit 1; }; done`
     - Pass: every required section heading is present
     - Fail: missing file or missing section; add sections and rerun
  2. [ ] Contract explicitly excludes Onramp app services from infra state by default.
     - Verify: `for pattern in "Onramp app services are not managed by OpenTofu by default" "must not be added to values/terraform.tfvars" "Ansible inventory" "OpenTofu state" "separate approved infrastructure plan"; do rg -qi "$pattern" docs/onramp-app-platform-contract.md || { echo "missing: $pattern"; exit 1; }; done`
     - Pass: every negative boundary statement is present
     - Fail: boundary is unclear or missing; revise and rerun
  3. [ ] Contract includes future provisioning and approval rules for the onramp host.
     - Verify: `for pattern in "Future provisioning gate" "reviewed just plan" "explicit approval" "Podman-in-LXC is experimental"; do rg -qi "$pattern" docs/onramp-app-platform-contract.md || { echo "missing: $pattern"; exit 1; }; done`
     - Pass: every future provisioning rule is present
     - Fail: provisioning gate is unclear; revise and rerun

### Wave 1 -- Validation Gate

**V1: Validate wave 1 documentation package** [medium] -- qa-engineer
- Blocked by: T1, T2
- Checks:
  1. Run all T1 and T2 acceptance criteria.
  2. `mkdir -p .specs/onramp-host-pilot/evidence && printf '%s\n' docs/hermes-operator-pilot-prd.md docs/onramp-app-platform-contract.md .specs/onramp-host-pilot/plan.md > .specs/onramp-host-pilot/evidence/public-safety-files.txt && python scripts/public-safety-check.py --tracked-files .specs/onramp-host-pilot/evidence/public-safety-files.txt` -- planned docs and plan pass public-safety scanning.
  3. `git diff --check -- docs/hermes-operator-pilot-prd.md docs/onramp-app-platform-contract.md .specs/onramp-host-pilot/plan.md` -- no whitespace errors.
  4. Cross-task integration: PRD and contract agree that Debian 13 VM plus Podman is the default onramp-host direction and Podman-in-LXC is experimental.
- On failure: create a fix task, update the relevant document, and rerun V1.

### Wave 2

**T3: Add README and docs navigation for the contract** [small] -- coding-light
- Blocked by: V1
- Description: Add a short pointer from `README.md` to the Hermes operator PRD and Onramp app-platform contract. Create `docs/README.md` as the docs index. Keep the main README concise and avoid duplicating the full contract.
- Files: `README.md`, `docs/README.md`
- Acceptance Criteria:
  1. [ ] README and docs index point operators to both new documents without changing workflow semantics.
     - Verify: `for path in README.md docs/README.md; do test -f "$path" || { echo "missing: $path"; exit 1; }; done; for target in "docs/hermes-operator-pilot-prd.md" "docs/onramp-app-platform-contract.md"; do rg -q "$target" README.md docs/README.md || { echo "missing nav: $target"; exit 1; }; done`
     - Pass: both navigation targets are present in README/docs index
     - Fail: no navigation or overlong duplicated content; revise and rerun
  2. [ ] README still documents `just validate`, `just plan`, and `just apply` as the normal workflow.
     - Verify: `for cmd in "just validate" "just plan" "just apply"; do rg -q "$cmd" README.md || { echo "missing: $cmd"; exit 1; }; done`
     - Pass: all workflow commands remain present
     - Fail: workflow guidance was removed or obscured; restore it and rerun

### Wave 2 -- Validation Gate

**V2: Validate wave 2 documentation navigation** [small] -- qa-engineer
- Blocked by: T3
- Checks:
  1. Run all T3 acceptance criteria.
  2. `mkdir -p .specs/onramp-host-pilot/evidence && printf '%s\n' README.md docs/README.md docs/hermes-operator-pilot-prd.md docs/onramp-app-platform-contract.md .specs/onramp-host-pilot/plan.md > .specs/onramp-host-pilot/evidence/public-safety-files.txt && python scripts/public-safety-check.py --tracked-files .specs/onramp-host-pilot/evidence/public-safety-files.txt` -- planned docs and plan pass public-safety scanning.
  3. `git diff --check -- README.md docs .specs/onramp-host-pilot/plan.md` -- no whitespace errors.
  4. Cross-task integration: README links or references the contract without implying live deployment has already been implemented.
- On failure: create a fix task, update navigation, and rerun V2.

## Dependency Graph

```
Wave 0: T0 -> V0
Wave 1: T1, T2 (parallel after V0) -> V1
Wave 2: T3 -> V2
Final: V2 -> F1 -> F2 -> F3 -> F4 -> F5
```

## Success Criteria

1. [ ] The repository contains a public-safe PRD plus app-platform contract that defines option 3 and the SearXNG pilot classification.
   - Verify: `for pattern in "option 3" "SearXNG" "Debian 13 VM running Podman" "onramp-vNext owns Docker app services" "Onramp app services are not managed by OpenTofu by default"; do rg -qi "$pattern" docs/hermes-operator-pilot-prd.md docs/onramp-app-platform-contract.md || { echo "missing: $pattern"; exit 1; }; done`
   - Pass: every required pattern is present and public-safety checks pass
2. [ ] The main README and docs index provide discoverable navigation to the contract without changing the reviewed infrastructure workflow.
   - Verify: `for path in README.md docs/README.md; do test -f "$path" || { echo "missing: $path"; exit 1; }; done; for target in "docs/hermes-operator-pilot-prd.md" "docs/onramp-app-platform-contract.md"; do rg -q "$target" README.md docs/README.md || { echo "missing nav: $target"; exit 1; }; done; for cmd in "just validate" "just plan" "just apply"; do rg -q "$cmd" README.md || { echo "missing: $cmd"; exit 1; }; done`
   - Pass: both navigation targets and all workflow commands are present
3. [ ] The complete docs-only MVP passes public-safety and repo validation.
   - Verify: `scripts/values.sh check && mkdir -p .specs/onramp-host-pilot/evidence && printf '%s\n' README.md docs/README.md docs/hermes-operator-pilot-prd.md docs/onramp-app-platform-contract.md .specs/onramp-host-pilot/plan.md .specs/onramp-host-pilot/evidence/validation.jsonl > .specs/onramp-host-pilot/evidence/public-safety-files.txt && python scripts/public-safety-check.py && python scripts/public-safety-check.py --tracked-files .specs/onramp-host-pilot/evidence/public-safety-files.txt && git diff --check && just validate`
   - Pass: all commands exit 0; if `scripts/values.sh check` fails, mark F2 blocked and do not archive

## Validation Contract

`/do-it` must satisfy this contract before reporting the plan complete or archiving it.

### Automation completeness

- Required: yes
- `/do-it` must be able to run all agent-runnable validation steps through documented commands, scripts, playbooks, or wrappers.
- Credentials are not required for documentation edits. `just validate` may use local approved private `values/` wiring but raw output must not be saved as evidence.
- Before repo-wide validation, run `scripts/values.sh check`. If required private values are absent, mark F2 blocked, update the Execution Status section, and do not archive. Run `just setup` only when the operator has configured or approved the values source.
- Manual-only steps are not required for this MVP.

### Required automated validation

1. [ ] Run task-specific acceptance criteria from T1, T2, and T3.
   - Command: see each task's `Verify:` command
   - Pass: every acceptance criterion passes as written
   - Fail: create/fix a task, rerun affected checks, then rerun repo-wide validation

2. [ ] Run public-safety and whitespace checks, including planned untracked docs/spec/evidence files.
   - Command: `mkdir -p .specs/onramp-host-pilot/evidence && printf '%s\n' README.md docs/README.md docs/hermes-operator-pilot-prd.md docs/onramp-app-platform-contract.md .specs/onramp-host-pilot/plan.md .specs/onramp-host-pilot/evidence/validation.jsonl > .specs/onramp-host-pilot/evidence/public-safety-files.txt && python scripts/public-safety-check.py && python scripts/public-safety-check.py --tracked-files .specs/onramp-host-pilot/evidence/public-safety-files.txt && git diff --check`
   - Pass: exits 0 with no errors
   - Fail: do not archive; fix public-safety or whitespace findings and rerun

3. [ ] Run the strongest repo-wide validation command when values preflight passes.
   - Command: `scripts/values.sh check && just validate`
   - Pass: exits 0 with no errors or warnings; save only exit status and sanitized summary in evidence
   - Fail: do not archive; if `scripts/values.sh check` fails, update the Execution Status section as blocked; if the failure is tooling-container related, run the public `just setup` repair path if appropriate, then rerun `just validate`

Do not require exact test function names, exhaustive evidence files, or audit-grade traceability unless those tests/scripts already exist or the user explicitly requests that rigor.

### Manual validation

Manual validation is exceptional. It should be `Required: no` unless the plan includes destructive operations, data-loss risk, irreversible external side effects, shared/work production impact, paid/billing/data-costing resources, secret exposure risk, hardware/physical checks, or genuinely subjective user judgment that cannot be replaced by safe automation. Scale matters: personal/local GitHub repos, local/home-lab, and new-backed-up systems are usually agent-runnable; work/shared/multi-user production systems and money/data-costing resources may need user gates when other people, spend, quota, or costly recovery could be affected.

- Required: no
- Justification: Automated validation is sufficient because this MVP only changes public-safe documentation and plan artifacts.
- Steps:
  1. None.

If manual validation is not required, `/do-it` may mark the manual gate complete after recording why automated evidence is sufficient.

### Deployment validation

- Required: no
- Procedure: None. This MVP intentionally does not deploy, provision, plan, apply, or mutate live infrastructure.

If deployment is skipped because it is out of scope, `/do-it` may mark the deployment gate complete after recording that no deployment was required.

### Archive rule

`/do-it` may archive this plan only after all required automated validation, task-specific verification, repo-wide validation, public-safety checks for tracked and planned untracked files, evidence sanitization, and archive preflight pass. Do not require manual validation merely to increase confidence in non-destructive documentation behavior. If any evidence artifact contains raw command logs, private values, real domains/IPs/hostnames, tokens, or rejected content, delete or redact it before archive.

## Telemetry & Evidence Contract

`/do-it` must record sanitized evidence in `.specs/onramp-host-pilot/evidence/validation.jsonl`. Terminal output alone is not durable evidence. Do not store raw command logs, secrets, real domains, real IPs, private DNS records, private inventory, tokens, or raw `values/` content.

Machine-readable evidence records must use JSON Lines with these fields:

```json
{"episode_id":"onramp-host-pilot","phase_id":"wave-1","task_id":"T1","validation_command":"rg -n ... docs/hermes-operator-pilot-prd.md","status":"pending|passed|failed|blocked","archive_status":"not_ready|ready|archived","started_at":"ISO-8601","completed_at":"ISO-8601","evidence":"non-secret terminal summary or artifact path"}
```

Required fields for every validation record:

- `episode_id`: `onramp-host-pilot`
- `phase_id`: `wave-1`, `wave-2`, or `final`
- `task_id`: one of `T0`, `V0`, `T1`, `T2`, `V1`, `T3`, `V2`, `F1`, `F2`, `F3`, `F4`, `F5`
- `validation_command`: exact command run, or `not required` for non-applicable final gates
- `status`: `pending`, `passed`, `failed`, or `blocked`
- `archive_status`: `not_ready`, `ready`, or `archived`
- `started_at`: ISO-8601 timestamp
- `completed_at`: ISO-8601 timestamp or null while running
- `evidence`: sanitized pass/fail signal or artifact path; do not include raw private command output

Minimal append helper for `/do-it` evidence records after each gate. Set `PHASE_ID`, `TASK_ID`, `VALIDATION_COMMAND`, `STATUS`, `ARCHIVE_STATUS`, and `EVIDENCE` in the shell before running it; values must be sanitized before export:

```bash
python -c 'import datetime,json,os,pathlib; p=pathlib.Path(".specs/onramp-host-pilot/evidence/validation.jsonl"); p.parent.mkdir(parents=True, exist_ok=True); rec={"episode_id":"onramp-host-pilot","phase_id":os.environ["PHASE_ID"],"task_id":os.environ["TASK_ID"],"validation_command":os.environ["VALIDATION_COMMAND"],"status":os.environ["STATUS"],"archive_status":os.environ["ARCHIVE_STATUS"],"started_at":os.environ.get("STARTED_AT", datetime.datetime.now(datetime.timezone.utc).isoformat()),"completed_at":os.environ.get("COMPLETED_AT", datetime.datetime.now(datetime.timezone.utc).isoformat()),"evidence":os.environ["EVIDENCE"]}; p.open("a", encoding="utf-8").write(json.dumps(rec, sort_keys=True)+"\n")'
```

Plan review data contract for future adaptive review:

```yaml
plan_profile: docs-architecture-contract
review_panel_decision: recommended
expected_reviewer_count: 6
selected_reviewer_personas:
  - reviewer
  - security-reviewer
  - product-manager
  - devops-pro as automation and operational-readiness reviewer
  - terraform-pro as infrastructure-boundary and IaC safety reviewer
  - qa-engineer as verification realism reviewer
selection_reasons:
  reviewer: validates completeness and standalone executability
  security-reviewer: validates public-safety, secret handling, and approval gates
  product-manager: validates MVP scope and duplicate-product-truth risk
  devops-pro: validates automation commands, values preflight, and evidence flow
  terraform-pro: validates homelab-infra versus Onramp ownership boundaries
  qa-engineer: validates acceptance criteria and false-positive risk
complexity_score: 3
risk_score: 2
expected_high_risk_areas:
  - accidentally implying live deployment exists
  - leaking private site identifiers in docs
  - blurring infrastructure and app-platform ownership
  - over-scoping the MVP into provisioning work
```

## Execution Status

- Status: completed-and-archived
- Last updated: 2026-07-07 complete
- Completed checklist items: T0, V0, T1, T2, V1, T3, V2, F1, F2, F3, F4, F5
- Last completed wave/gate: F5 archive preflight
- Next wave/gate: none
- Blockers: none; values preflight returned ok.
- Evidence artifact: `.specs/archive/onramp-host-pilot/evidence/validation.jsonl`
- Archive status: archived at `.specs/archive/onramp-host-pilot/plan.md`
- Repair loop evidence: initial `just validate` failed on ansible-lint line-length findings; subsequent run passed after splitting Docker Compose download URL lines. TFLint unused-variable warnings were resolved by referencing Forgejo storage-prep variables in a lifecycle precondition.

## Workflow Eval Record

- outcome: completed-and-archived
- friction:
  - category: validation-repair
    severity: low
    evidence: initial repo-wide validation failed on ansible-lint line-length findings in existing Docker Compose download commands.
    impact: required small out-of-plan validation repair before archive.
    recommended_change: keep line-length lint clean in service role shell snippets.
    candidate_test: `just validate`
  - category: validation-warning-repair
    severity: low
    evidence: TFLint reported Forgejo storage-prep variables as unused because they are consumed by `scripts/storage-vars.py` outside OpenTofu resources.
    impact: required explicit OpenTofu reference to satisfy static analysis and preserve the storage-prep contract.
    recommended_change: when variables are consumed by external workflow helpers, also represent the contract in HCL validation/preconditions.
    candidate_test: `just validate`
- missing_evidence: none
- improvement_candidates:
  - Record expected environment-only warnings separately from tool validation warnings in future validation contracts.
- eval_confidence: high
- post_run_reviewers: deterministic-checks-only
- archive_status: archived
- archive_path: `.specs/archive/onramp-host-pilot/plan.md`
- validation_commands_results:
  - `scripts/values.sh check`: passed
  - task-specific acceptance checks: passed
  - public-safety checks for tracked and planned files: passed
  - `git diff --check`: passed
  - `just validate`: passed after repair loop
- manual_gate_decision: not required; docs-only public-safe MVP
- deployment_gate_decision: not required; no live mutation in scope
- checklist_completion_state: complete
- blocker_reason: none
- execution_outcome: completed
- panel_quality_label: right-sized
- panel_quality_reason: reviewed plan exposed the key docs, safety, validation, and archive requirements; only existing repo lint warnings required repair.
- panel_quality_confidence: medium

## Handoff Notes

- PRD input precedence resolved to the conversation-created `docs/hermes-operator-pilot-prd.md`. If that file is absent, T1 must create it from the decisions embedded in this plan instead of treating absence as a blocker.
- Web research conclusions to preserve: Podman Compose is possible through external compose providers; Debian 13 provides modern Podman and podman-compose; Proxmox documents LXC nesting features but recommends QEMU VMs for maximum isolation and live migration when nesting containers; nested Podman requires privileges such as user namespaces, mounts, and often `/dev/fuse`.
- The recommended default onramp host is a Debian 13 VM running Podman. Podman-in-LXC is an experiment, not the default. Arch/CachyOS VM is not the default because rolling-release churn is undesirable for a durable onramp host.
- This plan must not mutate `C:/Projects/Personal/onramp-vNext`. Reading that sibling repo is optional and non-blocking; the required Onramp context is embedded in this plan. Do not archive raw filenames or content from that repo in this public repository.
- Earlier local `just plan` after merging PR #2 reported no OpenTofu changes. That result is context only. This plan does not require rerunning `just plan`; do not run `just plan`, `just apply`, or OpenTofu plan/apply/import/state commands for this MVP without a separate explicit user request.
- If `just validate` fails due tooling-container repair needs, follow the public repo guidance and run `just setup` before retrying. If `scripts/values.sh check` fails because private values are absent, mark F2 blocked rather than inventing placeholder private values. Do not invoke private just recipes directly.
- Evidence cleanup is part of rollback and archive preflight. Delete or redact `.specs/onramp-host-pilot/evidence/` if it contains raw logs, private values, real site identifiers, tokens, or rejected content.
- Exact prose fragments in acceptance criteria are intentional. They prevent shallow keyword-only docs from passing; implement the documents with those phrases unless the plan is deliberately updated with equivalent deterministic checks.
