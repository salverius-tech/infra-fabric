# Onramp substrate and SearXNG handoff

The selected canonical site generates a versioned, identity-bound, non-secret substrate projection at `values/sites/<site>/generated/onramp-handoff.json`. It is covered by the canonical projection manifest and must never be edited manually.

The projection is source-only compatibility work. The authorized `onramp-vNext` repository has no corresponding consumer requirement or implementation, so this repository does not treat it as an active cross-repository contract, a cutover plan, or evidence for retiring `searxng_onramp`.

## Canonical lifecycle

```bash
export VALUES_SITE=<site>
just validate
just plan
# apply only after explicit approval
just apply
```

Keep the shared host enabled whenever a shared-host workload is enabled. The canonical model owns the host/service relationship; generated projections provide consumer inputs and must not be edited.

## Generated contract

`onramp-handoff.json` uses API version `infra-fabric.onramp-handoff/v1` and kind `OnrampSubstrate`. When `onramp_host` is disabled, it records `metadata.enabled: false` and has no consumable `spec`. A consumer must fail closed rather than treating a disabled contract as a host.

When enabled, the contract contains only public/non-secret infrastructure metadata:

- canonical site, service, and shared-resource identity;
- VM resource type, canonical resource identity, hostname, and deterministic address;
- Debian 13, rootless Podman, deploy user/directory, and base Caddy capability;
- the infrastructure/application ownership split;
- the fact that temporary host-contained workload ownership remains with `infra-fabric`, without exporting those workload definitions.

The projection intentionally excludes VMIDs and other provider IDs, CPU architecture until it has canonical resource provenance, temporary workload definitions, SSH keys, provider inputs, protected values, tokens, credentials, state, plans, and generated-file write authority. Its projection-manifest digest binds the bytes to the selected canonical model; `verify-projections.py` also regenerates and compares the handoff contract to reject identity or ownership tampering.

## Ownership boundary

`infra-fabric` owns:

- Proxmox lifecycle;
- network and storage;
- host security;
- rootless Podman prerequisites; and
- base proxy capability.

An independently specified application-platform consumer would own:

- application definitions and deployment;
- application health and rollback; and
- application data lifecycle.

The handoff grants no Proxmox authority, provider access, protected-value access, or permission to edit generated projections.

## Future consumer requirements

If a future consumer explicitly adopts this projection, it must:

1. require the exact supported `api_version` and `kind`;
2. require `metadata.enabled: true` and a non-null `spec`;
3. bind its workspace to `metadata.canonical_site` and `spec.identity.canonical_resource`;
4. reject unknown contract versions instead of guessing compatibility;
5. treat the projection as read-only input; and
6. obtain secrets through its separately approved protected-input workflow, never through this artifact.

Consumer compatibility tests should use tracked public fixtures. No consumer acceptance work is implied until that consumer owns a requirement and implementation.

## Temporary workload retirement

SearXNG and other host-contained workloads remain owned by `infra-fabric`. Their definitions are deliberately not exported in the substrate projection. The projection alone is not an ownership-transfer or retirement trigger.

Any future ownership transfer or removal requires a consumer-owned requirement, explicit reviewed source change, and separately authorized live mutation. Do not delete the temporary implementation merely because a projection exists.

## Verification

Source-only verification may render the tracked public fixtures, verify projection identity/permissions, and exercise schema and tamper failures. It does not establish a consumer, deployment, endpoint, secret delivery, health, restore, rollback, or cutover result.
