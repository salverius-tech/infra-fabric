# Canonical architecture and ownership

This repository is a public-safe runbook for declaring and operating site infrastructure. The selected canonical site is the authority; every other representation is either protected input, derived output, runtime state, or external platform state.

## Source and output layers

```text
private site repository
  site.yaml -------------------- non-secret canonical model
  .sops.yaml ------------------- private SOPS/age policy
  secrets.sops.yaml ------------- encrypted logical secrets
       |
       v
canonical renderer and validators
       |
       +--> generated/terraform.auto.tfvars.json -- OpenTofu projection
       +--> generated/ansible-inventory.json ------ Ansible inventory
       +--> generated/ansible-vars.json ------------ Ansible variables
       +--> generated/dns-records.json ------------- DNS synchronization input
       +--> generated/manifest.json ---------------- identity and provenance
       |
       +--> OpenTofu ------------------------------- Proxmox resources and storage
       +--> Ansible -------------------------------- guest/service convergence
       +--> direct-access readiness ---------------- SSH trust and guest probes
```

Generated files are derived and must never be edited manually. The renderer may recreate them at any time. Runtime files such as host-key material, plans, state, and backups are not canonical projections.

## Ownership boundaries

| Concern | Authority | Consumer |
| --- | --- | --- |
| Site identity, lifecycle, policy | `site.yaml` | validation and mutation gates |
| Resource type, VM/LXC identity, network, storage | `site.yaml` | OpenTofu and generated inventory |
| Service selection and endpoints | `site.yaml` plus catalog contracts | projections, DNS, Caddy, Ansible |
| Service releases and immutable pins | `site.yaml` and catalog policy | OpenTofu/Ansible service roles |
| Secret values | encrypted `secrets.sops.yaml` | transient secret delivery |
| Secret recipient/decryption policy | private `.sops.yaml` and external age identity | SOPS tooling |
| Proxmox resource lifecycle | OpenTofu | Proxmox provider |
| Guest identity and service convergence | Ansible | direct guest endpoints |
| DNS records | canonical DNS projection | Technitium synchronization |
| HTTPS ingress | service Caddy contract | Caddy roles and provider secret delivery |
| Durable service state | service state policy and private backups | backup/restore workflows |

OpenTofu owns resource lifecycle. Ansible owns service configuration. OpenTofu must not use `local-exec` for service configuration, and Ansible service roles must not use Proxmox `pct` as their steady-state control plane.

## Operational sequence

1. Create or select the private site directory.
2. Complete `site.yaml`, `.sops.yaml`, `secrets.sops.yaml`, and the external age identity.
3. Run the explicit protected bootstrap identity workflow when required.
4. Run `VALUES_SITE=<site> just validate`.
5. Run `VALUES_SITE=<site> just plan` and review the saved plan.
6. Approve and run `VALUES_SITE=<site> just apply`.
7. Verify direct access, service health, DNS/HTTPS behavior, and a repeat plan.
8. Exercise state backup/restore for affected stateful services.

A passing validation or plan does not prove service convergence, live health, drift-free operation, or recovery readiness.

Direct `tofu plan`, `tofu apply`, and destroy execution are unsupported operator paths. Use the repository `just plan` and `just apply` wrappers so canonical projections, retained-state acknowledgement, saved-plan metadata, destructive classification, and site policy are enforced together. When intentionally disabling a service whose canonical `disable_policy` is `retain`, rerun planning with `INFRA_ALLOW_DESTROY=1` only after deciding that the retained resource may be removed; apply remains separately gated by the reviewed saved plan.

Supported wrappers serialize operations with a persistent private lock in the selected site directory. This enforces a single-controller/single-writer model only when every operator uses the same shared values filesystem and repository wrappers; it is not a distributed lock and cannot protect direct OpenTofu CLI use.

Immediately before a saved plan is applied, the wrapper re-verifies plan metadata and creates a checksum-bound, mode-`0700` snapshot under `values/sites/<site>/state-backups/` when local state already exists. Snapshot files and manifests are mode `0600`, installation is atomic, and the newest ten snapshots are retained. The canonical apply path also creates a read-only execution snapshot containing the reviewed plan and metadata, canonical site model, generated projections, encrypted secret bundle, and exact-site SOPS policy. Storage preparation, provider credential resolution, OpenTofu apply, and Ansible orchestration consume that snapshot rather than mutable live inputs; the newest five execution snapshots are retained as private evidence.

Verify or restore state only while all other controllers are stopped; the restore command acquires the same site lock and refuses to replace existing state without explicit acknowledgement:

```text
python3 scripts/state-snapshot.py verify --snapshot values/sites/<site>/state-backups/<snapshot>
python3 scripts/state-snapshot.py restore --snapshot values/sites/<site>/state-backups/<snapshot> --state values/sites/<site>/terraform.tfstate --replace-existing
```

A restore validates permissions, size, and checksum before atomically replacing the local state file. It does not migrate state or provide distributed locking; inspect and preserve the current private state separately before an operator-approved recovery.

## Site lifecycle states

- `disposable`: may be created and destroyed deliberately; use public-safe fixtures and retain no production assumptions.
- `persistent`: normal operational site; destruction requires explicit review and the site policy gate.
- `protected`: cannot be mutated through normal apply/destroy workflows.

`site.allow_apply` and `site.allow_destroy` are policy gates, not substitutes for operator approval. Production sites must not allow destroy.

## Private artifacts

Keep these outside public source and do not print their contents:

- age identities and recipient material;
- encrypted bundles and private SOPS policy;
- generated projections;
- plan files and metadata;
- Terraform/OpenTofu state and backups;
- controller/service host-key files;
- service-state archives and checksums;
- live endpoints and credentials.

For command details, use [Canonical site quick start](canonical-quick-start.md), [Public Just recipes](just-recipes.md), and [Canonical teardown](canonical-teardown.md).
