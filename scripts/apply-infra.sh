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
source scripts/site-context.sh
python scripts/workspace-preflight.py --require-values --require-secrets
python scripts/settings.py policy --action apply --canonical

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
execution_plan="${INFRA_VALUES_DIR}/tfplan"
execution_metadata="${INFRA_VALUES_DIR}/tfplan.meta.json"
execution_values_dir="${INFRA_VALUES_DIR}"
execution_snapshot=""
execution_snapshot_root="${INFRA_EXECUTION_SNAPSHOT_ROOT:-${INFRA_VALUES_DIR}/execution-snapshots}"
state_snapshot_root="${INFRA_STATE_SNAPSHOT_ROOT:-${INFRA_VALUES_DIR}/state-backups}"

target_service="${1:-}"
replace_service="${2:-}"
shift 2 || true
verify_args=()
for verify_arg in "$@"; do
  if [[ -n "${verify_arg}" ]]; then
    verify_args+=("${verify_arg}")
  fi
done
verify_saved_plan() {
  python scripts/tfplan-metadata.py verify \
    --plan "${execution_plan}" \
    --metadata "${execution_metadata}" \
    --target-service "${target_service}" \
    --replace-service "${replace_service}" \
    "${verify_args[@]}"
}
verify_saved_plan
python scripts/tfplan-metadata.py summary --metadata "${INFRA_VALUES_DIR}/tfplan.meta.json"
require_canonical_projection_set "${INFRA_VALUES_DIR}/generated"
# Apply consumes existing plan-bound projections and verifies them exactly once.
python scripts/verify-projections.py --site-file "${INFRA_VALUES_DIR}/site.yaml" --generated-dir "${INFRA_VALUES_DIR}/generated"
ansible_inventory="${INFRA_VALUES_DIR}/generated/ansible-inventory.json"

# The selected canonical site has a distinct SOPS-backed Proxmox-management
# identity materialized before this lifecycle payload starts. Check it before snapshots or
# provider mutation so an incomplete canonical secret contract fails closed.
if [[ ! -f "${HOME}/.ssh/canonical-proxmox-management" ]]; then
  printf "Canonical apply requires the SOPS-backed Proxmox management SSH identity.\n" >&2
  exit 2
fi

execution_snapshot="$(python scripts/execution-snapshot.py create \
  --values-dir "${INFRA_VALUES_DIR}" \
  --plan "${execution_plan}" \
  --metadata "${execution_metadata}" \
  --destination-root "${execution_snapshot_root}" \
  --site "${VALUES_SITE}")"
python scripts/execution-snapshot.py verify --snapshot "${execution_snapshot}"
execution_plan="${execution_snapshot}/tfplan"
execution_metadata="${execution_snapshot}/tfplan.meta.json"
execution_values_dir="${execution_snapshot}/values/sites/${VALUES_SITE}"
ansible_inventory="${execution_values_dir}/generated/ansible-inventory.json"
tofu_vars_file="../../${execution_values_dir}/generated/terraform.auto.tfvars.json"
export VALUES_DIR="${execution_snapshot}/values"

ansible_inventory_args=("-i" "${ansible_inventory}")

storage_vars_args=()
if [[ -n "${target_service}" ]]; then
  storage_vars_args+=(--service "${target_service}")
fi
projection_args=(--projection "${execution_values_dir}/generated/terraform.auto.tfvars.json")
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

# Reverify immutable execution inputs immediately before the mutation boundary.
if [[ -n "${execution_snapshot}" ]]; then
  python scripts/execution-snapshot.py verify --snapshot "${execution_snapshot}"
else
  verify_saved_plan
fi
python scripts/state-snapshot.py create \
  --state "${INFRA_VALUES_DIR}/terraform.tfstate" \
  --backup-dir "${state_snapshot_root}"

# A saved plan already contains its variable values. Do not let TF_VAR_* values
# from the runtime env be compared against those values during apply.
(
  while IFS='=' read -r variable _; do
    case "${variable}" in
      TF_VAR_*) unset "${variable}" ;;
    esac
  done < <(env)
  execution_plan_argument="${execution_plan}"
  if [[ "${execution_plan_argument}" != /* ]]; then
    execution_plan_argument="../../${execution_plan_argument}"
  fi
  apply_command=(tofu -chdir=infra/opentofu apply -state=../../${INFRA_VALUES_DIR}/terraform.tfstate "${execution_plan_argument}")
  python scripts/canonical-provider-env.py -- "${apply_command[@]}"
)

# Diagnostic only: mutation was authorized by the immediately preceding verification.
if [[ -n "${execution_snapshot}" ]]; then
  python scripts/execution-snapshot.py verify --snapshot "${execution_snapshot}"
else
  verify_saved_plan
fi

ansible_service_args=()
if [[ -n "${target_service}" ]]; then
  ansible_service_args+=(--service "${target_service}")
fi
python scripts/apply-ansible-services.py \
  "${ansible_service_args[@]}"
' bash "${target_service}" "${replace_service}" "${destroy_verify_flag}" "${stateful_batch_verify_flag}"
