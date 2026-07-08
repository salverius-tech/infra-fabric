---
date: 2026-07-07
status: synthesis-complete
---

# Review: Convert Service Ansible to Direct Service Access

## Review Panel
| Reviewer | Base Agent | Assigned Expert Persona | Why selected | Adversarial angle | Artifact |
|----------|------------|-------------------------|--------------|-------------------|----------|
| reviewer | reviewer | Completeness & explicitness reviewer | Mandatory standard reviewer | Assume a brand-new `/do-it` session lacks prior context | `.specs/direct-service-ansible/review-2/reviewer.md` |
| security-reviewer | security-reviewer | Security/red-team reviewer | Mandatory standard reviewer | Assume trust/credential mistakes can redirect root automation | `.specs/direct-service-ansible/review-2/security-reviewer.md` |
| product-manager | product-manager | Simplicity/scope reviewer | Mandatory standard reviewer | Assume new helper/DRY work is overbuilt unless concrete | `.specs/direct-service-ansible/review-2/product-manager.md` |
| devops-pro | devops-pro | Rollout and operational safety reviewer | Direct host trust, run-infra lifecycle, partial rollout risk | Assume first fresh LXC or new container session fails | `.specs/direct-service-ansible/review-2/devops-pro.md` |
| qa-engineer | qa-engineer | Verification realism reviewer | Plan relies on helper summaries and check-mode gates | Assume helper can false-pass without executing real checks | `.specs/direct-service-ansible/review-2/qa-engineer.md` |
| python-pro | python-pro | Python CLI/testability reviewer | New Python helper is central automation gate | Assume brittle CLI contracts and misleading exit codes | `.specs/direct-service-ansible/review-2/python-pro.md` |
| ansible-implementation-reviewer | coding-medium | Ansible implementation/idempotence reviewer | Main work is Ansible role/playbook migration | Assume direct module conversion changes handlers, ownership, idempotence | `.specs/direct-service-ansible/review-2/ansible-implementation-reviewer.md` |

## Standard Reviewer Findings
### reviewer
- High substantive defect: live direct probes are required for archive while deployment is not required, which can block fresh/source-only setups.
- Medium process defect: `|| true` masks syntax failures for direct-access-ready validation.
- Medium process defect: duplicate numbered policy checks make final gates ambiguous.
- Medium process defect: Wave 3 parallel edits can collide across shared playbooks/tests.
- Low substantive defect: redaction grep can both reject allowed placeholders and miss private values.

### security-reviewer
- High substantive defect: host-key refresh lacks a trusted key source and changed-key failure semantics.
- Medium process defect: known_hosts refresh is a controlled mutation, not purely non-destructive.
- High substantive defect: bootstrap handoff lacks a strict allowlist and could become a Proxmox backdoor.
- Medium substantive defect: accepting root direct access lacks compensating controls.
- Medium substantive defect: redaction coverage is too narrow.

### product-manager
- High low-value/theater: broad helper/DRY/evidence scope risks turning migration into a validation product.
- Medium process defect: tooling is front-loaded before a thin operational check.
- Medium substantive defect: `direct_access_ready` is broad enough to become a second orchestration layer.
- Medium low-value/theater: `dry-run-dryness` is subjective plan aesthetics rather than concrete regression prevention.
- Low duplicate: duplicate validation item 6.

## Additional Expert Findings
### devops-pro
- High substantive defect: known_hosts refresh in ephemeral `run-infra` sessions may not persist into later sessions.
- High substantive defect: a direct-host role cannot fix host-key trust before Ansible connects.
- Medium process defect: `|| true` masks handoff syntax failures.
- Medium process defect: duplicate validation gates can skip real policy checks.
- Medium process defect: mixed direct script invocation and `scripts/python.sh` usage may fail in fresh sessions.

### qa-engineer
- High false-positive risk: helper summaries may pass without invoking real Ansible operations.
- High false-positive risk: broad check-mode exceptions can hide untested mutating behavior.
- Medium process defect: duplicate validation numbering.
- High substantive defect: host-key refresh could silently bless conflicting keys.
- Medium low-value/theater: redaction grep is insufficient.

