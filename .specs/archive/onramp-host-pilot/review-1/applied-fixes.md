# Applied Fix Plan

| Finding | Category | Plan section(s) to edit | Edit intent | Checklist impact |
|---------|----------|-------------------------|-------------|------------------|
| Missing untracked PRD dependency | substantive defect | Objective, T1, Handoff Notes | Make PRD task create-or-update and embed source decisions in plan | No new task; T1 wording changes only |
| OR-style rg checks | process defect | T1, T2, T3, Success Criteria, Validation Contract | Replace alternation checks with per-pattern loops or exact file checks | No new task; acceptance criteria sharpened |
| Missing values preflight for `just validate` | process defect | Automation Plan, Validation Contract, Handoff Notes | Add explicit values preflight and blocked/setup outcome | No new task; F2 evidence requirements sharpened |
| Public-safety default scans tracked files only | process defect | Automation Plan, V1, V2, Success Criteria, Validation Contract, Archive preflight | Add explicit planned-file list scan using `--tracked-files` | No new task; validation commands sharpened |
| Cross-repo Onramp path dependency | process defect | Automation Plan, Handoff Notes | Make cross-repo read optional and avoid raw filename/content evidence | No new task |
| Terminal/raw evidence risk | process defect | Automation Plan, Validation Contract, Telemetry & Evidence Contract, Handoff Notes | Require sanitized evidence JSONL and forbid raw `just validate` logs | No new task; F gates evidence clarified |
| Missing Execution Status | process defect | New `## Execution Status` section | Add not-started status near end | No checklist change |
| Ambiguous plan/apply prohibition | process defect | Constraints, Explicit Deferrals, Handoff Notes | Explicitly forbid `just plan`, `just apply`, OpenTofu plan/apply/import/state commands unless separately requested | No checklist change |
| Optional docs/README path referenced by commands | hardening | T3, Task Breakdown, V2 | Make `docs/README.md` mandatory navigation file | T3 file count changes; no new task |
| Duplicate PRD/contract truth | hardening | T2, Objective, Handoff Notes | State contract purpose distinct from PRD | No checklist change |
| Negative state boundaries | hardening | T2 acceptance criteria | Require exact OpenTofu/tfvars/inventory/state exclusion statement | No checklist change |
| Future provisioning gate | hardening | T2 acceptance criteria, Handoff Notes | Require future provisioning paragraph | No checklist change |
| Failed-run evidence cleanup | hardening | Validation Contract, Handoff Notes | Add cleanup rule for evidence artifacts | No checklist change |
