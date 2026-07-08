---
date: 2026-07-07
status: synthesis-complete
---

# Review: SearXNG on Podman Onramp Host for Hermes

## Review Panel
| Reviewer | Base Agent | Assigned Expert Persona | Why selected | Adversarial angle | Artifact |
|----------|------------|-------------------------|--------------|-------------------|----------|
| reviewer | reviewer | Completeness and explicitness reviewer | Mandatory standard reviewer for standalone executability | Assume fresh `/do-it` lacks hidden context | `.specs/searxng-podman-runtime/review-1/reviewer.md` |
| security-reviewer | security-reviewer | Safety/security reviewer | Mandatory standard reviewer for operational risk | Assume VM/onramp-host leaks secrets or widens access | `.specs/searxng-podman-runtime/review-1/security-reviewer.md` |
| product-manager | product-manager | Scope/simplicity reviewer | Mandatory standard reviewer for size/fit | Assume platform work outruns the SearXNG need | `.specs/searxng-podman-runtime/review-1/product-manager.md` |
| terraform-pro | terraform-pro | Proxmox/OpenTofu VM substrate reviewer | Plan adds a Proxmox QEMU VM resource and tfvars/scaffold | Assume provider syntax or boot source is remembered incorrectly | `.specs/searxng-podman-runtime/review-1/terraform-pro.md` |
| devops-pro | devops-pro | Ansible/Podman operational-readiness reviewer | Plan configures Debian 13 Podman and Onramp target readiness | Assume SSH works but Onramp cannot deploy | `.specs/searxng-podman-runtime/review-1/devops-pro.md` |
| qa-engineer | qa-engineer | Verification realism reviewer | Plan has many grep-based acceptance checks and archive gates | Assume strings pass while behavior is broken | `.specs/searxng-podman-runtime/review-1/qa-engineer.md` |
| python-pro | python-pro | Settings and migration-script reviewer | Plan changes Python settings, inventory parity, and migrations | Assume string edits break registry/default/migration behavior | `.specs/searxng-podman-runtime/review-1/python-pro.md` |

## Standard Reviewer Findings
### reviewer
- Found missing concrete VM provisioning contract, missing planned public-safety file generation, non-enforcing negative SearXNG runtime check, ambiguous Hermes endpoint consumption scope, and grep-heavy validation.
### security-reviewer
- Found missing SSH/deploy-user hardening, missing network/firewall exposure contract, missing planned-file public-safety list, missing future rollback/runbook, and underspecified VM image provenance.
### product-manager
- Found scope mismatch: the plan could complete without a live SearXNG backend. Also flagged overbuilding before smoke proof and lack of Onramp-grounded handoff.

## Additional Expert Findings
### terraform-pro
- Confirmed no current VM pattern exists in repo and that the plan needed an explicit Debian 13 VM boot-source/template contract, provider-schema evidence, and duplicate VMID/IP safeguards.
### devops-pro
- Found undefined rootless/rootful Podman contract, deployment user, compose command/provider, socket/API semantics, SSH bootstrap assumptions, and runtime readiness checks.
### qa-engineer
- Found validation could pass on strings only, public-safety file was missing, negative runtime checks were ineffective, and archive evidence for forbidden operations was underdefined.
### python-pro
- Found wave ordering could break existing service-registry parity tests, migration enablement/idempotence was underspecified, Hermes/onramp_host dependency semantics were unclear, and migration output redaction needed tests.

## Suggested Additional Reviewers
- terraform-pro -- relevant because the riskiest implementation is a new Proxmox VM/OpenTofu substrate.
- devops-pro -- relevant because source success depends on Ansible, SSH bootstrap, Podman readiness, and operational contracts.
- qa-engineer -- relevant because the plan must be executable by `/do-it` and many original checks were grep-only.
- python-pro -- relevant because settings/inventory/migration scripts are Python and have existing parity tests.

## Bugs (must fix before execution)
1. VM boot source/template was undefined; fixed by requiring provider schema evidence and explicit Debian 13 template/image variables or stop/block behavior.
2. Public-safety tracked-file list was missing; fixed by adding T0b and validation requirements.
3. Negative SearXNG runtime check was non-enforcing; fixed by requiring a failing `if rg ...; then exit 1; fi` check for runtime code.
4. Hermes endpoint consumption scope was misleading; fixed by stating this source slice provides contract/scaffold and must mark runtime wiring implemented or follow-up.
5. SSH/deploy-user hardening was missing; fixed by requiring non-root deploy user, root/password SSH policy, sudo scope, key permissions, and SSH preflight.
6. Network/firewall exposure was missing; fixed by adding default-deny, allowed ingress/source CIDR, and no host-published app port contract.
7. Podman/Onramp runtime contract was undefined; fixed by requiring rootless/rootful choice, compose command/provider, socket/API semantics, and validation as Onramp user.
8. Wave ordering could break registry parity tests; fixed by moving minimal inventory/playbook stub into Wave 1 before parity validation.
9. Migration behavior and output redaction were underspecified; fixed by requiring enabled/absent/idempotent migration tests and sanitized stdout checks.
10. Rollback/runbook was missing; fixed by adding T8 and future deployment rollback requirements.

## Hardening
1. Scope truthfulness hardened: the plan now explicitly says completion does not create a live SearXNG URL.
2. Evidence redaction hardened with allowed/forbidden evidence fields for onramp-host topology, SSH targets, URLs, and sibling repo context.
3. Credential-flow clarity hardened with a dedicated subsection.
4. Archive handling hardened with F7 for archive completion and evidence `archive_status: archived`.
5. Checklist handling hardened with `/do-it` resume-ledger rules.

