set shell := ["bash", "-euo", "pipefail", "-c"]

export INFRA_HOST_UID := `scripts/host-id.sh uid`
export INFRA_HOST_GID := `scripts/host-id.sh gid`

# Show available commands
default:
    @just --list

# Fresh-checkout setup: build tools, create or clone values/, then show next files to edit
setup remote="" site="":
    docker compose build infra
    @env -u VALUES_SITE -u INFRA_VALUES_DIR scripts/python.sh scripts/settings.py validate >/dev/null
    @selected_remote="$(env -u VALUES_SITE -u INFRA_VALUES_DIR scripts/discover-values-remote.sh "{{remote}}")"; \
    if [[ -d values ]]; then \
        if [[ -n "{{site}}" ]]; then \
            if [[ -d "values/sites/{{site}}" ]]; then VALUES_SITE="{{site}}" scripts/values.sh check; else VALUES_SITE="{{site}}" scripts/values.sh init; fi; \
        else \
            scripts/values.sh check; \
        fi; \
    elif [[ -n "${selected_remote}" ]]; then \
        scripts/values.sh clone "${selected_remote}"; \
    else \
        scripts/values.sh init; \
    fi
    @if [[ -z "{{site}}" ]]; then scripts/python.sh scripts/migrate-values.py; fi
    docker compose run --rm infra python scripts/workspace-preflight.py --require-values
    @if [[ -t 0 && -t 1 ]]; then if [[ -n "{{site}}" ]]; then printf 'Skipping bootstrap credential initialization for canonical site; add the SOPS policy and bundle, then run the explicit ssh-initialize workflow.\n'; else INFRA_COPY_SSH_KEYS=true docker compose run --rm infra bash scripts/bootstrap-pve-token.sh --if-needed; fi; else printf 'Skipping Proxmox token bootstrap wizard because just setup is not interactive.\n'; fi
    @if [[ -t 0 && -t 1 ]]; then if [[ -n "{{site}}" ]]; then printf 'Skipping legacy domain wizard for canonical site; domain values come from site.yaml.\n'; else scripts/python.sh scripts/bootstrap-domain.py --if-needed; fi; else printf 'Skipping domain wizard because just setup is not interactive.\n'; fi
    @printf '\nEdit these private values before running `just validate` and `just plan`:\n'
    @if [[ -n "{{site}}" ]]; then printf '  values/sites/{{site}}/site.yaml\n  values/sites/{{site}}/.sops.yaml\n  values/sites/{{site}}/secrets.sops.yaml\n'; else printf '  values/.env\n  values/terraform.tfvars\n  values/dns-records.local.json\n  values/ansible/inventory/local.yml\n'; fi

# Initialize the selected canonical site's bootstrap SSH identity through SOPS
ssh-initialize SITE="dev":
    @site_arg="{{SITE}}"; site="${site_arg#SITE=}"; VALUES_SITE="${site}" SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-${HOME}/.config/infra-fabric/keys/${site}/site.age}" INFRA_VALUES_DIR="values/sites/${site}" scripts/run-infra.sh python scripts/ssh-initialize.py --site-file "/workspace/values/sites/${site}/site.yaml" --bundle "/workspace/values/sites/${site}/secrets.sops.yaml"; VALUES_SITE="${site}" scripts/python.sh scripts/canonical-render.py --site-file "/workspace/values/sites/${site}/site.yaml" --output-dir "/workspace/values/sites/${site}/generated"

# Show private values repo git status
[private]
status-values:
    scripts/values.sh status

# Verify values/ contains required files
[private]
check-values:
    scripts/values.sh check

# Migrate older private values layouts to the current schema
[private]
migrate-values: check-values
    scripts/python.sh scripts/migrate-values.py

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

# Edit the selected site's encrypted SOPS bundle; the external site age key is required
edit-secrets SITE="dev":
    @site_arg="{{SITE}}"; site="${site_arg#SITE=}"; VALUES_SITE="${site}" bash -c 'set -euo pipefail; source scripts/site-context.sh; require_site_context; require_canonical_authority; values_dir="$(site_values_dir)"; SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-${HOME}/.config/infra-fabric/keys/${VALUES_SITE}/site.age}"; export SOPS_AGE_KEY_FILE; [[ -f "${SOPS_AGE_KEY_FILE}" && -r "${SOPS_AGE_KEY_FILE}" ]] || { printf "External site age identity is missing or unreadable: %s\\n" "${SOPS_AGE_KEY_FILE}" >&2; exit 2; }; [[ -f "${values_dir}/.sops.yaml" && -f "${values_dir}/secrets.sops.yaml" ]] || { printf "Selected site SOPS policy or bundle is missing: %s\\n" "${values_dir}" >&2; exit 2; }; sops_bin="$(command -v sops || true)"; [[ -n "${sops_bin}" ]] || [[ -x "${HOME}/.local/bin/sops" ]] && sops_bin="${sops_bin:-${HOME}/.local/bin/sops}"; if [[ -n "${sops_bin}" ]]; then SOPS_EDITOR="${SOPS_EDITOR:-${EDITOR:-vi}}" "${sops_bin}" --config "${values_dir}/.sops.yaml" edit "${values_dir}/secrets.sops.yaml"; else source scripts/container-secret-transport.sh; transport_prepare; docker compose run --rm "${transport_compose_mount_args[@]}" "${transport_compose_env_args[@]}" infra sops --config "/workspace/${values_dir}/.sops.yaml" edit "/workspace/${values_dir}/secrets.sops.yaml"; fi'

# Check upstream releases and update eligible pinned versions after the safety hold period
update:
    scripts/require-site-context.sh
    source scripts/site-context.sh; require_canonical_authority
    scripts/python.sh scripts/update.py

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
