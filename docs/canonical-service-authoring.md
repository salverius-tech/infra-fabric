# Canonical service authoring

A new service is complete only when its canonical model, catalog, projections,
provisioning, orchestration, secret delivery, state policy, tests, and operator
contract agree. Adding a row to `infra/services.json`, an Ansible role, or a
container definition alone is not a supported service implementation.

This guide describes a source change. It does not authorize creating private
site values, secrets, plans, resources, or live services. Use the selected-site
workflow only after the public contract is complete.

## Choose the service boundary first

Start by deciding where the workload runs and who owns its lifecycle. That
decision determines which layers are required.

| Archetype | Catalog `runtime_owner` | Resource ownership | Typical use |
| --- | --- | --- | --- |
| `dedicated-lxc` | `guest` | New or existing LXC in `resources.guests` | Small Linux service with an independent guest boundary |
| `dedicated-vm` | `guest` | New or existing VM in `resources.guests` | Workload needing a VM, kernel features, or stronger isolation |
| `shared-host` | `shared_host` | Shared host in `resources.shared_hosts` | Host substrate, proxy, or platform capability |
| `no-runtime` | `none` | No independent guest; depends on another service or provider | Host-contained workload or integration such as `searxng_onramp` |

A `no-runtime` service may still have a release, secrets, Ansible playbook,
endpoints, state policy, and backup/restore contract. A host-contained workload
must declare the dependency that supplies its runtime; a provider or
control-plane integration may have no guest dependency. Do not create a
placeholder guest merely to fit a service into the dedicated-guest shape.

Before editing code, write down:

- the service ID, owner, dependencies, and runtime user;
- whether the service owns a guest, a shared-host workload, or no runtime;
- resource, storage, network, DNS, HTTPS, and direct diagnostic boundaries;
- immutable release source and rollback mechanism;
- state capability, backup/restore order, and disable behavior;
- required protected logical paths and their consumer environment names.

If any item has no clear owner, resolve the design before implementation. Do not
add an opaque override map, direct OpenTofu provisioner, raw Ansible inventory,
or a second configuration file to work around a missing contract.

## Start with a public-safe authoring manifest

Generate a reviewable design manifest before editing implementation files. The
tool is generate-only: it never edits the repository, creates site values,
decrypts or creates secrets, renders projections, plans, or applies.

For a stateful dedicated guest with a runtime secret:

```bash
scripts/python.sh scripts/service-author.py \
  --service-id <service_id> \
  --archetype dedicated-lxc \
  --config-model <ConfigModel> \
  --projection-contract <projection-contract> \
  --provisioning-contract <provisioning-contract> \
  --stateful \
  --state-contract <backup-restore-contract> \
  --secret services.<service_id>.secrets.<key>:runtime:<ENVIRONMENT_NAME> \
  --output /tmp/<service_id>-authoring-manifest.json
```

Use `dedicated-vm`, `shared-host`, or `no-runtime` when appropriate. Dedicated
and shared-host archetypes require `--provisioning-contract`; `no-runtime` does
not. Add `--stateful --state-contract ...` only when the service is
state-capable. Repeat `--secret` for every catalog-required service secret.
Each entry has the exact form:

```text
services.<service_id>.secrets.<key>:<classification>:<ENVIRONMENT_NAME>
```

The manifest contains logical paths and environment variable names, never
values. `classification` must be one supported by the authoring tool, such as
`runtime`, `provider`, `credential`, `token`, or `key`.

Review the manifest with the service design. It is evidence that all required
surfaces were considered; it is not permission to create protected inputs or
infrastructure.

## Implement the source contract

Work through the following layers in order. Keep one source of truth: operators
select and configure the service in `site.yaml`; the catalog defines what that
configuration is allowed to mean; consumer inputs are derived projections.

### 1. Register the service in the catalog

Add an entry in `infra/services.json`. The catalog is the implementation
contract and must define, as applicable:

