# Onramp substrate and SearXNG handoff

The selected canonical site owns a versioned, identity-bound, non-secret handoff projection for the Debian 13 Onramp shared-host substrate. The projection is generated as `values/sites/<site>/generated/onramp-handoff.json`, is covered by the canonical projection manifest, and must never be edited manually.

Generating the contract is source-complete. Consuming it from `onramp-vNext`, proving a live cutover, and retiring the temporary `searxng_onramp` implementation remain separate external acceptance gates.

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

The projection intentionally excludes VMIDs and other provider IDs, temporary workload definitions, SSH keys, provider inputs, protected values, tokens, credentials, state, plans, and generated-file write authority. Its projection-manifest digest binds the bytes to the selected canonical model; `verify-projections.py` also regenerates and compares the handoff contract to reject identity or ownership tampering.

## Ownership boundary

`infra-fabric` owns:

- Proxmox lifecycle;
- network and storage;
- host security;
- rootless Podman prerequisites; and
- base proxy capability.

`onramp-vNext` owns, after an accepted handoff:

- application definitions and deployment;
- application health and rollback; and
- application data lifecycle.

The handoff grants no Proxmox authority, provider access, protected-value access, or permission to edit generated projections.

## Consumer requirements

Before using the projection, an Onramp consumer must:

1. require the exact supported `api_version` and `kind`;
2. require `metadata.enabled: true` and a non-null `spec`;
3. bind its workspace to `metadata.canonical_site` and `spec.identity.canonical_resource`;
4. reject unknown contract versions instead of guessing compatibility;
5. treat the projection as read-only input; and
6. obtain secrets through its separately approved protected-input workflow, never through this artifact.

Consumer compatibility tests should use tracked public fixtures. Live deployment, endpoint, secret-delivery, backup/restore, health, rollback, and cutover evidence must be recorded in the environment-specific acceptance authority rather than inferred from source tests.

## Temporary workload retirement

SearXNG and other host-contained workloads remain owned by `infra-fabric` until `onramp-vNext` proves deployment, secret delivery, proxying, direct and HTTPS health, backup/restore, rollback, Hermes consumption, and development cutover. Their definitions are deliberately not exported in the substrate handoff. Retirement is evidence-triggered, not date-triggered.

After those gates pass, removal still requires an explicit reviewed source change and any live mutation requires its own plan/apply approval. Do not delete the temporary implementation merely because a handoff projection exists.

## Verification

Source-only verification may render the tracked public fixtures, verify projection identity/permissions, and exercise schema and tamper failures. Environment acceptance must separately verify the direct endpoint, intended HTTPS route, DNS, protected secret delivery, rootless runtime health, repeat plan, backup/restore, rollback, and consumer behavior without printing private URLs, query credentials, tokens, or certificate material.
