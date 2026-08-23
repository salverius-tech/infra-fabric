# Public Just recipes

`just --list` is the public command surface. Run commands from the repository root. The selected canonical site is represented by `values/sites/<site>/site.yaml` and protected values by `values/sites/<site>/secrets.sops.yaml`.

Select a site before every normal operator workflow (including values checks and validation):

```bash
export VALUES_SITE=<site>
```

Private implementation recipes are not operator commands. Legacy-layout recovery/import recipes are retired; canonical selected-site workflows are the only supported operator surface.

## `default`

```bash
just
```

Lists the supported public recipes. No files or infrastructure are changed.

## `setup`

```bash
just setup "" <site>
```

Requires `<site>` and creates or preserves that selected canonical-site scaffold before initializing the private values repository when required by the local workflow. `VALUES_SITE` plus `values/sites/<site>/site.yaml` are mandatory for every normal operator command. The selected site scaffold is public-safe and does not create SOPS identities, credentials, encrypted secret content, or legacy `.env`/tfvars/inventory inputs. Existing files are not overwritten. Complete private SOPS prerequisites before validation or planning.

The optional first argument is the private values remote; the second argument is the required site identifier. Prefer an existing private repository when one is already authoritative.

## `edit-secrets`

```bash
just edit-secrets SITE=<site>
```

Opens the selected encrypted SOPS bundle with the host `sops` binary when available, otherwise the repository tooling container. Requires the selected `site.yaml`, `.sops.yaml`, encrypted bundle, and readable external age identity. This mutates encrypted ciphertext; review the private repository diff afterward. It does not run validation, plan, or apply.

## `site-identity`

```bash
just site-identity generate SITE=<site>
just site-identity store SITE=<site>
just site-identity fetch SITE=<site>
just site-identity verify SITE=<site>
```

The explicit site age-identity lifecycle. `generate` creates the identity at the documented path when absent (never overwrites). `store` copies the full identity file into the operator's 1Password vault as the separate protected offline copy; requires the 1Password CLI and an interactive `op signin`. Set the target vault per invocation with a leading assignment:

```bash
just VAULT=<vault-name> site-identity store SITE=<site>
``` `fetch` recovers from the vault onto a fresh machine. `verify` performs a decryption round-trip against the selected site bundle and is mandatory after any recovery or before trusting any recovered key.

Key material is never printed; every overwrite requires an explicit `--force` passed after the action (`just site-identity store --force`). Manual recovery without the CLI remains fully supported: paste the vault contents into the documented path with `0600` permissions, then run `verify`. Re-store the identity in the vault as a mandatory step of any identity rotation. See [canonical secret operations](canonical-values-secret-operations.md).

## `ssh-initialize`

```bash
just ssh-initialize SITE=<site>
```

The explicit canonical SSH-identity operation. It decrypts only within the protected tooling boundary, validates or creates the distinct bootstrap and Proxmox-management private identities against their public pins, updates the encrypted canonical bundle, and refreshes derived projections. It requires complete canonical site/SOPS prerequisites and must not be used as a substitute for operator secret review.

## `update`

```bash
VALUES_SITE=<site> just update
```

Checks or updates managed public tool/service pins through the repository update workflow. Review the resulting public and selected private-site diffs, then run validation and a reviewed plan. It does not apply infrastructure.

## `test`

```bash
just test
```

Runs the full Python test suite in the pinned tooling container. It does not require `values/` and does not touch infrastructure.

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

Canonical service convergence uses a distinct selected-site SOPS-backed Proxmox-management SSH identity. Its public key is declared at `platform.proxmox.management.ssh_public_key`; its encrypted private key is stored only at `secrets.providers.proxmox.ssh_private_key`:

```bash
VALUES_SITE=<site> just apply
```

This identity is distinct from the SOPS-backed guest bootstrap identity. The wrapper materializes it transiently, verifies the matching key pair, and keeps strict host-key checking enabled. Do not provide an ambient controller-key selector, substitute a guest bootstrap key, or place private material in site values, generated projections, or state.

Generated projections use a controller-local private parent by default, while execution snapshots and state backups use sibling private roots under `${XDG_STATE_HOME:-$HOME/.local/state}/infra-fabric/sites/<site>/`. The generated parent contains the atomically published `generated/` child; the extra level is required because a bind-mount root cannot itself be renamed or exchanged. When overriding these locations, set `INFRA_GENERATED_ROOT`, `INFRA_EXECUTION_SNAPSHOT_ROOT`, and `INFRA_STATE_SNAPSHOT_ROOT` to separate absolute mode-`0700` private controller-local directories on a supporting filesystem. `INFRA_GENERATED_ROOT` names the mounted parent, and validation, planning, apply, and service-state consumers use its `generated/` child through `INFRA_GENERATED_DIR`. The snapshot roots hold sealed apply/teardown evidence. These settings do not weaken verification, permit replacement, or provide an unsafe fallback.

Additional acknowledgements are required for plans containing the corresponding risk classes:

```bash
INFRA_ALLOW_DESTROY=1 VALUES_SITE=<site> just apply
INFRA_ALLOW_STATEFUL_BATCH=1 VALUES_SITE=<site> just apply
```

These flags do not approve the operation by themselves. They do not authorize router/firewall changes, state surgery, credential rotation, or other work outside the saved plan.

## `teardown-plan`

```bash
VALUES_SITE=<site> just teardown-plan
```

Creates and displays a full-site guarded destroy plan. It requires canonical destroy policy and protected-input preflight, then writes private `destroy.tfplan` metadata bound to the selected site, canonical/projection identity, source commit, input hashes, scope, age, and destructive summary. Review it before any teardown apply.

## `teardown-apply`

```bash
VALUES_SITE=<site> just teardown-apply --approve
```

Consumes only a fresh verified guarded destroy plan. The literal `--approve` is an explicit acknowledgement, not a substitute for user authorization. Immediately before provider mutation, the wrapper re-verifies metadata, seals an immutable execution snapshot, and snapshots local state. It does not run Ansible after a successful destroy.

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

When a recipe reports a missing site, stale inputs, missing projections, failed policy verification, missing secrets, provider failure, or host-readiness failure, restore or create `values/sites/<site>/site.yaml` through `just setup "" <site>`, then correct the canonical source or prerequisite and rerun the public recipe. Use only the explicit migration/importer or recovery tools for legacy forensic work; they are not normal recipe fallbacks. Do not edit generated files, plans, state, or identity material to bypass a failed gate.
