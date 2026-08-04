# Public Just recipes

`just --list` is the public command surface. Run commands from the repository root. The selected canonical site is represented by `values/sites/<site>/site.yaml` and protected values by `values/sites/<site>/secrets.sops.yaml`.

Select a site before lifecycle work:

```bash
export VALUES_SITE=<site>
```

Private implementation recipes are not operator commands.

## `default`

```bash
just
```

Lists the supported public recipes. No files or infrastructure are changed.

## `setup`

```bash
just setup "" <site>
```

Creates or preserves the selected site scaffold and initializes the private values repository when required by the local workflow. The selected site scaffold is public-safe and does not create SOPS identities, credentials, or encrypted secret content. Existing files are not overwritten. Complete private SOPS prerequisites before validation or planning.

The optional first argument is the private values remote and the optional second argument is the site identifier. Prefer an existing private repository when one is already authoritative.

## `edit-secrets`

```bash
just edit-secrets SITE=<site>
```

Opens the selected encrypted SOPS bundle with the host `sops` binary when available, otherwise the repository tooling container. Requires the selected `site.yaml`, `.sops.yaml`, encrypted bundle, and readable external age identity. This mutates encrypted ciphertext; review the private repository diff afterward. It does not run validation, plan, or apply.

## `ssh-initialize`

```bash
just ssh-initialize SITE=<site>
```

The explicit bootstrap-identity operation. It decrypts only within the protected tooling boundary, validates the private identity against declared public keys, updates the encrypted canonical bundle, and refreshes derived projections. It requires complete canonical site/SOPS prerequisites and must not be used as a substitute for operator secret review.

## `update`

```bash
VALUES_SITE=<site> just update
```

Checks or updates managed public tool/service pins through the repository update workflow. Review the resulting public and selected private-site diffs, then run validation and a reviewed plan. It does not apply infrastructure.

## `validate`

```bash
VALUES_SITE=<site> just validate
```

Runs public safety checks, canonical model/catalog validation, projection checks, OpenTofu validation, linting, tests, DNS/schema checks, Ansible checks, and private site wiring checks. It is a validation gate, not live health or deployment evidence.

## `plan`

```bash
VALUES_SITE=<site> just plan
```

Refreshes and verifies selected-site generated projections, performs provider and host-readiness preflight, initializes/validates OpenTofu, and writes a saved plan and metadata under the selected site directory. It does not apply infrastructure, but it can contact the configured provider and changes private derived files. Do not edit generated projections or reuse a stale plan.

Optional controlled targeting:

```bash
INFRA_TARGET_SERVICE=<service> VALUES_SITE=<site> just plan
INFRA_REPLACE_SERVICE=<service> VALUES_SITE=<site> just plan
```

A targeted plan is a review aid, not a substitute for a subsequent full plan.

## `apply`

```bash
VALUES_SITE=<site> just apply
```

Verifies the saved plan and its input metadata, mutates infrastructure, runs the approved Ansible service chains, and performs configured post-apply checks. Use only after explicit approval of the fresh plan.

Additional acknowledgements are required for plans containing the corresponding risk classes:

```bash
INFRA_ALLOW_DESTROY=1 VALUES_SITE=<site> just apply
INFRA_ALLOW_STATEFUL_BATCH=1 VALUES_SITE=<site> just apply
```

These flags do not approve the operation by themselves. They do not authorize router/firewall changes, state surgery, credential rotation, or other work outside the saved plan.

## Canonical artifact locations

For the selected site, derived files are beneath:

```text
values/sites/<site>/generated/
values/sites/<site>/tfplan
values/sites/<site>/tfplan.meta.json
values/sites/<site>/terraform.tfstate*
```

Keep these private. Plan artifacts are disposable and must be regenerated when inputs or verification metadata change.

## Safe recovery rule

When a recipe reports stale inputs, missing projections, failed policy verification, missing secrets, provider failure, or host-readiness failure, correct the canonical source or prerequisite and rerun the public recipe. Do not edit generated files, plans, state, or identity material to bypass a failed gate.
