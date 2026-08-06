#!/usr/bin/env bash
set -euo pipefail

export INFRA_HOST_UID="${INFRA_HOST_UID:-$(scripts/host-id.sh uid)}"
export INFRA_HOST_GID="${INFRA_HOST_GID:-$(scripts/host-id.sh gid)}"

docker compose config >/dev/null
git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"

# shellcheck disable=SC2016
# The isolated inner Ansible lint stage retains these public-source contracts:
# lint_root="$(mktemp -d)"; cleanup_lint_root(); trap cleanup_lint_root EXIT;
# cp -a .ansible-lint ansible.cfg settings.example.json infra scaffold scripts "${lint_root}/";
# cd "${lint_root}"; ANSIBLE_CONFIG="${lint_root}/ansible.cfg" ansible-lint infra/ansible.
docker compose run --rm -v "${git_common_dir}:${git_common_dir}:ro" infra bash -euo pipefail -c '
stages=()
current_stage=""
print_summary() {
  status=$?
  if [[ ${status} -ne 0 && -n ${current_stage} ]]; then
    stages+=("FAIL ${current_stage}")
  fi
  printf "\n=== validation summary (exit %s) ===\n" "${status}"
  printf "%s\n" "${stages[@]:-no completed stages}"
  exit "${status}"
}
run_stage() {
  local name=$1
  shift
  current_stage=${name}
  printf "\n=== validation stage: %s ===\n" "${name}"
  "$@"
  stages+=("PASS ${name}")
  current_stage=""
}
trap print_summary EXIT

run_stage "preflight" python scripts/workspace-preflight.py
run_stage "opentofu" bash -euo pipefail -c "
  tofu -chdir=infra/opentofu init -backend=false
  tofu fmt -check -recursive infra/opentofu scaffold/terraform.tfvars
  tofu -chdir=infra/opentofu validate
  tflint --chdir=infra/opentofu --minimum-failure-severity=error
"
run_stage "shell" shellcheck scripts/*.sh tools/docker-entrypoint.sh
run_stage "python-quality" bash -euo pipefail -c "
  mapfile -t python_files < <(find infra/ansible scripts tests -type f -name '\''*.py'\'' | sort)
  python -m py_compile \"\${python_files[@]}\"
  quality_files=()
  while IFS= read -r file; do
    if [[ -n \"\${file}\" && \"\${file}\" != \#* ]]; then quality_files+=(\"\${file}\"); fi
  done < tools/python-format-files.txt
  black --check --diff \"\${quality_files[@]}\"
  ruff check --select=E9,F63,F7,F82 \"\${python_files[@]}\"
  mypy --follow-imports=skip --ignore-missing-imports scripts/canonical_values.py scripts/service_catalog.py
"
run_stage "contracts" bash -euo pipefail -c "
  python infra/ansible/scripts/apply-technitium-dns.py --check scaffold/dns-records.local.json
  python scripts/parse-env.py --env-file scaffold/.env.example >/dev/null
  python scripts/settings.py --settings settings.example.json validate >/dev/null
  python scripts/validate-service-contracts.py --repo .
  coverage erase
  coverage run --source=scripts -m unittest discover -s tests -p '\''test_*.py'\''
  coverage report --fail-under=70
"
run_stage "ansible" bash -euo pipefail -c "
  export ANSIBLE_TFVARS_FILE=scaffold/terraform.tfvars
  export INFRA_SETTINGS_FILE=settings.example.json
  ansible-inventory -i scaffold/ansible/inventory/local.yml -i infra/ansible/inventory/tfvars.py --list >/dev/null
  mapfile -t playbooks < <(python scripts/settings.py --settings settings.example.json ansible-playbooks --all)
  ansible-playbook -i scaffold/ansible/inventory/local.yml -i infra/ansible/inventory/tfvars.py --syntax-check \\
    infra/ansible/playbooks/storage-prep.yml \\
    infra/ansible/playbooks/guest-mount-feature-preflight.yml \\
    \"\${playbooks[@]}\"
  lint_root=\"\$(mktemp -d)\"
  cleanup_lint_root() { rm -rf \"\${lint_root}\"; }
  trap cleanup_lint_root EXIT
  cp -a .ansible-lint ansible.cfg settings.example.json infra scaffold scripts \"\${lint_root}/\"
  (cd \"\${lint_root}\" && ANSIBLE_CONFIG=\"\${lint_root}/ansible.cfg\" ansible-lint infra/ansible)
"
run_stage "summary" true
'
