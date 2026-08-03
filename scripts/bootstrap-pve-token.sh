#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source "$(dirname "$0")/site-context.sh"
values_dir="$(site_values_dir)"
env_file="${values_dir}/.env"
canonical_site=false
if [[ -f "${values_dir}/site.yaml" ]]; then
  canonical_site=true
fi
canonical_bundle="${values_dir}/secrets.sops.yaml"
canonical_key_file="${SOPS_AGE_KEY_FILE:-}"
canonical_secret_path="secrets.providers.proxmox.api_token"
force=0
if_needed=0

usage() {
  cat <<'USAGE'
Usage: scripts/bootstrap-pve-token.sh [--if-needed] [--force]

Interactively bootstrap a Proxmox API token for this repo:
  - prompts for the Proxmox host and API endpoint
  - verifies root SSH key access and pveum availability
  - creates/updates a dedicated Proxmox user ACL
  - creates an API token
  - canonical sites write the API token to the encrypted SOPS bundle
  - legacy sites write PROXMOX_VE_ENDPOINT, PROXMOX_VE_API_TOKEN, and PVE_HOST to values/.env

The token secret is never printed. Canonical sites store it only in SOPS.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      force=1
      ;;
    --if-needed)
      if_needed=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

require_file() {
  if [[ ! -f "$1" ]]; then
    printf 'Missing %s. Run just setup first.\n' "$1" >&2
    exit 1
  fi
}

envfile_python() {
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then
    python3 scripts/envfile.py "$@"
  else
    scripts/python.sh scripts/envfile.py "$@"
  fi
}

get_env_value() {
  local key="$1"
  envfile_python get "$env_file" "$key"
}

is_placeholder_token() {
  local value="$1"
  [[ -z "$value" || "$value" == *REPLACE_WITH_PROXMOX_TOKEN* || "$value" != *'!'* || "$value" != *'='* ]]
}

prompt() {
  local label="$1"
  local default_value="$2"
  local value
  if [[ -n "$default_value" ]]; then
    read -r -p "$label [$default_value]: " value
    printf '%s' "${value:-$default_value}"
  else
    read -r -p "$label: " value
    printf '%s' "$value"
  fi
}

confirm() {
  local label="$1"
  local answer
  read -r -p "$label [y/N]: " answer
  [[ "$answer" == "y" || "$answer" == "Y" || "$answer" == "yes" || "$answer" == "YES" ]]
}

set_env_var() {
  local key="$1"
  local value="$2"
  envfile_python set "$env_file" "$key" "$value"
}

validate_token_name() {
  local name="$1"
  [[ "$name" =~ ^[A-Za-z][A-Za-z0-9_.-]+$ ]]
}

