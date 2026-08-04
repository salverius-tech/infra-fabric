# Canonical site quick start

This is the supported operator path for a new or existing canonical site.

## 1. Create site scaffolding

From the repository root:

```bash
just setup "" <site>
export VALUES_SITE=<site>
```

This creates or preserves the selected site directory and public-safe `site.yaml` scaffold. If no site-specific fixture exists, setup renders `scaffold/sites/_template/site.yaml` and replaces its example site name. It does not create credentials or a private SOPS policy.

## 2. Establish private secret prerequisites

Outside tracked public source, provide the selected site’s:

- `.sops.yaml` policy;
- encrypted `secrets.sops.yaml` bundle;
- external age identity file with restrictive permissions.

The private site files are:

```text
values/sites/<site>/.sops.yaml
values/sites/<site>/secrets.sops.yaml
```

The bundle must use canonical paths such as `secrets.providers.<provider>.<key>`, `secrets.bootstrap.ssh_private_key`, `secrets.operator.password`, and `services.<service>.secrets.<key>` as required by the catalog. Never place plaintext credentials in `site.yaml`, generated projections, plans, state, or documentation.

## 3. Edit canonical inputs

Edit non-secret configuration in:

```text
values/sites/<site>/site.yaml
```

Use the encrypted editor for protected values:

```bash
just edit-secrets SITE=<site>
```

This changes encrypted ciphertext and requires the selected policy and external age identity.

## 4. Initialize the canonical bootstrap identity

After the site model, SOPS policy, encrypted bundle, and external age identity are ready:

```bash
just ssh-initialize SITE=<site>
```

This is an explicit secret-dependent operation. It validates the declared bootstrap public-key contract, updates the encrypted private identity, and refreshes derived projections. Setup, validation, planning, and apply do not invoke it automatically.

## 5. Validate

```bash
VALUES_SITE=<site> just validate
```

Validation checks the public repository, canonical model and catalog, projection contracts, OpenTofu and Ansible structure, tests, and private site wiring. It does not prove provider-backed plan equivalence, live host readiness, service health, or restore acceptance.

## 6. Plan

```bash
VALUES_SITE=<site> just plan
```

Planning is non-mutating to infrastructure but may contact the configured provider and refresh private derived projections. Review the saved plan and metadata under the selected site directory. Treat generated files and plan artifacts as private and derived.

Review at minimum:

- creates, updates, replacements, and destroys;
- service and resource identity;
- addresses, hostnames, VLANs, storage, and image pins;
- bootstrap/operator identity changes;
- secret delivery requirements;
- provider and host-readiness failures;
- stateful-service and backup implications.

## 7. Apply only after approval

```bash
VALUES_SITE=<site> just apply
```

Apply requires a fresh verified plan and explicit operator approval. It mutates infrastructure and runs the approved service orchestration chain. Afterward, verify service health, direct endpoints, DNS/HTTPS, and a repeat plan for drift.

## Source ownership

```text
Operator-edited: site.yaml, .sops.yaml, secrets.sops.yaml
Derived: generated projections, plan metadata, plan artifacts
External/private: age identities, recipient policy, credentials, state backups
```

For recipe details and controlled rollout flags, see [Public Just recipes](just-recipes.md). For failures, start with the failing gate named by the command; do not bypass it by editing generated files or passing unreviewed provider values.
