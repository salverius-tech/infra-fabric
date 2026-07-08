# Onramp App Platform Contract

## Purpose

This contract defines the boundary between `homelab-infra`, `onramp-vNext`, and Hermes for general Docker application services. It keeps this repository focused on durable infrastructure while allowing Hermes to operate across infrastructure and app-platform workflows.

The selected direction is option 3: `homelab-infra remains the durable infrastructure substrate`, `onramp-vNext owns Docker app services`, and `Hermes operates across both` through approved repo-native commands.

## Ownership

`homelab-infra` owns durable infrastructure resources and first-class services: Proxmox resources, service LAN addressing, static infrastructure DNS, service-local Caddy for first-class services, Ansible roles, and OpenTofu state.

`onramp-vNext` owns Docker app services by default. That includes application catalog entries, Compose or Podman workload definitions, app lifecycle, app-level health checks, and app-specific configuration that does not require infrastructure resource ownership.

Hermes is the operator cockpit. It may summarize status, run approved validation and planning commands, and guide the operator through approval gates. Hermes must not become a third source of truth for infrastructure or app deployment state.

## DNS Contract

`homelab-infra` may provision DNS needed for the onramp-host substrate and durable infrastructure services. Onramp app services should normally use an approved app-platform DNS convention, such as a wildcard or delegated subdomain, rather than one OpenTofu-managed static record per app.

Specific app DNS records can be promoted into `homelab-infra` only when a separate approved infrastructure plan justifies that they are durable platform resources rather than ordinary app catalog entries.

## Caddy Contract

First-class infrastructure services in this repository continue to use service-local Caddy by default. Technitium must not become a general ingress proxy for unrelated app services.

Onramp owns Caddy or reverse-proxy configuration for Onramp app services. The Onramp service `port` field means the container/service port reachable on the Compose network; it must not be reinterpreted as a host-published port unless a later contract explicitly changes that convention.

## Secrets Contract

Infrastructure secrets, Proxmox credentials, DNS API tokens, OpenTofu state, and private inventory belong in the ignored `values/` repo or approved local secret stores. They must not be copied into tracked public files.

Onramp app secrets belong to the app-platform secret mechanism selected by `onramp-vNext`. Hermes may reference whether required secrets are configured, but it must not print secret values, tokens, private domains, private hostnames, or private IP addresses.

## State Contract

OpenTofu state in this repository tracks infrastructure resources owned by `homelab-infra`. Onramp app services are not managed by OpenTofu by default and must not be added to values/terraform.tfvars, Ansible inventory, or OpenTofu state unless a separate approved infrastructure plan promotes that service or resource into this repository.

Onramp app deployment state belongs to `onramp-vNext` and its runtime. Hermes may aggregate state for operator visibility, but aggregated status is read-only evidence, not source-of-truth state.

## Approval Contract

`homelab-infra` mutation continues to require the reviewed workflow: `just validate`, reviewed `just plan`, and `just apply` only after explicit approval. Destroy, import, state surgery, router/firewall changes, or live service mutation require their own explicit approval.

Onramp app deployment approvals are owned by the Onramp workflow. Hermes can request approval and run approved commands only when the target repo and operation define a safe, repeatable path.

## Onramp Host Runtime

The default future onramp host is a Debian 13 VM running Podman. A VM provides stronger isolation and clearer operational boundaries for a general app substrate than nested containers in a Proxmox LXC.

Podman-in-LXC is experimental. It may be tested for lightweight workloads, but it requires explicit compatibility validation and must not be the default onramp-host direction for the SearXNG pilot or other general app services.

## SearXNG Pilot

SearXNG is classified as an Onramp app-platform service by default. It is useful beyond Hermes, is naturally packaged as an app workload, and should not force this repository to add a first-class LXC for every plugin backend.

For the first pilot, `homelab-infra` should provide only the future onramp-host substrate and any approved DNS or access contract. `onramp-vNext` should own the SearXNG service definition. Hermes should consume the approved SearXNG endpoint without bypassing either repository's workflow.

## Future Provisioning Gate

Future provisioning gate: onramp-host infrastructure work must be implemented in a separate reviewed plan before any live infrastructure mutation. That plan must include public-safe scaffold updates, private values migration guidance if needed, `just validate`, reviewed just plan output, and explicit approval before `just apply`.

Until that gate exists and passes, do not provision the Debian 13 VM, add onramp-host values to `values/terraform.tfvars`, create app DNS records, deploy SearXNG, or wire the Hermes plugin to a live endpoint.