- `runtime_owner`, `runtime`, `dependencies`, `inventory`, and `playbooks`;
- `configuration_schema`, `required_fields`, and `release_sources`;
- `state_capable` and `state_order` for stateful services;
- `terraform_addresses` and `terraform_replace_addresses` for resource-owning
  services;
- `required_secrets`, `secret_classifications`, and `secret_environment` for
  protected delivery;
- `update_policy` and, where needed, release-specific immutable-reference
  requirements.

Dependencies must name registered services and must match the canonical service
configuration. Inventory and Terraform addresses are contracts, not labels:
they must identify the actual generated inventory group and OpenTofu resource
or module address.

### 2. Define typed canonical configuration

Add a strict configuration model in `scripts/canonical_values.py`, register it
in the service-configuration registry, and use its name as the catalog
`configuration_schema`. Model only operator-owned values: enablement, resource
binding, endpoints, release metadata, state policy, and service-specific
configuration. If a service has no service-owned configuration, use the
reviewed resource-owned configuration exemption rather than an untyped map.

Update the public-safe test fixtures under `tests/fixtures/` to exercise the
new model, including invalid or missing required fields. The operator template
at `scaffold/sites/_template/site.yaml` must remain public-safe and
non-permissive; extend it when the full catalog contract requires the new
service entry. Never add live site values to a fixture or template.

### 3. Add explicit projections

Update `scripts/canonical_projections.py` for every OpenTofu and Ansible value
the service consumes. Add catalog inventory mappings for canonical fields where
the catalog is the mapping authority. Projections must be explicit and
identity-bound to the selected canonical service and resource; do not derive
variable names by convention or accept per-consumer override maps.

Confirm the generated outputs contain only the intended non-secret values:

- `terraform.auto.tfvars.json` for OpenTofu;
- `ansible-inventory.json` and `ansible-vars.json` for Ansible;
- `dns-records.json` for DNS synchronization when endpoints publish DNS;
- `onramp-handoff.json` only when a documented shared-host handoff applies.

Generated files are derived private artifacts. Never edit them to make a
consumer work.

### 4. Declare resources in OpenTofu

For a dedicated guest or shared host, add the OpenTofu declaration or module
binding under `infra/opentofu/`, then connect it to the canonical projection.
Cover the applicable resource identity, type, compute, network, storage, image
or template, lifecycle/start behavior, outputs, and replacement addresses.

OpenTofu owns resource lifecycle only. It must not use `local-exec` to install,
configure, or operate the service. A `no-runtime` service normally reuses its
dependency's resource; do not add an independent resource without revisiting
its archetype and catalog ownership.

### 5. Add Ansible convergence

Add or update the playbook in `infra/ansible/playbooks/` and a focused role
under `infra/ansible/roles/`. The catalog's `playbooks` and `inventory` entries
must match these paths and the generated inventory group.

The role should provide:

- FQCN Ansible modules, argument specifications, and safe defaults;
- idempotent installation and configuration tasks;
- immutable or checksum-verified artifacts, package versions, or image
  digests;
- templates, handlers, and validation in a safe order;
- transient secret inputs with `no_log: true` at sensitive boundaries;
- service-local health checks and direct endpoint diagnostics;
- failure-safe cleanup and documented rollback behavior.

Use Proxmox only for resource lifecycle, host-boundary readiness, storage
preparation, bootstrap, or recovery. Steady-state service configuration runs
through direct guest or shared-host access, not `pct` commands or an ambient
inventory.

### 6. Model release, DNS, ingress, and secrets

Store release selection in canonical service fields and catalog policy. Use a
version plus checksum, an immutable image digest, or another catalog-supported
immutable source. Document how `just update` participates, if it does, and how
a rollback is performed through a reviewed canonical change.

For a browser-facing service, add canonical endpoints and DNS metadata, then
let the DNS projection and Ansible synchronization create records. First-class
guests normally use an application plus service-local Caddy; host-contained
workloads follow the documented shared-host Caddy contract. Do not call DNS
APIs from OpenTofu.

