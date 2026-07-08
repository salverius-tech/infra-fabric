---
date: 2026-07-07
status: synthesis-complete
---

# Review: Onramp Host Pilot Contract

## Review Panel
| Reviewer | Base Agent | Assigned Expert Persona | Why selected | Adversarial angle | Artifact |
|----------|------------|-------------------------|--------------|-------------------|----------|
| reviewer | reviewer | Completeness and explicitness reviewer | Mandatory standard reviewer for hidden assumptions and executable clarity | Assume a fresh `/do-it` has no conversation context and weak checks pass shallow docs | `.specs/onramp-host-pilot/review-1/reviewer.md` |
| security-reviewer | security-reviewer | Safety, redaction, rollback reviewer | Mandatory standard reviewer for safety and secret leakage | Assume evidence logs and cross-repo reads leak local/private data | `.specs/onramp-host-pilot/review-1/security-reviewer.md` |
| product-manager | product-manager | Simplicity and scope reviewer | Mandatory standard reviewer for proportionality | Assume the plan duplicates product truth and overbuilds process | `.specs/onramp-host-pilot/review-1/product-manager.md` |
| devops-pro | devops-pro | Automation and operational-readiness reviewer | Plan depends on `/do-it`, `just validate`, evidence capture, and tooling preconditions | Assume a fresh session lacks private values or silently skips path-dependent context | `.specs/onramp-host-pilot/review-1/devops-pro.md` |
| terraform-pro | terraform-pro | Infrastructure-boundary and IaC safety reviewer | Plan draws the line between OpenTofu substrate and Onramp app services | Assume a future executor confuses docs decisions with permission to run plan/apply | `.specs/onramp-host-pilot/review-1/terraform-pro.md` |
| qa-engineer | qa-engineer | Verification realism and false-positive acceptance reviewer | Plan is docs-only and relies on grep-style acceptance checks | Assume shallow docs can satisfy current checks without proving the contract | `.specs/onramp-host-pilot/review-1/qa-engineer.md` |

## Standard Reviewer Findings
### reviewer
- High substantive defect: T1 depends on an untracked PRD draft that might be absent for a fresh executor; T1 should create or update the PRD and the plan should embed the required decisions.
- Medium process defect: multiple acceptance commands use regex alternation, so one keyword can pass checks that claim all topics are present.
- Medium process defect: optional `docs/README.md` is named in commands as if it always exists.
- Medium substantive defect: cross-repo Onramp path is machine-specific and lacks fallback.

### security-reviewer
- Medium process defect: public-safety command scans tracked files by default, so new docs/evidence can escape checks unless explicitly included.
- Medium process defect: cross-repo context and evidence capture can leak local metadata if raw filenames or logs are stored.
- Medium substantive defect: `just validate` evidence could capture private values output unless the plan restricts evidence to exit status and sanitized summary.
- Low process defect: rollback ignores untracked evidence cleanup.

### product-manager
- Duplicate: separate PRD plus contract may become duplicate product truth; if retained, each artifact needs a distinct purpose.
- Medium substantive defect: broad OR checks create false confidence.
- Low-value/theater: reading only Onramp PRD filenames is not useful validation.
- Low-value/theater: full JSONL evidence schema may be disproportionate, though some durable evidence is still needed.

## Additional Expert Findings
### devops-pro
- High process defect: `just validate` can be blocked by private `values/` setup in a brand-new session; the plan needs a preflight/precondition or blocked outcome.
- Medium substantive defect: broad `rg` alternation checks are false-positive prone.
- Medium process defect: cross-repo path can silently produce empty evidence.
- Medium process defect: evidence is optional where archive depends on resumable verification.

### terraform-pro
- Medium process defect: plan/apply exclusions leave enough ambiguity that an executor might run `just plan` for a docs-only MVP.
- Medium substantive defect: ownership contract does not require explicit negative state boundaries for Onramp apps.
- Low process defect: future VM/LXC provisioning gate is underspecified.

### qa-engineer
- High-labeled findings were category-labeled `false positive` but the substance duplicated the real OR-regex verification defect.
- Medium substantive defect: cross-repo coherence is claimed without actual comparison to Onramp assumptions.
- Medium process defect: evidence requirements can be terminal-only and non-durable.

## Suggested Additional Reviewers
- devops-pro -- relevant because `/do-it` automation, local tooling, `just validate`, and evidence capture are central to execution readiness.
- terraform-pro -- relevant because the plan defines what must stay out of OpenTofu state and what future infra provisioning requires.
- qa-engineer -- relevant because documentation acceptance checks are easy to satisfy with shallow keyword matches.

## Bugs (must fix before execution)
1. T1 can depend on a missing untracked PRD draft. Fix by making T1 create-or-update the PRD and embedding the required decisions in the plan.
2. Acceptance criteria use OR-style `rg` checks that pass when only one required topic is present. Fix with per-topic assertions or a deterministic checker.
3. `just validate` can be blocked by missing/invalid private `values/`. Fix with an explicit preflight and blocked outcome while keeping `just validate` required when values are available.
4. New docs, specs, and evidence are not necessarily scanned by `public-safety-check.py` because it defaults to tracked files. Fix by adding explicit tracked-file-list checks for planned untracked files.
5. Machine-specific Onramp reads are required but not portable or useful. Fix by making external Onramp reads optional/non-blocking and relying on embedded sanitized context.
6. Evidence can be terminal-only or raw log-like. Fix by requiring sanitized evidence records and forbidding raw `just validate` output archival.
7. The plan lacks an `## Execution Status` section required by the plan integrity contract. Fix by adding a not-started execution status section.
8. Plan/apply prohibitions are not explicit enough for a docs-only MVP. Fix by forbidding `just plan`, `just apply`, OpenTofu plan/apply/import/state commands unless separately requested.

