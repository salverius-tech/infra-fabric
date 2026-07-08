I inspected `.specs/direct-service-ansible/plan.md`, `scripts/settings.py`, `tests/test_settings.py`, `tests/test_service_registry_parity.py`, and `tests/test_ansible_safety.py`. No files modified.

## Current repo facts

- `scripts/settings.py` already has the service registry and playbook mapping:
  - `technitium` includes `technitium.yml`, `caddy-proxy.yml`, `technitium-dns.yml`
  - all service playbooks exist per `tests/test_service_registry_parity.py`
- `infra/ansible/inventory/tfvars.py` already has service → inventory group mapping via `SERVICE_HOSTS`.
- `caddy-proxy.yml` is currently registered under `technitium` service but still runs on `pve`; the helper should map it to the `technitium` group for the future direct-service structure.
- `tests/test_ansible_safety.py` still has stale Forgejo runner task-name assertions like “Stage ... on Proxmox host” / “Push ... into LXC”; those should be replaced with semantic assertions.

## Minimal implementation proposal

### 1. Add `scripts/check-direct-service-ansible.py`

Keep it source/static-first. Do not read or print private inventory hostvars by default.

Core behavior:

- Import `scripts/settings.py` for enabled services and playbooks.
- Import `infra/ansible/inventory/tfvars.py` only for public service group metadata, especially `SERVICE_HOSTS`.
- Build a registry:

```python
service -> playbooks -> expected target group
```

Special cases:

- `infra/ansible/playbooks/caddy-proxy.yml` → `technitium`
- `infra/ansible/playbooks/technitium-dns.yml` → `localhost`
- `onramp-host.yml` → `onramp_host`
- disabled services should be emitted as explicit `skipped`.

Suggested subcommands for source-only contract:

- `inventory`
  - Shows enabled/disabled service names, group names, playbook names.
  - Never prints hostnames, IPs, users, tokens, raw inventory.
- `execution-mode`
  - With `settings.example.json`, report `source-only`.
- `bootstrap-plan`
  - Prints sanitized ordered phases:
    - `lxc_ready`
    - `direct_access_ready`
    - `known_hosts`
    - `direct_ssh_python_probe`
    - `direct_service_role`
- `playbooks`
  - YAML-aware parse of playbooks.
  - Fails if a service role runs on `pve` outside allowlisted lifecycle/bootstrap roles.
  - Should initially fail against current playbooks until the Ansible conversion lands.
- `policy`
  - YAML-aware forbidden `pct` detector for roles/playbooks.
  - Detect both string commands and argv-list forms.
- `pve-boundary`
  - Allows `lxc_ready`, storage prep, direct-access bootstrap/recovery only.
- `structure`
  - Checks `direct-access-ready.yml` exists when `--check handoff`.
  - Checks shared primitives only by objective file/path presence, not subjective “DRY” scoring.
- `syntax --fixture-public`
  - Runs or prepares `ansible-playbook --syntax-check` against committed public fixture inventory/settings.
- `check-mode --fixture-public`
  - Static check-mode safety scan only: command/shell tasks must have `changed_when`, `creates`, `removes`, or an explicit documented exemption.

Exit codes:

- `0`: all required checks pass.
- `1`: validation failure.
- `2`: bad input/settings/parse error.
- `3`: redaction/public-safety breach.
- `4`: live-only check requested without required live inputs.

Redaction:

- All emitted evidence should pass a final public-safety scanner.
- Allow placeholders: `example.internal`, `git.example.internal`, `apps.example.net`, RFC 5737 IPs.
- Block common private leakage patterns: RFC1918 IPs, raw SSH keys, tokens, bearer strings, `values/` raw hostvars, non-example domains.

### 2. Add focused tests

#### New file: `tests/test_direct_service_ansible.py`

Cover helper internals without live infra:

- Derives enabled services from `settings.example.json`.
- Includes disabled service skips.
- Maps `caddy-proxy.yml` to `technitium`.
- Maps `technitium-dns.yml` to `localhost`.
- Fails unknown/missing target groups.
- Redaction blocks fake private values but permits documented examples.
- Subcommands return nonzero for parse errors and redaction breaches.
- `--help` exits `0`.

#### Update: `tests/test_service_registry_parity.py`

Add parity checks:

- Every `settings.SERVICES[*]["playbooks"]` path has an expected source-only target group.
- Every service in `settings.SERVICES` exists in `tfvars_inventory.SERVICE_HOSTS`.
- Special-case playbook mappings are explicit and tested.

#### Update: `tests/test_ansible_safety.py`

Minimal safe change:

- Replace regex-only/stale task-name assertions with YAML-aware parsing.
- Remove dependence on stale Forgejo runner task names that encode Proxmox staging.
- Add forbidden steady-state `pct` checks for:
  - `ansible.builtin.command`
  - `ansible.builtin.shell`
  - `command`
  - `shell`
  - `argv` list forms
- Allowlist only:
  - `infra/ansible/roles/lxc_ready/**`
  - future `infra/ansible/playbooks/direct-access-ready.yml`
  - future `infra/ansible/roles/direct_access_ready/**`
  - storage/pve-boundary files if explicitly named.

### 3. Optional public fixtures

Add only if needed for source-only syntax/check-mode commands:

- `tests/fixtures/direct-service-ansible/inventory.yml`
- `tests/fixtures/direct-service-ansible/settings.json`

Keep fixtures sanitized with `example.internal` and RFC 5737 addresses only.

## Validation commands

After implementation:

```bash
scripts/python.sh -m unittest \
  tests.test_settings \
  tests.test_service_registry_parity \
  tests.test_ansible_safety \
  tests.test_direct_service_ansible
```

```bash
scripts/python.sh scripts/check-direct-service-ansible.py --help
scripts/python.sh scripts/check-direct-service-ansible.py execution-mode --settings settings.example.json --redacted
scripts/python.sh scripts/check-direct-service-ansible.py inventory --settings settings.example.json --redacted
scripts/python.sh scripts/check-direct-service-ansible.py bootstrap-plan --settings settings.example.json --redacted
scripts/python.sh scripts/check-direct-service-ansible.py policy --settings settings.example.json --redacted
scripts/python.sh scripts/check-direct-service-ansible.py pve-boundary --settings settings.example.json --redacted
scripts/python.sh scripts/check-direct-service-ansible.py structure --settings settings.example.json --check handoff --redacted
```

Full repo gate after source changes:

```bash
just validate
```