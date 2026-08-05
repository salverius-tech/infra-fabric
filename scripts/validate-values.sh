#!/usr/bin/env bash
set -euo pipefail

source scripts/site-context.sh
require_site_context
require_canonical_authority

# shellcheck disable=SC2016
scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values
ansible_inventory="${INFRA_VALUES_DIR}/ansible/inventory/local.yml"
dns_records_file="${INFRA_VALUES_DIR}/dns-records.local.json"
canonical_site=false
if [[ -f "${INFRA_VALUES_DIR}/site.yaml" ]]; then
  python scripts/canonical-values.py --site-file "${INFRA_VALUES_DIR}/site.yaml" validate >/dev/null
  # Validation owns a non-provider projection refresh so a newly scaffolded
  # canonical site can pass structural checks before it has a reviewed plan.
  source_commit="$(git rev-parse HEAD 2>/dev/null || printf "unknown")"
  python scripts/canonical-render.py \
    --site-file "${INFRA_VALUES_DIR}/site.yaml" \
    --output-dir "${INFRA_VALUES_DIR}/generated" \
    --source-commit "${source_commit}"
  python scripts/verify-projections.py --site-file "${INFRA_VALUES_DIR}/site.yaml" --generated-dir "${INFRA_VALUES_DIR}/generated"
  ansible_inventory="${INFRA_VALUES_DIR}/generated/ansible-inventory.json"
  tofu_vars_file="../../${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json"
  dns_records_file="${INFRA_VALUES_DIR}/generated/dns-records.json"
  canonical_ansible=true
  canonical_site=true
  playbook_projection_args=(--projection "${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json")
else
  python scripts/settings.py validate >/dev/null
  playbook_projection_args=()
fi

python infra/ansible/scripts/apply-technitium-dns.py --check "${dns_records_file}"

ansible_inventory_args=("-i" "${ansible_inventory}")
if [[ "${canonical_site}" != true ]]; then
  ansible_inventory_args+=("-i" "infra/ansible/inventory/tfvars.py")
fi

ansible-inventory "${ansible_inventory_args[@]}" --list >/dev/null

mapfile -t playbooks < <(python scripts/settings.py ansible-playbooks "${playbook_projection_args[@]}")
ansible-playbook "${ansible_inventory_args[@]}" --syntax-check \
  infra/ansible/playbooks/storage-prep.yml \
  infra/ansible/playbooks/guest-mount-feature-preflight.yml \
  "${playbooks[@]}"
'
