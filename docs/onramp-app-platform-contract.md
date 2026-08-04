# Onramp application platform contract

The canonical service model distinguishes infrastructure ownership from application ownership.

## This repository owns

- Proxmox resources and shared-host substrates;
- service LAN identity, canonical endpoints, and infrastructure DNS projections;
- first-class guest services and their service-local Caddy configuration;
- shared-host readiness and explicitly contracted shared-host workloads;
- OpenTofu state and Ansible orchestration for those resources.

## Shared-host application owner owns

- application catalog and workload definitions;
- Compose/Podman lifecycle and app-level health checks;
- app-specific configuration that does not require infrastructure ownership;
- application rollback and data lifecycle within the shared-host contract.

A workload is added to this repository only when a canonical service-authoring manifest, resource/projection contract, secret contract, state policy, and reviewed implementation establish the ownership boundary.

## Canonical workflow

```bash
export VALUES_SITE=<site>
just validate
just plan
# explicit approval required
just apply
```

Use the canonical service-authoring guide before promoting a workload into this repository. Do not create a second configuration source for shared-host workloads. Browser-facing first-class guests normally use app plus service-local Caddy; shared-host applications use the documented shared Caddy contract.

## Safety

Destroy, import, state changes, router/firewall changes, credential rotation, and live workload mutation require separate explicit approval. After approved changes, verify direct service health, DNS/HTTPS, and a repeat plan.
