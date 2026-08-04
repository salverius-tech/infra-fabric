# Service catalog and implementation map

The service catalog in `infra/services.json` is the implementation contract. It binds a service identifier to runtime ownership, dependencies, schemas, projections, secret delivery, playbooks, state behavior, and OpenTofu addresses. `site.yaml` selects and configures services; it does not replace the catalog.

## Cataloged services

| Service | Runtime owner | Dependencies | Stateful | Primary role/playbook |
| --- | --- | --- | --- | --- |
| `technitium` | dedicated guest | — | yes | `technitium.yml`, `technitium-dns.yml`, `caddy-proxy.yml` |
| `forgejo` | dedicated guest | — | yes | `forgejo.yml` |
| `forgejo_runner` | dedicated guest | `forgejo` | no | `forgejo-runner.yml` |
| `infisical` | dedicated guest | — | yes | `infisical.yml` |
| `hermes` | dedicated guest | — | yes | `hermes.yml` |
| `sssf` | dedicated guest VM | — | yes | `sssf.yml` |
| `onramp_host` | shared host | — | yes | `onramp-host.yml` |
| `searxng_onramp` | host-contained workload | `onramp_host` | yes | `searxng-onramp.yml` |
| `infisical_onramp` | host-contained workload | `onramp_host` | yes | `infisical-onramp.yml` |
| `tailscale_client` | dedicated guest | — | no | `tailscale-client.yml` |

A service with runtime owner `none` does not own a separate guest. Its resource and lifecycle belong to its declared host dependency.

## What must be covered for a service

A first-class service change is incomplete until the relevant contract is covered in all applicable layers:

1. **Catalog** — add the service to `infra/services.json`, including runtime owner, dependencies, state capability, release source, playbooks, resource addresses, secret classification, and allowed overrides.
2. **Canonical schema** — define the typed `site.yaml` configuration and endpoint/release/state fields.
3. **Projection** — emit only the compatibility variables required by consumers and identity-bind them to the canonical service/resource.
4. **OpenTofu** — declare or bind the resource lifecycle, storage, network, release inputs, and outputs.
5. **Ansible** — add the playbook/role for guest or shared-host convergence; keep steady-state service configuration at direct service endpoints.
6. **Secrets** — declare logical secret paths, provider namespaces, classifications, and transient environment bindings. Never persist decrypted values in generated files.
7. **State** — add backup/restore behavior and a state policy for state-capable services.
8. **Tests** — cover schema, catalog, projection identity, secret delivery, Ansible compatibility, and relevant orchestration behavior.
9. **Documentation** — document ownership, prerequisites, health checks, update/rollback behavior, and recovery evidence.

Use the service authoring manifest as design evidence, not as permission to create site values, secrets, state, plans, or infrastructure.

## Runtime placement rules

- Dedicated guest services own their guest resource in `resources.guests`.
- Shared-host workloads use `resources.shared_hosts` and must declare the host dependency.
- Browser-facing services normally use service-local Caddy; shared-host workloads use the documented shared-host Caddy contract.
- DNS synchronization belongs to Ansible and the canonical DNS projection, not OpenTofu resources.
- Service identity, ownership, dependencies, runtime, releases, state, and allowed configuration belong in the catalog and typed canonical model.

## Health and recovery evidence

For every enabled stateful service, record separately:

- structural validation;
- provider-backed plan;
- direct guest/service readiness;
- service health endpoint or command;
- repeat-plan drift result;
- backup archive and checksum evidence;
- restore rehearsal result.

Do not call a service operational based only on a successful OpenTofu apply. See [Canonical readiness](canonical-readiness.md), [Managed service-state backup and restore](service-state-backup.md), and [Service update policy](service-update-policy.md).
