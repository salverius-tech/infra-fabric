## Finding 1
category: substantive defect
severity: high
severity_rationale: The plan requires a direct `caddy_proxy` target that the dynamic inventory cannot produce, so Wave 2 and success criteria fail or encourage a fake inventory group.
evidence: `plan.md` T3/success criteria map `caddy-proxy` to `hosts: caddy_proxy`; `infra/ansible/inventory/tfvars.py` `SERVICE_HOSTS` has `technitium`, `forgejo`, `forgejo_runner`, `tailscale_client`, `infisical`, `hermes`, `onramp_host`, but no `caddy_proxy`. `scripts/settings.py` also has no `caddy_proxy` service.
required_fix: Change caddy-proxy verification/playbook target to the actual service host group (`technitium`) or explicitly add and test a real `caddy_proxy` inventory source.
confidence: high

## Finding 2
category: substantive defect
severity: medium
severity_rationale: Connectivity checks can pass without testing the services actually enabled in private settings, leaving the central direct-access assumption unverified.
evidence: T1 and success criteria hardcode `for g in technitium forgejo forgejo_runner infisical hermes tailscale_client onramp_host`; Ansible unmatched/empty groups can be skipped, while the plan says disabled groups are “skipped intentionally” without deriving the enabled list from `settings.local.json`.
required_fix: Generate the group list from `scripts/settings.py services` inside the same container/settings context, then assert each enabled group has at least one host before running `ansible -m ping`.
confidence: high

## Finding 3
category: process defect
severity: medium
severity_rationale: Several required checks may run on the Windows/Git Bash host instead of the repo’s Docker Python, causing false failures or false passes unrelated to implementation.
evidence: T3, T6, and success criteria use bare `python - <<'PY'`; project workflow and the plan’s own focused commands use `scripts/python.sh`/`scripts/run-infra.sh` for portability under Git Bash/Docker.
required_fix: Replace bare inline Python with `scripts/python.sh - <<'PY'` or a committed unittest invoked through `scripts/python.sh -m unittest`.
confidence: high

## Finding 4
category: substantive defect
severity: medium
severity_rationale: The test plan asks to keep Proxmox-specific assertions intact while removing Proxmox-mediated execution, making the tests either block the refactor or preserve stale task names.
evidence: T2 says existing safety tests remain intact; current `tests/test_ansible_safety.py` asserts task names such as `Stage Forgejo runner config on Proxmox host`, `Push Forgejo runner config into LXC`, and checks those exact blocks for `no_log`.
required_fix: Add an explicit task to rewrite these tests around semantic guarantees (secret-protected runner config/registration, no forbidden `pct`) rather than exact Proxmox task names.
confidence: high
