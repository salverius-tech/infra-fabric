#!/usr/bin/env bash
# Site age identity lifecycle helper: generate, store in 1Password, recover,
# and verify. Key material is never echoed to stdout or logs.
#
# Usage:
#   scripts/site-age-identity.sh <action> [SITE=<site>] [--force]
# where action is generate | store | fetch | verify.
#
# The first argument must be an action. SITE= and --force may follow in any
# order. An explicit SITE= overrides VALUES_SITE; there is no implicit default
# site. generate and verify accept no extra arguments; store and fetch accept
# only --force.
#
# 1Password integration is optional and interactive: `op` must be installed
# and signed in (`op signin`). The toolchain never requires it; recovery from
# a manual 1Password paste is always available. See
# docs/canonical-values-secret-operations.md.
#
# Safety invariants:
#   * store never deletes a prior vault item: on --force the existing item is
#     renamed to a unique "previous-*" backup title, not removed. Archived
#     previous-* content is retained and never deleted.
#   * integrity is byte-for-byte, and no cross-command step claims atomicity.
#     Local publishes are atomic no-clobber renames/hardlinks.
#   * every transient file lives in a private, umask-077 staging directory on
#     the same filesystem as the identity and is removed by an EXIT trap.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# shellcheck source=scripts/site-context.sh
source "${repo_root}/scripts/site-context.sh"

# ---- argument parsing (must run before requiring site context) ----
#
# The first positional argument must be an action. Remaining arguments carry
# SITE=<site> and/or --force in any order. An explicit SITE= overrides
# VALUES_SITE; there is no implicit default site. Unknown or duplicate SITE
# arguments are rejected, and --force is rejected for generate/verify.
action=""
site=""
force=0

die() { printf '%s\n' "$*" >&2; exit 2; }

usage() {
  printf 'Usage: %s {generate|store [--force]|fetch [--force]|verify} [SITE=<site>]\n' "$0" >&2
  printf '       Site may come from SITE=<site> or VALUES_SITE=<site> in any flag order; there is no implicit default site.\n' >&2
}

parse_args() {
  local arg candidate seen_site=0
  [[ $# -ge 1 ]] || { usage; exit 2; }
  action="$1"
  shift
  case "${action}" in
    generate|store|fetch|verify) : ;;
    *) printf 'unknown action: %s\n' "${action}" >&2; usage; exit 2 ;;
  esac
  for arg in "$@"; do
    case "${arg}" in
      --force)
        force=1 ;;
      SITE=*)
        candidate="${arg#SITE=}"
        if [[ -z "${candidate}" || ! "${candidate}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ || "${candidate}" == *..* ]]; then
          die "invalid SITE override: ${arg}"
        fi
        [[ ${seen_site} -eq 0 ]] || die "duplicate SITE override: ${arg}"
        seen_site=1
        site="${candidate}" ;;
      *)
        printf 'unknown argument: %s\n' "${arg}" >&2
        usage
        exit 2 ;;
    esac
  done
  if [[ "${force}" -eq 1 && "${action}" != store && "${action}" != fetch ]]; then
    die "--force is only valid with store or fetch; got action '${action}'"
  fi
  if [[ -n "${site}" ]]; then
    export VALUES_SITE="${site}"
  fi
}

parse_args "$@"

require_site_context
identity_dir="${INFRA_IDENTITY_DIR:-${HOME}/.config/infra-fabric/keys/${VALUES_SITE}}"
identity_file="${identity_dir}/site.age"
op_item_title="infra-fabric-site-age-identity-${VALUES_SITE}"
op_vault="${OP_VAULT:-}"

# Global staging directory; valid at trap time because it never goes out of scope.
_staging_dir=""
_cleanup_staging() {
  if [[ -n "${_staging_dir}" && -d "${_staging_dir}" ]]; then
    rm -rf -- "${_staging_dir}"
  fi
}
trap _cleanup_staging EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

umask 077

