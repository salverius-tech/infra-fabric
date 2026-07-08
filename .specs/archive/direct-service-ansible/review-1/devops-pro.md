## Finding 1
category: substantive defect
severity: high
severity_rationale: The plan’s required verification cannot pass for the Caddy proxy as written, blocking implementation or encouraging an invented inventory group.
evidence: Plan T3/Success Criteria assert `hosts: caddy_proxy`. `infra/ansible/inventory/tfvars.py` `SERVICE_HOSTS` has no `caddy_proxy`; `settings.py` wires `caddy-proxy.yml` under the `technitium` service, and current role tasks use `technitium_vmid`.
required_fix: Decide whether Caddy proxy is a Technitium-hosted role (`hosts: technitium`) or a first-class service; update inventory, settings, playbook assertions, and validation commands consistently.
confidence: high

## Finding 2
category: substantive defect
severity: medium
severity_rationale: The direct connectivity matrix is not operationally realistic for disabled services and may fail or produce misleading “skipped” claims.
evidence: The plan hard-codes `for g in technitium forgejo forgejo_runner infisical hermes tailscale_client onramp_host`, while `settings.py` defaults to only `technitium` and `forgejo`; `tfvars.py` only emits groups for enabled services.
required_fix: Generate the ping target list from `scripts/settings.py services` or inventory children, and explicitly skip disabled groups with logged non-secret evidence.
confidence: high

## Finding 3
category: substantive defect
severity: high
severity_rationale: If a service is reachable via Proxmox but not direct SSH, the plan only blocks, leaving no safe migration or recovery path for a likely current-state failure mode.
evidence: T1 says “Do not use Proxmox fallback as success” and “mark plan blocked”; deferrals exclude creating users, but current roles configure through `pct`, so direct SSH may not already exist everywhere.
required_fix: Add a gated bootstrap/recovery decision tree: diagnose DNS/SSH/user/firewall, optionally run an explicitly approved Proxmox lifecycle bootstrap to enable direct SSH, or exclude/narrow the service before Wave 2.
confidence: medium

## Finding 4
category: process defect
severity: medium
severity_rationale: Static tests and syntax checks can pass while converted roles fail at runtime due permissions, paths, handlers, package state, or service manager behavior.
evidence: Wave 2 validation requires unit tests, greps, syntax checks, and ping, but no per-service non-mutating role execution such as `ansible-playbook --check --diff --limit <service>` or targeted dry-run after conversion.
required_fix: Add per-service check-mode/diff validation where modules support it, document tasks that cannot check-mode, and require a focused direct playbook dry run before repo-wide validation.
confidence: high

## Finding 5
category: substantive defect
severity: medium
severity_rationale: Live rollout recovery is under-specified for a multi-service migration; Git revert does not undo partially applied config files or service restarts.
evidence: Rollback only lists `git restore`/`git revert`; deployment section jumps from `just plan` to `just apply` for all services, with no serial rollout, backups, health checks, or per-service rollback commands.
required_fix: Define approved live rollout as serial per service with pre-change backups, restart boundaries, post-service health checks/log checks, and explicit rollback steps for changed env files, Caddyfiles, systemd units, and runner registration.
confidence: high
