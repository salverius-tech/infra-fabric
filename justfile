set shell := ["bash", "-euo", "pipefail", "-c"]

# Show available commands
default:
    @just --list

# Fresh-checkout setup: build tools, create or clone values/, then show next files to edit
setup remote="":
    docker compose build infra
    @if [[ -d values ]]; then \
        scripts/values.sh check; \
    elif [[ -n "{{remote}}" ]]; then \
        scripts/values.sh clone "{{remote}}"; \
    else \
        scripts/values.sh init; \
    fi
    @printf '\nEdit these private values before running `just validate` and `just plan`:\n'
    @printf '  values/.env\n  values/terraform.tfvars\n  values/dns-records.local.json\n  values/ansible/inventory/local.yml\n'

# Show private values repo git status
[private]
status-values:
    scripts/values.sh status

# Verify values/ contains required files
[private]
check-values:
    scripts/values.sh check

# Validate public-safety rules for tracked source and scaffold templates
[private]
validate-public-safety:
    scripts/public-safety-check.sh

# Validate tracked public source only; does not require values/
[private]
validate-public: validate-public-safety
    docker compose config >/dev/null
    docker compose run --rm infra tofu -chdir=infra/opentofu init -backend=false
    docker compose run --rm infra tofu fmt -check infra/opentofu scaffold/terraform.tfvars
    docker compose run --rm infra tofu -chdir=infra/opentofu validate
    docker compose run --rm infra shellcheck scripts/*.sh tools/docker-entrypoint.sh
    docker compose run --rm infra python -m py_compile infra/opentofu/scripts/apply-technitium-dns.py scripts/parse-env.py tests/test_apply_technitium_dns.py
    docker compose run --rm infra python infra/opentofu/scripts/apply-technitium-dns.py --check scaffold/dns-records.local.json
    docker compose run --rm infra python scripts/parse-env.py scaffold/.env.example >/dev/null
    docker compose run --rm infra python -m unittest discover -s tests -p 'test_*.py'
    docker compose run --rm infra ansible-playbook -i scaffold/ansible/inventory/local.yml --syntax-check infra/ansible/playbooks/site.yml
    docker compose run --rm infra ansible-lint infra/ansible

# Validate only private values wiring and data shape
[private]
validate-values: check-values
    scripts/run-infra.sh python infra/opentofu/scripts/apply-technitium-dns.py --check values/dns-records.local.json
    scripts/run-infra.sh ansible-inventory -i values/ansible/inventory/local.yml --list >/dev/null
    scripts/run-infra.sh ansible-playbook -i values/ansible/inventory/local.yml --syntax-check infra/ansible/playbooks/site.yml

# Validate public source and private values wiring
validate: validate-public validate-values

# Review infrastructure changes using private values; writes tfplan for `just apply`
plan: check-values
    rm -f tfplan *.tfplan
    scripts/run-infra.sh tofu -chdir=infra/opentofu init
    scripts/run-infra.sh tofu -chdir=infra/opentofu plan -var-file=../../values/terraform.tfvars -state=../../values/terraform.tfstate -out=../../tfplan
    scripts/run-infra.sh tofu -chdir=infra/opentofu show ../../tfplan

# Apply reviewed infrastructure plan, then configure services with Ansible
apply: check-values
    test -f tfplan
    @printf 'About to apply existing tfplan. Review its timestamp before continuing:\n'
    @ls -l tfplan
    scripts/run-infra.sh tofu -chdir=infra/opentofu apply -state=../../values/terraform.tfstate ../../tfplan
    rm -f tfplan *.tfplan
    scripts/run-infra.sh ansible-playbook -i values/ansible/inventory/local.yml infra/ansible/playbooks/site.yml
