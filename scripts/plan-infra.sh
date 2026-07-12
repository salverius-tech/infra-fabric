#!/usr/bin/env bash
set -euo pipefail

rm -f tfplan tfplan.meta.json ./*.tfplan ./*.tfplan.meta.json

target_service="${INFRA_TARGET_SERVICE:-}"

# shellcheck disable=SC2016
INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values
python scripts/settings.py summary
storage_vars_args=()
if [[ -n "${1:-}" ]]; then
  storage_vars_args+=(--service "${1}")
fi
python scripts/storage-vars.py --summary "${storage_vars_args[@]}"
python scripts/guest-mount-feature-vars.py --summary

guest_mount_feature_vars="$(python scripts/guest-mount-feature-vars.py)"
ansible-playbook \
  -i values/ansible/inventory/local.yml \
  -i infra/ansible/inventory/tfvars.py \
  -e "${guest_mount_feature_vars}" \
  infra/ansible/playbooks/guest-mount-feature-preflight.yml

tofu -chdir=infra/opentofu init

enabled_services="$(python scripts/settings.py tofu-var)"
target_args=()
if [[ -n "${1:-}" ]]; then
  while IFS= read -r target; do
    [[ -n "${target}" ]] && target_args+=("-target=${target}")
  done < <(python scripts/settings.py tofu-targets "${1}")
  printf "Creating one-service canary plan for %s. A full plan is required after this rollout.\n" "${1}"
fi

tofu -chdir=infra/opentofu plan \
  -var "enabled_services=${enabled_services}" \
  -var-file=../../values/terraform.tfvars \
  -state=../../values/terraform.tfstate \
  "${target_args[@]}" \
  -out=../../tfplan

tofu -chdir=infra/opentofu show ../../tfplan
python scripts/tfplan-metadata.py create --plan tfplan --metadata tfplan.meta.json --print-summary
' bash "${target_service}"
