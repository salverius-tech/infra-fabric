#!/usr/bin/env bash
set -euo pipefail

source scripts/site-context.sh
require_site_context
require_canonical_authority

# shellcheck disable=SC2016
scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values
python scripts/canonical-values.py --site-file "${INFRA_VALUES_DIR}/site.yaml" validate >/dev/null
# Validation owns one non-provider projection refresh so a newly scaffolded
# canonical site can pass structural checks before it has a reviewed plan.
source_commit="$(git rev-parse HEAD 2>/dev/null || printf "unknown")"
generated_dir="${INFRA_GENERATED_DIR:-${INFRA_VALUES_DIR}/generated}"
python scripts/canonical-render.py \
  --site-file "${INFRA_VALUES_DIR}/site.yaml" \
  --output-dir "${generated_dir}" \
  --source-commit "${source_commit}"
python scripts/verify-projections.py --site-file "${INFRA_VALUES_DIR}/site.yaml" --generated-dir "${generated_dir}"
ansible_inventory="${generated_dir}/ansible-inventory.json"
dns_records_file="${generated_dir}/dns-records.json"
playbook_projection_args=(--projection "${generated_dir}/terraform.auto.tfvars.json")

python infra/ansible/scripts/apply-technitium-dns.py --check "${dns_records_file}"

ansible_inventory_args=("-i" "${ansible_inventory}")

ansible-inventory "${ansible_inventory_args[@]}" --list >/dev/null

mapfile -t playbooks < <(python scripts/settings.py ansible-playbooks "${playbook_projection_args[@]}")
ansible-playbook "${ansible_inventory_args[@]}" --syntax-check \
  infra/ansible/playbooks/storage-prep.yml \
  infra/ansible/playbooks/guest-mount-feature-preflight.yml \
  "${playbooks[@]}"
'
