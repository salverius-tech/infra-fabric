# Product Manager Review

## Finding 1
- category: low-value/theater
- severity: high
- severity_rationale: The plan makes a cross-service access-pattern migration depend on building a broad validation product and shared primitives before the core conversion can start.
- evidence: MVP requires `scripts/check-direct-service-ansible.py` with many subcommands plus `direct_access_ready`, shared Caddy/Docker/file primitives, DRY checks, docs, and final evidence formats.
- required_fix: Cut MVP to direct playbook/role conversion, minimal host-key/connectivity checks, and one policy test for forbidden steady-state `pct`. Defer Caddy/Docker primitive extraction, `dry-run-dryness`, and machine-readable evidence schema.
- confidence: high

## Finding 2
- category: process defect
- severity: medium
- severity_rationale: The task order front-loads tooling before confirming the simplest operational facts, increasing work before proving need.
- evidence: Wave 1 T2 builds the helper/handoff first; Wave 2 T1 then verifies direct inventory, SSH, Python, and become posture. The plan already records a direct-access experiment showing TCP/22 and Ansible ping work except host-key trust.
- required_fix: Move a thin T1-style posture check before T2 using existing Ansible/ssh commands or a temporary narrow script. Build only the helper behavior that the check proves is needed.
- confidence: high

## Finding 3
- category: substantive defect
- severity: medium
- severity_rationale: `direct_access_ready` is specified broadly enough to become a second orchestration layer and Proxmox backdoor.
- evidence: The handoff may perform readiness, minimal bootstrap, known_hosts refresh, direct SSH/Python/root-or-become verification, and appears in service playbooks before every role.
- required_fix: Define its exact minimal contract: no service config, no package installs except explicitly approved Python bootstrap, no secret writes, no app-specific tasks. Prefer built-in Ansible `known_hosts`, `wait_for_connection`, `raw` bootstrap, and `assert` tasks over custom orchestration logic.
- confidence: medium

## Finding 4
- category: low-value/theater
- severity: medium
- severity_rationale: Several proposed checks validate plan aesthetics rather than preventing user-visible failure.
- evidence: `dry-run-dryness` must prove reusable handoff usage, shared primitive adoption, and avoidance of unsafe abstraction. This is subjective and likely to encode reviewer preferences into a migration script.
- required_fix: Replace `dry-run-dryness` with concrete regression tests: service playbooks include the handoff, direct roles contain no forbidden `pct`, and secret files have `no_log`/mode/final destination. Track abstraction decisions in the plan, not executable policy.
- confidence: high

## Finding 5
- category: duplicate
- severity: low
- severity_rationale: Duplicated validation steps create ambiguity over what `/do-it` must satisfy and invite checklist drift.
- evidence: The Validation Contract has duplicate numbered item `6`; one “policy checks” item repeats the `bootstrap-plan` command before the real `policy && pve-boundary` command.
- required_fix: Remove the duplicate `6`, keep one policy-check step with the correct command, and renumber the validation contract once.
- confidence: high
