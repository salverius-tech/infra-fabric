# Canonical readiness matrix

A successful structural validation is not production readiness. Record each gate before an approved apply.

| Gate | Evidence | Required before apply |
| --- | --- | --- |
| Site model | Selected `site.yaml` parses and satisfies the canonical schema. | Yes |
| Catalog binding | Enabled services have complete catalog ownership, schema, projection, and secret metadata. | Yes |
| Generated projections | Renderer output is current, value-free where required, and not hand-edited. | Yes |
| Protected bundle | SOPS policy and encrypted bundle exist; required logical paths are complete; external age identity is readable. | Yes |
| Provider preflight | OpenTofu initializes, refreshes, and evaluates the selected site without unreviewed errors. | Yes |
| Plan review | Saved plan and metadata match the selected site, target scope, and replacement/destruction controls. | Yes |
| Host trust | Management and service host identities are verified through approved trust material. | Yes |
| Convergence | Bootstrap identity, operator identity, service roles, handlers, and health checks complete idempotently. | Yes |
| Post-change drift | A repeat plan reports no unexpected changes. | Yes |
| Recovery rehearsal | Stateful backups, restore paths, and service-specific recovery checks have been exercised for the affected services. | Stateful services |

`just validate` covers structural and provider-independent checks. `just plan` adds provider-backed refresh and local generated artifacts. Neither command proves convergence, post-change drift, or recovery.

## Apply boundary

`just apply` is an infrastructure mutation. Review the saved plan, confirm the selected site and target, and explicitly approve the resource changes. Destructive and stateful controls are separate gates; setting an environment variable is not approval by itself.
