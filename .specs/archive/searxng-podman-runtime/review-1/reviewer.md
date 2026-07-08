---
reviewer: completeness-explicitness-reviewer
status: complete
finding_count: 5
---

# Findings

- severity: high
  category: "substantive defect"
  confidence: high
  evidence: "severity_rationale: A fresh /do-it can produce unprovisionable or provider-invalid HCL. Plan lines 75 and 207 say verify provider/resource shape before HCL, but never require an explicit Debian 13 VM image/template/clone prerequisite or variable contract. Current repo evidence shows only LXC resources/templates, no VM pattern."
  required_fix: "Add a concrete VM provisioning contract: provider resource version/schema source, Debian 13 image/template/clone prerequisite, required tfvars keys, cloud-init method, and an acceptance check proving the chosen resource validates."
- severity: medium
  category: "process defect"
  confidence: high
  evidence: "severity_rationale: Required validation can fail for an artifact the plan never creates. Lines 255 and 340 run public-safety-check with .specs/searxng-podman-runtime/evidence/public-safety-files.txt, but no task creates or populates that file."
  required_fix: "Add a task/acceptance criterion to generate public-safety-files.txt from all touched tracked plus planned untracked files before V1/final validation, or remove the --tracked-files command."
- severity: medium
  category: "process defect"
  confidence: high
  evidence: "severity_rationale: The no-SearXNG-runtime check is non-enforcing. Line 281 uses `! rg -n 'searxng|searx' ... || true`; with `|| true`, the verification exits success even when forbidden runtime references exist."
  required_fix: "Replace with a failing check, e.g. `if rg -n 'searxng|searx' infra/ansible/roles/onramp_host infra/opentofu; then exit 1; fi`, with documented allowed docs-only paths."
- severity: medium
  category: "substantive defect"
  confidence: medium
  evidence: "severity_rationale: The plan introduces a Hermes env var but does not require wiring Hermes to consume it. Lines 104, 308-330 allow docs/scaffold-only `HERMES_WEB_SEARXNG_URL`; out of scope excludes plugin implementation, but acceptance says Hermes has a contract, not that existing Hermes deployment passes the variable through."
  required_fix: "State whether this slice must update Hermes Ansible/runtime env templating. If yes, add files/checks. If no, rename success criteria to docs-only contract and add a follow-up prerequisite for Hermes runtime consumption."
- severity: medium
  category: "process defect"
  confidence: high
  evidence: "severity_rationale: Several pass criteria are grep-only and can pass on comments or docs. Lines 233, 235, 277, 298, and 309 mostly check strings, not parsed settings/HCL/Ansible behavior. This is weak for a fresh execution that adds infra resources."
  required_fix: "Add behavioral checks: settings unit test for onramp_host, tofu fmt/validate on actual variables, ansible-playbook --syntax-check for onramp-host.yml, ansible-lint, and a docs link check or explicit file inspection requirements."
