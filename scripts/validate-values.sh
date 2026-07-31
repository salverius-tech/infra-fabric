#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC2016
scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values
python scripts/settings.py validate >/dev/null
python infra/ansible/scripts/apply-technitium-dns.py --check "${INFRA_VALUES_DIR}/dns-records.local.json"

ansible_inventory="${INFRA_VALUES_DIR}/ansible/inventory/local.yml"
if [[ -f "${INFRA_VALUES_DIR}/generated/manifest.json" && -f "${INFRA_VALUES_DIR}/generated/ansible-inventory.json" ]]; then
  ansible_inventory="${INFRA_VALUES_DIR}/generated/ansible-inventory.json"
fi

ansible-inventory -i "${ansible_inventory}" -i infra/ansible/inventory/tfvars.py --list >/dev/null

mapfile -t playbooks < <(python scripts/settings.py ansible-playbooks)
ansible-playbook -i "${ansible_inventory}" -i infra/ansible/inventory/tfvars.py --syntax-check \
  infra/ansible/playbooks/storage-prep.yml \
  infra/ansible/playbooks/guest-mount-feature-preflight.yml \
  "${playbooks[@]}"
'