### python-pro
- Medium substantive defect: helper exit statuses are not contracted.
- Medium substantive defect: redaction tests are insufficient and can reject placeholders.
- Medium process defect: known_hosts mutation lacks isolation/dry-run/atomicity requirements.
- Medium substantive defect: public fixture coverage is incomplete for non-live helper subcommands.
- Low duplicate: duplicate validation item 6.

### ansible-implementation-reviewer
- High substantive defect: `direct_access_ready` spans pve/controller/direct execution contexts and cannot be a simple direct role.
- High substantive defect: direct module conversion lacks handler/idempotence criteria for daemon reloads, Caddy validation, and restart timing.
- Medium substantive defect: check-mode exceptions can be theater without idempotence guards.
- Medium substantive defect: direct copy/template can silently alter file ownership beyond secret files.
- Medium process defect: Wave 3 tasks may proceed on stale direct-access assumptions.

## Suggested Additional Reviewers
- devops-pro -- Relevant for run-infra Docker lifecycle, persistent trust state, rollout ordering, and fresh LXC failure modes.
- qa-engineer -- Relevant for helper false positives, check-mode realism, acceptance criteria, and archive gates.
- python-pro -- Relevant for CLI contracts, exit statuses, fixtures, and redaction logic.
- coding-medium as Ansible implementation reviewer -- Relevant for Ansible host context, handler semantics, file ownership, and idempotence.

## Bugs (must fix before execution)
1. Define execution modes so source-only/fresh setups do not require pre-existing live LXCs, while current/live deployments still run direct probes when values are present.
2. Replace host-key refresh with a persistent, scoped, authenticated trust workflow: managed `values/` known_hosts path, Proxmox-derived expected fingerprints, absent/unchanged/conflict states, fail-closed changed-key handling, and validation across new `run-infra` sessions.
3. Split `direct_access_ready` into explicit pve/controller/direct execution contexts; it cannot be a simple direct-host role that fixes trust before connection.
4. Add a strict bootstrap allowlist and approval semantics so the handoff cannot become a Proxmox steady-state backdoor.
5. Define helper CLI contracts: real Ansible invocation where required, public fixtures for static modes, exit-code semantics, redaction boundaries, and nonzero failure propagation.
6. Remove `|| true` syntax masking and duplicate/mislabeled validation items.
7. Add handler/idempotence/file-ownership criteria for direct module conversion.
8. Add check-mode exception budget with idempotence guards and compensating evidence.

## Hardening
1. Replace `dry-run-dryness` with concrete structure/shared-primitive policy checks; avoid subjective abstraction enforcement.
2. Add root direct-access compensating controls and a tracked deferral for non-root service users.
3. Add Wave 3 sequencing/file ownership rules to prevent parallel collisions.
4. Expand redaction testing with fixtures for private IPs/domains/tokens/usernames/keys and allowlisted placeholders.
5. Standardize helper invocation style: host-side via `scripts/python.sh`, inside `run-infra` via `python scripts/check-direct-service-ansible.py`.

## Simpler Alternatives / Scope Reductions
1. Defer broad Caddy/Docker abstraction unless identical repeated behavior is proven by concrete structure checks.
2. Remove `dry-run-dryness`; keep only objective checks for handoff inclusion, no forbidden `pct`, file permissions/no_log, and handler/idempotence.
3. Keep machine-readable evidence minimal and do not let it block the core migration beyond non-secret pass/fail records.

## Automation Readiness
- Agent-runnable operational steps: Not ready before fixes; helper modes need CLI contracts and execution mode split.
- Credential/auth flow clarity: Needs persistent scoped known_hosts and root-access controls.
- Evidence and archive gates: Duplicate validation items and live/source ambiguity must be fixed.
- Manual-only steps and justification: Existing source edits need no approval; changed host-key replacement and bootstrap mutations need explicit approval semantics.

## Contested or Dismissed Findings
1. Product-manager's “build only after posture check” was partially accepted as hardening, not a strict blocker: the helper is still needed first for durable automation, but the plan now should include a thin source/public mode and not overbuild subjective DRY checks.
2. `dry-run-dryness` was downgraded from a bug to a hardening/scope issue; it is harmful mainly because it is subjective and should be replaced with concrete checks.
3. Redaction grep issues were treated as hardening unless they protect archived evidence from live/private commands, where they become part of helper contract fixes.

