# Canonical development environment

This guide covers disposable development work for a selected canonical site. It is for implementing and verifying repository changes without using production resources, credentials, state, backups, or live service guests.

## Preconditions

Use a private values repository containing a development site:

```text
values/sites/dev/site.yaml
values/sites/dev/.sops.yaml
values/sites/dev/secrets.sops.yaml
```

Keep the SOPS age identity external and use only public-safe fixtures in tracked source.

## Development lifecycle

```bash
export VALUES_SITE=dev
just validate
just plan
# apply only after explicit approval and only against the disposable development site
just apply
```

Reset or rebuild the development site through a reviewed plan. Never reuse production values, state, backups, databases, or credentials.

## Implementing a service

Before coding, generate and review an authoring manifest:

```bash
scripts/python.sh scripts/service-author.py \
  --service-id <service_id> \
  --archetype dedicated-lxc \
  --config-model <ConfigModel> \
  --projection-contract <projection-contract> \
  --provisioning-contract <provisioning-contract> \
  --output /tmp/<service_id>-authoring-manifest.json
```

Then follow [Canonical service authoring](canonical-service-authoring.md). A service change is incomplete until its catalog, typed model, projections, infrastructure, Ansible role, secret delivery, state policy, fixtures, tests, and operator documentation are aligned.

## Ansible contract

Keep resource declaration in OpenTofu and guest configuration in Ansible. New or changed roles should provide:

- pinned artifacts and checksums;
- explicit transient secret inputs;
- idempotent tasks and restart handlers;
- argument specifications and safe defaults;
- service-local health checks;
- direct-access diagnostics;
- failure-safe behavior and rollback notes;
- tested LXC/VM assumptions.

Do not use OpenTofu `local-exec` for service configuration.

## DNS and HTTPS

Add public-safe endpoint placeholders to canonical fixtures and keep actual site records private. Synchronize DNS through the documented Ansible workflow. Browser-facing first-class guests normally use application plus service-local Caddy; shared-host services follow the shared-host Caddy contract. Verify both direct service access and the intended development HTTPS route without printing private endpoint or certificate material.

## Test-first workflow

Write a focused failing test before implementing a new behavior. Run the smallest test first, implement the minimum behavior, then run the relevant suite and repository validation in the tooling container.

Useful focused suites include:

```bash
scripts/python.sh -m unittest -v \
  tests.test_service_catalog \
  tests.test_canonical_values \
  tests.test_ansible_canonical_compat \
  tests.test_secret_delivery \
  tests.test_service_state \
  tests.test_opentofu_output_bindings \
  tests.test_service_author
```

For stateful services, also test first run, repeat run, failure cleanup, backup, restore, and disable behavior. Add disposable guest smoke coverage where static tests cannot prove systemd, networking, storage, or integration behavior.

## Verification gates

Run `VALUES_SITE=dev just validate`, then a reviewed `VALUES_SITE=dev just plan`. Inspect resource identity, addresses, storage, releases, service dependencies, secret delivery requirements, and destructive changes. Apply only after explicit approval. Confirm direct service health and a repeat plan after any approved development apply.

## Agent safety

Keep tracked files public-safe. Do not read or expose private site values unnecessarily. Do not apply, destroy, import, restore, rotate identities, alter state, or mutate network infrastructure without explicit approval. Prefer reversible disposable development changes and preserve a reset path.
