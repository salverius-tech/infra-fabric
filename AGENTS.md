# AGENTS.md

Guidance for coding agents working in this repository.

## Overview

This repository is a public-safe, reusable runbook for canonical site infrastructure: Proxmox resources, Technitium DNS, Caddy, Forgejo, Infisical, Hermes, and shared-host application substrates.

The selected canonical site model is authoritative:

- `values/sites/<site>/site.yaml` owns non-secret site, resource, service, endpoint, release, storage, and state configuration.
- `values/sites/<site>/secrets.sops.yaml` owns encrypted protected logical values.
- `values/sites/<site>/.sops.yaml` and external age identities are private deployment policy/material.
- `values/sites/<site>/generated/` is derived and must never be edited.

Tracked source must remain public-safe and use placeholders such as `example.internal`, `apps.example.net`, and RFC 5737 addresses. Real endpoints, domains, addresses, credentials, state, plans, identities, and backups belong in private external storage.

## Safety rules

- Do not run `tofu apply`, `terraform apply`, destroy, import, or state surgery without explicit user approval.
- Do not commit secrets, live site values, identities, state, plans, generated private artifacts, or credentials to the public repository.
- Do not mutate production routers, firewalls, DNS infrastructure, or service guests without explicit approval.
- Service version changes use managed pins/checksums and the public `just update` → `just validate` → `just plan` → approved `just apply` workflow.
- Prefer direct service endpoints for diagnostics. Use Proxmox access for resource lifecycle, host-boundary readiness, storage preparation, bootstrap, and recovery.
- Keep service orchestration in Ansible and infrastructure/resource declaration in OpenTofu. Do not use OpenTofu `local-exec` for service configuration.
- Generated secrets and protected values must remain encrypted or transient, must be idempotent, and must never appear in logs or responses.

## Public command surface

The supported recipes are:

```text
just
just setup "" <site>
just edit-secrets SITE=<site>
just ssh-initialize SITE=<site>
VALUES_SITE=<site> just update
VALUES_SITE=<site> just validate
VALUES_SITE=<site> just plan
VALUES_SITE=<site> just apply
```

`edit-secrets` and `ssh-initialize` are explicit protected-input operations. `apply` is the only normal infrastructure mutation operation and requires explicit approval of a fresh verified plan. Private implementation recipes are not operator commands.

## Workflow

1. Inspect the relevant canonical model, catalog, schema, projection, and tests before changing code.
2. Keep all tracked examples public-safe.
3. Run `VALUES_SITE=<site> just validate` after source or canonical fixture changes.
4. If a plan is requested, run `VALUES_SITE=<site> just plan` and summarize creates, changes, replacements, and destroys without exposing private values.
5. Apply only after explicit approval using `VALUES_SITE=<site> just apply`.
6. If plan verification fails, correct canonical inputs and rerun plan; never edit saved plans or generated projections.
7. For service changes, use the canonical service-authoring contract and add catalog/schema/projection/OpenTofu/Ansible/secret/state/test/doc coverage as applicable.

## Design doctrine

- Canonical site configuration is the only normal authoring surface.
- Service identity, ownership, dependencies, runtime, releases, state, and allowed configuration belong in the catalog and typed canonical model.
- Consumer projections are derived from the canonical model and must be identity-verified before use.
- Secret delivery is explicit and transient. Logical paths use `services.<service>.secrets.<key>` and catalog-declared provider namespaces.
- DNS synchronization belongs in Ansible. Do not call DNS APIs from OpenTofu resources.
- New browser-facing first-class guests normally use app plus service-local Caddy; shared-host services use the documented shared Caddy contract.
- A service-authoring manifest is design evidence, not permission to create secrets, site values, state, plans, or infrastructure.

## Verification and response hygiene

Before finalizing work, run relevant tests and `git diff --check`. Distinguish static validation, provider-backed planning, live health, and recovery evidence. Never print credentials, private keys, tokens, recipient material, live endpoints, state contents, or decrypted values.
