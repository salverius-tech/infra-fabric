## Finding 1
category: substantive defect
severity: high
severity_rationale: Fresh or new-session runs can pass known-host refresh in one container, then fail connectivity/apply in the next because trust is not persisted.
evidence: Plan runs `known-hosts` and `connectivity` in separate `scripts/run-infra.sh` invocations. `scripts/run-infra.sh` uses `docker compose run --rm`; `compose.yaml` mounts `${HOME}/.ssh` read-only; `tools/docker-entrypoint.sh` copies `known_hosts` into ephemeral `/home/anvil/.ssh`.
required_fix: Specify a persistent managed known_hosts path in `values/` or another approved local state path, wire Ansible to use it, and validate a new `run-infra` session after refresh.
confidence: high

## Finding 2
category: substantive defect
severity: high
severity_rationale: A direct-host role cannot repair SSH trust if Ansible must connect to that host before the role runs.
evidence: T2 allows `direct_access_ready` as a role included in service playbooks; T3 says include the handoff before the direct service role. With normal host-key checking, play connection/gathering can occur before role tasks, blocking fresh LXCs.
required_fix: Require the handoff to execute on `localhost`/`pve` in a prior play, with `gather_facts: false` where needed, before any direct-host play connection is attempted.
confidence: high

## Finding 3
category: process defect
severity: medium
severity_rationale: The validation gate can report success while syntax checking of the new handoff playbook is broken.
evidence: T2 acceptance criterion 4 verifies `ansible-playbook --syntax-check infra/ansible/playbooks/direct-access-ready.yml 2>/dev/null || true`, which masks all failures and missing-file errors.
required_fix: Remove `|| true`; if the handoff is role-only, replace this with a deterministic helper/policy test that fails when no valid playbook or include path exists.
confidence: high

## Finding 4
category: process defect
severity: medium
severity_rationale: The final validation contract is internally inconsistent and may skip the actual no-`pct` policy check.
evidence: The contract has two numbered item 6 entries named “Run policy checks...”; the first runs only `bootstrap-plan`, not `policy`, and duplicates earlier bootstrap validation.
required_fix: Deduplicate and renumber the contract. Keep one bootstrap/DRY check and one explicit `policy && pve-boundary` check, both required before archive.
confidence: high

## Finding 5
category: process defect
severity: medium
severity_rationale: Several documented commands may fail in fresh sessions if the new helper lacks executable permission or shebang.
evidence: The plan mixes `scripts/python.sh scripts/check-direct-service-ansible.py ...` with direct execution `scripts/check-direct-service-ansible.py ...` inside `run-infra.sh` commands.
required_fix: Either require shebang plus executable mode and test direct invocation in CI/validation, or standardize every command on `scripts/python.sh scripts/check-direct-service-ansible.py`.
confidence: medium
