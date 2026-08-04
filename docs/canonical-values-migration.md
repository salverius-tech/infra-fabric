# Canonical model operations

The selected canonical site is the only normal lifecycle input. `site.yaml` owns non-secret configuration, `secrets.sops.yaml` owns encrypted protected values, and verified generated projections are derived consumer inputs.

## Required site layout

```text
values/sites/<site>/site.yaml
values/sites/<site>/.sops.yaml
values/sites/<site>/secrets.sops.yaml
values/sites/<site>/generated/
```

Use the public workflow:

```bash
just setup "" <site>
export VALUES_SITE=<site>
just edit-secrets SITE=<site>
just ssh-initialize SITE=<site>
VALUES_SITE=<site> just validate
VALUES_SITE=<site> just plan
VALUES_SITE=<site> just apply
```

The last command requires explicit approval and a fresh verified plan.

## Canonical validation

```bash
scripts/python.sh scripts/canonical-values.py \
  --site-file values/sites/<site>/site.yaml validate
```

This validates site identity, the strict typed model, catalog ownership, service dependencies, resource references, release contracts, storage, and configuration schemas. It does not edit the site or perform infrastructure mutation.

## Projection lifecycle

Planning renders the selected site into verified consumer projections beneath its `generated/` directory. Projections are identity-bound, non-secret, and derived. They must not be edited manually or used as a second source of truth.

The normal lifecycle uses the public `just` recipes. Low-level render and consumer helpers are implementation details and should be invoked directly only while developing or testing the canonical workflow.

## Secret contract

Required protected paths are declared by the catalog and delivered transiently to approved consumers. Service secrets use `services.<service>.secrets.<key>`. Provider values use catalog-declared provider namespaces. Decrypted values must never enter site YAML, projections, plans, state, logs, reports, or command arguments.

## Migration and recovery

Canonical site creation is an explicit operation that preserves the selected site’s source files and protected bundle. Review all model, projection, secret, provider, state, and operational requirements before using a site for live planning. Recovery and restoration use disposable restricted workspaces and value-free manifests, then return to the canonical site workflow after verification.

Passing model validation is not live health evidence. Passing a plan is not approval to apply. Passing apply is not a substitute for direct service smoke tests, repeat-plan drift checks, or state restore rehearsal.
