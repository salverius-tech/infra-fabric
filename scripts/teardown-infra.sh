#!/usr/bin/env bash
set -euo pipefail

# Guarded canonical teardown. This is intentionally separate from normal apply:
# it only accepts a fresh, metadata-bound destroy plan and never runs Ansible.
source scripts/site-context.sh
require_site_context
require_canonical_authority

action="${1:-}"
case "${action}" in
  plan|apply) ;;
  *)
    printf 'Usage: scripts/teardown-infra.sh {plan|apply --approve}\n' >&2
    exit 2
    ;;
esac
if [[ "${action}" == "apply" && "${2:-}" != "--approve" ]]; then
  printf 'Teardown apply requires an explicit --approve argument after review of the fresh destroy plan.\n' >&2
  exit 2
fi

# shellcheck disable=SC2016
INFRA_COPY_SSH_KEYS=true INFRA_SSH_IDENTITY_SOURCE=sops scripts/run-infra.sh bash -euo pipefail -c '
umask 077
python scripts/workspace-preflight.py --require-values --require-secrets
python scripts/settings.py policy --action destroy --canonical

plan_path="${INFRA_VALUES_DIR}/destroy.tfplan"
metadata_path="${INFRA_VALUES_DIR}/destroy.tfplan.meta.json"
if [[ "${1}" == "plan" ]]; then
  for required_projection in manifest.json terraform.auto.tfvars.json ansible-inventory.json ansible-vars.json dns-records.json; do
    if [[ ! -f "${INFRA_VALUES_DIR}/generated/${required_projection}" ]]; then
      printf "Canonical teardown requires a complete verified projection set. Run just plan after correcting canonical inputs.\n" >&2
      exit 1
    fi
  done
  python scripts/verify-projections.py --site-file "${INFRA_VALUES_DIR}/site.yaml" --generated-dir "${INFRA_VALUES_DIR}/generated"
  tofu -chdir=infra/opentofu init
  plan_tmp="$(mktemp "${INFRA_VALUES_DIR}/.destroy-tfplan-next.XXXXXX")"
  metadata_tmp="$(mktemp "${INFRA_VALUES_DIR}/.destroy-tfplan-meta-next.XXXXXX")"
  cleanup() { rm -f "${plan_tmp}" "${metadata_tmp}"; }
  trap cleanup EXIT
  rm -f "${plan_tmp}" "${metadata_tmp}"
  destroy_command=(tofu -chdir=infra/opentofu plan -destroy \
    -var="stateful_destroy_acknowledged=true" \
    -var-file="../../${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json" \
    -state="../../${INFRA_VALUES_DIR}/terraform.tfstate" \
    -out="../../${plan_tmp}")
  python scripts/canonical-provider-env.py -- "${destroy_command[@]}"
  tofu -chdir=infra/opentofu show "../../${plan_tmp}"
  python scripts/tfplan-metadata.py create \
    --plan "${plan_tmp}" --metadata "${metadata_tmp}" --operation destroy --print-summary
  chmod 600 "${plan_tmp}" "${metadata_tmp}"
  mv -f "${plan_tmp}" "${plan_path}"
  mv -f "${metadata_tmp}" "${metadata_path}"
  plan_tmp=""
  metadata_tmp=""
  exit 0
fi

[[ -f "${plan_path}" && -f "${metadata_path}" ]] || {
  printf "No saved destroy plan found. Run just teardown-plan, review it, then run just teardown-apply --approve.\n" >&2
  exit 1
}
python scripts/tfplan-metadata.py verify \
  --plan "${plan_path}" --metadata "${metadata_path}" --operation destroy --allow-destroy --allow-stateful-batch
python scripts/tfplan-metadata.py summary --metadata "${metadata_path}"
execution_snapshot="$(python scripts/execution-snapshot.py create \
  --values-dir "${INFRA_VALUES_DIR}" --plan "${plan_path}" --metadata "${metadata_path}" \
  --destination-root "${INFRA_VALUES_DIR}/execution-snapshots" --site "${VALUES_SITE}")"
cleanup_artifacts() { rm -f "${plan_path}" "${metadata_path}"; }
trap cleanup_artifacts EXIT
python scripts/execution-snapshot.py verify --snapshot "${execution_snapshot}"
python scripts/state-snapshot.py create \
  --state "${INFRA_VALUES_DIR}/terraform.tfstate" --backup-dir "${INFRA_VALUES_DIR}/state-backups"
python scripts/execution-snapshot.py verify --snapshot "${execution_snapshot}"
(
  while IFS="=" read -r variable _; do
    case "${variable}" in TF_VAR_*) unset "${variable}" ;; esac
  done < <(env)
  python scripts/canonical-provider-env.py -- \
    tofu -chdir=infra/opentofu apply \
      -state="../../${INFRA_VALUES_DIR}/terraform.tfstate" \
      "../../${execution_snapshot}/tfplan"
)
python scripts/execution-snapshot.py verify --snapshot "${execution_snapshot}"
printf "Guarded teardown completed. Verify provider state before removing any retained recovery artifacts.\n"
' bash "${action}"