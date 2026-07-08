---
date: 2026-07-07
status: synthesis-complete
---

# Review: Convert Service Ansible to Direct Service Access

## Review Panel
| Reviewer | Base Agent | Assigned Expert Persona | Why selected | Adversarial angle | Artifact |
|----------|------------|-------------------------|--------------|-------------------|----------|
| reviewer | reviewer | Completeness & explicitness reviewer | Mandatory standard reviewer | Assume fresh `/do-it` has no hidden context | `.specs/direct-service-ansible/review-1/reviewer.md` |
| security-reviewer | security-reviewer | Security and operational hazard reviewer | Mandatory standard reviewer | Assume direct SSH broadens privileges or leaks private data | `.specs/direct-service-ansible/review-1/security-reviewer.md` |
| product-manager | product-manager | Scope/simplicity reviewer | Mandatory standard reviewer | Challenge over-broad/brittle plan shape | `.specs/direct-service-ansible/review-1/product-manager.md` |
| devops-pro | devops-pro | Ansible rollout and operations safety reviewer | Cross-service live operations migration | Assume direct SSH fails and broad role conversion breaks one service | `.specs/direct-service-ansible/review-1/devops-pro.md` |
| qa-engineer | qa-engineer | Verification realism and regression coverage reviewer | Plan relies heavily on static validation | Assume grep/syntax passes while runtime breaks | `.specs/direct-service-ansible/review-1/qa-engineer.md` |
| python-pro | python-pro | Python inventory/test tooling reviewer | Dynamic inventory/settings/tests gate execution | Assume hard-coded loops disagree with settings | `.specs/direct-service-ansible/review-1/python-pro.md` |
| terraform-pro | terraform-pro | IaC/service-boundary reviewer | OpenTofu-derived inventory and Proxmox boundary are central | Assume refactor accidentally forces infra/state changes | `.specs/direct-service-ansible/review-1/terraform-pro.md` |

## Standard Reviewer Findings
### reviewer
- High substantive defect: plan invents `caddy_proxy` as a direct inventory group even though the role is Technitium-local.
- High process defect: hard-coded service connectivity loops contradict settings-enabled service semantics.
- Medium substantive defect: blanket `hosts: pve` readiness requirement is wrong for some playbooks.
- Medium substantive defect: direct module conversion lacks an explicit idempotent template/copy/handler pattern.

### security-reviewer
- High substantive defect: direct SSH may broaden root access because inventory defaults to `root`; plan needs a no-broaden gate.
- Medium substantive defect: ping does not prove `become` works.
- Medium substantive defect: secret file staging/mode/no-tempfile behavior is underspecified.
- Medium process defect: disabled service loops can fail or pressure unsafe enabling.
- Low process defect: saved evidence could leak private topology unless redacted.

### product-manager
- High substantive defect: `caddy_proxy` target does not exist.
- High process defect: repeated hard-coded connectivity command is not settings-aware.
- Medium substantive defect: universal pve readiness check is over-broad.
- Medium low-value/theater: raw text checks are brittle.
- Medium process defect: duplicated long commands should become a helper/wrapper.

## Additional Expert Findings
### devops-pro
- High substantive defect: `caddy_proxy` target is invalid.
- Medium substantive defect: direct connectivity matrix is not realistic for disabled services.
- High substantive defect: no gated bootstrap/recovery path when service is reachable via Proxmox but not direct SSH.
- Medium process defect: static tests/syntax checks do not exercise converted roles enough.
- Medium substantive defect: live rollout rollback is under-specified.

### qa-engineer
- High substantive defect: acceptance could pass while pve still performs service configuration.
- High finding labeled false positive by reviewer, but substantively valid: tests prove text absence/syntax, not service behavior.
- Medium substantive defect: disabled services can block or be silently treated as success.
- Medium process defect: raw inventory evidence can violate public-safety constraints.
- Medium process defect: existing tests assert stale Proxmox task names.

