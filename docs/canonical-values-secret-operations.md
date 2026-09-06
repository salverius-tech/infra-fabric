# Canonical secret operations

**Status:** public operational contract. Recipient and key material remain private and external to this repository.

## Boundary

- `site.yaml` contains non-secret canonical configuration.
- `secrets.sops.yaml` is encrypted and site-scoped.
- `.sops.yaml` is private deployment policy for the selected site.
- The external age identity is private operator material and must have restrictive permissions.
- Generated projections, plans, state, inventories, logs, and reports must not contain decrypted values.
- Bootstrap private SSH material is stored only at `secrets.bootstrap.ssh_private_key`, validated against `bootstrap.ssh.public_keys`, and materialized only inside the protected tooling boundary.
- Service values use `services.<service>.secrets.<key>`; provider values use `secrets.providers.<provider>.<key>`.
- The current provider paths are `secrets.providers.proxmox.api_token` and `secrets.providers.cloudflare.api_token`; the operator identity password is `secrets.operator.password`.

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

### 1Password-backed identity backup

A password manager vault (for example 1Password) is an approved location for the separate offline identity copy: it is client-side encrypted, access-controlled, and independent of the controller host. The identity file is small plain text (a comment header with the public key plus one `AGE-SECRET-KEY-...` line) and stores verbatim as a secure note.

`scripts/site-age-identity.sh` wraps the lifecycle; it never prints key material and refuses to overwrite without `--force`. The site is taken only from an explicit `SITE=<site>` argument or `VALUES_SITE=<site>`; there is no implicit default site. `--force` is accepted only for `store` and `fetch` and may appear before or after the site argument. Vault operations require the host `op` CLI, an interactive `op signin`, `OP_VAULT`, and host `python3` plus `age-keygen`; key material is never echoed. 1Password integration is optional: the toolchain always works from the identity file alone, and manual recovery (paste contents into place, then run the same verification) remains fully supported.

- **Create**: `VALUES_SITE=<site> scripts/site-age-identity.sh generate`
- **Store external copy**: sign in with `op signin`, set `OP_VAULT`, then `VALUES_SITE=<site> scripts/site-age-identity.sh store`. Store the full file contents including the public-key comment.
- **Recover on a fresh machine**: install the age/sops toolchain and optionally `op`; then either `VALUES_SITE=<site> scripts/site-age-identity.sh fetch` or manually recreate the file at the documented path with `0600` permissions from the vault item.
- **Verify before trusting** (mandatory after any recovery): `VALUES_SITE=<site> scripts/site-age-identity.sh verify` performs a decryption round-trip against the real site bundle. A wrong or truncated key fails closed here before any consumer touches secret material.

`store` takes one private immutable snapshot of the local identity at operation start, then reads the vault item back as its `notesPlain` JSON field (shared readback for `store` and `fetch`) and byte-compares it against that snapshot before any promotion; a concurrent local rotation applies to a later store operation. On `--force` it creates and verifies a new uniquely-titled staged vault item, renames the existing item by its item id to a `previous-*` backup title, then promotes the staged item to the canonical title; the prior item is never deleted. Without `--force` an existing canonical item is left unchanged. `fetch` stages the vault notes, validates them as an age identity, and publishes locally only after validation, preserving any existing local file on failure.

These steps are not transactional and there is no automatic retry or cleanup. A partial failure may leave a staged `*.stage-*` title and/or a `*.previous-*` backup title in the vault, with the canonical title absent. Reconcile manually through the 1Password UI using the item ids, and verify the recovered identity before any cleanup. The old archived `previous-*` key may still be needed to decrypt older encrypted backups, so do not delete it until those backups are verified. Local temporary files are removed on normal completion, error, and catchable signals; cleanup is not guaranteed after an uncatchable `SIGKILL`.

Do not use a 1Password service-account token stored on the controller to automate these steps; that would reintroduce a host-local single point of failure with vault-wide reach. Interactive `op signin` by the operator keeps the vault outside the machine's failure domain. Re-store the identity in the vault as a mandatory step of any rotation.

## Restore rehearsal

A disposable rehearsal with synthetic values must prove:

1. encrypted bundle and value-free metadata restore successfully;
2. the external key file has restrictive permissions;
3. selected site and policy match;
4. every catalog-required path resolves;
5. values, key material, and sentinels never appear in output or artifacts;
6. temporary material is removed on success, failure, interruption, and termination paths where supported.

A rehearsal is not production deployment evidence. Live identity provisioning, backup storage, and consumer delivery require separate private operational approval.