Declare secret metadata in the catalog and implement its approved transient
consumer boundary in `scripts/secret_provider.py` and
`scripts/secret_delivery.py` where required. Values belong only in the selected
site's encrypted `secrets.sops.yaml`; never put them in `site.yaml`, fixtures,
projections, command arguments, plans, state, templates, or logs.

### 7. Add state and recovery behavior

For a state-capable service, register the service in
`infra/ansible/vars/service-state.yml`, implement backup and restore handling,
and define the catalog `state_order`. Include application data, databases, and
configuration required for a usable restore, but exclude independently managed
credentials unless their recovery contract explicitly covers them.

Document the disable policy and the effect of a resource replacement or
destroy. Add tests for backup selection, archive validation, restore ordering,
and post-restore health. A non-state-capable service must remain explicitly
unsupported for backup/restore rather than silently inheriting another
service's state contract.

### 8. Add tests and operator guidance

Add focused tests alongside the relevant contracts. At minimum, cover catalog
metadata and dependency closure, canonical schema failures, projection output
and identity, OpenTofu bindings, Ansible syntax/role safety, secret delivery,
and service state where applicable. Add first-run, repeat-run, and
failure-cleanup coverage where static tests cannot prove the behavior.

Create or update an operator document under `docs/` that explains:

- the service boundary and prerequisites;
- canonical fields an operator may set and protected logical paths required;
- normal health and log checks through direct endpoints;
- release update and rollback procedure;
- backup, restore, and recovery evidence for stateful services;
- DNS/HTTPS and shared-host dependencies where applicable.

Link the document from `docs/README.md` and add it to
`docs/documentation-inventory.json` with the appropriate classification.

## Verify the implementation

After the source contract is implemented, rerun the authoring check:

```bash
scripts/python.sh scripts/service-author.py \
  --service-id <service_id> \
  --archetype <archetype> \
  --config-model <ConfigModel> \
  --projection-contract <projection-contract> \
  --provisioning-contract <provisioning-contract> \
  --check-repository . \
  --output /tmp/<service_id>-authoring-manifest.json
```

Pass the same `--stateful`, `--state-contract`, and `--secret` options used to
create the manifest. Then run the catalog-wide read-only contract gate:

```bash
scripts/python.sh scripts/validate-service-contracts.py --repo .
```

`just validate-public` runs the catalog-wide check automatically. The authoring
check verifies repository surfaces; it does not prove the service is deployable
or healthy.

Run focused tests while developing, then the normal public validation:

```bash
just validate-public
```

For an authorized selected-site rollout, continue only after the source checks
pass:

```bash
VALUES_SITE=<site> just validate
VALUES_SITE=<site> just plan
# Apply only after explicit approval of the fresh reviewed plan.
VALUES_SITE=<site> just apply
```

After an approved apply, record direct health, DNS/HTTPS behavior when
applicable, a repeat plan, and a backup/restore rehearsal for stateful
services. See [Canonical readiness](canonical-readiness.md) for the difference
between source validation, planning, convergence, drift, and recovery evidence.

## Completion checklist

A reviewer should be able to answer yes to every applicable item:

- Is the archetype and runtime owner correct?
- Does the catalog declare dependencies, schema, release, inventory, playbooks,
  resource addresses, secret metadata, and state policy?
- Does a strict canonical model own every operator-editable field?
- Do explicit projections supply every OpenTofu and Ansible consumer?
- Does OpenTofu own only resources, while Ansible owns convergence?
- Are artifacts immutable or checksum-verified, and is rollback documented?
- Are protected values declared logically and delivered transiently?
- Do DNS, ingress, direct diagnostics, and shared-host boundaries have one
  documented owner?
- Do stateful services have tested backup, restore, disable, and replacement
  behavior?
- Do public-safe fixtures, focused tests, and operator documentation cover the
  feature?
- Has a fresh selected-site plan been reviewed before any apply?

A missing answer is a design or implementation gap. It is not permission to
introduce an ad hoc variable, generated-file edit, compatibility fallback, or
second configuration source.
