# Canonical teardown and site retirement

There is no normal `just destroy` recipe. Destruction is an explicit OpenTofu workflow because it removes resources and may remove durable service data.

## Before teardown

1. Confirm the selected site and lifecycle policy.
2. Confirm the site is not production or protected.
3. Decide whether service-state backups are required. Do not create backups automatically if the site is intentionally disposable.
4. Ensure no other apply, plan, restore, or state operation is running.
5. Do not remove host-key material until the destroy has completed.

The destroy plan is the review boundary. Never run a blind `tofu destroy` against a shared or production state.

## Plan the teardown

From the repository root, replace `<site>` with the selected site:

```bash
SOPS_AGE_KEY_FILE="$HOME/.config/infra-fabric/keys/<site>/site.age" \
VALUES_SITE=<site> \
INFRA_VALUES_DIR=values/sites/<site> \
INFRA_COPY_SSH_KEYS=true \
INFRA_SSH_IDENTITY_SOURCE=sops \
scripts/run-infra.sh bash -euo pipefail -c '
  python scripts/workspace-preflight.py --require-values --require-secrets
  python scripts/settings.py policy --action destroy --canonical
  tofu -chdir=infra/opentofu init

  destroy_plan="${INFRA_VALUES_DIR}/.destroy.tfplan"
  rm -f "${destroy_plan}"
  destroy_command=(
    tofu -chdir=infra/opentofu plan
    -destroy
    -var-file="../../${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json"
    -state="../../${INFRA_VALUES_DIR}/terraform.tfstate"
    -out="../../${destroy_plan}"
  )
  python scripts/canonical-provider-env.py -- "${destroy_command[@]}"
  tofu -chdir=infra/opentofu show "../../${destroy_plan}"
'
```

Review the complete output. Confirm that the resources, storage, image/template artifacts, and outputs belong only to the selected site. If the plan is unexpected, stop and correct the canonical inputs or state reconciliation before applying.

## Apply the teardown

After explicit approval of the reviewed destroy plan:

```bash
SOPS_AGE_KEY_FILE="$HOME/.config/infra-fabric/keys/<site>/site.age" \
VALUES_SITE=<site> \
INFRA_VALUES_DIR=values/sites/<site> \
INFRA_COPY_SSH_KEYS=true \
INFRA_SSH_IDENTITY_SOURCE=sops \
scripts/run-infra.sh bash -euo pipefail -c '
  python scripts/workspace-preflight.py --require-values --require-secrets
  python scripts/settings.py policy --action destroy --canonical

  destroy_plan="${INFRA_VALUES_DIR}/.destroy.tfplan"
  test -f "${destroy_plan}"
  apply_command=(
    tofu -chdir=infra/opentofu apply
    -state="../../${INFRA_VALUES_DIR}/terraform.tfstate"
    "../../${destroy_plan}"
  )
  python scripts/canonical-provider-env.py -- "${apply_command[@]}"
  rm -f "${destroy_plan}"
'
```

If the apply fails, retain the plan and state for diagnosis. Do not delete state or host-key files until the actual resource result is understood.

## After successful teardown

Verify that the selected state has no resources:

```bash
VALUES_SITE=<site> INFRA_VALUES_DIR=values/sites/<site> \
scripts/run-infra.sh bash -euo pipefail -c \
  'tofu -chdir=infra/opentofu state list -state="../../${INFRA_VALUES_DIR}/terraform.tfstate"'
```

For a permanently retired disposable site, remove only artifacts that are no longer needed:

- generated projections;
- empty state;
- transient host-key material;
- obsolete legacy files;
- service-state archives when recovery is no longer desired.

Retain `site.yaml`, `.sops.yaml`, and `secrets.sops.yaml` if the canonical definition should remain available for future recreation. Generated projections and state can be recreated; encrypted secret values cannot be reconstructed without their source.
