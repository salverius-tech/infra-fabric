#!/usr/bin/env bash
set -euo pipefail

source scripts/site-context.sh
require_site_context
require_canonical_authority

destroy_verify_flag=""
if [[ "${INFRA_ALLOW_DESTROY:-}" == "1" ]]; then
  destroy_verify_flag="--allow-destroy"
fi
stateful_batch_verify_flag=""
if [[ "${INFRA_ALLOW_STATEFUL_BATCH:-}" == "1" ]]; then
  stateful_batch_verify_flag="--allow-stateful-batch"
fi
target_service="${INFRA_TARGET_SERVICE:-}"
replace_service="${INFRA_REPLACE_SERVICE:-}"
if [[ -n "${replace_service}" ]]; then
  if [[ -n "${target_service}" && "${target_service}" != "${replace_service}" ]]; then
    printf 'INFRA_TARGET_SERVICE and INFRA_REPLACE_SERVICE must match when both are set.\n' >&2
    exit 2
  fi
  target_service="${replace_service}"
fi

# shellcheck disable=SC2016
INFRA_COPY_SSH_KEYS=true INFRA_SSH_IDENTITY_SOURCE=sops scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values --require-secrets
if [[ -f "${INFRA_VALUES_DIR}/site.yaml" ]]; then
  python scripts/settings.py policy --action apply --canonical
else
  python scripts/settings.py policy --action apply
fi

if [[ ! -f "${INFRA_VALUES_DIR}/tfplan" && ! -f "${INFRA_VALUES_DIR}/tfplan.meta.json" ]]; then
  printf "No saved infrastructure plan found. Run just plan, review the output, then run just apply.\n" >&2
  exit 1
fi
if [[ ! -f "${INFRA_VALUES_DIR}/tfplan" ]]; then
  printf "Saved plan file is missing for the selected site. Run just plan again.\n" >&2
  exit 1
fi
if [[ ! -f "${INFRA_VALUES_DIR}/tfplan.meta.json" ]]; then
  printf "Saved plan metadata is missing for the selected site. Run just plan again.\n" >&2
  exit 1
fi

target_service="${1:-}"
replace_service="${2:-}"
shift 2 || true
verify_args=()
for verify_arg in "$@"; do
  if [[ -n "${verify_arg}" ]]; then
    verify_args+=("${verify_arg}")
  fi
done
python scripts/tfplan-metadata.py verify \
  --plan "${INFRA_VALUES_DIR}/tfplan" \
  --metadata "${INFRA_VALUES_DIR}/tfplan.meta.json" \
  --target-service "${target_service}" \
  --replace-service "${replace_service}" \
  "${verify_args[@]}"
python scripts/tfplan-metadata.py summary --metadata "${INFRA_VALUES_DIR}/tfplan.meta.json"
if [[ ! -f "${INFRA_VALUES_DIR}/site.yaml" ]]; then
  python scripts/settings.py summary
fi
ansible_inventory="${INFRA_VALUES_DIR}/ansible/inventory/local.yml"
canonical_ansible_args=()
canonical_site=false
if [[ -f "${INFRA_VALUES_DIR}/site.yaml" ]]; then
  for required_projection in manifest.json terraform.auto.tfvars.json ansible-inventory.json ansible-vars.json dns-records.json; do
    if [[ ! -f "${INFRA_VALUES_DIR}/generated/${required_projection}" ]]; then
      printf "%s\n" "Canonical site exists but generated projection is missing: ${required_projection}. Run just plan again." >&2
      exit 1
    fi
  done
  python scripts/verify-projections.py --site-file "${INFRA_VALUES_DIR}/site.yaml" --generated-dir "${INFRA_VALUES_DIR}/generated"
  ansible_inventory="${INFRA_VALUES_DIR}/generated/ansible-inventory.json"
  tofu_vars_file="../../${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json"
  canonical_ansible_args=(--canonical-ansible)
  canonical_site=true
fi

ansible_inventory_args=("-i" "${ansible_inventory}")
if [[ "${#canonical_ansible_args[@]}" -eq 0 ]]; then
  ansible_inventory_args+=("-i" "infra/ansible/inventory/tfvars.py")
fi

storage_vars_args=()
if [[ -n "${target_service}" ]]; then
  storage_vars_args+=(--service "${target_service}")
fi
projection_args=()
if [[ "${canonical_site}" == true ]]; then
  projection_args+=(--projection "${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json")
fi
python scripts/storage-vars.py --summary "${storage_vars_args[@]}" "${projection_args[@]}"
python scripts/guest-mount-feature-vars.py --summary "${projection_args[@]}"

guest_mount_feature_vars="$(python scripts/guest-mount-feature-vars.py "${projection_args[@]}")"
ansible-playbook \
  "${ansible_inventory_args[@]}" \
  -e "${guest_mount_feature_vars}" \
  infra/ansible/playbooks/guest-mount-feature-preflight.yml

printf "Applying verified tfplan created by just plan.\n"
cleanup_plan_artifacts() {
  rm -f "${INFRA_VALUES_DIR}/tfplan" "${INFRA_VALUES_DIR}/tfplan.meta.json"
}
trap cleanup_plan_artifacts EXIT

storage_vars="$(python scripts/storage-vars.py "${storage_vars_args[@]}" "${projection_args[@]}")"
if python -c "import json, sys; raise SystemExit(0 if json.loads(sys.argv[1]).get(\"storage_bind_mounts\") else 1)" "${storage_vars}"; then
  ansible-playbook \
    "${ansible_inventory_args[@]}" \
    -e "${storage_vars}" \
    infra/ansible/playbooks/storage-prep.yml
fi

# A saved plan already contains its variable values. Do not let TF_VAR_* values
# from the runtime env be compared against those values during apply.
(
  while IFS='=' read -r variable _; do
    case "${variable}" in
      TF_VAR_*) unset "${variable}" ;;
    esac
  done < <(env)
  apply_command=(tofu -chdir=infra/opentofu apply -state=../../${INFRA_VALUES_DIR}/terraform.tfstate ../../${INFRA_VALUES_DIR}/tfplan)
  if [[ "${canonical_site}" == true ]]; then
    python scripts/canonical-provider-env.py -- "${apply_command[@]}"
  else
    "${apply_command[@]}"
  fi
)

python scripts/tfplan-metadata.py verify \
  --plan "${INFRA_VALUES_DIR}/tfplan" \
  --metadata "${INFRA_VALUES_DIR}/tfplan.meta.json" \
  --target-service "${target_service}" \
  --replace-service "${replace_service}" \
  "${verify_args[@]}"

ansible_service_args=()
if [[ -n "${target_service}" ]]; then
  ansible_service_args+=(--service "${target_service}")
fi
if [[ "${#canonical_ansible_args[@]}" -gt 0 ]]; then
  python scripts/apply-ansible-services.py \
    "${canonical_ansible_args[@]}" \
    "${ansible_service_args[@]}"
else
  python scripts/apply-ansible-services.py \
    --inventory "${ansible_inventory}" \
    --inventory infra/ansible/inventory/tfvars.py \
    --env-file "${INFRA_VALUES_DIR}/.env" \
    "${ansible_service_args[@]}"
fi
' bash "${target_service}" "${replace_service}" "${destroy_verify_flag}" "${stateful_batch_verify_flag}"