### python-pro
- High substantive defect: `caddy_proxy` group does not exist in dynamic inventory.
- Medium substantive defect: hard-coded connectivity checks do not prove enabled private services.
- Medium process defect: bare `python - <<` commands can run outside repo tooling.
- Medium substantive defect: existing tests may preserve stale Proxmox task names.

### terraform-pro
- High substantive defect: regex `pct (exec|push|enter)` misses argv-style YAML tasks where `pct` and subcommand are separate list entries.
- High substantive defect: direct SSH may not be bootstrapped for fresh LXCs because current package setup occurs via `pct exec`.
- High substantive defect: Forgejo Runner role contains Proxmox-host mutations and cannot be moved wholesale into the runner LXC.
- Medium substantive defect: `caddy_proxy` target does not exist.
- Medium process defect: hard-coded connectivity loop ignores enabled services.

## Suggested Additional Reviewers
- devops-pro -- relevant for rollout, direct SSH reachability, partial failure recovery, and deployment boundary safety.
- qa-engineer -- relevant for acceptance criteria quality and regression tests that must prove policy rather than comments/strings.
- python-pro -- relevant for settings/dynamic inventory/test helpers that should generate enabled-service matrices.
- terraform-pro -- relevant for preserving OpenTofu/Proxmox lifecycle ownership and avoiding accidental infra mutations.

## Bugs (must fix before execution)
1. Invalid `caddy_proxy` target. Caddy proxy is currently tied to Technitium/DNS LXC; dynamic inventory has no `caddy_proxy` service group. The plan must target `technitium` or explicitly add an alias.
2. Hard-coded connectivity/syntax loops ignore enabled services and disabled groups. The plan must require a settings/inventory-derived helper and sanitized checked/skipped evidence.
3. Regex-only `pct` checks are insufficient. Existing YAML uses argv lists with `- pct` / `- push`; tests must parse YAML or otherwise detect argv-style forbidden commands.
4. The plan overstates direct conversion by moving all roles wholesale. Forgejo Runner includes Proxmox-host SSH authorization/trust tasks and needs a split direct-in-LXC vs pve-host-boundary design.
5. The plan lacks a direct SSH/bootstrap prerequisite. It must verify SSH + Python + become for enabled services, and define a gated bootstrap/recovery path if direct access is missing.
6. The plan's validation can pass while pve still configures services. It needs YAML-aware tests proving pve plays are limited to lifecycle/bootstrap/storage and service roles run only in direct plays.
7. Secret file handling and evidence redaction are underspecified. The plan must require final-path copy/template with owner/mode/no_log, no temp secret staging, and sanitized evidence artifacts.

## Hardening
1. Add a tracked helper script instead of repeating long one-liners across plan sections.
2. Replace bare `python - <<'PY'` checks with `scripts/python.sh` or committed unit tests.
3. Add per-service check-mode/diff or direct dry-run validation where safe, with explicit exceptions for tasks that do not support check mode.
4. Define live rollout as optional, serial, and approval-gated with per-service backups/health checks/rollback.
5. Update stale test assertions that reference Proxmox-specific task names while preserving semantic no-log/idempotence checks.

## Simpler Alternatives / Scope Reductions
1. Use `onramp_host` as a reference pattern but implement a shared validation helper first; this reduces duplicated command drift.
2. Treat Caddy proxy as a Technitium-hosted role, not a new service group, unless a separate design promotes it.
3. Split conversion into service cohorts with the same final policy rather than one undifferentiated “convert all roles” task.

## Automation Readiness
- Agent-runnable operational steps: Not ready until commands are generated from settings/inventory rather than hard-coded group lists.
- Credential/auth flow clarity: Needs a direct SSH + become probe and no-broaden-root-SSH gate.
- Evidence and archive gates: Need sanitized evidence format and no raw `ansible-inventory --graph` persistence.
- Manual-only steps and justification: Source-level work does not need manual validation; live apply remains explicit-approval-gated.
- Execution checklist: Present but must be updated to include helper script, bootstrap/access gate, role-boundary split, and YAML-aware policy tests.

