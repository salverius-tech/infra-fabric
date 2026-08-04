# homelab-infra

A public-safe, repo-driven runbook for canonical site infrastructure. Proxmox resources, service placement, networking, releases, DNS, HTTPS, Ansible orchestration, and service state are described by the selected canonical site model.

## Source of truth

For a selected site, operators edit only:

- `values/sites/<site>/site.yaml` — non-secret site and service configuration;
- `values/sites/<site>/.sops.yaml` — private SOPS policy supplied outside this public repository;
- `values/sites/<site>/secrets.sops.yaml` — encrypted canonical secret bundle.

Generated projections under `values/sites/<site>/generated/` are derived artifacts. Do not edit them. Age identities, recipient policy, credentials, state, plans, and live site values remain private and outside tracked public source.

## Canonical quick start

From the repository root:

```bash
just setup "" <site>
export VALUES_SITE=<site>
```

Complete the private site SOPS policy, encrypted bundle, and external age identity, then follow [Canonical site quick start](docs/canonical-quick-start.md).

## Normal workflow

```bash
export VALUES_SITE=<site>
just validate
just plan
# Review creates, updates, replacements, destroys, credentials, and service boundaries.
# Run apply only after explicit operator approval.
just apply
```

`validate` is the structural and static gate. `plan` refreshes and verifies private generated projections and performs provider/readiness preflight before producing a saved plan. `apply` is the infrastructure mutation gate and accepts only a fresh verified plan.

Read [Public Just recipes](docs/just-recipes.md) for parameters, side effects, and safety controls.

## Add a service

Use [Canonical service authoring](docs/canonical-service-authoring.md) before changing the service catalog or implementation. The public-safe authoring tool produces a reviewable contract manifest and never creates site values, secrets, plans, state, or resources:

```bash
scripts/python.sh scripts/service-author.py \
  --service-id <service_id> \
  --archetype dedicated-lxc \
  --config-model <ConfigModel> \
  --projection-contract <projection-contract> \
  --provisioning-contract <provisioning-contract> \
  --output /tmp/<service_id>-authoring-manifest.json
```

## Safety boundaries

- Keep tracked material public-safe; use placeholders and RFC 5737 addresses in fixtures.
- Keep site values, encrypted bundles, state, plans, generated projections, and identities in the private site repository or approved external stores.
- Never print or commit credentials, keys, tokens, recipient material, live endpoints, or state contents.
- Do not apply, destroy, import, alter state, or mutate routers/firewalls without explicit approval.
- Use direct service endpoints for service diagnostics. Use the Proxmox boundary for resource lifecycle and host-boundary readiness.

## Documentation

- [Canonical site quick start](docs/canonical-quick-start.md)
- [Canonical architecture and ownership](docs/canonical-architecture.md)
- [Public Just recipes](docs/just-recipes.md)
- [Service catalog and implementation map](docs/service-catalog.md)
- [Canonical service authoring](docs/canonical-service-authoring.md)
- [Canonical secret operations](docs/canonical-values-secret-operations.md)
- [Canonical teardown and site retirement](docs/canonical-teardown.md)
- [Service update policy](docs/service-update-policy.md)
- [Documentation index](docs/README.md)
