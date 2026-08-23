#!/usr/bin/env bash
# Site age identity lifecycle helper: generate, store in 1Password, recover,
# and verify. Key material is never echoed to stdout or logs.
#
# Usage:
#   VALUES_SITE=<site> scripts/site-age-identity.sh generate
#   VALUES_SITE=<site> scripts/site-age-identity.sh store [--force]
#   VALUES_SITE=<site> scripts/site-age-identity.sh fetch [--force]
#   VALUES_SITE=<site> scripts/site-age-identity.sh verify
#
# 1Password integration is optional and interactive: `op` must be installed
# and signed in (`op signin`). The toolchain never requires it; recovery from
# a manual 1Password paste is always available. See
# docs/canonical-values-secret-operations.md.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
source "${repo_root}/scripts/site-context.sh"

require_site_context
identity_dir="${INFRA_IDENTITY_DIR:-${HOME}/.config/infra-fabric/keys/${VALUES_SITE}}"
identity_file="${identity_dir}/site.age"
op_item_title="infra-fabric-site-age-identity-${VALUES_SITE}"
op_vault="${OP_VAULT:-}"

die() { printf '%s\n' "$*" >&2; exit 2; }

require_key_tools() {
  command -v age-keygen >/dev/null || die "age-keygen is required"
}

require_op() {
  command -v op >/dev/null || die "1Password CLI (op) is required for this operation; install it or recover manually per docs/canonical-values-secret-operations.md"
  [[ -n "${op_vault}" ]] || die "set OP_VAULT to the target 1Password vault name"
  op whoami >/dev/null 2>&1 || die "op is not signed in; run 'op signin' first"
}

cmd_generate() {
  [[ -f "${identity_file}" ]] && die "identity already exists: ${identity_file}; refusing to overwrite"
  require_key_tools
  mkdir -p "${identity_dir}"
  chmod 700 "${identity_dir}"
  age-keygen -o "${identity_file}" 2>/dev/null >/dev/null
  chmod 600 "${identity_file}"
  local public_key
  public_key="$(grep -oE '^# public key: .*' "${identity_file}" | head -1 | sed 's/^# public key: //')"
  printf 'generated site identity for %s\npublic key: %s\nstore a copy with: %s store\n' \
    "${VALUES_SITE}" "${public_key}" "$0"
}

cmd_store() {
  [[ -f "${identity_file}" ]] || die "no identity at ${identity_file}; run generate first"
  require_op
  local force=""
  [[ "${1:-}" == "--force" ]] && force=1
  if op item get "${op_item_title}" --vault "${op_vault}" >/dev/null 2>&1; then
    [[ -n "${force}" ]] || die "1Password item already exists: ${op_item_title}; pass --force to replace it"
    op item delete "${op_item_title}" --vault "${op_vault}"
  fi
  # Build a private item template so the vault stores the full identity file
  # contents (never a path or other literal). The template is created with
  # 0600 in a private directory and removed immediately.
  local template_dir template
  template_dir="$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/site-identity.XXXXXX")"
  chmod 700 "${template_dir}"
  template="${template_dir}/item-template.json"
  trap 'rm -rf "${template_dir}"' RETURN
  python3 - "$identity_file" "$op_item_title" > "${template}" <<'PYEOF'
import json, sys
contents = open(sys.argv[1], encoding="utf-8").read()
print(json.dumps({
    "title": sys.argv[2],
    "category": "SECURE_NOTE",
    "fields": [
        {"id": "notesPlain", "type": "STRING", "purpose": "NOTES", "value": contents, "label": "notes"}
    ],
}))
PYEOF
  op item create --template "${template}" --vault "${op_vault}" >/dev/null
  rm -rf "${template_dir}"
  verify_stored_identity() {
    # Read back through the item JSON (field-reference URIs are ambiguous for
    # template-created items) and byte-compare against the identity file.
    op item get "${op_item_title}" --vault "${op_vault}" --format json 2>/dev/null \
      | python3 -c '
import json, sys
item = json.load(sys.stdin)
for field in item.get("fields", []):
    if field.get("id") == "notesPlain" or field.get("label") == "notes":
        sys.stdout.write(field.get("value") or "")
        break
' 
  }
  local stored_bytes local_bytes
  stored_bytes="$(verify_stored_identity | wc -c)"
  local_bytes="$(wc -c < "${identity_file}")"
  if ! verify_stored_identity | cmp -s - "${identity_file}"; then
    die "stored item does not match the identity file (stored ${stored_bytes} bytes, local ${local_bytes} bytes; empty stored count means the notes field could not be read back). The vault copy is unreliable - delete item ${op_item_title} and re-run store."
  fi
  printf 'stored and verified identity for %s as 1Password item %s in vault %s\n' \
    "${VALUES_SITE}" "${op_item_title}" "${op_vault}"
}

cmd_fetch() {
  require_op
  local force=""
  [[ "${1:-}" == "--force" ]] && force=1
  if [[ -f "${identity_file}" ]]; then
    [[ -n "${force}" ]] || die "identity already exists at ${identity_file}; pass --force to replace it"
    rm -f "${identity_file}"
  fi
  mkdir -p "${identity_dir}"
  chmod 700 "${identity_dir}"
  umask 177
  op read "op://${op_vault}/${op_item_title}/notes.note_text" > "${identity_file}"
  chmod 600 "${identity_file}"
  grep -qE '^AGE-SECRET-KEY-' "${identity_file}" || die "recovered file does not contain an age secret key; refusing"
  printf 'recovered identity for %s\npublic key comment: %s\nnext: verify against the site bundle with: %s verify\n' \
    "${VALUES_SITE}" "$(grep -oE '^# public key: .*' "${identity_file}" | head -1)" "$0"
}

cmd_verify() {
  [[ -f "${identity_file}" ]] || die "no identity at ${identity_file}"
  [[ -f "${identity_file}.backup" ]] && cp "${identity_file}" "${identity_file}.backup.pre-verify"
  local values_dir
  values_dir="$(site_values_dir)"
  SOPS_AGE_KEY_FILE="${identity_file}" sops \
    --config "${repo_root}/${values_dir}/.sops.yaml" \
    -d "${repo_root}/${values_dir}/secrets.sops.yaml" >/dev/null
  printf 'identity verified: decrypted the %s site bundle successfully\n' "${VALUES_SITE}"
}

case "${1:-}" in
  generate) shift; cmd_generate "$@" ;;
  store) shift; cmd_store "$@" ;;
  fetch) shift; cmd_fetch "$@" ;;
  verify) shift; cmd_verify "$@" ;;
  *) usage_die() { printf 'Usage: %s {generate|store [--force]|fetch [--force]|verify}\n' "$0" >&2; }; usage_die; exit 2 ;;
esac
