# Canonical Values Secret Operations

**Status:** public operational contract; recipient and key material remain private and unconfigured in this repository

This document defines the safe lifecycle for the encrypted canonical secret bundle at
`values/sites/<site>/secrets.sops.yaml`. It does not contain private age keys,
recipients, decrypted values, or production credentials. The tracked `.sops.yaml`
contains a deliberate placeholder recipient and is not an operational encryption
policy until the private workflow supplies the real recipient.

## Boundary and ownership

- `site.yaml` contains non-secret configuration only.
- `secrets.sops.yaml` is ciphertext and must remain site-scoped.
- The service catalog owns required logical paths and classifications.
- The provider resolves only paths requested by the selected enabled-service set.
- Consumer delivery is separate from ordinary OpenTofu, Ansible inventory, DNS,
  and runtime projections. Secret values must not enter those projections, state,
  plans, logs, reports, or tracker files.
- The external age key file is private operator material. It must be a regular,
  readable file with no group/other permission bits and must never be read into
  documentation or command output.
- The bootstrap SSH private key is stored at the encrypted logical path
  `secrets.bootstrap.ssh_private_key`. It is not part of `site.yaml`, generated
  projections, plans, state, or ordinary service delivery. Canonical tooling
  materializes it only inside the short-lived tooling container, verifies its
  derived public key against `bootstrap.ssh.public_keys`, and removes it with
  the container filesystem. The SOPS age identity remains separate and external;
  it must never be stored inside the bundle it decrypts.

## Initial key creation

1. Create the site recipient and a separately controlled recovery recipient, with
   corresponding private age identities in the approved private key-management
   system. Keep both private identities outside the repository and outside ordinary
   dotenv, Terraform state, plan, inventory, and backup artifacts. The recovery
   identity is not mounted during routine operations.
2. Record the exact site-plus-recovery recipient set in the private deployment policy for the exact
   `values/sites/<site>/secrets.sops.yaml` scope. Do not replace the public
   placeholder in this repository with a private recipient.
3. Create the encrypted bundle with only the logical namespaces and values needed
   by the catalog-approved consumers. Validate the public policy scope and bundle
   recipient metadata without decrypting during ordinary preflight.
4. Verify the ciphertext hash and a value-free required-secret report. Never use a
   secret value or sentinel as an identity check.

For canonical SSH execution, add the matching unencrypted-at-runtime private key
under `secrets.bootstrap.ssh_private_key` through the approved SOPS editing
workflow. The key may be encrypted at rest by SOPS, but it must not require an
interactive SSH passphrase after SOPS decryption. The canonical workflow derives
its public half with `ssh-keygen -y` and fails closed unless it matches one of the
declared bootstrap public keys. Do not add the private key to projections or copy
it through the ordinary service-secret environment boundary.

For a private deployment policy, preflight can receive the policy metadata through
the operator environment without committing it to this repository:

```bash
export INFRA_SOPS_POLICY_PATH=<private-policy-root>/.sops.yaml
export INFRA_SOPS_AGE_RECIPIENTS='age1site...,age1recovery...'
```

The recipient list is metadata, not secret material, but it must still remain out
of tracked public files when it identifies private operational policy. Preflight
passes the expected set to both the policy-rule check and encrypted-bundle metadata
check. A mismatch fails closed before required-secret resolution or consumer
delivery. Omit these variables only for public scaffold validation where the
placeholder policy is intentionally reported as not configured.

## Rotation and revocation

Rotation is an explicit, reversible operation:

1. Generate a new site recipient and private identity using the approved private
   workflow.
2. Temporarily re-encrypt each selected site bundle to the old site recipient, new
   site recipient, and unchanged recovery recipient.
3. Validate policy scope, recipient-set equality, ciphertext identity, and required
   logical paths before delivery.
4. Run a consumer-specific smoke check without printing values. Record only site,
   operation, recipient-policy state, ciphertext identity, and result metadata.
5. Re-encrypt to the new site recipient plus the recovery recipient, then revoke or
   destroy the old private identity only after all required bundles and
   recovery backups have been verified with the new identity.

A revoked recipient must not remain an accepted delivery path. If rotation fails,
restore the prior ciphertext and private-key reference from the approved backup
without changing ordinary consumer inputs.

## Logical-path migration

The operator password contract is identity-neutral:
`secrets.operator.password`, delivered transiently as `INFRA_OPERATOR_PASSWORD`.
Older private bundles may contain `secrets.operator.systemboss_password`. Migrate
those bundles with the repository helper from the repository root:

```bash
bash scripts/python.sh scripts/migrate-secret-bundle.py \
  values/sites/<site>/secrets.sops.yaml
```

The command is dry-run by default. It decrypts only in memory, reports metadata,
and does not modify the ciphertext. Review the result, then repeat with `--apply`
to write a re-encrypted bundle. Apply mode creates the ciphertext backup
`secrets.sops.yaml.pre-migration` beside the bundle and refuses to overwrite an
existing migration backup. Do not delete that backup until the migrated bundle has
passed recipient-policy and required-path validation.

The migration fails closed if both old and new paths exist with different values.
It never prints decrypted values, writes plaintext outside a restricted temporary
directory, or changes any other logical secret path.

## Backup and recovery

Back up ciphertext and value-free manifests, not decrypted secret material. A backup
manifest should contain only:

- site identifier and bundle relative path;
- schema/renderer version;
- ciphertext hash and file size;
- selected source paths and backup identifier;
- recipient-policy state and creation time.

Private age identities require a separate protected offline backup with independent
access control. Do not place private identities beside repository backups or in the
repository. Recovery must restore a disposable copy first, validate its recipient
metadata and required logical paths, and only then make it available to an approved
consumer.

Recovery is fail-closed when the site is wrong, the bundle is altered, the recipient
set is unexpected, required paths are missing, or the key file is missing,
unreadable, or too permissive. Errors must identify only the failed contract, never
secret values, recipient payloads, or key contents.

## Disposable restore test

A restore rehearsal must use a temporary site fixture and synthetic secret values.
It must prove:

1. the encrypted bundle and value-free manifest restore to a restricted temporary
   directory;
2. the key file is supplied through the external key-file boundary and has mode
   `0600` (or stricter);
3. the selected site and recipient policy match;
4. every catalog-required logical path resolves;
5. no value, key content, or sentinel appears in stdout, stderr, logs, manifests,
   or exception text; and
6. the temporary directory and files are removed on success, validation failure,
   provider failure, interruption, and termination paths where the runner permits
   cleanup.

This rehearsal is not production deployment evidence. Live recipient provisioning,
backup storage, and consumer-specific delivery require the private operational
workflow and separate approval.

## Current repository contract

The repository currently supports structural bundle validation, logical-path
resolution, secret/ciphertext identities, metadata-only SOPS/age checks, required
secret evaluation, protected temporary material helpers, identity-neutral operator
path migration, and explicit transient consumer delivery for the canonical Ansible
bootstrap boundary. It does **not** yet
make provider, runtime, recovery, or generated secrets authoritative for all live
consumers. Legacy consumer inputs and broader consumer cutover therefore remain
unchanged and deferred.
