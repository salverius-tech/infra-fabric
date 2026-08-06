# Canonical teardown and site retirement

Teardown is a separate guarded full-site workflow because it removes resources and may remove durable service data. There is no unguarded `just destroy` recipe and direct OpenTofu lifecycle commands are not supported operator paths.

## Before teardown

1. Confirm the selected site and lifecycle policy.
2. Confirm the site is not production or protected.
3. Decide whether service-state backups are required. Do not create backups automatically if the site is intentionally disposable.
4. Ensure every controller uses the repository wrappers on the same selected-site filesystem. The wrapper holds the site lock while the plan or teardown executes; it is not a distributed lock.
5. Do not remove host-key material until the destroy has completed.

The saved destroy plan is the review boundary. The wrapper binds it to its hash, expiration, site, canonical model/projection identity, Git commit, input hashes, full-site scope, and destructive summary. Never bypass that boundary against a shared or production state.

## Plan the teardown

From the repository root, replace `<site>` with the selected site:

```bash
VALUES_SITE=<site> just teardown-plan
```

Review the complete output. Confirm that the resources, storage, image/template artifacts, and outputs belong only to the selected site. If the plan is unexpected, stop and correct the canonical inputs or state reconciliation before applying.

## Apply the teardown

After explicit approval of the reviewed destroy plan, use the literal approval argument:

```bash
VALUES_SITE=<site> just teardown-apply --approve
```

Immediately before mutation, the wrapper re-verifies the reviewed metadata, seals an immutable execution snapshot, and creates a local state snapshot. The destroy plan artifacts are consumed after the attempt; retain the state snapshot, execution snapshot, and host-key material for diagnosis. Do not delete state or host-key files until the actual resource result is understood.

## After successful teardown

Run a fresh `VALUES_SITE=<site> just plan` only after separately approving the read-only provider contact. Do not use raw state commands to decide whether teardown completed.

For a permanently retired disposable site, remove only artifacts that are no longer needed:

- generated projections;
- empty state;
- transient host-key material;
- obsolete legacy files;
- service-state archives when recovery is no longer desired.

Retain `site.yaml`, `.sops.yaml`, and `secrets.sops.yaml` if the canonical definition should remain available for future recreation. Generated projections and state can be recreated; encrypted secret values cannot be reconstructed without their source.
