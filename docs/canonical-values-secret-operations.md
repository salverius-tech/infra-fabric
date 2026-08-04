# Canonical secret operations

**Status:** public operational contract. Recipient and key material remain private and external to this repository.

## Boundary

- `site.yaml` contains non-secret canonical configuration.
- `secrets.sops.yaml` is encrypted and site-scoped.
- `.sops.yaml` is private deployment policy for the selected site.
- The external age identity is private operator material and must have restrictive permissions.
- Generated projections, plans, state, inventories, logs, and reports must not contain decrypted values.
- Bootstrap private SSH material is stored only at `secrets.bootstrap.ssh_private_key`, validated against `bootstrap.ssh.public_keys`, and materialized only inside the protected tooling boundary.
- Service values use `services.<service>.secrets.<key>`; provider values use catalog-declared provider namespaces.

## New site prerequisites

1. Create the site scaffold:

   ```bash
   just setup "" <site>
   export VALUES_SITE=<site>
   ```

2. Create the site and recovery age identities in the approved private key-management system. Keep both outside the repository and ordinary runtime environments.
3. Configure the private `.sops.yaml` policy for the exact site bundle and supply the external age identity.
4. Create or update the encrypted bundle with only catalog-approved logical paths.
5. Verify recipient-policy metadata and required logical-path metadata without printing values.
6. Run `just edit-secrets SITE=<site>` for protected edits and `just ssh-initialize SITE=<site>` for explicit bootstrap identity setup.

Setup does not create credentials or initialize the bootstrap key automatically.

## Editing and delivery

Use:

```bash
just edit-secrets SITE=<site>
VALUES_SITE=<site> just validate
```

Secret delivery resolves only required paths for the selected enabled services, passes values transiently to the approved consumer boundary, and removes protected temporary material on completion and failure. Do not put secrets in `site.yaml`, generated projections, OpenTofu variables, state, plans, command arguments, or logs.

## Rotation

1. Generate a replacement site identity through the approved private workflow.
2. Re-encrypt the selected site bundle to the old site identity, new site identity, and recovery identity.
3. Validate policy scope, recipient-set equality, ciphertext identity, and required logical paths.
4. Run non-secret consumer smoke checks and record only metadata.
5. Re-encrypt to the new site identity plus recovery identity.
6. Revoke the old identity only after all bundles and recovery backups are verified.

If rotation fails, restore the prior ciphertext and private-key reference from the approved backup. Do not modify ordinary consumer inputs to bypass a policy mismatch.

## Backup and recovery

Back up ciphertext and value-free manifests, not decrypted secret material. A manifest may contain site identifier, relative bundle path, schema/renderer version, ciphertext hash and size, recipient-policy state, selected source paths, backup ID, and creation time.

Private age identities require separate protected offline backup and access control. Recovery must use a disposable restricted workspace, verify site identity, ciphertext identity, recipient policy, required paths, key permissions, cleanup, and redaction before any approved consumer sees the restored bundle.

## Restore rehearsal

A disposable rehearsal with synthetic values must prove:

1. encrypted bundle and value-free metadata restore successfully;
2. the external key file has restrictive permissions;
3. selected site and policy match;
4. every catalog-required path resolves;
5. values, key material, and sentinels never appear in output or artifacts;
6. temporary material is removed on success, failure, interruption, and termination paths where supported.

A rehearsal is not production deployment evidence. Live identity provisioning, backup storage, and consumer delivery require separate private operational approval.
