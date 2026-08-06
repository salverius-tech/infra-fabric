# Super Simple Software Factory service

SSSF is a stateful software-factory runtime installed on one dedicated Debian VM per canonical site. It is not an always-on infrastructure controller: it stamps an approved target repository with the upstream `.claude/skills/sssf` skill and runs named ADW workflows as the non-root `sssf` user.

The public repository pins the reviewed upstream source at:

```text
https://github.com/disler/super-simple-software-factory
commit de31374882e7a4e3e5b7bb9bd09e69dc2f779356
```

## Boundaries

- OpenTofu owns the VM, root disk, and separate durable data disk.
- Ansible owns packages, the non-root runtime user, the pinned checkout, config,
  workspace helper, health command, and optional visualizer unit.
- Provider keys and repository-access tokens are protected runtime values. They
  are never placed in canonical non-secret projections or command arguments.
- The repository allow-list is canonical configuration. `sssf-init` refuses any
  repository not listed for the selected site.
- Agent workflows can execute shell commands and modify authorized workspaces.
  They must not receive infrastructure apply credentials or unrestricted host
  filesystem access.
- The visualizer is disabled by default and binds only to loopback when enabled.
  Do not publish it through Caddy without an approved authentication and private
  network boundary.

## Operator workflow

After a selected site has been validated, planned, and explicitly approved for
apply, connect directly to the service VM using the generated inventory and the
canonical non-root access path:

```bash
ansible sssf -m ping
ansible sssf -b -m command -a /usr/local/bin/sssf-health
ansible sssf -b -m command -a "/usr/local/bin/sssf-init https://git.example.internal/example/project.git"
```

The last command creates an isolated workspace below `/srv/sssf/workspaces/`.
Run the upstream installer from that workspace root as `sssf` when the target
repository is ready for SSSF stamping. Do not run it as root and do not run it
against the infrastructure or private-values repository unless that repository
has been explicitly approved and allow-listed.

The runtime trace database and raw session files live under `/var/lib/sssf/`.
The workspace root is `/srv/sssf/workspaces/`. Both are private service state.

## Visualizer and stuck runs

The optional `sssf-visualizer` systemd unit serves the upstream Bun/Vite
visualizer on the configured loopback host and port. Inspect it without
exposing credentials:

```bash
systemctl status sssf-visualizer
journalctl -u sssf-visualizer --since -1h
ss -ltnp | grep 4600
```

Stop a stuck workflow from the target workspace using the upstream documented
workflow controls. Do not kill arbitrary processes from the Proxmox host or use
`pct`/host-boundary commands for steady-state service configuration.

## Updates and rollback

Update SSSF only by changing the canonical `services.sssf.release.commit` to a
reviewed upstream commit and running the normal `just update` → `just validate`
→ `just plan` workflow for each site independently. The role checks out the
exact commit and fails if the guest revision differs. Back up state before
replacing the VM or changing the data layout. Revert the canonical commit and
rerun the non-mutating plan for rollback review.

## Reviewed runtime artifact cache

The controller must retain reviewed Pi and Bun archives outside both repositories at
`/var/lib/infra-fabric/artifacts/sssf/`. The role requires the versioned `uv`, `pi`,
and `bun` archives from that cache and verifies their repository-tracked SHA-256
before extraction. Do not replace this cache with a guest-side installer, a mutable
release URL, or an artifact in the canonical/private values repository.

Populate the cache only after separately reviewing the release, archive layout, and
checksum. Cache paths are `tool/version/filename`, for example
`pi/0.83.0/pi-linux-x64.tar.gz`. Preserve previous reviewed versions for rollback;
changing a pin remains a public-source review followed by validation, planning, and
an explicitly approved apply.

## State backup and restore

Use the managed service-state workflow:

```bash
scripts/service-state.sh backup sssf
scripts/service-state.sh restore-if-present sssf
scripts/service-state.sh restore sssf values/service-backups/sssf/sssf-state-<timestamp>.tar.gz
```

Archives include the pinned checkout, factory configuration, SQLite traces,
raw sessions, and approved workspaces. Treat them as sensitive private state:
raw prompts and model output may contain proprietary source. Verify capacity,
checksum, and manifest before restore; a failed preflight must not stop the
service or remove current state.

## Safety gates

The SSSF VM does not receive OpenTofu credentials, Proxmox credentials, or
private-values decryption identities. Applying infrastructure remains an
external, separately approved operation. Development and production have
independent VM values, repository allow-lists, and provider credentials.
