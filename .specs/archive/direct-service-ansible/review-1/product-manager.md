# Product Manager Review

## Finding 1
category: substantive defect
severity: high
severity_rationale: The plan cannot pass as written because it requires a non-existent direct target for Caddy proxy.
evidence: `infra/ansible/inventory/tfvars.py` defines service groups for technitium, forgejo, forgejo_runner, tailscale_client, infisical, hermes, and onramp_host, but not `caddy_proxy`. `scripts/settings.py` nests `caddy-proxy.yml` under the `technitium` service. The plan’s T3 and Success Criteria require `infra/ansible/playbooks/caddy-proxy.yml` to contain `hosts: caddy_proxy`.
required_fix: Treat Caddy proxy as Technitium/DNS LXC configuration (`hosts: technitium`) or add a justified `caddy_proxy` inventory alias before requiring it.
confidence: high

## Finding 2
category: process defect
severity: high
severity_rationale: The repeated connectivity command does not implement the plan’s enabled-service semantics and can fail or produce misleading results for disabled services.
evidence: T1, Success Criteria, and Validation Contract loop over `technitium forgejo forgejo_runner infisical hermes tailscale_client onramp_host` unconditionally. `scripts/settings.py` defaults only to `technitium` and `forgejo`; dynamic inventory only emits groups for enabled services.
required_fix: Replace hard-coded loops with a helper/wrapper that reads `scripts/settings.py services`, expands dependencies, maps service names to inventory groups, and intentionally skips disabled services with explicit non-secret output.
confidence: high

## Finding 3
category: substantive defect
severity: medium
severity_rationale: The plan mandates a readiness `hosts: pve` play for every service, even where that may be the wrong boundary or unsupported by inventory.
evidence: T3 and Success Criteria assert `assert 'hosts: pve' in text` for every listed service playbook, including `caddy-proxy.yml` and `tailscale-client.yml`. The stated objective says Proxmox readiness plays are needed “where needed,” not universally.
required_fix: Define which playbooks actually need Proxmox lifecycle readiness and make acceptance criteria per-service. Do not require `hosts: pve` for configuration-only or disabled/unsupported playbooks.
confidence: medium

## Finding 4
category: low-value/theater
severity: medium
severity_rationale: Several acceptance checks are brittle text searches that can pass on comments or fail on valid YAML structure, giving false confidence for a high-risk Ansible refactor.
evidence: T3/Succcess Criteria use raw string assertions for `hosts: pve` and `hosts: {group}`. Docs validation greps broad phrases. Forbidden `pct` checks use regex only, without distinguishing comments, recovery tasks, or generated examples.
required_fix: Parse playbooks as YAML in tests, assert play host targets and role placement structurally, and maintain an explicit allowlist for lifecycle/recovery `pct` usage.
confidence: medium

## Finding 5
category: process defect
severity: medium
severity_rationale: The plan duplicates long, credential-sensitive validation one-liners across multiple sections, increasing drift and operator error instead of simplifying execution.
evidence: The direct connectivity matrix and Ansible syntax-check loop appear in Automation Plan, T1, V2, V3, Success Criteria, and Validation Contract with hard-coded services/playbooks.
required_fix: Add one tracked validation helper, e.g. `scripts/check-direct-service-ansible.py` or a narrow internal script invoked by `just validate`, that runs the matrix and syntax checks from settings-derived service lists.
confidence: high
