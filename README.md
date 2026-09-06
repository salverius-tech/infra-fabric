# infra-fabric

A public-safe, repo-driven runbook for canonical site infrastructure. Proxmox resources, service placement, networking, releases, DNS, HTTPS, Ansible orchestration, and service state are described by the selected canonical site model.

## Source of truth

`infra-fabric` is the public runbook and implementation repository. The `values/`
directory is a separate private Git checkout mounted under the runbook root; it
is not a second public configuration tree.

For a selected site, the canonical inputs are:

- `values/sites/<site>/site.yaml` — non-secret site, resource, service,
  endpoint, release, storage, and state configuration;
- `values/sites/<site>/secrets.sops.yaml` — encrypted logical secret values;
- `values/sites/<site>/.sops.yaml` — private SOPS policy, not part of the
  non-secret model.

Generated projections under `values/sites/<site>/generated/` and runtime
artifacts such as plans, state, backups, and host-key material are derived
private artifacts. Do not edit them. Age identities, recipient policy,
credentials, and live site values remain private and outside tracked public
source.

## Prerequisites

Use a Linux `amd64` host with Git, GNU Make-compatible shell utilities, `just`, and Docker Engine with the Compose plugin. The tooling image installs checksum-pinned Linux `amd64` OpenTofu, TFLint, and SOPS binaries, so non-`amd64` hosts are not supported by this workflow. Ensure Docker is available to the invoking user before running `just setup` or any validation recipe. Site-specific protected-input operations additionally require a private SOPS policy, encrypted bundle, and external age identity; structural validation itself does not decrypt them.

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

Start with the [documentation index](docs/README.md), then use the [service operations matrix](docs/service-operations.md) for catalog-derived day-two health, credential, update, backup, restore, and recovery boundaries. Supported lifecycle commands are the `just` recipes; direct `site.yml` and raw OpenTofu/Terraform lifecycle use are unsupported.

- [Canonical site quick start](docs/canonical-quick-start.md)
- [Canonical architecture and ownership](docs/canonical-architecture.md)
- [Public Just recipes](docs/just-recipes.md)
- [Service catalog and implementation map](docs/service-catalog.md)
- [Canonical service authoring](docs/canonical-service-authoring.md)
- [Canonical secret operations](docs/canonical-values-secret-operations.md)
- [Canonical teardown and site retirement](docs/canonical-teardown.md)
- [Service update policy](docs/service-update-policy.md)
- [Documentation index](docs/README.md)
