# QA Engineer Review

## Finding 1
category: substantive defect
severity: high
severity_rationale: Acceptance can pass while Proxmox still performs service configuration.
evidence: T3/Success Criteria only assert each playbook contains both `hosts: pve` and `hosts: <service>`. A playbook with a direct no-op play plus a full service role under `hosts: pve` passes. No criterion parses YAML to prove pve plays are limited to `lxc_ready`/storage prep.
required_fix: Add a YAML-aware guardrail: pve plays in service playbooks may include only allowlisted lifecycle roles/tasks; service roles must execute only in direct service plays.
confidence: high

## Finding 2
category: false positive
severity: high
severity_rationale: Tests mostly prove text absence/syntax, not that converted roles still configure services correctly.
evidence: Role criteria rely on `rg "pct (exec|push|enter)"`, `ansible-playbook --syntax-check`, and existing safety unit tests. A broken conversion that omits file deployment, handlers, ownership, or restart behavior can satisfy these checks.
required_fix: Add behavior-oriented verification for critical role effects, e.g. check-mode/diff or targeted assertions that required templates/files/services/handlers exist per role, plus idempotence checks where safe.
confidence: high

## Finding 3
category: substantive defect
severity: medium
severity_rationale: Disabled services can either block validation or be silently treated as success.
evidence: Connectivity commands loop hardcoded groups `technitium forgejo forgejo_runner infisical hermes tailscale_client onramp_host`, while the plan says disabled groups must be skipped. `tfvars.py` only renders groups from enabled `settings.services`.
required_fix: Generate the validation matrix from `scripts/settings.py services`/dynamic inventory, fail on no matched hosts for enabled services, and record explicit skipped-disabled evidence.
confidence: high

## Finding 4
category: process defect
severity: medium
severity_rationale: Evidence gates conflict with the repo’s public-safety requirement.
evidence: T1 asks to archive `ansible-inventory --graph` and ping summaries; those can include private hostnames/IPs from `values/terraform.tfvars`. The telemetry contract says not to record private IPs/domains but gives no redaction command or required sanitized artifact format.
required_fix: Require a redacted evidence helper or structured summary containing service group names/status only, with no hostnames, IPs, domains, or inventory dumps.
confidence: medium

## Finding 5
category: process defect
severity: medium
severity_rationale: Existing tests may force stale Proxmox-shaped task names or fail after correct direct conversion.
evidence: `tests/test_ansible_safety.py` currently asserts task names like “Stage Forgejo runner config on Proxmox host” and “Push Forgejo runner config into LXC”. T5 says converted direct runner registration must pass this suite, but the plan does not require updating these assertions to direct-service semantics.
required_fix: In T2/T5, explicitly update safety tests to assert secret/idempotence behavior independent of Proxmox task names and remove stale Proxmox wording.
confidence: high