## Verification Notes
1. Live/source contradiction confirmed in plan: Validation Contract requires direct service known_hosts/connectivity/become probes, while Deployment validation says deployment is not required for MVP archive.
2. Host-key persistence concern confirmed in repo: `scripts/run-infra.sh` uses `docker compose run --rm`; `compose.yaml` mounts host `.ssh` read-only; `tools/docker-entrypoint.sh` copies known_hosts into container home, so in-container trust updates are ephemeral unless a managed writable path is added.
3. Syntax masking confirmed in plan: T2 AC4 uses `ansible-playbook --syntax-check ... 2>/dev/null || true`.
4. Duplicate validation confirmed in plan: two numbered item `6` entries under Required automated validation, one mislabeled as policy while running bootstrap-plan.
5. Direct role trust issue confirmed by Ansible semantics and plan wording: service playbooks include the handoff before direct roles, but normal direct-host play connection occurs before role tasks.

## Reviewer Artifact Status
| Reviewer | Artifact | Status | Notes |
|----------|----------|--------|-------|
| reviewer | `.specs/direct-service-ansible/review-2/reviewer.md` | read | usable |
| security-reviewer | `.specs/direct-service-ansible/review-2/security-reviewer.md` | read | usable |
| product-manager | `.specs/direct-service-ansible/review-2/product-manager.md` | read | usable |
| devops-pro | `.specs/direct-service-ansible/review-2/devops-pro.md` | read | usable |
| qa-engineer | `.specs/direct-service-ansible/review-2/qa-engineer.md` | read | usable |
| python-pro | `.specs/direct-service-ansible/review-2/python-pro.md` | read | usable |
| ansible-implementation-reviewer | `.specs/direct-service-ansible/review-2/ansible-implementation-reviewer.md` | read | usable |

## Adaptive Review Data
| Field | Value |
|-------|-------|
| review_strategy | manual-review-it |
| complexity_score | 9/10: cross-service Ansible migration, bootstrap trust, helper/tooling, live/fresh modes |
| risk_score | 7/10: root SSH, host-key trust, multiple live services if deployed |
| recommended_reviewer_count | 7: standard 3 plus DevOps, QA, Python, Ansible implementation |
| selected_reviewers | reviewer, security-reviewer, product-manager, devops-pro, qa-engineer, python-pro, ansible-implementation-reviewer |
| review_yield | 35 findings; must-fix 8 merged; hardening 5 merged; duplicates 3; low-value/theater 3; false-positive risk 2 |
| execution_readiness_changed | yes: plan requires execution-mode split, persistent known_hosts, strict handoff contexts, CLI contracts, and validation cleanup |

## Timing Notes
| Step | Duration | Notes |
|------|----------|-------|
| Initial review panel | per-reviewer timing unavailable | 7/7 succeeded |
| Artifact reads | per-reviewer timing unavailable | all expected reviewer artifacts read |
| Recovery calls | not run | no missing/unusable artifacts |
| Verification | per-command timing unavailable | static reads plus targeted grep of plan/run-infra/compose/entrypoint |
| Synthesis | per-step timing unavailable | `.specs/direct-service-ansible/review-2/synthesis.md` |

## Auto-Apply Plan
- Applied fixes artifact: `.specs/direct-service-ansible/review-2/applied-fixes.md`
- Known-blocker fixes artifact: `not run/no prior blockers found`
- Section integrity check: passed after each edit batch
- Standalone-readiness result: `STANDALONE READY`
- Repair passes used: 2
- Non-blocking standalone note remaining: source-only mode still references `just validate`; acceptable for current repo context, but future public-only validation fallback could clarify new-user bootstrap docs.

## Review Artifact
Wrote full synthesis to: `.specs/direct-service-ansible/review-2/synthesis.md`

## Overall Verdict
**Ready to execute** after auto-applied plan fixes and standalone-readiness repairs.

## Recommended Next Step
- Execute via `/do-it .specs/direct-service-ansible/plan.md`.
