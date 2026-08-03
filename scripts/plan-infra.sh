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
if [[ ! -f "${INFRA_VALUES_DIR}/site.yaml" ]]; then
  python scripts/settings.py summary
fi
for plan_artifact in "${INFRA_VALUES_DIR}/tfplan" "${INFRA_VALUES_DIR}/tfplan.meta.json"; do
  if [[ -e "${plan_artifact}" ]] && [[ $(stat -c "%a" "${plan_artifact}") != "600" ]]; then
    printf "Removing plan artifact with non-private permissions: %s\\n" "${plan_artifact}" >&2
    rm -f "${plan_artifact}"
  fi
done

generated_tmp=""
generated_backup=""
generated_verified=false
plan_tmp=""
metadata_tmp=""
cleanup_generated_tmp() {
  if [[ -n "${generated_tmp}" && -d "${generated_tmp}" ]]; then
    rm -rf "${generated_tmp}"
  fi
  if [[ -n "${generated_backup}" && ! "${generated_verified}" == true && -e "${generated_backup}" ]]; then
    rm -rf "${generated_dir}" 2>/dev/null || true
    mv "${generated_backup}" "${generated_dir}" || printf "Unable to restore prior canonical projections.\\n" >&2
  fi
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

if [[ -f "${INFRA_VALUES_DIR}/site.yaml" ]]; then
  generated_dir="${INFRA_VALUES_DIR}/generated"
  generated_tmp="$(mktemp -d "${INFRA_VALUES_DIR}/.canonical-generated.XXXXXX")"
  source_commit="$(git rev-parse HEAD 2>/dev/null || printf "unknown")"
  python scripts/canonical-render.py \
    --site-file "${INFRA_VALUES_DIR}/site.yaml" \
    --output-dir "${generated_tmp}" \
    --source-commit "${source_commit}"
  if [[ -e "${generated_dir}" ]]; then
    generated_backup="$(mktemp -d "${INFRA_VALUES_DIR}/.canonical-generated-previous.XXXXXX")"
    rmdir "${generated_backup}"
    mv "${generated_dir}" "${generated_backup}"
  fi
  if ! mv "${generated_tmp}" "${generated_dir}"; then
    printf "Unable to install refreshed canonical projections.\\n" >&2
    exit 1
  fi
  generated_tmp=""
  python scripts/verify-projections.py \
    --site-file "${INFRA_VALUES_DIR}/site.yaml" \
    --generated-dir "${generated_dir}"
  generated_verified=true
  if [[ -n "${generated_backup}" ]]; then
    rm -rf "${generated_backup}"
    generated_backup=""
  fi
  printf "Canonical non-secret projections refreshed for %s.\\n" "${INFRA_VALUES_DIR}"
fi

ansible_inventory="${INFRA_VALUES_DIR}/ansible/inventory/local.yml"
tofu_vars_file="../../${INFRA_VALUES_DIR}/terraform.tfvars"
canonical_site=false
if [[ -f "${INFRA_VALUES_DIR}/site.yaml" ]]; then
  for required_projection in manifest.json terraform.auto.tfvars.json ansible-inventory.json ansible-vars.json dns-records.json; do
    if [[ ! -f "${INFRA_VALUES_DIR}/generated/${required_projection}" ]]; then
      printf "%s\n" "Canonical site exists but generated projection is missing: ${required_projection}. Render projections before planning." >&2
      exit 1
    fi
  done
  python scripts/verify-projections.py --site-file "${INFRA_VALUES_DIR}/site.yaml" --generated-dir "${INFRA_VALUES_DIR}/generated"
  ansible_inventory="${INFRA_VALUES_DIR}/generated/ansible-inventory.json"
  tofu_vars_file="../../${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json"
  canonical_site=true
fi

if [[ "${canonical_site}" == true && "${equivalence_required}" == true && -z "${INFRA_EQUIVALENCE_BEFORE_JSON:-}" ]]; then
  printf "%s\\n" "Canonical planning requires INFRA_EQUIVALENCE_BEFORE_JSON when INFRA_REQUIRE_EQUIVALENCE=true." >&2
  exit 2
fi

ansible_inventory_args=("-i" "${ansible_inventory}")
if [[ "${canonical_site}" != true ]]; then
  ansible_inventory_args+=("-i" "infra/ansible/inventory/tfvars.py")
fi

storage_vars_args=()
if [[ -n "${1:-}" ]]; then
  storage_vars_args+=(--service "${1}")
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

tofu -chdir=infra/opentofu init

enabled_services_args=()
target_args=()
replace_args=()
if [[ "${canonical_site}" == true ]]; then
  enabled_services_args=()
else
  enabled_services="$(python scripts/settings.py tofu-var)"
  enabled_services_args=("-var" "enabled_services=${enabled_services}")
fi
if [[ -n "${1:-}" ]]; then
  target_projection_args=()
  if [[ "${canonical_site}" == true ]]; then
    target_projection_args+=(--projection "${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json")
  fi
  while IFS= read -r target; do
    [[ -n "${target}" ]] && target_args+=("-target=${target}")
  done < <(python scripts/settings.py tofu-targets "${1}" "${target_projection_args[@]}")
  printf "Creating one-service canary plan for %s. A full plan is required after this rollout.\n" "${1}"
fi
if [[ -n "${2:-}" ]]; then
  replace_runtime_args=()
  if [[ "${canonical_site}" == true ]]; then
    replace_runtime_args+=(--projection "${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json")
  fi
  replace_runtime="$(python scripts/service-runtime.py "${2}" "${replace_runtime_args[@]}")"
  replace_projection_args=()
  if [[ "${canonical_site}" == true ]]; then
    replace_projection_args+=(--projection "${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json")
  fi
  while IFS= read -r target; do
    [[ -n "${target}" ]] && replace_args+=("-replace=${target}")
  done < <(python scripts/settings.py tofu-replace-targets "${2}" --runtime "${replace_runtime}" "${replace_projection_args[@]}")
  printf "Forcing replacement of %s service resources for runtime %s. Review destroy/create output carefully.\n" "${2}" "${replace_runtime}"
fi

plan_tmp="$(mktemp "${INFRA_VALUES_DIR}/.tfplan-next.XXXXXX")"
rm -f "${plan_tmp}"
plan_command=(tofu -chdir=infra/opentofu plan \
  "${enabled_services_args[@]}" \
  -var-file="${tofu_vars_file}" \
  -state=../../${INFRA_VALUES_DIR}/terraform.tfstate \
  "${target_args[@]}" \
  "${replace_args[@]}" \
  -out="../../${plan_tmp}")
if [[ "${canonical_site}" == true ]]; then
  python scripts/canonical-provider-env.py -- "${plan_command[@]}"
else
  "${plan_command[@]}"
fi

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
