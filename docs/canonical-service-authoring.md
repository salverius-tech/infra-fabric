# Canonical service authoring

A new service is complete only when its canonical model, catalog, projections, provisioning, orchestration, secret delivery, state policy, tests, and operator contract agree. Adding a row to `infra/services.json` alone is not a supported service implementation.

## Start with a public-safe authoring manifest

Generate a reviewable contract before editing implementation files:

```bash
scripts/python.sh scripts/service-author.py \
  --service-id <service_id> \
  --archetype dedicated-lxc \
  --config-model <ConfigModel> \
  --projection-contract <projection-contract> \
  --provisioning-contract <provisioning-contract> \
  --output /tmp/<service_id>-authoring-manifest.json
```

The tool is generate-only. It never creates site values, SOPS policy, encrypted secrets, identities, inventory, state, plans, projections, provider resources, or repository stubs. Review the manifest before implementation.

After implementation, run the non-mutating surface check against the repository:

```bash
scripts/python.sh scripts/service-author.py \
  --service-id <service_id> \
  --archetype dedicated-lxc \
  --config-model <ConfigModel> \
  --projection-contract <projection-contract> \
  --provisioning-contract <provisioning-contract> \
  --check-repository . \
  --output /tmp/<service_id>-authoring-manifest.json
```

The check requires catalog registration with the required schema/release/override/field/runtime metadata and representations in canonical schema, projections, OpenTofu, Ansible, tests, scaffold fixtures, state policy when stateful, and operator documentation. For services with catalog-required secrets, pass matching `--secret logical_path:classification:environment` entries so the manifest can be checked against the catalog without exposing values. It does not claim the service is deployable; run the normal validation and reviewed site plan separately.

To validate every registered public service contract in one read-only gate:

```bash
scripts/python.sh scripts/validate-service-contracts.py --repo .
```

The catalog-wide gate also validates typed metadata semantics: runtime-owned services need release sources, Terraform addresses, replacement contracts, and inventory mappings; shared-host and no-runtime entries may omit guest-only contracts; dependencies must reference registered services; stateful entries need a state order; and every declared secret needs supported classification and environment metadata. `just validate-public` runs this catalog-wide check automatically. Reviewers and CI can request a deterministic JSON report with `--report <path>`; it contains only service IDs, statuses, errors, and summary counts.

Supported archetypes:

- `dedicated-lxc` — service owns an LXC resource and guest configuration;
- `dedicated-vm` — service owns a VM resource and guest configuration;
- `shared-host` — service runs on an already managed shared host and does not own a new guest unless explicitly declared;
- `no-runtime` — integration, provider, or control-plane behavior without a service guest.

## Contract matrix

| Concern | Required implementation surface |
|---|---|
| Catalog | `infra/services.json`, parsed and validated by `scripts/service_catalog.py` |
| Canonical schema | Typed configuration in `scripts/canonical_values.py`, or an explicit reviewed exemption |
| Resource ownership | `services.tf`, `variables.tf`, per-service OpenTofu files, lifecycle/state addresses, and outputs when applicable |
| Projection | `scripts/canonical_projections.py`, with explicit OpenTofu and Ansible consumer mappings |
| Ansible | Playbook, role, defaults, argument spec, templates, handlers, health checks, and inventory mapping |
| Secrets | Catalog logical paths, classifications, consumer environment bindings, `secret_provider.py`, `secret_delivery.py`, and delivery tests |
| State | `infra/ansible/vars/service-state.yml`, backup paths, restore behavior, disable policy, and restore tests when stateful |
| Release | Immutable version/source/checksum or image digest and update/rollback behavior |
| Scaffold | Public-safe canonical fixture under `scaffold/sites/` and service configuration fixtures |
| Tests | Catalog parity, canonical model, projections, OpenTofu bindings, Ansible contract, secret delivery, state, and health tests |
| Documentation | Operator setup, update, diagnostics, backup/restore, rollback, and direct-access runbook |

## Implementation sequence

1. Define the service archetype, ownership boundary, dependencies, runtime user, network endpoint, state capability, release source, and disable behavior.
2. Add the catalog contract and dependency ordering.
3. Add the typed canonical configuration model or explicit no-configuration exemption.
4. Add canonical resource/service fixture data with public-safe placeholders.
5. Add explicit projection mappings for every OpenTofu and Ansible consumer. Do not infer variable names from service IDs.
6. Add OpenTofu resource/module declarations, storage, image, lifecycle, outputs, and replacement/state addresses for resource-owning services.
7. Add Ansible orchestration with idempotent tasks, pinned artifacts, explicit secret inputs, handlers, health checks, direct diagnostics, and failure-safe behavior.
8. Declare only secret metadata in the catalog: logical path, class, consumer environment, condition, and state-exposure policy. Never put secret values in `site.yaml`, projections, plans, state, arguments, or logs.
9. Add state backup/restore and disable/destroy behavior for stateful services.
10. Add public-safe fixtures, conversion mappings only where required by the canonical source contract, and focused tests.
11. Add the operator document and link it from `docs/README.md`.
12. Run static validation, focused tests, a reviewed selected-site plan, service smoke checks, repeat-plan drift checks, and restore rehearsal where applicable.

## Acceptance gates

### Public/static gates

- catalog dependency and service-registry parity;
- strict canonical schema validation;
- complete projection and consumer mapping;
- OpenTofu format/validate and output-binding checks;
- Ansible syntax, lint, role contract, and argument-spec checks;
- secret path/classification/environment-binding coverage;
- release pin/checksum or immutable image validation;
- public-safety and placeholder scans;
- first-run, repeat-run, and failure-cleanup tests.

### Private/live gates

- selected site SOPS policy and required secret paths;
- provider-backed reviewed plan;
- host identity/readiness and direct endpoint checks;
- service installation/configuration smoke test;
- DNS/HTTPS verification where applicable;
- post-apply repeat plan with acceptable drift;
- backup/restore rehearsal for stateful services;
- explicit approval before any infrastructure mutation.

## Service authoring manifest fields

The generated manifest records only public-safe metadata:

- service ID and archetype;
- configuration, projection, provisioning, and state contract identifiers;
- secret logical paths with classification and environment names, never values;
- required implementation files and review gates;
- explicit safety flags proving that no repository or infrastructure mutation occurred.

A manifest that lacks a required contract is a design rejection, not permission to fill the gap with an ad hoc variable or a second configuration source.