validate_user_id() {
  local user="$1"
  [[ "$user" =~ ^[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+$ ]]
}

if [[ "${canonical_site}" != true ]]; then
  require_file "$env_file"
fi

if [[ "${canonical_site}" == true ]]; then
  require_file "${canonical_bundle}"
  if [[ -z "${canonical_key_file}" || ! -r "${canonical_key_file}" ]]; then
    printf 'Canonical SOPS age identity is missing or unreadable.\n' >&2
    exit 1
  fi
fi

if [[ "${canonical_site}" == true ]]; then
  if [[ "$if_needed" -eq 1 && "$force" -eq 0 ]] && \
    python scripts/canonical-secret-set.py --bundle "${canonical_bundle}" --path "${canonical_secret_path}" --check >/dev/null 2>&1; then
    printf 'Proxmox API token already exists in the canonical SOPS bundle; skipping bootstrap wizard.\n'
    exit 0
  fi
  current_token=""
  current_endpoint="$(python -c 'import sys; from ruamel.yaml import YAML; data=YAML(typ="safe").load(open(sys.argv[1])); print(data.get("platform", {}).get("proxmox", {}).get("endpoint", ""))' "${values_dir}/site.yaml")"
  current_pve_host="$(python -c 'import sys; from ruamel.yaml import YAML; data=YAML(typ="safe").load(open(sys.argv[1])); print(data.get("platform", {}).get("proxmox", {}).get("management", {}).get("host", ""))' "${values_dir}/site.yaml")"
else
  current_token="$(get_env_value PROXMOX_VE_API_TOKEN || true)"
  current_endpoint="$(get_env_value PROXMOX_VE_ENDPOINT || true)"
  current_pve_host="$(get_env_value PVE_HOST || true)"
  if [[ "$if_needed" -eq 1 && "$force" -eq 0 ]] && \
    ! is_placeholder_token "$current_token" && \
    [[ -n "$current_endpoint" && "$current_endpoint" != *REPLACE* ]] && \
    [[ -n "$current_pve_host" && "$current_pve_host" != *REPLACE* ]]; then
    printf 'Proxmox API endpoint, token, and SSH target already configured in %s; skipping bootstrap wizard.\n' "$env_file"
    exit 0
  fi
fi

if [[ ! -t 0 || ! -t 1 ]]; then
  printf 'Skipping Proxmox token bootstrap wizard because stdin/stdout is not interactive.\n'
  exit 0
fi

if [[ "${canonical_site}" != true && "$force" -eq 0 ]] && ! is_placeholder_token "$current_token"; then
  printf 'A Proxmox API token is already configured in %s.\n' "$env_file"
  if ! confirm 'Rotate/replace it now?'; then
    exit 0
  fi
fi

if ! confirm 'Bootstrap a Proxmox API token over SSH now? This will create/update a Proxmox user, ACL, and token.'; then
  printf 'Skipped Proxmox token bootstrap.\n'
  exit 0
fi

existing_host="${current_pve_host:-$(get_env_value PVE_HOST || true)}"
existing_endpoint="${current_endpoint:-$(get_env_value PROXMOX_VE_ENDPOINT || true)}"
existing_host="${existing_host#root@}"

pve_host="$(prompt 'Proxmox host' "${existing_host:-proxmox.example.internal}")"
pve_host="${pve_host#root@}"
ssh_target="root@${pve_host}"

default_endpoint="${existing_endpoint:-https://${pve_host}:8006/}"
api_endpoint="$(prompt 'Proxmox API endpoint' "$default_endpoint")"
pve_user="$(prompt 'Proxmox API user to create/use' 'terraform@pve')"
token_id="$(prompt 'Proxmox API token id' 'homelab-infra')"
pve_role="$(prompt 'Proxmox ACL role' 'Administrator')"

if ! validate_user_id "$pve_user"; then
  printf 'Invalid Proxmox user id: %s\n' "$pve_user" >&2
  exit 1
fi
if ! validate_token_name "$token_id"; then
  printf 'Invalid token id: %s\n' "$token_id" >&2
  exit 1
fi
if [[ -z "$pve_role" ]]; then
  printf 'Proxmox role must not be empty.\n' >&2
  exit 1
fi

ssh_identity_file=""
if [[ -n "${INFRA_SSH_IDENTITY_FILE:-}" ]]; then
  if [[ ! "${INFRA_SSH_IDENTITY_FILE}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    printf 'INFRA_SSH_IDENTITY_FILE is invalid.\n' >&2
    exit 1
  fi
  ssh_identity_file="${HOME}/.ssh/${INFRA_SSH_IDENTITY_FILE}"
  if [[ ! -f "${ssh_identity_file}" ]]; then
    printf 'Configured SSH identity is unavailable: %s\n' "${INFRA_SSH_IDENTITY_FILE}" >&2
    exit 1
  fi
fi

ssh_run() {
  local batch_mode="$1"
  shift
  local args=(-o ConnectTimeout=10)
  if [[ "$batch_mode" == "batch" ]]; then
    args+=(-o BatchMode=yes)
  fi
  if [[ -n "$ssh_identity_file" ]]; then
    args+=(-i "$ssh_identity_file" -o IdentitiesOnly=yes)
  fi
  ssh "${args[@]}" -- "$ssh_target" "$@"
}

try_pveum() {
  ssh_run batch 'command -v pveum >/dev/null'
}

public_key_file() {
  if [[ -f "$HOME/.ssh/id_ed25519.pub" ]]; then
    printf '%s' "$HOME/.ssh/id_ed25519.pub"
  elif [[ -f "$HOME/.ssh/id_rsa.pub" ]]; then
    printf '%s' "$HOME/.ssh/id_rsa.pub"
  fi
}

print_authorized_keys_command() {
  local pubkey_file pubkey escaped_pubkey
  pubkey_file="$(public_key_file)"
  if [[ -z "$pubkey_file" ]]; then
    printf 'No default public key found at ~/.ssh/id_ed25519.pub or ~/.ssh/id_rsa.pub.\n'
    printf 'Create one with: ssh-keygen -t ed25519\n'
    return
  fi
  pubkey="$(<"$pubkey_file")"
  escaped_pubkey="$(printf '%s' "$pubkey" | sed "s/'/'\\\\''/g")"
  printf '\nDefault SSH keys did not work for root@%s.\n' "$pve_host"
  printf 'Log in to the Proxmox host as root using its console or password SSH, then run this command:\n\n'
  printf "install -d -m 0700 /root/.ssh && touch /root/.ssh/authorized_keys && chmod 0600 /root/.ssh/authorized_keys && (grep -qxF '%s' /root/.ssh/authorized_keys || printf '%%s\\n' '%s' >> /root/.ssh/authorized_keys)\n\n" "$escaped_pubkey" "$escaped_pubkey"
}

printf 'Testing root SSH key access to %s...\n' "$pve_host"
if ! try_pveum; then
  printf 'Default SSH keys did not work for root@%s, or pveum was unavailable.\n' "$pve_host"
  while true; do
    printf '\nChoose an authentication fallback:\n'
    printf '  1) Use an alternate SSH private key file\n'
    printf '  2) Show command to authorize my default public SSH key on Proxmox\n'
    printf '  3) Retry default SSH key test\n'
    printf '  4) Abort\n'
    auth_choice="$(prompt 'Selection' '1')"
    case "$auth_choice" in
      1)
        ssh_identity_file="$(prompt 'SSH private key file' '')"
        ssh_identity_file="${ssh_identity_file/#\~/$HOME}"
        if [[ ! -f "$ssh_identity_file" ]]; then
          printf 'Key file not found: %s\n' "$ssh_identity_file" >&2
          continue
        fi
        printf 'Testing root SSH access to %s with %s...\n' "$pve_host" "$ssh_identity_file"
        if try_pveum; then
          break
        fi
        printf 'Alternate key did not work, or pveum was unavailable.\n'
        ;;
      2)
        print_authorized_keys_command
        ;;
      3)
        ssh_identity_file=""
        printf 'Testing root SSH key access to %s...\n' "$pve_host"
        if try_pveum; then
          break
        fi
        printf 'Default SSH keys still did not work, or pveum was unavailable.\n'
        ;;
      4)
        printf 'Aborted Proxmox token bootstrap.\n'
        exit 1
        ;;
      *)
        printf 'Invalid selection: %s\n' "$auth_choice" >&2
        ;;
    esac
  done
