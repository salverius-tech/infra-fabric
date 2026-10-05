#!/usr/bin/env bash
set -euo pipefail

site_arg="${1:-}"
site="${site_arg#SITE=}"
if [[ -z "${site}" || "${site_arg}" != "SITE="* ]]; then
  printf 'Usage: scripts/ssh-initialize.sh SITE=<site>\n' >&2
  exit 2
fi

VALUES_SITE="${site}"
SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-${HOME}/.config/infra-fabric/keys/${site}/site.age}"
INFRA_VALUES_DIR="values/sites/${site}"
export VALUES_SITE SOPS_AGE_KEY_FILE INFRA_VALUES_DIR

scripts/run-infra.sh python scripts/ssh-initialize.py \
  --site-file "/workspace/values/sites/${site}/site.yaml" \
  --bundle "/workspace/values/sites/${site}/secrets.sops.yaml"

VALUES_SITE="${site}" scripts/python.sh scripts/canonical-render.py \
  --site-file "/workspace/values/sites/${site}/site.yaml" \
  --output-dir "/workspace/values/sites/${site}/generated"
