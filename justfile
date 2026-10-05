set shell := ["bash", "-euo", "pipefail", "-c"]

export INFRA_HOST_UID := `scripts/host-id.sh uid`
export INFRA_HOST_GID := `scripts/host-id.sh gid`

# Target 1Password vault for site age-identity operations; override with: just VAULT=<name> ...
VAULT := ""
export OP_VAULT := VAULT

# Show available commands
default:
    @just --list

# Fresh-checkout canonical setup: build tools, create or clone values/, then show selected site inputs
setup remote="" site="":
    @site_arg="{{site}}"; [[ -n "${site_arg}" ]] || { printf 'A canonical site is required. Run `just setup "" <site>`; use explicit migration or recovery tools for legacy forensics.\n' >&2; exit 2; }
    @source scripts/host-ssh-directory.sh; require_host_ssh_directory
    docker compose build infra
    @selected_remote="{{remote}}"; \
    if [[ -d values ]]; then \
        if [[ -d "values/sites/{{site}}" ]]; then VALUES_SITE="{{site}}" scripts/values.sh check; else VALUES_SITE="{{site}}" scripts/values.sh init; fi; \
    elif [[ -n "${selected_remote}" ]]; then \
        scripts/values.sh clone "${selected_remote}"; VALUES_SITE="{{site}}" scripts/values.sh check; \
    else \
        VALUES_SITE="{{site}}" scripts/values.sh init; \
    fi
    @VALUES_SITE="{{site}}" docker compose run --rm infra python scripts/workspace-preflight.py --require-values
    @printf 'Setup does not create credentials or invoke legacy wizards. Add the SOPS policy and bundle, then run the explicit ssh-initialize workflow if required.\n'
    @printf '\nEdit these private values before running `just validate` and `just plan`:\n'
    @printf '  values/sites/{{site}}/site.yaml\n  values/sites/{{site}}/.sops.yaml\n  values/sites/{{site}}/secrets.sops.yaml\n'

# Initialize the selected canonical site's bootstrap SSH identity through SOPS
ssh-initialize SITE="dev":
    @scripts/ssh-initialize.sh "{{SITE}}"

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
    scripts/validate-public.sh

# Validate only private values wiring and data shape
[private]
validate-values: check-values
    scripts/validate-values.sh

# Validate the selected canonical site: public source plus site-local private wiring
validate:
    scripts/require-site-context.sh
    just validate-public
    just validate-values

# Run the full Python test suite in the pinned tooling container; does not require values/
test *args:
    scripts/python.sh -m unittest discover -s tests -p 'test_*.py' {{args}}

# Run portable documentation contracts on the host; not a substitute for just test
test-local:
    python3 -m unittest \\
        tests.test_documentation_contract.DocumentationContractTests.test_documentation_inventory_covers_every_tracked_markdown_file \\
        tests.test_documentation_contract.DocumentationContractTests.test_tracked_markdown_relative_links_and_anchors_resolve \\
        tests.test_documentation_contract.DocumentationContractTests.test_installed_scaffold_readme_has_no_broken_relative_document_links

# Edit the selected site's encrypted SOPS bundle; the external site age key is required
edit-secrets SITE="dev":
    @scripts/edit-secrets.sh "{{SITE}}"

# Site age-identity lifecycle: generate | store | fetch | verify (store/fetch accept --force)
[positional-arguments]
site-identity +args:
    @scripts/site-age-identity.sh "$@"

# Check upstream releases and update eligible pinned versions after the safety hold period; pass --dry-run to report without writes
update *args:
    scripts/require-site-context.sh
    source scripts/site-context.sh; require_site_context
    scripts/python.sh scripts/update.py {{args}}

# Show recent Forgejo Actions runs for the private values repo
[private]
actions-status limit="10":
    scripts/require-site-context.sh
    INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh python scripts/forgejo-actions-monitor.py status --limit "{{limit}}"

# Watch a Forgejo Actions run until it reaches a terminal state
[private]
actions-watch run="latest":
    scripts/require-site-context.sh
    INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh python scripts/forgejo-actions-monitor.py watch "{{run}}"

# Show redacted logs for a Forgejo Actions run
[private]
actions-logs run="latest" tail="200":
    scripts/require-site-context.sh
    INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh python scripts/forgejo-actions-monitor.py logs "{{run}}" --tail "{{tail}}"

# Show Forgejo Actions runner registration and service status
[private]
actions-runners:
    scripts/require-site-context.sh
    INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh python scripts/forgejo-actions-monitor.py runners

# Remove saved plan artifacts
[private]
clean-plans:
    scripts/require-site-context.sh
    source scripts/site-context.sh; values_dir="$(site_values_dir)"; rm -f "${values_dir}/tfplan" "${values_dir}/tfplan.meta.json" "${values_dir}"/*.tfplan "${values_dir}"/*.tfplan.meta.json

# Review infrastructure changes using private values; writes tfplan for `just apply`
plan:
    scripts/require-site-context.sh
    just check-values
    scripts/plan-infra.sh

# Apply reviewed infrastructure plan, then configure services with Ansible
apply:
    scripts/require-site-context.sh
    just check-values
    scripts/apply-infra.sh

# Exercise the guarded Hermes failed-activation rollback path on disposable dev only
rehearse-development-rollback approval="":
    scripts/require-site-context.sh
    scripts/rehearse-development-rollback.sh "{{approval}}"

# Create a guarded full-site destroy plan; review before the separately approved teardown apply
teardown-plan:
    scripts/require-site-context.sh
    just check-values
    scripts/teardown-infra.sh plan

# Apply the reviewed guarded destroy plan; requires literal --approve
teardown-apply approval="":
    scripts/require-site-context.sh
    just check-values
    scripts/teardown-infra.sh apply "{{approval}}"
