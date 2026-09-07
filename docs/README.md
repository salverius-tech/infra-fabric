# Documentation index

Public-safe documentation for canonical site infrastructure.

## Start here

- [Canonical site quick start](canonical-quick-start.md) — initialize a site, establish protected prerequisites, validate, plan, and apply safely.
- [Canonical architecture and ownership](canonical-architecture.md) — source layers, generated projections, OpenTofu/Ansible boundaries, lifecycle, and private artifacts.
- [Public Just recipes](just-recipes.md) — supported commands, parameters, side effects, and safety gates.
- [Service catalog and implementation map](service-catalog.md) — every catalog service, runtime owner, dependency, state behavior, and implementation coverage requirement.
- [Canonical service authoring](canonical-service-authoring.md) — end-to-end guide for choosing an archetype and implementing catalog, schema, projections, OpenTofu, Ansible, secrets, state, tests, and operations.
- [Canonical readiness matrix](canonical-readiness.md) — distinguish structural validation, provider planning, convergence, drift, and recovery gates.
- [Canonical troubleshooting](canonical-troubleshooting.md) — diagnose site, SOPS, projection, provider, host-trust, service, storage, and drift failures.
- [Governance records](governance/package-completion.md) — source completion, original audit dispositions, approved decisions, and environment-specific acceptance evidence.

## Canonical operations

- [Canonical secret operations](canonical-values-secret-operations.md) — SOPS/age policy, bootstrap identity, rotation, backup, recovery, and restore rehearsal.
- [Canonical teardown and site retirement](canonical-teardown.md) — reviewed destroy plans, state handling, artifact cleanup, and retirement boundaries.
- [Service update policy](service-update-policy.md) — managed releases, pins, checksums, rollback, and maintenance windows.
- [Service operations matrix](service-operations.md) — catalog-derived health, logs, credentials, update/rollback, state, and recovery routing for every registered service.
- [Hermes tuning](hermes-tuning.md) — managed Hermes runtime tuning.
- [Hermes Control operations](hermes-control-operations.md) — companion-stack operation and verification.
- [Hermes-independent controller recovery](hermes-independent-recovery.md) — recover the canonical workflow without depending on Hermes.
- [Managed service-state backup and restore](service-state-backup.md) — state backup and restore contracts.
- [Super Simple Software Factory](sssf.md) — dedicated VM installation, workspace, visualizer, health, and state operations.
- [Hermes state backup and restore](hermes-state-backup.md) — Hermes-specific state handling.
- [Onramp app-platform contract](onramp-app-platform-contract.md) — ownership and placement boundaries for shared-host applications.
- [Onramp host runbook](onramp-host-runbook.md) — canonical shared-host substrate operation.
- [Onramp SearXNG handoff](onramp-searxng-handoff.md) — shared-host service ownership contract.
- [Debian baseline](debian-baseline.md) — guest and host operating-system policy.
- [Development acceptance gate runbook](development-acceptance-gate-runbook.md) — exact, separately approved development acceptance procedures and boundaries.

## Contributor and architecture references

- [Documentation authority inventory](documentation-inventory.json) — maintained classification of current public documentation.
- [Production acquisition inventory](production-acquisition-inventory.json) — source-only register of every tracked production image/network installer consumer, its static integrity evidence, and explicit unresolved paths.
- [Development environment](development-environment.md) — disposable development workflow and implementation safety.
- [Original audit finding dispositions](governance/audit-dispositions.md) — commit-qualified original finding provenance and static remediation evidence.
- [Explicit approved decisions](governance/explicit-decisions.md) — closed decision authority with commit-qualified references.
- [Environment-specific acceptance matrix](governance/acceptance-matrix.md) — development-only evidence and unevidenced environment boundaries.

- [Normalized plan equivalence](normalized-plan-equivalence.md) — report-only comparison schema and boundaries.

All current documents assume a selected canonical site. Generated projections are derived and must not be edited. Live site values, state, credentials, identities, and plans remain private and are not examples in this documentation. The scaffold template is the complete public-safe starting shape for `site.yaml`; the matching SOPS policy and encrypted bundle are always created privately.
