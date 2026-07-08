# Ansible Implementation Review

## Finding 1
category: substantive defect
severity: high
severity_rationale: A mixed pve/localhost/direct bootstrap cannot be safely expressed as an ordinary service role without changing where tasks execute.
evidence: Plan requires `direct_access_ready` to do `lxc_ready`/bootstrap, host-key trust refresh, and direct SSH/Python/root-or-become verification, then says service playbooks should include the reusable handoff before direct roles. Those operations have three different execution hosts: `pve`, controller/infra container known_hosts, and the service host.
required_fix: Define the handoff as explicit plays or an action/helper with `delegate_to`/`run_once` semantics per step, and add tests proving each subtask executes on the intended host.
confidence: high

## Finding 2
category: substantive defect
severity: high
severity_rationale: Direct module conversion can restart services at different times or omit daemon reloads, causing stale units or unnecessary restarts.
evidence: Current roles notify handlers from drift-gated `pct push` tasks, e.g. Forgejo systemd service/app.ini/sshd config and Caddy env/Caddyfile changes notify restarts. The plan says use `template`, `copy`, `file`, and `systemd` but has no acceptance criterion preserving notify-only-on-change, daemon_reload after unit/override changes, or Caddy config validation before restart.
required_fix: Add handler/idempotence criteria per converted role: changed templates notify exactly the matching handler, unit changes trigger daemon_reload before restart, Caddy validates config, and unchanged second runs produce no restart notifications.
confidence: high

## Finding 3
category: substantive defect
severity: medium
severity_rationale: Check-mode can become theater if command-heavy tasks are merely exempted while idempotence semantics change.
evidence: T4 allows `command`/`shell` where modules are impractical and acceptance criterion 4 passes if check-mode reports “documented task-level exceptions.” Existing Forgejo Runner registration, Caddy module installation, and application CLI configuration are command-like workflows where `creates`, `changed_when`, and `check_mode: false` choices determine whether reruns restart or re-register.
required_fix: Require each check-mode exception to include its idempotence guard (`creates`/probe/changed_when), secret logging posture, and whether it can notify handlers. Add static tests for command tasks lacking explicit check-mode/idempotence behavior.
confidence: medium

## Finding 4
category: substantive defect
severity: medium
severity_rationale: File ownership may silently change when replacing `pct push` with direct `template`/`copy`, especially for app-owned configs.
evidence: The plan requires owner/group/mode checks for secret env/config files, but non-secret service files also matter: systemd units, sshd snippets, Caddyfile, app.ini-like configs, runner config, and directories currently created inside LXCs by root via `pct exec`. Direct tasks with `become: true` default to root ownership unless specified, which may differ from app expectations.
required_fix: Extend acceptance criteria/tests to require explicit owner/group/mode for all direct-managed files and directories, not only secret files, and compare them against current role intent/templates before conversion.
confidence: medium

## Finding 5
category: process defect
severity: medium
severity_rationale: The wave ordering lets broad direct-role edits proceed after one-time connectivity probes, but does not revalidate host-key/become after the handoff/playbook structure changes until late validation.
evidence: V2 proves direct access before Wave 3. T3 then changes service playbook targeting and handoff usage; T4-T6 change roles. V3 checks direct probes still pass, but individual tasks can proceed in parallel against stale assumptions about `ansible_user`, `become`, and group mapping.
required_fix: Add per-task preconditions for T3-T6 to run the helper inventory/become checks for their target groups immediately before editing/validating, or make V2 evidence an explicit input artifact consumed by each task.
confidence: medium