## Contested or Dismissed Findings
1. QA labeled weak behavior testing as `false positive`; synthesis treats it as valid hardening/substantive validation weakness because multiple reviewers independently identified static checks that can pass on broken behavior.
2. Universal pve readiness was downgraded from bug to part of the broader boundary fix: not every playbook needs identical readiness; plan must define per-service lifecycle expectations.
3. Live rollout rollback gaps are not blockers for source-only archive, but must be explicit if live apply is added/approved.

## Verification Notes
1. Confirmed invalid `caddy_proxy`: `infra/ansible/inventory/tfvars.py` `SERVICE_HOSTS` has no `caddy_proxy`; `scripts/settings.py` lists `caddy-proxy.yml` under `technitium`; `infra/ansible/playbooks/caddy-proxy.yml` uses `technitium_vmid`.
2. Confirmed hard-coded settings issue: `scripts/settings.py` defaults to `technitium`, `forgejo`, and dynamic inventory emits enabled services only.
3. Confirmed argv-style `pct` risk: `rg` shows roles contain YAML list items with `- pct`; regex `pct (exec|push|enter)` would miss split argv forms.
4. Confirmed Forgejo Runner boundary concern by static inspection showing runner role contains SSH authorization/trust tasks associated with Proxmox-host operations.

## Reviewer Artifact Status
| Reviewer | Artifact | Status | Notes |
|----------|----------|--------|-------|
| reviewer | `.specs/direct-service-ansible/review-1/reviewer.md` | read | usable |
| security-reviewer | `.specs/direct-service-ansible/review-1/security-reviewer.md` | read | usable |
| product-manager | `.specs/direct-service-ansible/review-1/product-manager.md` | read | usable |
| devops-pro | `.specs/direct-service-ansible/review-1/devops-pro.md` | read | usable |
| qa-engineer | `.specs/direct-service-ansible/review-1/qa-engineer.md` | read | usable |
| python-pro | `.specs/direct-service-ansible/review-1/python-pro.md` | read | usable |
| terraform-pro | `.specs/direct-service-ansible/review-1/terraform-pro.md` | read | usable |

## Timing Notes
| Step | Duration | Notes |
|------|----------|-------|
| Initial review panel | unavailable | 7/7 reviewers succeeded; per-reviewer timing unavailable |
| Artifact reads | unavailable | all expected reviewer artifacts read |
| Recovery calls | not run | no missing/unusable artifacts |
| Verification | unavailable | static reads/grep against plan, settings, inventory, caddy proxy, and role files |
| Synthesis | unavailable | `.specs/direct-service-ansible/review-1/synthesis.md` |

## Adaptive Review Data
| Field | Value |
|-------|-------|
| review_strategy | manual-review-it with auto-apply |
| complexity_score | 8/10: cross-service Ansible role/playbook migration |
| risk_score | 6/10: source-only by default, but live deployment would affect multiple homelab services |
| recommended_reviewer_count | 7: standard 3 plus devops, QA, Python tooling, Terraform/service-boundary |
| selected_reviewers | reviewer, security-reviewer, product-manager, devops-pro, qa-engineer, python-pro, terraform-pro |
| review_yield | 31 raw findings; 7 must-fix themes; 5 hardening themes; duplicates merged; 1 mislabeled false-positive retained as validation issue |
| execution_readiness_changed | yes: plan needs settings-derived helper, YAML-aware tests, direct access/become gate, service-boundary split |

## Auto-Apply Plan
- Applied fixes artifact: `.specs/direct-service-ansible/review-1/applied-fixes.md`
- Known-blocker fixes artifact: not run/no prior blockers
- Section integrity check: passed
- Standalone-readiness result: STANDALONE READY
- Repair passes used: 1

## Review Artifact
Wrote full synthesis to: `.specs/direct-service-ansible/review-1/synthesis.md`

## Overall Verdict
**Ready to execute** after auto-applied plan fixes and standalone-readiness repair pass 1.

## Recommended Next Step
- Execute via `/do-it .specs/direct-service-ansible/plan.md`.
