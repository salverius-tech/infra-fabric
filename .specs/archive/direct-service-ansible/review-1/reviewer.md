---
reviewer: reviewer
status: complete
finding_count: 4
---

# Findings

- severity: high
  category: "substantive defect"
  confidence: high
  evidence: "Severity rationale: T3/success criteria require `hosts: caddy_proxy`, but `infra/ansible/inventory/tfvars.py` SERVICE_HOSTS has no `caddy_proxy`; `caddy-proxy.yml` configures Caddy on the Technitium LXC using `technitium_vmid`. A fresh /do-it following the plan will fail verification or invent an unsupported group."
  required_fix: "Decide the target: either run the caddy_proxy role on `hosts: technitium` (likely, because it is Technitium-local Caddy) and update all commands/tests, or explicitly add/test a `caddy_proxy` inventory alias with documented hostvars."
- severity: high
  category: "process defect"
  confidence: high
  evidence: "Severity rationale: Connectivity and syntax commands loop over `technitium forgejo forgejo_runner infisical hermes tailscale_client onramp_host` unconditionally, while `settings.py` enables only selected services and defaults to `technitium, forgejo`. The plan says disabled groups are skipped, but the shell loop does not read settings or skip absent groups."
  required_fix: "Replace hard-coded loops with services from `scripts/settings.py services` plus required dependencies/onramp handling, or provide a tested skip wrapper that treats absent disabled groups as skipped and absent enabled groups as failure."
- severity: medium
  category: "substantive defect"
  confidence: medium
  evidence: "Severity rationale: T3/success criteria assert every service playbook must contain `hosts: pve` readiness. The plan also says Caddy proxy is not a separate LXC and onramp already direct. This hard-coded assertion can force bogus Proxmox readiness plays or fail valid direct-only/service-local playbooks."
  required_fix: "Define per-playbook expected lifecycle boundary: e.g. LXC service install playbooks require `lxc_ready` on `pve`; service-local Caddy may share Technitium readiness; onramp remains direct-only. Update verification to check role placement, not blanket `hosts: pve`."
- severity: medium
  category: "substantive defect"
  confidence: medium
  evidence: "Severity rationale: The plan says convert `pct push`/staging to direct modules but does not specify how to translate existing Proxmox-local temp-file hash/idempotence patterns in roles such as `roles/forgejo/tasks/main.yml` and `roles/hermes/tasks/main.yml`. A fresh implementer may preserve shell/temp semantics incorrectly or weaken no_log/idempotence."
  required_fix: "Add an implementation pattern: use `template/copy` directly to destination with owner/mode/no_log, `notify` handlers for restarts, `command` only for validation with `changed_when:false`, and remove Proxmox `/tmp/*.{{ vmid }}` staging/hashes. Require check-mode or diff/idempotence evidence where feasible."
