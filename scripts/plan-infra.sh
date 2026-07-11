#!/usr/bin/env bash
set -euo pipefail

rm -f tfplan tfplan.meta.json ./*.tfplan ./*.tfplan.meta.json

# shellcheck disable=SC2016
INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values
python scripts/settings.py summary
python scripts/storage-vars.py --summary
python scripts/guest-mount-feature-vars.py --summary

guest_mount_feature_vars="$(python scripts/guest-mount-feature-vars.py)"
ansible-playbook \
  -i values/ansible/inventory/local.yml \
  -i infra/ansible/inventory/tfvars.py \
  -e "${guest_mount_feature_vars}" \
  infra/ansible/playbooks/guest-mount-feature-preflight.yml

tofu -chdir=infra/opentofu init

enabled_services="$(python scripts/settings.py tofu-var)"
tofu -chdir=infra/opentofu plan \
  -var "enabled_services=${enabled_services}" \
  -var-file=../../values/terraform.tfvars \
  -state=../../values/terraform.tfstate \
  -out=../../tfplan

tofu -chdir=infra/opentofu show ../../tfplan
python scripts/tfplan-metadata.py create --plan tfplan --metadata tfplan.meta.json --print-summary
'
