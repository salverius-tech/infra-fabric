# Canonical Values Migration Boundary

**Status:** canonical operational authority with explicit legacy compatibility

For a selected site, `site.yaml` plus verified generated projections are the
normal consumer inputs. Legacy `terraform.tfvars`, dotenv, DNS, and Ansible
inventory inputs are compatibility-only and are rejected by `plan`, `apply`,
and `validate` unless the operator explicitly sets:

```bash
INFRA_ALLOW_LEGACY_COMPATIBILITY=true
```

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
`--inventory`; mixed canonical/legacy authority is rejected. The canonical Ansible mode is now the operational path for selected canonical
sites. The legacy invocation is retained only for the explicit compatibility
environment override above.

The site migration orchestrator retains its compatibility-only migration behavior. A
`--canonical-base` candidate path remains fail-closed until the selected source
has no unresolved conflicts and all protected/provider inputs have an approved
delivery contract:

```bash
scripts/python.sh scripts/migrate-site-values.py \\
  --values-dir values \\
  --site dev \\
  --canonical-base /path/to/approved-base.yaml \\
  --apply
```

At present, the command performs discovery before any move and refuses
candidate construction when the selected source has protected/provider inputs
without an approved delivery contract or has genuine source conflicts. It must
leave the legacy values unchanged.

When a selected development site already contains a valid `site.yaml` and
`site.json` but is missing only its migration manifest, use the explicit adoption
boundary instead of rerunning migration or moving legacy files:

```bash
scripts/python.sh scripts/migrate-site-values.py \\
  --values-dir values \\
  --site dev \\
  --adopt-existing \\
  --apply
```

Adoption validates site identity, lifecycle/apply policy, the canonical model, and
the existing service list, then writes a mode-0600 manifest with zero legacy move
operations. It never deletes, moves, or rewrites legacy values. It refuses
incomplete or conflicting existing sites and remains dry-run by default.

The report-only discovery CLI also supports an explicitly admitted bounded runtime
scope. It still fails closed and writes no candidate unless the selected source
passes admission and an approved canonical base declares every overlaid resource:

```bash
scripts/legacy-values-discovery.py \\
  --values-dir /path/to/legacy/values \\
  --candidate-base /path/to/approved-base.yaml \\
  --candidate-output /tmp/site-candidate.yaml \\
  --site dev
```

No `site.yaml` or `secrets.sops.yaml` is fabricated by these paths. A successful
candidate remains a disposable migration artifact and must be loaded through the
canonical model from an identity-matching `<site>/site.yaml` layout, then rendered
and verified as a complete non-secret projection set before any private installation.

The Ansible semantic discovery and normalized importer boundary can inspect the
public inventory and static consumer references without executing Ansible:

```bash
scripts/python.sh scripts/ansible_semantic_discovery.py \\
  --repo . \\
  --output /tmp/ansible-semantic-discovery.json
```

The report records exact inventory identities, supported consumer references,
value-free secret/provider classification, operational/lifecycle dispositions,
and bounded dynamic-reference metadata. It never evaluates arbitrary Jinja,
retains secret values, mutates legacy inputs, or decrypts secrets. Normalized
non-secret mapped observations can now be admitted through the runtime importer;
unresolved dynamic expressions, protected/provider inputs, and selected-source
conflicts remain outside candidate generation.

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

That opt-in exercises the bounded non-secret importer and its typed owners,
including the documented Forgejo, Technitium, Infisical, Hermes, SearXNG,
Tailscale, Caddy, and resource-identity fields. It performs normalization,
conflict detection, and value-free residual reporting. Unsupported/dynamic
inventory, protected/provider inputs, or selected-source conflicts still block
candidate generation; canonical consumer authority is established separately
by verified projections and the operational compatibility gate.

The report records mapped fields, conflicts, and each unsupported inventory key
with its source path and type; dynamic Jinja-style expressions are marked as
`dynamic-expression` and remain unsupported, without storing secret or unknown value contents.
The bounded Forgejo importer also admits `forgejo_root_url` and normalizes
absolute HTTP(S) URLs to a trailing-slash form before conflict comparison.
The report output must be outside `values/`; discovery itself never changes legacy
files. When `--values-dir` points at a site-aware directory containing `site.json`, the
report also includes the public site identity/policy metadata without changing
that file. Candidate generation remains a separate explicit command as
documented above.
Treat the report as migration review evidence. Legacy inventory and any
conflict, unknown, unsupported, or non-concrete observation keep candidate
generation fail-closed. Secret bundle generation remains a separate SOPS/age
operation and is not performed by the public candidate command.

The migration entry point also supports an explicit transactional mode:
`--transactional --backup-dir <private-directory>`. This creates an exclusive,
verified backup of mutable legacy inputs before migration and restores it if
migration fails. The ordinary compatibility mode remains available, but
operational migration should use the transactional mode.

## Source-of-truth boundary

Until a separately reviewed compatibility-removal phase is complete:

- `values/sites/<site>/site.yaml` is the canonical operator-edited model for a
  selected site.
- For a selected canonical site, `validate`, `plan`, and `apply` require and verify
  the complete generated projection set; they do not silently fall back to legacy
  inventory or tfvars.
- `values/terraform.tfvars`, `values/.env`,
  `values/ansible/inventory/local.yml`, and other legacy files remain the
  compatibility inputs when no canonical site is selected.
- Passing canonical validation does **not** prove provider-specific plan equivalence,
  live infrastructure health, backup/restore acceptance, or production readiness.
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
