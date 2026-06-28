#!/usr/bin/env bash
set -euo pipefail

fail=0

report() {
  printf '%s\n' "$1" >&2
  fail=1
}

required_scaffold=(
  scaffold/.env.example
  scaffold/terraform.tfvars
  scaffold/dns-records.local.json
  scaffold/ansible/inventory/local.yml
)

for path in "${required_scaffold[@]}"; do
  if [[ ! -f "${path}" ]]; then
    report "Missing required scaffold file: ${path}"
    continue
  fi
  if git check-ignore -q -- "${path}"; then
    report "Required scaffold file is ignored: ${path}"
  fi
done

sensitive_dir="private"
if [[ -d "${sensitive_dir}" ]]; then
  report "Repo-local ${sensitive_dir} directory is not allowed; use values/ or storage outside this checkout."
fi
if git grep -n "${sensitive_dir}/" -- ':!values/**' >/tmp/public-safety-sensitive.$$ 2>/dev/null; then
  cat /tmp/public-safety-sensitive.$$ >&2
  report "Tracked files must not reference a repo-local ${sensitive_dir} directory."
fi
rm -f /tmp/public-safety-sensitive.$$

if git grep -nE '(^|[^0-9])(10\.[0-9]{1,3}\.[0-9]{1,3}\.|192\.168\.[0-9]{1,3}\.|172\.(1[6-9]|2[0-9]|3[0-1])\.[0-9]{1,3}\.)' -- ':!values/**' >/tmp/public-safety-rfc1918.$$ 2>/dev/null; then
  cat /tmp/public-safety-rfc1918.$$ >&2
  report 'Tracked files must use RFC 5737/example addresses instead of live RFC 1918 ranges.'
fi
rm -f /tmp/public-safety-rfc1918.$$

if git grep -nE 'BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY|CF_DNS_API_TOKEN=.*[A-Za-z0-9]{20,}|PROXMOX_VE_API_TOKEN=.*[A-Za-z0-9]{20,}' -- ':!values/**' >/tmp/public-safety-secrets.$$ 2>/dev/null; then
  cat /tmp/public-safety-secrets.$$ >&2
  report 'Tracked files contain secret-looking material.'
fi
rm -f /tmp/public-safety-secrets.$$

if [[ "${fail}" -ne 0 ]]; then
  exit 1
fi

printf 'Public safety checks passed.\n'
