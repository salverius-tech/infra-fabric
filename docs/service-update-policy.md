# Service update policy

Managed services should use deterministic version pins and the normal reviewed workflow:

```bash
VALUES_SITE=<site> just update
VALUES_SITE=<site> just validate
VALUES_SITE=<site> just plan
VALUES_SITE=<site> just apply
```

`just update` applies the release-age safety hold before changing supported pins. Its output includes a deterministic, public-safe **Service update policy (catalog)** status section. Those service statuses are derived from the `update_policy` entry in `infra/services.json`, rather than a second hard-coded list in the updater. After any update, review the diff and plan before applying.

## Managed pins

A service belongs in `just update` when the repo can identify a specific upstream release and update a deterministic local pin. The catalog marks Forgejo and Forgejo runner as `MANAGED`; the runner status also covers its repository-owned Docker Compose and `just` pins. The catalog marks SSSF `MANAGED` for its repository-owned uv, Pi, and Bun version/checksum pins; its upstream application commit remains an operator-reviewed change.

For downloadable tools or archives, prefer a version plus checksum. If upstream artifacts are mutable or unversioned, cache the reviewed artifact in ignored private storage and install from that cache during `just apply`.

## Technitium

Technitium DNS is managed by Ansible and must not be upgraded by rerunning an upstream installer. The current implementation:

- Pins a version and portable tarball SHA256 in private values.
- Downloads the versioned archive from the Technitium archive endpoint.
- Optionally stages a controller-side archive cache configured with `technitium_artifact_path`.
- Compares the installed-version marker with the requested pin.
- Validates the archive layout and checksum before activation.
- Performs health checks and retains rollback state during activation.

Technitium is not currently a target of `just update`. To change it, update the private version/checksum together, then run `just validate`, review `just plan`, and apply only after approval. Do not use the upstream installer as a routine update mechanism.

## Catalog status meanings

Every cataloged service must declare one update policy with a public-safe detail string:

- `MANAGED` — `just update` checks the declared repository or canonical release pins after the release-age hold. It never applies infrastructure or service changes.
- `MANUAL` — an operator changes the reviewed immutable image, release, or paired checksum through the normal `validate` → `plan` → approved `apply` workflow.
- `UNMANAGED` — the repository has no package-update implementation for that service. Currently this applies to the Tailscale client, which is installed only when missing.

The catalog status is an update-policy boundary, not a claim that a service is healthy or operational. It contains no private values, endpoints, or release lookup results.

## Other update boundaries

`just update` manages repository-owned SSSF uv, Pi, and Bun version/checksum pins in addition to OpenTofu, TFLint, Forgejo, Forgejo runner, Docker Compose, and just pins. Updating an SSSF pin does not download a guest artifact: before apply, an operator must review and place the matching archive in `/var/lib/infra-fabric/artifacts/sssf/`. Caddy build inputs are version-pinned but do not yet have an automated update target. General guest OS upgrades are also outside the `just update` workflow; the Tailscale client status is cataloged as `UNMANAGED`.

For components not managed by `just update`, document the reviewed pin or package policy explicitly and avoid ad hoc production upgrades.

## Guest security updates

Guest operating-system updates are intentionally **operator-initiated**, not unattended. The current policy is:

- apply guest package updates only through an approved Ansible change in the normal reviewed workflow;
- disable automatic reboot behavior; report any reboot requirement for a separately reviewed maintenance action;
- scope maintenance to explicitly selected services/guests and record restart impact before the change;
- do not couple guest package updates with a managed application release-pin change;
- keep Caddy and Tailscale within their existing explicit provenance/update paths rather than silently treating them as general OS updates;
- treat Technitium as a critical-DNS exception: use its version/checksum/health/rollback workflow, never a blanket package-upgrade action.

This policy is a design boundary, not an unattended-update implementation. Any future security-update role must add LXC and VM coverage, no-auto-reboot verification, restart/reboot reporting, and an explicit opt-in inventory contract before it is enabled.