fi
printf 'Root SSH key and pveum check passed.\n'

printf 'Creating/updating Proxmox API user, ACL, and token...\n'
# shellcheck disable=SC2016 # Remote script expands on the Proxmox host, not locally.
remote_script='set -euo pipefail
user="$1"
token="$2"
role="$3"
comment="infra-fabric OpenTofu token"
if ! pveum user list | grep -Fq "$user"; then
  pveum user add "$user" --comment "infra-fabric OpenTofu service user"
fi
pveum acl modify / --users "$user" --roles "$role"
if pveum user token list "$user" 2>/dev/null | grep -Fq "$token"; then
  pveum user token remove "$user" "$token"
fi
json="$(pveum user token add "$user" "$token" --privsep 0 --comment "$comment" --output-format json)"
secret="$(printf "%s\n" "$json" | sed -n "s/.*\"value\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p")"
if [[ -z "$secret" ]]; then
  printf "Failed to parse Proxmox token secret.\n" >&2
  exit 1
fi
printf "%s\n" "$secret"
'
secret="$(ssh_run batch bash -s -- "$pve_user" "$token_id" "$pve_role" <<<"$remote_script")"
if [[ -z "$secret" ]]; then
  printf 'Proxmox token creation returned an empty secret.\n' >&2
  exit 1
fi

if [[ "${canonical_site}" == true ]]; then
  secret_set_args=()
  if [[ "$force" -eq 1 ]]; then
    secret_set_args+=(--replace)
  fi
  CANONICAL_VALUE="${pve_user}!${token_id}=${secret}" \
    python scripts/canonical-secret-set.py \
      --bundle "${canonical_bundle}" \
      --path "${canonical_secret_path}" \
      --value-env CANONICAL_VALUE \
      "${secret_set_args[@]}"
  printf 'Wrote the Proxmox API token to the canonical encrypted SOPS bundle.\n'
else
  set_env_var PROXMOX_VE_ENDPOINT "$api_endpoint"
  set_env_var PROXMOX_VE_API_TOKEN "${pve_user}!${token_id}=${secret}"
  set_env_var PVE_HOST "$ssh_target"
  printf 'Wrote Proxmox endpoint, API token, and SSH target to %s.\n' "$env_file"
fi
printf 'Token secret was not printed. Next: edit remaining values files, then run just validate.\n'