# Prepend repo_root to values-relative paths unless the path is already
# absolute (e.g. an absolute VALUES_DIR override).
join_repo_path() {
  local p="$1"
  if [[ "${p}" = /* ]]; then
    printf '%s\n' "${p}"
  else
    printf '%s\n' "${repo_root}/${p}"
  fi
}

require_key_tools() {
  command -v age-keygen >/dev/null || die "age-keygen is required"
}

require_python() {
  command -v python3 >/dev/null || die "python3 is required on the host for 1Password note handling; install python3 and retry"
}

require_op() {
  command -v op >/dev/null || die "1Password CLI (op) is required for this operation; install it or recover manually per docs/canonical-values-secret-operations.md"
  [[ -n "${op_vault}" ]] || die "set OP_VAULT to the target 1Password vault name"
  op whoami >/dev/null 2>&1 || die "op is not signed in; run 'op signin' first"
  require_python
}

# Private staging directory on the identity filesystem (enables atomic rename).
# Rejects a symlink or non-directory identity_dir before any chmod/mkdir.
init_staging() {
  if [[ -n "${_staging_dir}" ]]; then
    return
  fi
  if [[ -L "${identity_dir}" ]]; then
    die "identity directory is a symlink: ${identity_dir}; refusing"
  fi
  if [[ -e "${identity_dir}" && ! -d "${identity_dir}" ]]; then
    die "identity directory is not a directory: ${identity_dir}; refusing"
  fi
  mkdir -p "${identity_dir}"
  chmod 700 "${identity_dir}"
  _staging_dir="$(mktemp -d "${identity_dir}/.staging.XXXXXX")" || die "could not create a private staging directory"
  chmod 700 "${_staging_dir}"
}

# Extract the notesPlain value from an item JSON document (shared by store and
# fetch) and write it to stdout. Requires exactly one notesPlain field whose
# value is a string. On any problem it prints a generic message to stderr
# (never a Python traceback) and exits nonzero.
extract_notes() {
  python3 - "$1" 2>"${_staging_dir}/extract.err" <<'PY'
import json, sys
try:
    item = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.stderr.write("could not read 1Password item data\n")
    sys.exit(1)
fields = [f for f in item.get("fields", []) if f.get("id") == "notesPlain"]
if len(fields) != 1:
    sys.stderr.write("1Password item did not contain exactly one notesPlain note; refusing to continue\n")
    sys.exit(1)
value = fields[0].get("value")
if not isinstance(value, str):
    sys.stderr.write("1Password note field did not contain a text value; refusing to continue\n")
    sys.exit(1)
sys.stdout.write(value)
PY
}

# Validate that a file on disk parses as an age identity. Rejects empty or
# malformed content; the caller must never proceed past this checkpoint.
require_valid_identity() {
  local file="$1"
  [[ -s "${file}" ]] || die "identity file is empty: ${file}"
  if ! age-keygen -y "${file}" >/dev/null 2>&1 < /dev/null; then
    die "identity file is not a valid age identity (age-keygen rejected it): ${file}"
  fi
  return 0
}

# Print the id of the staged/known item whose id we just created.
item_id_from_json() {
  python3 - "$1" 2>"${_staging_dir}/id.extract.err" <<'PY'
import json, sys
try:
    item = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.stderr.write("could not read 1Password create response\n")
    sys.exit(1)
sys.stdout.write(item.get("id") or item.get("uuid") or "")
PY
}

# Reject non-alphanumeric 1Password item ids before embedding them in any path.
check_op_id() {
  local id="$1"
  [[ -n "${id}" ]] || die "refusing: empty 1Password item id"
  [[ "${id}" =~ ^[A-Za-z0-9]+$ ]] || die "refusing: 1Password item id contains unexpected characters"
}

# Find the id of the vault item whose title exactly equals "$1".
# Prints the id alone on success; prints nothing when no such item exists.
# Fails closed: dies on a transport/listing error, and prints AMBIGUOUS (nonzero)
# when more than one item shares the exact title. Never deletes or edits.
find_exact_item() {
  local want="$1" list_file
  list_file="${_staging_dir}/item-list.json"
  init_staging
  if ! op item list --vault "${op_vault}" --format json > "${list_file}" 2>"${_staging_dir}/list.err"; then
    die "could not list 1Password vault '${op_vault}'; refusing to continue. No vault item was created. Run op whoami and confirm OP_VAULT, then rerun."
  fi
  python3 - "${list_file}" "${want}" 2>"${_staging_dir}/find.err" <<'PY'
import json, sys
try:
    items = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.stderr.write("could not read 1Password item list\n")
    sys.exit(1)
want = sys.argv[2]
ids = [it.get("id") or it.get("uuid") for it in items if it.get("title") == want]
if len(ids) == 1:
    sys.stdout.write(ids[0])
elif len(ids) > 1:
    sys.stdout.write("AMBIGUOUS")
PY
}

# Print a caller-usable dual result: 0 = ok, 1 = none/regular; and handle the
# AMBIGUOUS sentinel by dying here so every lookup path fails closed.
find_exact_checked() {
  local title="$1" out
  out="$(find_exact_item "${title}")" || { die "1Password vault listing failed; no item was created. Run op whoami and confirm OP_VAULT."; }
  if [[ "${out}" == "AMBIGUOUS" ]]; then
    die "multiple 1Password items titled '${title}' exist in vault '${op_vault}'; refusing to operate. The prior identity is untouched. Remove the duplicate, then rerun."
  fi
  printf '%s\n' "${out}"
}

# Write the notesPlain of vault item `id` to `out_file` (defaults to a staging
# path derived from the id). Honors a provided second output path argument.
get_item_notes() {
  local id="$1"
  local out="${2:-${_staging_dir}/notes-${1}.txt}"
  check_op_id "${id}"
  if ! op item get "${id}" --vault "${op_vault}" --format json > "${_staging_dir}/get-${id}.json" 2>"${_staging_dir}/get.err"; then
    die "could not read back 1Password item '${id}' from vault '${op_vault}'. Any prior item is retained (a copy may exist under a previous-* title); reconcile the vault contents and rerun."
  fi
  extract_notes "${_staging_dir}/get-${id}.json" > "${out}"
}

# Create a new unique-titled SECURE_NOTE item holding the snapshot contents and
# print its id. The existing item (if any) is never touched here.
stage_item() {
  local snapshot="$1" title="$2"
  init_staging
  local template="${_staging_dir}/template.json"
  if ! python3 - "${snapshot}" "${title}" > "${template}" 2>"${_staging_dir}/template.err" <<'PY'
import json, sys
contents = open(sys.argv[1], encoding="utf-8").read()
print(json.dumps({
    "title": sys.argv[2],
    "category": "SECURE_NOTE",
    "fields": [
        {"id": "notesPlain", "type": "STRING", "purpose": "NOTES", "value": contents, "label": "notes"}
    ],
}))
PY
  then
    die "failed to render the 1Password item template; no item was created. Fix the identity file and rerun ${0} store."
  fi
  local created="${_staging_dir}/created.json"
  if ! op item create --template "${template}" --vault "${op_vault}" --format json > "${created}" 2>"${_staging_dir}/created.err"; then
    die "failed to create the staged 1Password item; a copy may or may not have been created (a timeout can create it before reporting failure). Check 'op' sign-in and OP_VAULT, reconcile the vault contents, and rerun ${0} store."
  fi
  item_id_from_json "${created}"
}

rename_item() {
  local id="$1" title="$2"
  check_op_id "${id}"
  init_staging
  if ! op item edit "${id}" --title "${title}" --vault "${op_vault}" >/dev/null 2>"${_staging_dir}/edit.err"; then
    die "1Password refused to rename item '${id}' to '${title}' in vault '${op_vault}'. Nothing was deleted; a prior copy may be under a previous-* title. Retry or restore manually per docs/canonical-values-secret-operations.md."
  fi
}

# Read a vault item back and byte-compare its notes against this operation's
# immutable local snapshot.
verify_item_against() {
  local id="$1" title="$2" snapshot="$3" stored
  stored="${_staging_dir}/verify-${id}.txt"
  get_item_notes "${id}" "${stored}"
  local stored_bytes snapshot_bytes
  stored_bytes="$(wc -c < "${stored}")"
  snapshot_bytes="$(wc -c < "${snapshot}")"
  if [[ "${stored_bytes}" -ne "${snapshot_bytes}" ]] || ! cmp -s "${stored}" "${snapshot}"; then
    die "stored item '${title}' does not match the operation identity snapshot (${stored_bytes} vs ${snapshot_bytes} bytes). 1Password copies are never deleted at store time; any prior item is preserved under a previous-* title. The local identity is intact. Reconcile and rerun store."
  fi
}

# Copy the original identity through one held, no-follow regular-file handle.
# The resulting staging file is the sole local input for this store operation.
snapshot_store_identity() {
  local snapshot="${_staging_dir}/identity.age"
  if ! python3 - "${repo_root}" "${identity_file}" "${snapshot}" 2>"${_staging_dir}/snapshot.err" <<'PY'
import sys
from pathlib import Path

try:
    sys.path.insert(0, str(Path(sys.argv[1]) / "scripts"))
    from private_files import (PrivateFileError, atomic_copy, open_regular_file,
                               stream_sha256_handle)
    source, destination = Path(sys.argv[2]), Path(sys.argv[3])
    with open_regular_file(source, "identity file") as handle:
        digest = stream_sha256_handle(handle)
        atomic_copy(handle, destination, label="identity file", expected_sha256=digest,
                    replace_existing=False)
except Exception:
    sys.stderr.write("could not safely snapshot identity file\n")
    sys.exit(1)
PY
  then
    die "could not safely snapshot identity file; refusing to store"
  fi
  printf '%s\n' "${snapshot}"
}

# Publish a validated staged file to the identity path atomically without
# clobbering an existing destination (hard link under a non-existent name).
publish_no_clobber() {
  local src="$1" dest="$2"
  if ! ln --no-target-directory -- "${src}" "${dest}" 2>/dev/null; then
    die "destination already exists or cannot be linked: ${dest}; refusing to overwrite"
  fi
}

cmd_generate() {
  [[ -e "${identity_file}" || -L "${identity_file}" ]] && die "identity path already exists: ${identity_file}; refusing to overwrite"
  require_key_tools
  init_staging
  local staged="${_staging_dir}/generated.age"
  age-keygen -o "${staged}" >/dev/null 2>"${_staging_dir}/agegen.err"
  chmod 600 "${staged}"
  require_valid_identity "${staged}"
  publish_no_clobber "${staged}" "${identity_file}"
  printf 'generated site identity for %s\nstore a copy with: %s store\n' \
    "${VALUES_SITE}" "$0"
}

cmd_store() {
  require_op
  require_key_tools
  init_staging
  local snapshot
  snapshot="$(snapshot_store_identity)"
  require_valid_identity "${snapshot}"

  # Locate the canonical item by exact title; fail closed on error/ambiguity.
  local current_id=""
  current_id="$(find_exact_checked "${op_item_title}")"
  if [[ -n "${current_id}" ]]; then
    check_op_id "${current_id}"
  fi
  if [[ -n "${current_id}" && "${force}" -ne 1 ]]; then
    die "1Password item already exists: ${op_item_title} in vault ${op_vault}; it was left unchanged. Pass --force to publish a copy under a backup title."
  fi

  local run_id stage_title stage_id backup_title
  run_id="$$.$(date 2>/dev/null +%s%N || date +%s)"
  stage_title="${op_item_title}.stage-${run_id}"
  stage_id="$(stage_item "${snapshot}" "${stage_title}")"
  [[ -n "${stage_id}" ]] || die "could not determine the id of the newly created staged item; nothing was moved"

  # The staged copy is byte-for-byte as the identity before any promotion.
  verify_item_against "${stage_id}" "${stage_title}" "${snapshot}"

  # Promote: on --force, first retain the prior item under a unique backup
  # title (preserving it), then move the staged item to the canonical title.
  if [[ -n "${current_id}" ]]; then
    backup_title="${op_item_title}.previous-${run_id}"
    rename_item "${current_id}" "${backup_title}"
  fi
  rename_item "${stage_id}" "${op_item_title}"
  verify_item_against "${stage_id}" "${op_item_title}" "${snapshot}"

  printf 'stored and verified identity for %s as 1Password item %s in vault %s\n' \
    "${VALUES_SITE}" "${op_item_title}" "${op_vault}"
}

cmd_fetch() {
  require_op
  require_key_tools
  init_staging

  # Rejects a symlink, directory, or other non-regular destination so we never
  # clobber an unrelated path.
  if [[ -L "${identity_file}" || -d "${identity_file}" ]]; then
    die "identity destination is a symlink or directory: ${identity_file}; refusing to overwrite"
  fi
  if [[ -e "${identity_file}" ]]; then
    [[ -f "${identity_file}" ]] || die "identity destination is not a regular file: ${identity_file}; refusing"
    [[ "${force}" -eq 1 ]] || die "identity already exists at ${identity_file}; pass --force to replace it"
  fi

  local staged="${_staging_dir}/staged.age" current_id
  current_id="$(find_exact_checked "${op_item_title}")"
  [[ -n "${current_id}" ]] || die "no 1Password item '${op_item_title}' exists in vault '${op_vault}'; nothing was changed. Store the identity first, or restore it from the original terminal that generated it."

  # Stage on the same filesystem, extract and validate before atomic publish.
  get_item_notes "${current_id}" "${staged}"
  [[ -s "${staged}" ]] || die "the stored 1Password item is empty; refusing to publish an empty identity. The local identity, if any, is untouched."
  chmod 600 "${staged}"
  if ! require_valid_identity "${staged}"; then
    die "the fetched identity is not a valid age identity; refusing to overwrite the identity file. If any local copy existed it was left in place; reconcile the vault contents and fetch again."
  fi

  # Atomic publish: hardlink for no-clobber (no-force), rename for force.
  if [[ "${force}" -eq 1 ]]; then
    mv --no-target-directory --force -- "${staged}" "${identity_file}"
  else
    publish_no_clobber "${staged}" "${identity_file}"
  fi
  printf 'recovered identity for %s\nverify against the site bundle with: %s verify\n' \
    "${VALUES_SITE}" "$0"
}

cmd_verify() {
  [[ -L "${identity_file}" ]] && die "identity path is a symlink: ${identity_file}; refusing"
  [[ -f "${identity_file}" ]] || die "no identity at ${identity_file}"
  local values_dir
  values_dir="$(site_values_dir)"
  [[ -L "${values_dir}" ]] && die "values directory is a symlink: ${values_dir}; refusing"
  [[ -d "${values_dir}" ]] || die "values directory is not a directory: ${values_dir}"
  if ! SOPS_AGE_KEY_FILE="${identity_file}" sops \
      --config "$(join_repo_path "${values_dir}/.sops.yaml")" \
      -d "$(join_repo_path "${values_dir}/secrets.sops.yaml")" >/dev/null 2>/dev/null; then
    die "identity verification failed: the site bundle could not be decrypted with this identity. The identity file was not modified; reconcile the identity and the site bundle, then rerun verify."
  fi
  printf 'identity verified: decrypted the %s site bundle successfully\n' "${VALUES_SITE}"
}

# Bottom dispatch consumes only the normalized argv (action + validated flags);
# no further argument shifting is required here.
case "${action}" in
  generate) cmd_generate ;;
  store) cmd_store ;;
  fetch) cmd_fetch ;;
  verify) cmd_verify ;;
  *) usage; exit 2 ;;
esac