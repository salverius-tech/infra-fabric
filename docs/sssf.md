# Super Simple Software Factory service

The SSSF VM explicitly selects the portable `x86-64-v3` virtual CPU baseline so
the pinned Pi runtime can use AVX/AVX2 instructions. Other canonical VMs retain
the compatibility default `x86-64-v2-AES` when `compute.cpu_type` is omitted;
physical-host passthrough (`host`) is not an allowed canonical value.

SSSF is a stateful software-factory runtime installed on one dedicated Debian VM
per canonical site. It is not an always-on infrastructure controller: it stamps
an approved target repository with the upstream `.claude/skills/sssf` skill and
runs named ADW workflows as the non-root `sssf` user.

The public repository pins the reviewed upstream source at:

```text
https://github.com/disler/super-simple-software-factory
commit de31374882e7a4e3e5b7bb9bd09e69dc2f779356
```

## Ownership and non-fork boundary

Pinned upstream artifacts remain unmodified. This includes upstream `install.py`,
ADWs, ADW modules, prompts, the `.claude/skills/sssf/` skill, and the visualizer
source. Infra-fabric does not patch, fork, or copy local changes back into those
artifacts.

Infra-fabric owns the dedicated VM and disks, verification of the reviewed
upstream and runtime-tool pins, the `sssf` runtime user and filesystem layout,
protected-value delivery, the systemd wrapper, workspace confinement,
site-specific supported-roster configuration, health checks, and state backup
and restore. It may supply a site configuration beside an initialized workspace;
that configuration is not a modification of upstream source.

