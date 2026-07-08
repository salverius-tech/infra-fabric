# Terraform/OpenTofu and service-boundary review

## Finding 1
category: substantive defect
severity: high
severity_rationale: The plan can falsely certify removal of Proxmox-mediated service config while `pct` remains in argv-style tasks.
evidence: Acceptance checks use `rg -n "pct (exec|push|enter)"`; existing tasks include split argv such as `infra/ansible/roles/forgejo/tasks/main.yml` lines 289-295 with `- pct` then `- push`, which that regex does not match.
required_fix: Replace grep-only checks with YAML-aware tests that detect command argv beginning with `pct` and forbidden subcommands, with explicit allowlist for `lxc_ready`/bootstrap/recovery.
confidence: high

## Finding 2
category: substantive defect
severity: high
severity_rationale: The refactor may break fresh LXC bootstrap by requiring direct SSH before in-guest SSH/Python readiness is established.
evidence: OpenTofu LXC resources inject `user_account.keys`/password, but service roles currently perform initial package setup through `pct exec`; only Forgejo explicitly installs `openssh-server`, while several roles list `openssh-client` only.
required_fix: Add an explicit Proxmox-owned bootstrap boundary for SSH/Python/service prerequisites, or document and test the template guarantee that sshd is enabled before direct Ansible runs.
confidence: medium-high

## Finding 3
category: substantive defect
severity: high
severity_rationale: Moving the whole Forgejo Runner role to the runner host would misplace Proxmox-host mutations and weaken the lifecycle/resource boundary.
evidence: `infra/ansible/roles/forgejo_runner/tasks/main.yml` creates `/root/.ssh` and authorizes the runner key on the Proxmox host, then uses the Proxmox host key for runner trust.
required_fix: Split runner tasks: direct in-LXC runner configuration on `forgejo_runner`, but Proxmox host authorization/trust or storage-adjacent tasks in a separate `pve` play with explicit approval semantics.
confidence: high

## Finding 4
category: substantive defect
severity: medium
severity_rationale: The proposed `caddy-proxy` direct target does not exist in OpenTofu-derived inventory and could force unnecessary inventory/resource-shape changes.
evidence: `tfvars.py` defines service groups for `technitium`, `forgejo`, `forgejo_runner`, `tailscale_client`, `infisical`, `hermes`, and `onramp_host`; no `caddy_proxy` group exists. `settings.py` lists `caddy-proxy.yml` under the `technitium` service.
required_fix: Run the Caddy proxy role against the `technitium` direct group, or add a documented inventory alias without changing OpenTofu resources/state.
confidence: high

## Finding 5
category: process defect
severity: medium
severity_rationale: The connectivity gate can pass/fail for the wrong reason because it loops hard-coded groups instead of enabled services.
evidence: The matrix always pings `technitium forgejo forgejo_runner infisical hermes tailscale_client onramp_host`, but `settings.example.json` omits `tailscale_client` and dynamic inventory only emits groups for enabled services.
required_fix: Generate the ping list from `scripts/settings.py services` plus inventory graph, skip disabled services explicitly, and fail if an enabled service has zero matched hosts.
confidence: high
