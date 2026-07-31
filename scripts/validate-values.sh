#!/usr/bin/env bash
set -euo pipefail

source scripts/site-context.sh
require_canonical_authority

# shellcheck disable=SC2016
scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values
python scripts/settings.py validate >/dev/null
python infra/ansible/scripts/apply-technitium-dns.py --check "${INFRA_VALUES_DIR}/dns-records.local.json"

ansible_inventory="${INFRA_VALUES_DIR}/ansible/inventory/local.yml"
if [[ -f "${INFRA_VALUES_DIR}/site.yaml" ]]; then
  for required_projection in manifest.json terraform.auto.tfvars.json ansible-inventory.json ansible-vars.json dns-records.json; do
    if [[ ! -f "${INFRA_VALUES_DIR}/generated/${required_projection}" ]]; then
      printf "%s\n" "Canonical site exists but generated projection is missing: ${required_projection}. Run just plan." >&2
      exit 1
    fi
  done
  python scripts/verify-projections.py --site-file "${INFRA_VALUES_DIR}/site.yaml" --generated-dir "${INFRA_VALUES_DIR}/generated"
  ansible_inventory="${INFRA_VALUES_DIR}/generated/ansible-inventory.json"
  tofu_vars_file="../../${INFRA_VALUES_DIR}/generated/terraform.auto.tfvars.json"
  canonical_ansible=true
fi

ansible-inventory -i "${ansible_inventory}" -i infra/ansible/inventory/tfvars.py --list >/dev/null

mapfile -t playbooks < <(python scripts/settings.py ansible-playbooks)
ansible-playbook -i "${ansible_inventory}" -i infra/ansible/inventory/tfvars.py --syntax-check \
  infra/ansible/playbooks/storage-prep.yml \
  infra/ansible/playbooks/guest-mount-feature-preflight.yml \
  "${playbooks[@]}"
'