The upstream `install.py` contract is run from a target repository root; its
installer-produced layout includes `.claude/skills/sssf/` and `adws/`, with
upstream starter data below that target workspace. Infra-fabric's managed roster
redirects runtime traces and sessions to `/var/lib/sssf/factory/adw_data/`. The roster path is
`adws/adw_sssf_config/sssf.config.yaml` (the workspace's `sssf.config.yaml`). The managed source template is
`/etc/sssf/sssf.config.yaml`; after the ordinary non-`--force` upstream install,
`sssf-init` deliberately replaces only that roster and links the workspace's
gitignored `.env` to the protected managed environment. Existing upstream-stamped
ADWs, modules, prompts, and recipes are not force-overwritten. `sssf-init` is not
permission to hand-create a parallel layout or edit the pinned skill as a site
override.

## Boundaries

- OpenTofu owns the VM, root disk, and separate durable data disk.
- Ansible owns packages, the non-root runtime user, pin verification, the pinned
  checkout, runtime configuration, secret delivery, workspace helper, health
  command, and optional visualizer systemd wrapper.
- Provider keys and repository-access tokens are protected runtime values. They
  are never placed in canonical non-secret projections or command arguments.
- The repository allow-list is canonical configuration. `sssf-init` refuses any
  repository not listed for the selected site.
- A site selects a **single provider** for its supported roster. Only that
  provider's logical secret path is required and delivered; inactive provider
  credentials must not be fabricated or delivered merely because upstream can
  support them.
- Agent workflows can execute shell commands and modify authorized workspaces.
  They must not receive infrastructure apply credentials or unrestricted host
  filesystem access.
- The visualizer is disabled by default and binds only to loopback when enabled.
  Do not publish it through Caddy without an approved authentication and private
  network boundary.

## Operator workflow and workspace confinement

After a selected site has been validated, planned, and explicitly approved for
apply, use the canonical service workflow to establish access and collect
service-health evidence. Raw `ansible` or `ansible-playbook` commands without
the selected site's verified generated inventory, generated variables, and SSH
trust transport are unsupported; they must not use an ambient inventory.

For an approved target repository, run the exact safe form below as the non-root
`sssf` user through that same selected-site access transport:

```bash
/usr/local/bin/sssf-init https://host/org/repo
```

Use the exact allow-listed repository URL (with or without its `.git` suffix).
Do not run `sssf-init` as root and do not use it for the infrastructure or
private-values repository unless that repository has been explicitly approved
and allow-listed. Operators must not supply the optional workspace argument:
the managed default derives the workspace name from the allow-listed repository
and places it below `/srv/sssf/workspaces/`. This preserves the wrapper's
workspace confinement instead of accepting an arbitrary path.

The runtime trace database and raw session files live under `/var/lib/sssf/`.
The workspace root is `/srv/sssf/workspaces/`. Both are private service state.

## Visualizer and stuck runs

The optional `sssf-visualizer` systemd unit owns only the upstream visualizer
wrapper; it does not alter visualizer source. The production contract is a
built UI served by Bun in server mode: build the upstream visualizer with its
pinned lockfile, then run `bun run server/index.ts` with the managed trace DB and
port. The unit applies a localhost-only systemd network policy because the
upstream server exposes no host-binding setting. Development-server mode is not
the supported production service mode.

Inspect it without exposing credentials:

```bash
systemctl status sssf-visualizer
journalctl -u sssf-visualizer --since -1h
ss -ltnp | grep 4600
```

Stop a stuck workflow from the target workspace using the upstream documented
workflow controls. Do not kill arbitrary processes from the Proxmox host or use
`pct`/host-boundary commands for steady-state service configuration.

## Future pin-update compatibility workflow

A future pin-update compatibility workflow is required before changing
`services.sssf.release.commit`: review the candidate upstream commit and its
installer/layout, ADWs, modules, prompts, roster/config schema, and visualizer
build/start contract; update only the canonical pin and any infra-fabric wrapper
or configuration adapter required by that reviewed contract; then run the normal
`VALUES_SITE=<site> just update` → `VALUES_SITE=<site> just validate` →
`VALUES_SITE=<site> just plan` sequence. Review the resulting plan and obtain
separate approval before apply. Preserve the prior reviewed pin and runtime
artifacts for rollback. Never solve a compatibility break by modifying the
pinned upstream checkout.

The compatibility check must run the candidate installer in a temporary public
fixture and validate its produced layout, managed roster, ADW imports, and
visualizer build/server contract. Updating a pin does not automatically run the
installer with `--force` in existing workspaces: upstream documents that `--force`
overwrites user-owned prompts and configuration, so any workspace refresh is a
separate reviewed operation.

The role checks out the exact commit and must fail if the guest revision differs.
Back up state before replacing the VM or changing the data layout. For rollback,
restore the prior canonical commit and run a non-mutating plan for review.

## Reviewed runtime artifact cache

The controller must retain reviewed Pi and Bun archives outside both repositories
at `/var/lib/infra-fabric/artifacts/sssf/`. The role requires the versioned `uv`,
`pi`, and `bun` archives from that cache and verifies their repository-tracked
SHA-256 before extraction. Do not replace this cache with a guest-side installer,
a mutable release URL, or an artifact in the canonical/private values repository.

Populate the cache only after separately reviewing the release, archive layout,
and checksum. Cache paths are `tool/version/filename`, for example
`pi/0.83.0/pi-linux-x64.tar.gz`. Preserve previous reviewed versions for rollback;
changing a pin remains a public-source review followed by validation, planning,
and an explicitly approved apply.

## State backup and restore

Use the managed service-state workflow:

```bash
VALUES_SITE=<site> scripts/service-state.sh backup sssf
VALUES_SITE=<site> scripts/service-state.sh restore-if-present sssf
VALUES_SITE=<site> scripts/service-state.sh restore sssf values/sites/<site>/service-backups/sssf/sssf-state-<timestamp>.tar.gz
```

Archives include the pinned checkout, factory configuration, SQLite traces, raw
sessions, and approved workspaces. Treat them as sensitive private state: raw
prompts and model output may contain proprietary source. Verify capacity,
checksum, and manifest before restore; a failed preflight must not stop the
service or remove current state.

## Evidence boundary

Static documentation checks, source validation, pin verification, and a provider
plan must not be treated as live acceptance evidence. Live health, an approved
workflow smoke, visualizer access-boundary verification, and backup/restore
rehearsal are separate evidence layers and remain unclaimed here.

## Safety gates

The SSSF VM does not receive OpenTofu credentials, Proxmox credentials, or
private-values decryption identities. Applying infrastructure remains an
external, separately approved operation. Development and production have
independent VM values, repository allow-lists, and provider credentials.
