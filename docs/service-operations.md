# Service operations matrix

**Authority:** operator guidance. The [service catalog](../infra/services.json) is the machine-readable source for registered services, state capability, ownership, releases, secret paths, and playbooks. This page is the catalog-derived day-two routing matrix; it does not replace catalog data or authorize a live operation.

## Evidence boundaries

`just validate` and the repository tests establish only source/configuration evidence. A successful `just plan` is provider-backed planning evidence, not a deployment. Health, logs, backup contents, restore, rollback, and recovery are **external evidence required** until an authorized run records them for the selected site. Never turn an unchecked table cell below into a claim that a production service is healthy or recoverable.

Use the supported lifecycle entry points only:

```bash
VALUES_SITE=<site> just update
VALUES_SITE=<site> just validate
VALUES_SITE=<site> just plan
# Apply only a fresh reviewed plan after explicit approval.
VALUES_SITE=<site> just apply
```

Do not invoke raw OpenTofu/Terraform lifecycle commands, run an unguarded Ansible `site.yml`, or edit `values/sites/<site>/generated/`. They bypass the selected-site, immutable-plan, serialization, or projection checks. `site.yml` is not a supported orchestration entry point. Direct service endpoints and host logs are diagnostic evidence only; they do not replace the lifecycle workflow.

## Standard diagnostic stages

Follow these named stages in order and stop at the first failing boundary:

1. **canonical-input** — run `VALUES_SITE=<site> just validate`; correct `site.yaml` or protected logical-path prerequisites, never generated output.
2. **provider-plan** — run `VALUES_SITE=<site> just plan`; inspect the fresh summary and resolve provider/preflight errors without editing state or a saved plan.
3. **host-trust** — after an authorized apply, confirm the generated inventory and strict SSH/host-key boundary before any service diagnosis.
4. **service-health** — collect the service-specific health and log evidence below from the selected target; redact endpoints and credentials from tickets.
5. **state-recovery** — for a state-capable service, use the managed backup/restore workflow and record archive validation plus post-restore health. For a non-state-capable service, treat backup/restore as explicitly unsupported.

The full failure trees and trust boundaries are in [canonical troubleshooting](canonical-troubleshooting.md); managed archive commands are in [service-state backup and restore](service-state-backup.md).

## Catalog-derived matrix

All services registered in `infra/services.json` appear exactly once. **Credentials** means logical paths are declared in the catalog and are edited only through `just edit-secrets`; it never means that values have been checked. **Logs** are the owning systemd unit or the catalog-declared Compose workload, collected only after Stage 3. **Rollback** means revert the reviewed canonical release/configuration change, then validate, plan, and obtain a new approved apply; never mutate a running service with an ad-hoc installer.

| Service | Health and logs | Credentials | Update / rollback | Backup and restore verification | Failure recovery |
| --- | --- | --- | --- | --- | --- |
| `technitium` | DNS/API health after direct diagnostic authorization; `journalctl -u dns` | catalog: provider DNS token | manual paired version/checksum review; rollback canonical pin | state-capable: managed archive; validate archive and post-restore DNS/API health | Stage 1 → 3 → inspect DNS unit; recover with managed state workflow |
| `forgejo` | HTTP/SSH health; `journalctl -u forgejo` | catalog: Forgejo runtime paths plus provider DNS token | managed release check; rollback canonical release/configuration | state-capable: managed archive including configured database; validate archive and post-restore HTTP/SSH health | inspect service/database dependency; do not permit SQLite fallback for PostgreSQL recovery |
| `tailscale_client` | authenticated client status; `journalctl -u tailscaled` | catalog: Tailscale auth key | unmanaged: no repository upgrade policy; rollback the reviewed canonical change rather than mutating the client | **N/A/unsupported:** catalog is not state-capable | recover identity/connectivity through Stage 3; do not copy auth keys into logs or shell history |
| `forgejo_runner` | runner registration/job acceptance; `journalctl -u forgejo-runner` | catalog: registration secret | managed release check; rollback canonical release/configuration | **N/A/unsupported:** catalog is not state-capable | recover by verifying the Forgejo dependency before re-registration; rotate/re-enter secret only with protected-input workflow |
| `infisical` | HTTPS/application health; owning Compose logs | catalog: runtime paths plus provider DNS token | manual immutable image/release review; rollback canonical image/release | state-capable: managed archive; validate archive and post-restore application health | inspect Compose/database readiness; restore only through managed state workflow |
| `infisical_onramp` | HTTPS/application health; shared-host Compose logs | catalog: Infisical-onramp runtime paths | manual shared-host image/release review; rollback canonical image/release | state-capable: managed archive; validate archive and post-restore application health | first recover `onramp_host`, then the application; no independent guest lifecycle exists |
| `hermes` | gateway/dashboard health; `journalctl -u hermes-gateway` and `journalctl -u hermes-dashboard` when enabled | catalog: conditional Control/dashboard runtime paths plus provider DNS token | manual immutable release review; rollback canonical release/configuration | state-capable: managed archive; validate archive and post-restore gateway health | use [Hermes Control operations](hermes-control-operations.md); preserve approval and audit boundaries |
| `sssf` | visualizer/workspace health; `journalctl -u sssf-visualizer` when enabled | catalog: selected provider path only | managed repository-tool pin check; upstream commit rollback is canonical/reviewed | state-capable: managed archive; validate archive and post-restore workspace/visualizer health | verify selected provider path and workspace mount; do not require inactive provider credentials |
| `onramp_host` | host readiness and proxy/platform health; systemd and Compose logs for affected workload | catalog: provider DNS token | manual shared-host package/config review; rollback canonical change | state-capable host contract: managed archive as catalog-configured | restore host trust/readiness first; then recover dependent onramp applications in dependency order |
| `searxng_onramp` | search endpoint health; shared-host Compose logs | catalog: SearXNG secret key | manual immutable image/digest review; rollback canonical image/digest | state-capable: managed archive; validate archive and post-restore search health | first recover `onramp_host`, then SearXNG; its standalone guest lifecycle is **N/A** |

## Managed state recovery

For a selected state-capable service, the executable public sequence is:

```bash
VALUES_SITE=<site> just validate
# Create or select the site-local managed archive through the documented service-state wrapper.
VALUES_SITE=<site> scripts/service-state.sh backup <service>
VALUES_SITE=<site> scripts/service-state.sh restore <service> values/service-backups/<service>/<archive>.tar.gz
VALUES_SITE=<site> just validate
```

The wrapper validates service selection against the catalog and uses the paired generated inventory/vars. Archive creation, restore, and post-restore health are live operations: obtain explicit authorization, retain restrictive archive permissions, and record Stage 4/5 evidence separately. Do not run restore to test this documentation.

## Compatibility and migration boundary

The canonical inputs are `values/sites/<site>/site.yaml` and `values/sites/<site>/secrets.sops.yaml`; `generated/` is derived. Migration/import compatibility is limited to the explicit tooling documented in [canonical model operations](canonical-values-migration.md). Resolve migration errors with its validation/render path, preserve legacy inputs until the documented parity and retirement decision gates pass, and never use a legacy `.env`, raw tfvars, direct `site.yml`, or raw OpenTofu command as a fallback authoring or recovery path.

## Evidence status

This matrix is source-derived documentation. It confirms catalog coverage and supported command boundaries only. Provider planning, live health, backup creation, restore verification, rollback rehearsal, and failure-recovery rehearsal remain external evidence gates for each selected site.
