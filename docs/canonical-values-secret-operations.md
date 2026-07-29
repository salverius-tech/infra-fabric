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

## Initial key creation

1. Create the site recipient and its corresponding private age identity in the
   approved private key-management system. Keep the private identity outside the
   repository and outside ordinary dotenv, Terraform state, plan, inventory, and
   backup artifacts.
2. Record the recipient in the private deployment policy for the exact
   `values/sites/<site>/secrets.sops.yaml` scope. Do not replace the public
   placeholder in this repository with a private recipient.
3. Create the encrypted bundle with only the logical namespaces and values needed
   by the catalog-approved consumers. Validate the public policy scope and bundle
   recipient metadata without decrypting during ordinary preflight.
4. Verify the ciphertext hash and a value-free required-secret report. Never use a
   secret value or sentinel as an identity check.

## Rotation and revocation

Rotation is an explicit, reversible operation:

1. Generate a new recipient and private identity using the approved private
   workflow.
2. Re-encrypt each selected site bundle to the new recipient while retaining the
   old identity only for the bounded recovery window.
3. Validate policy scope, recipient-set equality, ciphertext identity, and required
   logical paths before delivery.
4. Run a consumer-specific smoke check without printing values. Record only site,
   operation, recipient-policy state, ciphertext identity, and result metadata.
5. Revoke or destroy the old private identity only after all required bundles and
   recovery backups have been verified with the new identity.

A revoked recipient must not remain an accepted delivery path. If rotation fails,
restore the prior ciphertext and private-key reference from the approved backup
without changing ordinary consumer inputs.

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
secret evaluation, and protected temporary material helpers. It does **not** yet
make provider, bootstrap, runtime, recovery, or generated secrets authoritative for
all live consumers. Legacy consumer inputs and consumer cutover therefore remain
unchanged and deferred.