## Hardening
1. Make `docs/README.md` mandatory if commands reference it.
2. Give the separate contract a distinct purpose from the PRD to avoid duplicate product truth.
3. Require explicit negative state boundaries: Onramp apps must not enter OpenTofu state, tfvars, or Ansible inventory unless promoted by a separate approved infra plan.
4. Add a future provisioning gate paragraph for Debian VM/LXC onramp-host work.
5. Add cleanup guidance for failed runs or rejected evidence artifacts.

## Simpler Alternatives / Scope Reductions
1. A single PRD decision section or ADR could be enough. If the separate contract remains, it must be a concise boundary/ownership contract, not a duplicate PRD.
2. Remove mandatory cross-repo filename reading. It does not prove the contract and makes execution machine-specific.
3. Use one required sanitized validation JSONL or summary artifact rather than broad telemetry ceremony.

## Automation Readiness
- Agent-runnable operational steps: Mostly present, but require fixes for portable preflight, optional Onramp context, and explicit `values/` precondition.
- Credential/auth flow clarity: No credentials required for docs edits. `just validate` may rely on existing local `values/`; plan must classify missing values as blocked or run setup, not as manual validation.
- Evidence and archive gates: Need durable sanitized evidence file and explicit public-safety scanning of untracked planned files.
- Manual-only steps and justification: Manual validation remains not required because MVP is docs-only and reversible.
- Checklist ledger: Present and consistent, but needs `Execution Status` and any new/changed validation gates reflected without marking work complete.

## Contested or Dismissed Findings
1. qa-engineer labeled the OR-regex defect as `false positive`, but the evidence confirms a real process defect. Treated as duplicate of reviewer/product/devops findings.
2. Product-manager suggested collapsing the separate contract. Treated as hardening/scope advice, not a must-fix, because the plan can justify distinct PRD versus contract purposes.
3. Full JSONL evidence was criticized as theater. Treated partly valid: keep a minimal sanitized evidence record because `/do-it` needs durable evidence, but avoid raw logs and excessive schema work.

## Verification Notes
1. Confirmed OR-regex issue by reading plan acceptance criteria under T1, T2, T3, and Success Criteria: each uses alternation patterns with `rg`, which exits 0 on any match.
2. Confirmed untracked PRD dependency from plan Constraints and T1: the plan records untracked `docs/hermes-operator-pilot-prd.md`, and T1 says update the file rather than create-or-update.
3. Confirmed public-safety default by reading `scripts/public-safety-check.py`: it uses `git ls-files` unless `--tracked-files` is provided.
4. Confirmed missing `## Execution Status` by section scan of the reviewed plan.

## Reviewer Artifact Status
| Reviewer | Artifact | Status | Notes |
|----------|----------|--------|-------|
| reviewer | `.specs/onramp-host-pilot/review-1/reviewer.md` | read | usable artifact |
| security-reviewer | `.specs/onramp-host-pilot/review-1/security-reviewer.md` | read | usable artifact |
| product-manager | `.specs/onramp-host-pilot/review-1/product-manager.md` | read | usable artifact |
| devops-pro | `.specs/onramp-host-pilot/review-1/devops-pro.md` | read | usable JSON artifact |
| terraform-pro | `.specs/onramp-host-pilot/review-1/terraform-pro.md` | read | usable artifact |
| qa-engineer | `.specs/onramp-host-pilot/review-1/qa-engineer.md` | read | usable artifact despite some category mislabels |

## Timing Notes
| Step | Duration | Notes |
|------|----------|-------|
| Initial review panel | unknown | 6/6 reviewers succeeded; per-reviewer timing unavailable |
| Artifact reads | unknown | all expected reviewer artifacts read |
| Recovery calls | not run | no missing/unusable artifacts |
| Verification | unknown | read plan and `scripts/public-safety-check.py`; no high finding remained unverified |
| Synthesis | unknown | `.specs/onramp-host-pilot/review-1/synthesis.md` |

## Adaptive Review Data
| Field | Value |
|-------|-------|
| review_strategy | manual-review-it |
| complexity_score | 3: docs-only work, but cross-repo architecture boundary and automation readiness increase complexity |
| risk_score | 2: no live mutation, but public-safety/evidence and future infra boundaries matter |
| recommended_reviewer_count | 6: standard panel plus devops, terraform, QA was sufficient |
| selected_reviewers | reviewer, security-reviewer, product-manager, devops-pro, terraform-pro, qa-engineer |
| review_yield | 25 raw findings; 8 must-fix bugs; 7 hardening items; duplicates around OR checks and evidence; 2 low-value/theater; 2 category false positives from qa labels; all must-fix and hardening items applied to the plan |
| execution_readiness_changed | yes: plan now has create-or-update PRD, per-topic validation, values preflight, explicit public-safety file list, evidence rules, Execution Status, and standalone-ready preflight/evidence tasks |

## Auto-Apply Plan
- Applied fixes artifact: `.specs/onramp-host-pilot/review-1/applied-fixes.md`
- Known-blocker fixes artifact: not run/no prior blockers
- Section integrity check: passed
- Standalone-readiness result: STANDALONE READY
- Repair passes used: 1 blocker repair pass plus non-blocking hardening edits

## Review Artifact
Wrote full synthesis to: `.specs/onramp-host-pilot/review-1/synthesis.md`

## Overall Verdict
**Ready to execute**

## Recommended Next Step
- Execute via `/do-it .specs/onramp-host-pilot/plan.md`.
