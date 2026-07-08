---
reviewer: security-reviewer
status: complete
finding_count: 4
---

# Findings

- severity: medium
  category: "process defect"
  confidence: high
  evidence: "Severity rationale: new docs/evidence may be archived with private identifiers. Plan relies on `python scripts/public-safety-check.py`, but that script scans `git ls-files` only; plan says `docs/hermes-operator-pilot-prd.md` is untracked and creates `docs/onramp-app-platform-contract.md` plus possible `.specs/.../evidence/`."
  required_fix: "Add an archive gate that scans staged plus untracked planned files, or extend the command with an explicit file list covering new docs and evidence before archive."
- severity: medium
  category: "process defect"
  confidence: medium
  evidence: "Severity rationale: external context can leak local/private project metadata into `.specs` evidence. Automation Plan reads `C:/Projects/Personal/onramp-vNext/docs/prd/*.md` and records a sanitized filename list, but no command enforces sanitization and that repo is outside this public-safety boundary."
  required_fix: "Remove the cross-repo read from the MVP or require only a hand-written sanitized summary with no raw filenames/content stored in this repo. If cross-repo context is necessary, add an explicit redaction check before writing evidence."
- severity: medium
  category: "substantive defect"
  confidence: medium
  evidence: "Severity rationale: validation may expose private `values/`-derived data in archived logs. Plan allows `just validate` using local private wiring and says it must not print secrets, but evidence contract permits terminal output or `.specs/.../evidence/` records without a redacted-log capture procedure."
  required_fix: "Specify that `just validate` evidence must be limited to exit status and sanitized summary, not raw command output. Add a grep/public-safety pass over any saved evidence and require deletion/redaction before archive."
- severity: low
  category: "process defect"
  confidence: medium
  evidence: "Severity rationale: rollback is incomplete if evidence files contain sensitive material. Risk section says rollback is easy by reverting uncommitted Git diffs, but untracked `.specs/.../evidence/` files and raw terminal logs are outside normal diff review and may persist after a failed run."
  required_fix: "Add cleanup steps for failed or rejected runs: enumerate untracked evidence artifacts, review them for sensitive data, and delete or redact them before marking rollback/archive gates complete."