## Simpler Alternatives / Scope Reductions
1. Product review argued for first proving a minimal SearXNG smoke backend before building a generic VM platform. This was not adopted as a blocker because the user selected a runtime implementation plan, but the plan now avoids claiming a live backend and requires a future deployment/smoke plan.
2. Evidence ledger overhead was flagged as process-heavy. It remains because `/do-it` requires durable evidence, but the plan now focuses evidence on sanitized pass/fail signals.

## Automation Readiness
- Agent-runnable operational steps: improved; tasks now include concrete checks for provider schema, service registry parity, inventory mapping, Podman readiness, and no-runtime-SearXNG enforcement.
- Credential/auth flow clarity: improved; private values own SSH/user/endpoint details, tracked source owns names/policy/placeholders only.
- Evidence and archive gates: improved; T0b creates the planned-file list, evidence redaction is explicit, F7 covers archive completion.
- Manual-only steps and justification: clear; no manual gate for source validation, explicit approval required only for future `just plan`/`just apply` or sibling-repo mutation.
- Execution checklist: consistent after edits; all executable tasks/gates have unchecked checklist items.
- Standalone-readiness result: `STANDALONE READY` after auto-apply and one small hardening pass.

## Contested or Dismissed Findings
1. QA artifact labeled two substantive validation gaps as `false positive`; synthesis treated the underlying evidence as valid hardening/bug material because plan/code inspection confirmed weak checks.
2. Product finding that the whole VM platform may be overbuilt was downgraded to scope hardening, not a blocker, because the user explicitly chose this runtime implementation direction.
3. Standalone reviewer hardening that provider-schema command could be more exact remains non-blocking; the plan now requires non-mutating provider schema/docs evidence but leaves exact command to available tooling.

## Verification Notes
1. VM-pattern finding verified with `rg`: existing `infra/opentofu` uses `proxmox_virtual_environment_container` and LXC template download, with no `proxmox_virtual_environment_vm` pattern.
2. Registry-parity finding verified by reading `tests/test_service_registry_parity.py`, which requires `scripts/settings.py` services, OpenTofu enabled-services validation, inventory `SERVICE_HOSTS`, and playbook paths to align.
3. Migration finding verified by reading `scripts/migrate-values.py`, including `enabled_optional_services` behavior and migration output pathways.
4. Inventory/bootstrap assumptions verified by reading `infra/ansible/inventory/tfvars.py`, which currently defaults service hosts to `ansible_user=root`.

## Reviewer Artifact Status
| Reviewer | Artifact | Status | Notes |
|----------|----------|--------|-------|
| reviewer | `.specs/searxng-podman-runtime/review-1/reviewer.md` | read | artifact usable |
| security-reviewer | `.specs/searxng-podman-runtime/review-1/security-reviewer.md` | read | artifact usable |
| product-manager | `.specs/searxng-podman-runtime/review-1/product-manager.md` | read | JSON-shaped artifact usable |
| terraform-pro | `.specs/searxng-podman-runtime/review-1/terraform-pro.md` | read | JSON-shaped artifact usable |
| devops-pro | `.specs/searxng-podman-runtime/review-1/devops-pro.md` | read | JSON-shaped artifact usable |
| qa-engineer | `.specs/searxng-podman-runtime/review-1/qa-engineer.md` | read | artifact usable despite questionable category labels |
| python-pro | `.specs/searxng-podman-runtime/review-1/python-pro.md` | read | JSON-shaped artifact usable |

## Adaptive Review Data
| Field | Value |
|-------|-------|
| review_strategy | manual-review-it |
| complexity_score | 4/5; cross-cutting OpenTofu, Ansible, Python settings/migration, docs, and future deployment safety |
| risk_score | 4/5; source-only now, but plans a future network-facing Proxmox VM and deployment target |
| recommended_reviewer_count | 7; standard 3 plus Terraform, DevOps, QA, Python were all warranted |
| selected_reviewers | reviewer, security-reviewer, product-manager, terraform-pro, devops-pro, qa-engineer, python-pro |
| review_yield | 32 total raw findings; 16 must-fix/process/substantive issues applied; 5 hardening/readiness improvements applied; 1 low-value/theater downgraded; 2 mislabeled false positives reclassified by synthesis; duplicates merged |
| execution_readiness_changed | yes; plan changed from not ready to standalone ready after VM boot-source, validation, security, evidence, and archive fixes |
| panel_quality_inputs | findings changed task structure, wave ordering, validation commands, risk/credential clarity, archive rules, and automation readiness |

## Timing Notes
| Step | Duration | Notes |
|------|----------|-------|
| Initial review panel | unavailable | 7/7 reviewers succeeded; per-reviewer timing unavailable |
| Artifact reads | unavailable | all expected reviewer artifacts read; no recovery needed |
| Recovery calls | not run | no missing/unusable artifacts |
| Verification | unavailable | used targeted `rg` and `read` of tests/settings/migration/inventory files |
| Synthesis | unavailable | artifact path `.specs/searxng-podman-runtime/review-1/synthesis.md` |

## Auto-Apply Plan
- Applied fixes artifact: `.specs/searxng-podman-runtime/review-1/applied-fixes.md`
- Known-blocker fixes artifact: `.specs/searxng-podman-runtime/review-1/known-blocker-fixes.md`
- Section integrity check: passed
- Standalone-readiness result: `STANDALONE READY`
- Repair passes used: 0 blocker repair passes; 1 non-blocking hardening pass

## Review Artifact
Wrote full synthesis to: `.specs/searxng-podman-runtime/review-1/synthesis.md`

## Overall Verdict
**Ready to execute**

## Recommended Next Step
- execute via `/do-it .specs/searxng-podman-runtime/plan.md`
