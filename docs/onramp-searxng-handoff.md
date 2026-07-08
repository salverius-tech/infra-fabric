# Onramp SearXNG handoff

This is a public-safe handoff for a future `onramp-vNext` implementation. `onramp-vNext` owns the SearXNG container definition, reverse proxy/Caddy configuration, app deployment workflow, and service lifecycle. `homelab-infra` only prepares the optional Debian 13 Podman `onramp_host` VM and exposes private-values-backed connection facts.

No live SearXNG URL exists from this source-only slice.

## Context status

Read-only sibling context was optional during this plan. If `C:/Projects/Personal/onramp-vNext` was unavailable, treat this as a generic handoff and confirm exact file paths/commands on the Onramp side before implementation.

## Inputs from homelab-infra/private values

- `onramp_host` service selected in `settings.local.json` only when the onramp-host VM should be managed.
- `values/terraform.tfvars` remains the source of truth for `onramp_host_vmid`, `onramp_host_ipv4_address`, `onramp_host_hostname`, `onramp_host_deploy_user`, and `onramp_host_deploy_dir`.
- Ansible inventory derives the onramp-host SSH target from tfvars; do not duplicate real hostnames or IP addresses in tracked Onramp files.
- Hermes consumes `HERMES_WEB_SEARXNG_URL` from private runtime values when the future `web-searxng` plugin/runtime wiring is implemented.

## Onramp implementation checklist

1. Add a SearXNG app/service definition in `onramp-vNext`; do not add SearXNG as a first-class `homelab-infra` LXC.
2. Target the `onramp_host` Podman host through private inventory/outputs from this repo.
3. Keep Onramp service `port` fields as container/service ports reachable on the Compose network. Do not reinterpret them as host-published ports.
4. Add Onramp-owned Caddy/reverse-proxy routing for `https://searxng.apps.example.net` or the private equivalent.
5. Forbid default host-published app ports. Only the approved Onramp reverse proxy should bind host ports such as 80/443.
6. Emit or document the final internal/public SearXNG URL for private values as `HERMES_WEB_SEARXNG_URL`.
7. Validate the service with an Onramp dry run, Podman deployment, reverse-proxy health check, and Hermes endpoint smoke check in a later reviewed deployment plan.

## Ownership boundary

- `homelab-infra`: VM substrate, SSH/bootstrap policy, rootless Podman readiness, default-deny firewall posture, and docs/runbooks.
- `onramp-vNext`: SearXNG image/configuration, Compose/Podman service, reverse proxy/Caddy rules, app updates, and app rollback.
- Hermes: consumes the private SearXNG endpoint through `HERMES_WEB_SEARXNG_URL`; plugin/runtime implementation is a follow-up.
