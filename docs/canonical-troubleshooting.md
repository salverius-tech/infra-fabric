# Canonical troubleshooting

Use the selected site context for every diagnostic. Do not print protected values, decrypted bundles, state, plans, hostnames, addresses, or tokens.

## Site and schema errors

Confirm `VALUES_SITE=<site>` is set and that `values/sites/<site>/site.yaml` exists. Run `just validate` and fix the first schema path reported. Do not edit generated projections to silence a validation error.

## SOPS and secret-path errors

Check the selected site’s `.sops.yaml`, encrypted bundle, and external age identity. Confirm required logical paths rather than values. `just edit-secrets SITE=<site>` needs a working editor and readable identity; it mutates encrypted ciphertext.

## Projection errors

Remove stale generated artifacts only through the supported site workflow, then rerun validation. Compare value-free projection metadata and check that the canonical file—not a generated file—contains the intended change.

## OpenTofu or provider errors

Separate initialization, provider connectivity, refresh, schema evaluation, and resource planning failures. Re-run `VALUES_SITE=<site> just plan` after correcting inputs; do not edit a saved plan or state artifact.

## Host trust and SSH errors

Use the approved management/service endpoint and verify host identity material. `just ssh-initialize` requires explicit site context and an external protected identity. Do not bypass host-key verification.

## Service convergence errors

Use direct service endpoints first. Inspect the affected role’s idempotent task failure, handler ordering, and health check. Re-run the selected playbook only through the reviewed workflow; do not use ad hoc guest mutation as a substitute.

## Storage and state errors

Confirm the canonical volume type, source, target, backup policy, and mount semantics are complete. Stateful changes require a reviewed plan, backup evidence, and restore validation. Missing source details are a blocker, not a reason to infer a mount.

## Post-apply drift

Run a fresh selected-site plan after an approved apply. Investigate every unexpected change before declaring convergence. A clean structural validation alone is insufficient.
