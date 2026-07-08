---
reviewer: security-reviewer
status: complete
finding_count: 5
---

# Findings

- severity: high
  category: "substantive defect"
  confidence: high
  evidence: "severity_rationale: high because the new onramp host becomes an SSH deployment target for a sibling repo. Plan only says \"SSH public keys and root/user access consistent with existing bootstrap patterns\" and Podman readiness checks; it has no acceptance criteria for non-root deploy user, root login, password auth, sudo scope, or authorized-key ownership."
  required_fix: "Add explicit SSH/user hardening requirements and validation: dedicated non-root deploy user from private values, password auth disabled, root SSH disabled or justified, locked sudoers scope, authorized_keys permissions, and Ansible checks that fail unsafe defaults."
- severity: high
  category: "substantive defect"
  confidence: high
  evidence: "severity_rationale: high because this creates a network-facing app substrate. Plan delegates Caddy/reverse-proxy ownership to Onramp and only checks Podman installation; it never defines default host firewall policy, allowed ingress, source ranges, or host-published-port constraints for app services."
  required_fix: "Add a network exposure contract: default deny inbound on the VM, explicit allowed SSH/reverse-proxy ports and source CIDRs, no host-published service ports except approved proxy bindings, plus validation inspecting firewall rules and Onramp handoff wording."
- severity: medium
  category: "process defect"
  confidence: high
  evidence: "severity_rationale: medium because archive gates can miss public-safety leaks. V1 references `python scripts/public-safety-check.py --tracked-files .specs/.../public-safety-files.txt`, but the plan never requires generating that file or including planned untracked docs/spec/evidence files before scans."
  required_fix: "Add a required step to generate and review the file list from `git diff --name-only` plus untracked planned files, include new docs/scaffold/spec artifacts, and fail archive if the list is absent, stale, or excludes touched tracked/untracked files."
- severity: medium
  category: "substantive defect"
  confidence: medium
  evidence: "severity_rationale: medium because future live apply can create persistent Proxmox resources with unclear recovery. The plan says source rollback is Git revert and future apply rollback must follow a reviewed plan, but acceptance/archive gates do not require documenting VM destroy/disable/state/import recovery paths."
  required_fix: "Before archive, require a public-safe rollback/runbook section for onramp_host: how to disable service selection, expected plan effects, VM deletion/retention decision points, state/import precautions, DNS cleanup ownership, and no state surgery without explicit approval."
- severity: medium
  category: "substantive defect"
  confidence: medium
  evidence: "severity_rationale: medium because the VM OS/template path is underspecified. The plan demands a Debian 13 VM and says verify provider docs, but acceptance criteria do not require an approved image/template source, checksum/signature, cloud-init prerequisite, or failure mode if Debian 13 image support is unavailable."
  required_fix: "Add acceptance criteria for image provenance and bootstrapping: public-safe variables for template/image ID, documented creation prerequisite, checksum/signature or trusted local template evidence, cloud-init support validation, and a stop/update-plan gate if Debian 13 VM provisioning is not supported."
