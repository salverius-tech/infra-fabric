#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || "$1" != "--approve-development-rollback" ]]; then
  printf 'Usage: VALUES_SITE=dev scripts/rehearse-development-rollback.sh --approve-development-rollback\n' >&2
  exit 2
fi

source scripts/site-context.sh
require_site_context

if [[ "${VALUES_SITE}" != "dev" ]]; then
  printf 'Development rollback rehearsal is limited to VALUES_SITE=dev.\n' >&2
  exit 2
fi

values_dir="$(site_values_dir)"
inventory="/workspace/${values_dir}/generated/ansible-inventory.json"
vars_file="/workspace/${values_dir}/generated/ansible-vars.json"
flat_vars_file="/tmp/.development-rollback-ansible-vars.json"

set +e
INFRA_COPY_SSH_KEYS=true INFRA_SSH_IDENTITY_SOURCE=sops scripts/run-infra.sh bash -euo pipefail -c \
  "export PATH=/opt/ansible/bin:\$PATH; python /workspace/scripts/flatten-ansible-vars.py --input ${vars_file@Q} --output ${flat_vars_file@Q}; trap 'rm -f ${flat_vars_file@Q}' EXIT; ansible-playbook -i ${inventory@Q} -e @${flat_vars_file@Q} -e '{\"ansible_ssh_private_key_file\":\"/home/anvil/.ssh/canonical-bootstrap\",\"ansible_ssh_common_args\":\"-o UserKnownHostsFile=/workspace/${values_dir}/ansible/known_hosts -o StrictHostKeyChecking=yes\",\"hermes_rollback_rehearsal_approved\":true}' infra/ansible/playbooks/hermes-rollback-rehearsal.yml"
status=$?
set -e

if [[ ${status} -ne 0 ]]; then
  printf 'Development rollback rehearsal did not restore Hermes successfully.\n' >&2
  exit "${status}"
fi

printf 'Development rollback rehearsal completed with restored Hermes health.\n'