- category: process defect
  severity: medium
  severity_rationale: Ambiguous plan/apply exclusions can cause provider/backend contact and plan artifact churn in a docs-only MVP.
  evidence: The plan says “Running `just plan` or `just apply` for new infrastructure” is deferred, but later normalizes `just validate` only and says no provisioning is in scope. The qualifier “for new infrastructure” leaves room for an executor to run `just plan` anyway for documentation changes.
  required_fix: State explicitly that this MVP must not run `just plan`, `just apply`, OpenTofu plan/apply, imports, or state commands unless the user gives a separate explicit request.
  confidence: high
- category: substantive defect
  severity: medium
  severity_rationale: The ownership contract can still permit state drift because prohibited state boundaries are not required as acceptance criteria.
  evidence: T2 requires generic sections for “State” and “Approval” and only verifies regex terms plus “not managed through OpenTofu by default.” It does not require saying Onramp containers, Compose services, ports, and app secrets must not be added to OpenTofu state, Ansible inventory, or tfvars.
  required_fix: Add acceptance criteria requiring explicit negative boundaries: only the onramp-host substrate belongs in homelab-infra state; Onramp app services remain out of OpenTofu/Ansible inventory/tfvars unless promoted by a separate approved infra plan.
  confidence: high
- category: process defect
  severity: low
  severity_rationale: Future VM/LXC work is deferred, but the follow-up approval gate is underspecified for a plan meant to prevent accidental infra mutation.
  evidence: The plan selects “Provision an Onramp onramp host with `homelab-infra`” and recommends a Debian 13 VM, while deferring provisioning. It does not require the docs to say future VM/LXC creation needs a new infrastructure plan, reviewed `just plan`, and explicit apply approval.
  required_fix: Require the contract or PRD to include a “future provisioning gate” paragraph covering separate plan, OpenTofu diff review, no apply without explicit approval, and Podman-in-LXC as experimental only.
  confidence: medium
