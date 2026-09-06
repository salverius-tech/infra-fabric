# Onramp host runbook

`onramp_host` is a canonical shared-host substrate for rootless application workloads. It is an infrastructure resource owned by this repository; application ownership and lifecycle follow the shared-host contract.

## Canonical configuration

Select the site and edit its canonical model:

```bash
export VALUES_SITE=<site>
# edit values/sites/<site>/site.yaml
VALUES_SITE=<site> just validate
VALUES_SITE=<site> just plan
```

The model declares the host resource, runtime user, network identity, storage, release/image pins, security posture, and enabled shared-host services. Protected application values belong in the selected encrypted SOPS bundle under catalog-declared logical paths.

## Enable or disable

Enable the shared host and each workload through the canonical service map. Keep dependencies explicit: a shared-host workload requires its host resource. Removing a host or stateful workload can plan replacements or destroys; review the complete plan before any approved apply.

```bash
VALUES_SITE=<site> just plan
# inspect resource, storage, DNS/HTTPS, and workload changes
VALUES_SITE=<site> just apply
```

Apply requires explicit approval. Do not remove or edit generated projections to suppress a planned change.

## Operational checks

After an approved apply:

- verify host readiness and direct SSH access using the declared non-root operator path;
- verify rootless runtime and shared Caddy health;
- verify each workload’s direct endpoint and intended HTTPS route;
- verify DNS records through the documented Ansible workflow;
- run a repeat plan and investigate unexpected drift.

## Ownership boundary

This repository owns the host substrate, canonical resource identity, shared-host readiness, and explicitly contracted workloads. App-specific container definitions and lifecycle belong to the documented shared-host application owner unless a separate canonical service contract promotes them here.
