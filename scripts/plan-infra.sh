#!/usr/bin/env bash
set -euo pipefail

source scripts/site-context.sh
require_site_context
require_canonical_authority

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
equivalence_after_json=""
equivalence_required="${INFRA_REQUIRE_EQUIVALENCE:-false}"
umask 077
python scripts/workspace-preflight.py --require-values --require-secrets
for plan_artifact in "${INFRA_VALUES_DIR}/tfplan" "${INFRA_VALUES_DIR}/tfplan.meta.json"; do
  if [[ -e "${plan_artifact}" ]] && [[ $(stat -c "%a" "${plan_artifact}") != "600" ]]; then
    printf "Removing plan artifact with non-private permissions: %s\\n" "${plan_artifact}" >&2
    rm -f "${plan_artifact}"
  fi
done

plan_tmp=""
metadata_tmp=""
cleanup_generated_tmp() {
  if [[ -n "${equivalence_after_json}" ]]; then
    rm -f "${equivalence_after_json}"
  fi
  if [[ -n "${plan_tmp}" ]]; then
    rm -f "${plan_tmp}"
  fi
  if [[ -n "${metadata_tmp}" ]]; then
    rm -f "${metadata_tmp}"
  fi
}
trap cleanup_generated_tmp EXIT

generated_dir="${INFRA_VALUES_DIR}/generated"
source_commit="$(git rev-parse HEAD 2>/dev/null || printf "unknown")"
python scripts/canonical-render.py \
  --site-file "${INFRA_VALUES_DIR}/site.yaml" \
  --output-dir "${generated_dir}" \
  --source-commit "${source_commit}"
python scripts/verify-projections.py \
  --site-file "${INFRA_VALUES_DIR}/site.yaml" \
  --generated-dir "${generated_dir}"
printf "Canonical non-secret projections refreshed for %s.\\n" "${INFRA_VALUES_DIR}"

ansible_inventory="${INFRA_VALUES_DIR}/generated/ansible-inventory.json"
tofu_vars_file="../../${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json"

if [[ "${equivalence_required}" == true && -z "${INFRA_EQUIVALENCE_BEFORE_JSON:-}" ]]; then
  printf "%s\\n" "Canonical planning requires INFRA_EQUIVALENCE_BEFORE_JSON when INFRA_REQUIRE_EQUIVALENCE=true." >&2
  exit 2
fi

ansible_inventory_args=("-i" "${ansible_inventory}")

storage_vars_args=()
if [[ -n "${1:-}" ]]; then
  storage_vars_args+=(--service "${1}")
fi
projection_args=(--projection "${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json")
python scripts/storage-vars.py --summary "${storage_vars_args[@]}" "${projection_args[@]}"
python scripts/guest-mount-feature-vars.py --summary "${projection_args[@]}"

guest_mount_feature_vars="$(python scripts/guest-mount-feature-vars.py "${projection_args[@]}")"
ansible-playbook \
  "${ansible_inventory_args[@]}" \
  -e "${guest_mount_feature_vars}" \
  infra/ansible/playbooks/guest-mount-feature-preflight.yml

tofu -chdir=infra/opentofu init

enabled_services_args=()
target_args=()
replace_args=()
if [[ -n "${1:-}" ]]; then
  target_projection_args=(--projection "${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json")
  while IFS= read -r target; do
    [[ -n "${target}" ]] && target_args+=("-target=${target}")
  done < <(python scripts/settings.py tofu-targets "${1}" "${target_projection_args[@]}")
  printf "Creating one-service canary plan for %s. A full plan is required after this rollout.\n" "${1}"
fi
if [[ -n "${2:-}" ]]; then
  replace_runtime_args=(--projection "${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json")
  replace_runtime="$(python scripts/service-runtime.py "${2}" "${replace_runtime_args[@]}")"
  replace_projection_args=(--projection "${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json")
  while IFS= read -r target; do
    [[ -n "${target}" ]] && replace_args+=("-replace=${target}")
  done < <(python scripts/settings.py tofu-replace-targets "${2}" --runtime "${replace_runtime}" "${replace_projection_args[@]}")
  printf "Forcing replacement of %s service resources for runtime %s. Review destroy/create output carefully.\n" "${2}" "${replace_runtime}"
fi

plan_tmp="$(mktemp "${INFRA_VALUES_DIR}/.tfplan-next.XXXXXX")"
rm -f "${plan_tmp}"
stateful_destroy_acknowledged=false
if [[ "${INFRA_ALLOW_DESTROY:-0}" == "1" ]]; then
  stateful_destroy_acknowledged=true
fi
plan_command=(tofu -chdir=infra/opentofu plan \
  "${enabled_services_args[@]}" \
  -var="stateful_destroy_acknowledged=${stateful_destroy_acknowledged}" \
  -var-file="${tofu_vars_file}" \
  -state=../../${INFRA_VALUES_DIR}/terraform.tfstate \
  "${target_args[@]}" \
  "${replace_args[@]}" \
  -out="../../${plan_tmp}")
python scripts/canonical-provider-env.py -- "${plan_command[@]}"

tofu -chdir=infra/opentofu show "../../${plan_tmp}"

if [[ -n "${INFRA_EQUIVALENCE_BEFORE_JSON:-}" ]]; then
  equivalence_after_json="$(mktemp "${INFRA_VALUES_DIR}/.tfplan-equivalence.XXXXXX.json")"
  tofu -chdir=infra/opentofu show -json "../../${plan_tmp}" > "${equivalence_after_json}"
  if ! python scripts/report-plan-equivalence.py "${INFRA_EQUIVALENCE_BEFORE_JSON}" "${equivalence_after_json}"; then
    printf "%s\n" "Plan equivalence review failed; inspect the redacted report before proceeding." >&2
    exit 1
  fi
fi

metadata_tmp="$(mktemp "${INFRA_VALUES_DIR}/.tfplan-meta-next.XXXXXX")"
python scripts/tfplan-metadata.py create \
  --plan "${plan_tmp}" \
  --metadata "${metadata_tmp}" \
  --target-service "${1:-}" \
  --replace-service "${2:-}" \
  --print-summary
chmod 600 "${plan_tmp}" "${metadata_tmp}"
mv -f "${plan_tmp}" "${INFRA_VALUES_DIR}/tfplan"
plan_tmp=""
mv -f "${metadata_tmp}" "${INFRA_VALUES_DIR}/tfplan.meta.json"
metadata_tmp=""
' bash "${target_service}" "${replace_service}"
