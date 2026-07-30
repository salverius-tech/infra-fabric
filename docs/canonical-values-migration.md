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

The generated projections can also be exercised through the opt-in paired
Ansible compatibility boundary after canonical rendering has produced and
verified `values/generated/`:

```bash
scripts/python.sh scripts/apply-ansible-services.py \
  --canonical-ansible \
  --mode sequential
```

This mode requires a selected canonical site, reads the identity-verified
`ansible-inventory.json`, writes flattened non-secret compatibility variables to
a temporary mode-0600 file, and passes both inputs to every playbook. The
temporary file is removed on exit. Do not combine `--canonical-ansible` with
`--inventory`; mixed canonical/legacy authority is rejected. The default
`apply-ansible-services.py` invocation remains legacy and the opt-in mode is
not evidence of full plan/apply parity.

The site migration orchestrator currently retains the legacy compatibility-only
migration behavior. A `--canonical-base` candidate path is intentionally
fail-closed until the declared runtime importer scope is admitted:

```bash
scripts/python.sh scripts/migrate-site-values.py \\
  --values-dir values \\
  --site dev \\
  --canonical-base /path/to/approved-base.yaml \\
  --apply
```

At present, the command performs discovery before any move and then refuses
candidate construction because runtime importer admission is incomplete. It
must leave the legacy values unchanged. This strict gate prevents token-level
mapping matches from being mistaken for complete importer readiness.

The report-only discovery CLI retains the candidate-shaped interface for a
future explicitly admitted runtime scope, but currently fails closed and writes
no candidate:

```bash
scripts/legacy-values-discovery.py \\
  --values-dir /path/to/legacy/values \\
  --candidate-base /path/to/approved-base.yaml \\
  --candidate-output /tmp/site-candidate.yaml \\
  --site dev
```

No `site.yaml` or `secrets.sops.yaml` is fabricated by these blocked paths.

The first report-only Ansible semantic discovery slice can inspect the public
inventory and static consumer references without executing Ansible:

```bash
scripts/python.sh scripts/ansible_semantic_discovery.py \\
  --repo . \\
  --output /tmp/ansible-semantic-discovery.json
```

The report records exact inventory identities, supported consumer references,
value-free secret/provider classification, and operational/lifecycle review
dispositions. It never retains inventory values, generates candidates, decrypts
secrets, mutates legacy inputs, or enables consumer cutover. Dynamic Ansible
resolution, cross-source correlation, and runtime importer admission remain
review-required.

Review legacy inputs separately with the read-only discovery command:

```bash
scripts/python.sh scripts/legacy-values-discovery.py \
  --values-dir values \
  --output /tmp/legacy-values-review.json
```

The report reads `.env`, `terraform.tfvars`, settings/DNS JSON, and
`ansible/inventory/local.yml` when present. For the bounded public Ansible
importer slice, opt in explicitly with the public repository root and scaffold
inventory:

```bash
scripts/python.sh scripts/legacy-values-discovery.py \
  --values-dir values \
  --repo . \
  --ansible-inventory scaffold/ansible/inventory/local.yml \
  --output /tmp/legacy-values-ansible-review.json
```

That opt-in admits only `all.vars.forgejo_domain` and
`all.vars.forgejo_version`; the remaining inventory is
reported as unsupported. It performs normalization and conflict detection but
still cannot generate a candidate or enable consumer cutover.

The report records mapped fields, conflicts,
and unmapped values without storing secret or unknown value contents. The
report output must be outside `values/`; discovery itself never changes legacy
files. Candidate generation is a separate explicit command as documented above.

Treat the report as migration review evidence. Legacy inventory and any
conflict, unknown, unsupported, or non-concrete observation keep candidate
generation fail-closed. Secret bundle generation remains a separate SOPS/age
operation and is not performed by the public candidate command.

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
