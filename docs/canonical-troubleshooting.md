# Canonical troubleshooting

## Diagnostic stage summary

Use the named order in [service operations](service-operations.md#standard-diagnostic-stages): `canonical-input`, `provider-plan`, `host-trust`, `service-health`, then `state-recovery`. The stages are intentionally fail-fast in CI and in operator diagnosis: do not skip to direct service intervention, raw OpenTofu/Terraform, or `site.yml` because an earlier boundary failed. A passing static check is source evidence only; provider, live-health, backup/restore, and recovery evidence require separately authorized execution.

Use the selected site context for every diagnostic. Do not print protected values, decrypted bundles, state, plans, hostnames, addresses, or tokens.

## Site and schema errors

Confirm `VALUES_SITE=<site>` is set and that `values/sites/<site>/site.yaml` exists. If it is missing, restore or create it with `just setup "" <site>` before rerunning the canonical recipe; legacy files are not a normal workflow fallback. Run `just validate` and fix the first schema path reported. Do not edit generated projections to silence a validation error.

## SOPS and secret-path errors

Check the selected site’s `.sops.yaml`, encrypted bundle, and external age identity. Confirm required logical paths rather than values. `just edit-secrets SITE=<site>` needs a working editor and readable identity; it mutates encrypted ciphertext.

### Identity and secret recovery after controller loss

If the controller host is lost or unrecoverable, reconstruct the secret prerequisites before any plan, apply, or restore step:

1. Clone the public repository and the private values repository from their remotes; confirm the private checkout contains the selected site’s `.sops.yaml` and encrypted bundle.
2. Recover the site age identity from its external copy — for example the 1Password vault item created via `just VAULT=<vault> site-identity store` (search for `infra-fabric-site-age-identity-<site>`). Either fetch it directly:

   ```bash
   op signin
   just VAULT=<vault> site-identity fetch SITE=<site>
   ```

   or manually paste the note contents into `~/.config/infra-fabric/keys/<site>/site.age` with `0600` permissions. The note must contain an `AGE-SECRET-KEY-...` line plus its public-key comment; a value that is only a file path is not an identity.
3. Verify before trusting: `just site-identity verify SITE=<site>` decrypts the real site bundle and fails closed on a wrong or truncated key. No consumer should touch secret material until this passes.
4. Then resume the standard workflow: `just validate`, a reviewed plan, apply, convergence, and guarded state restores per [storage and state](#storage-and-state-errors) below.

Without a recoverable identity copy, every encrypted value for the site is permanently unreadable regardless of backup availability — which is why the external copy is a mandatory prerequisite (`just VAULT=<vault> site-identity store`) rather than an optional convenience.

## Projection errors

Remove stale generated artifacts only through the supported site workflow, then rerun validation. Compare value-free projection metadata and check that the canonical file—not a generated file—contains the intended change.

## OpenTofu or provider errors

Separate initialization, provider connectivity, refresh, schema evaluation, and resource planning failures. Re-run `VALUES_SITE=<site> just plan` after correcting inputs; do not edit a saved plan or state artifact.

## Host trust and SSH errors

Use the approved management/service endpoint and verify host identity material. `just ssh-initialize` requires explicit site context and an external protected identity. Do not bypass host-key verification.

### After an intentional guest replacement

A guest recreated through an approved apply (model disable/re-enable cycle or equivalent) generates new SSH host keys. The direct-access readiness check fails closed with `SSH host key changed for <endpoint>` and the pipeline offers no blanket acceptance knob by design. The sanctioned procedure is explicit, targeted trust replacement:

1. Confirm the replacement is the one you performed: the reviewed plan's create entry and the execution snapshot timestamp must match the guest you expect. Never accept a key change you cannot attribute to your own approved apply.
2. Remove only the replaced guest's controller trust entry:
   `ssh-keygen -R <guest endpoint> -f values/sites/<site>/ansible/known_hosts`.
3. Re-run `VALUES_SITE=<site> just plan` and `just apply`. With no existing entry, the readiness check enrolls the new keys as a first enrollment instead of accepting a change.
4. A recreated guest has no converged identities: run the targeted first-boot identity recovery
   (`INFRA_HOST_IDENTITY_ONLY=<resource> INFRA_HOST_IDENTITY_SKIP_ROOT=false` through the wrapped tooling session),
   then a normal apply. Stateful services additionally need `scripts/service-state.sh restore-if-present <service>`
   after convergence.

Never disable host-key verification or accept changes into the shared known_hosts file without this attribution step.

## Service convergence errors

Use direct service endpoints first. Inspect the affected role’s idempotent task failure, handler ordering, and health check. Re-run the selected playbook only through the reviewed workflow; do not use ad hoc guest mutation as a substitute.

## Storage and state errors

Confirm the canonical volume type, source, target, backup policy, and mount semantics are complete. Stateful changes require a reviewed plan, backup evidence, and restore validation. Missing source details are a blocker, not a reason to infer a mount.

## Post-apply drift

Run a fresh selected-site plan after an approved apply. Investigate every unexpected change before declaring convergence. A clean structural validation alone is insufficient.
