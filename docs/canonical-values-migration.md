# Canonical Values Migration Boundary

**Status:** validation-only compatibility window; no consumer cutover

The canonical site model is being introduced alongside the existing private values
inputs. During this window, `site.yaml` is validated as a separate, additive
input. The existing `terraform.tfvars`, dotenv, DNS, and Ansible inventory files
remain the active consumer inputs for the normal infrastructure workflow.

## Validation-only workflow

Run canonical validation explicitly for a selected site:

```bash
scripts/python.sh scripts/canonical-values.py \
  --site-file values/sites/dev/site.yaml validate
```

This loads and strictly validates the selected `site.yaml` against
`infra/services.json`, checks the site-directory identity, and prints only a
redacted model identity. It does not rewrite the file, render consumer inputs
for normal use, change OpenTofu or Ansible arguments, or apply infrastructure.
Replace `dev` with the selected site directory; do not validate one site's file
as another site.

Review legacy inputs separately with the read-only discovery command:

```bash
scripts/python.sh scripts/legacy-values-discovery.py \
  --values-dir values \
  --output /tmp/legacy-values-review.json
```

The report reads `.env`, `terraform.tfvars`, settings/DNS JSON, and
`ansible/inventory/local.yml` when present. It records mapped fields, conflicts,
and unmapped values without storing secret or unknown value contents. The
output must be outside `values/`; the command uses a restricted report file and
never writes a `site.yaml` or changes legacy files.

Treat the report as migration review evidence only. Legacy inventory is
currently classified as unsupported for automatic mapping, and any conflict,
unknown, or unsupported observation keeps candidate generation fail-closed.
There is no automatic importer in this validation slice.

## Source-of-truth boundary

Until a separately reviewed cutover is complete:

- `values/sites/<site>/site.yaml` is the canonical model under validation only.
- `values/terraform.tfvars`, `values/.env`,
  `values/ansible/inventory/local.yml`, and the other legacy files remain the
  active consumer inputs.
- Passing canonical validation does **not** prove semantic parity with legacy
  inputs, Ansible inventory compatibility, OpenTofu plan equivalence, or
  migration readiness.
- Passing legacy discovery does **not** create or update canonical files.
- Do not use the generated report as an OpenTofu/Ansible input and do not run
  migration apply, infrastructure apply, destroy, import, or state surgery as
  part of this check.

The smallest safe validation slice is therefore two independent gates:

1. canonical schema/catalog validation for the selected `site.yaml`;
2. redacted, non-mutating legacy discovery for `terraform.tfvars` and inventory,
   with conflicts and unsupported fields reported for later mapping work.

Cross-source equality, candidate generation, compatibility-adapter wiring, and
consumer cutover require a complete mapping matrix and separate reviewed
implementation slices. They are intentionally outside this boundary.

## Verification and cleanup

Use a disposable output path for the legacy report. Inspect it for review, then
remove it when no longer needed. The report may contain source keys and
redacted metadata, but must not contain credentials, secret sentinels, or
arbitrary unknown values.

For repository-level validation, use the normal command:

```bash
just validate
```

The canonical and legacy commands above are focused migration checks; they do
not replace the normal validation, reviewed `just plan`, or explicitly approved
`just apply` workflow.
