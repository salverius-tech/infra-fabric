# Canonical site values template

This directory is a public-safe template for the private values repository. The selected site model is the only operator-edited configuration source.

## Canonical layout

```text
values/
└── sites/
    └── <site>/
        ├── site.yaml
        ├── .sops.yaml
        ├── secrets.sops.yaml
        └── generated/       # derived; never edit
```

`site.yaml` contains non-secret platform, resource, service, endpoint, release, storage, and state configuration. `secrets.sops.yaml` contains only encrypted canonical logical secret paths. The SOPS policy and age identities are private deployment material. Generated projections, plans, state, backups, and local credentials remain private derived artifacts.

For a new public-safe starting shape, copy `scaffold/sites/_template/` and replace the `example` identity and all example values before private validation. The template disables apply and destroy by default.

## Initialize a site

From the runbook repository root:

```bash
just setup "" <site>
export VALUES_SITE=<site>
```

Complete the selected private SOPS policy, encrypted bundle, and external age identity before running secret editing, bootstrap initialization, validation, or planning. Follow [Canonical site quick start](../docs/canonical-quick-start.md).

## Canonical workflow

```bash
just edit-secrets SITE=<site>
just ssh-initialize SITE=<site>
VALUES_SITE=<site> just validate
VALUES_SITE=<site> just plan
# after explicit approval only
VALUES_SITE=<site> just apply
```

The first two commands are explicit protected-input operations. Validation is structural/static. Planning refreshes and verifies derived projections and performs provider/readiness preflight. Apply mutates infrastructure and service state only from a fresh verified plan.

## Editing rules

- Edit `site.yaml` for non-secret configuration.
- Use `just edit-secrets SITE=<site>` for protected values.
- Never edit `generated/`, plan files, state, or derived inventory/projection files.
- Never place credentials, private keys, tokens, recipient material, or live site values in public tracked source.
- Keep all service secrets under `services.<service>.secrets.<key>`.
- Keep provider secrets under their catalog-declared provider namespace.
- Use public-safe placeholders in fixtures and scaffolds.

## Adding a service

Read [Canonical service authoring](../docs/canonical-service-authoring.md) before changing the service catalog. Generate a public-safe contract manifest first:

```bash
scripts/python.sh scripts/service-author.py \
  --service-id <service_id> \
  --archetype dedicated-lxc \
  --config-model <ConfigModel> \
  --projection-contract <projection-contract> \
  --provisioning-contract <provisioning-contract> \
  --output /tmp/<service_id>-authoring-manifest.json
```
