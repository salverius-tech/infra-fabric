# App-host runbook

The optional `onramp_host` service creates a Debian 13 VM substrate for Onramp-managed Podman services. It is not a SearXNG deployment by itself.

## Enable or disable

- Enable: add `onramp_host` to `settings.local.json` services and fill the private `values/terraform.tfvars` onramp-host fields.
- Disable: remove `onramp_host` from `settings.local.json` services, then run a reviewed `just plan` before any apply.

Removing `onramp_host` can cause OpenTofu to plan VM changes or destroy actions. Do not run `just apply`, destroy, import, or state surgery without explicit approval.

## Private values source of truth

`values/terraform.tfvars` owns the onramp-host VM shape:

- VMID, hostname, Debian 13 genericcloud image URL/file name, datastore, CPU, memory, disk
- static IPv4/CIDR, gateway, DNS servers, search domain, bridge, optional VLAN
- cloud-init/bootstrap user, SSH public keys, deploy user, deploy directory, SSH policy, and firewall source CIDRs

Tracked scaffold values use only placeholders such as `onramp-host.example.internal`, `searxng.apps.example.net`, and `192.0.2.0/24`. The onramp-host VM must be built from a clean cloud image; do not point it at a mutable VM template with existing cloud-init state.

## Future deployment validation

A later live deployment plan must:

1. Run `just plan` and summarize creates, changes, and destroys.
2. Obtain explicit operator approval before `just apply`.
3. Run `just apply` to create/configure the VM and onramp-host readiness role.
4. Verify SSH reachability as the Onramp deploy user.
5. Verify rootless `podman info`, the selected Compose provider, rootless socket semantics if used, and deployment directory ownership.
6. Deploy SearXNG through `onramp-vNext`.
7. Validate Onramp reverse proxy/Caddy ownership and confirm no default host-published app ports exist outside approved proxy ports.
8. Set private `HERMES_WEB_SEARXNG_URL` and smoke-test Hermes search integration once the plugin/runtime exists.

## Rollback choices

Before applying a rollback, decide whether the VM should be retained or deleted.

- Retain VM: remove or pause Onramp workloads, remove `onramp_host` from active orchestration only when a reviewed `just plan` shows acceptable changes, and keep private DNS/inventory values for future reuse.
- Delete VM: stop Onramp workloads first, clean up Onramp app state and proxy records, remove `onramp_host` from settings, review `just plan`, then apply only after explicit approval.

DNS cleanup belongs to the component that created the records: Technitium records are synced by `homelab-infra`, while app reverse-proxy names for SearXNG are Onramp-owned unless a later plan changes that boundary. Private values follow-up may include removing `HERMES_WEB_SEARXNG_URL`, onramp-host tfvars, and Onramp inventory entries.

Do not perform OpenTofu state surgery, import, destroy, or live mutation without explicit approval and a rollback path.
