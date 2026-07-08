---
reviewer: reviewer
status: complete
finding_count: 5
---

# Findings

- severity: high
  category: "substantive defect"
  confidence: high
  evidence: "Severity rationale: a fresh source-only /do-it can be impossible to complete. The Validation Contract requires live known-hosts/connectivity/become probes against values/settings.local.json, but Deployment validation says live deployment is not required for MVP archive. Fresh/new-user systems may have no LXCs until approved apply."
  required_fix: "Define execution modes. Either require existing live services for archive, or add a no-live/fresh-source validation path that proves bootstrap sequencing statically and defers live probes until approved deployment."
- severity: medium
  category: "process defect"
  confidence: high
  evidence: "Severity rationale: a required check can never fail. T2 AC4 verify command ends with `ansible-playbook --syntax-check infra/ansible/playbooks/direct-access-ready.yml 2>/dev/null || true`, so missing/broken playbook syntax is masked while the pass criterion claims syntax/test coverage."
  required_fix: "Remove `|| true` and stderr suppression, or split role-included vs standalone implementations into explicit alternative checks with real failure conditions."
- severity: medium
  category: "process defect"
  confidence: high
  evidence: "Severity rationale: final validation instructions are ambiguous. Required automated validation has duplicate item `6`; the first is titled policy checks but runs only `bootstrap-plan`, then another item 6 runs real policy/pve-boundary checks."
  required_fix: "Renumber the validation contract and remove the duplicate/mis-titled policy item, or fold bootstrap-plan into the fresh-setup check so each final gate has one unambiguous command."
- severity: medium
  category: "process defect"
  confidence: medium
  evidence: "Severity rationale: parallel /do-it workers can collide. Wave 3 marks T3-T6 parallel after V2, but T3 edits playbooks/site/tests while T4-T6 edit related roles/playbooks/tests and depend on the helper’s policy shape. No merge ownership or ordering is specified."
  required_fix: "Add sequencing or file ownership rules for Wave 3: e.g. T3 playbook skeleton first, then role cohorts in parallel, then one integrator updates shared tests/site orchestration."
- severity: low
  category: "substantive defect"
  confidence: medium
  evidence: "Severity rationale: redaction verification can fail on allowed public placeholders or miss other private values. T8 checks for `192\\.168\\.|ilude|\\.internal|\\.local`; the repo explicitly allows examples like `example.internal`, while real private domains may not match these strings."
  required_fix: "Replace hard-coded redaction grep with public-safety-check plus helper tests seeded with representative private fixtures and allowlisted documentation placeholders such as `example.internal`."
