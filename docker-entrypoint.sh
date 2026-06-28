#!/usr/bin/env bash
set -euo pipefail

if [[ -d /ssh-ro ]]; then
  install -d -m 0700 /root/.ssh
  cp -a /ssh-ro/. /root/.ssh/ 2>/dev/null || true
  chmod 0700 /root/.ssh
  find /root/.ssh -type f -name '*.pub' -exec chmod 0644 {} + 2>/dev/null || true
  find /root/.ssh -type f ! -name '*.pub' -exec chmod 0600 {} + 2>/dev/null || true
fi

exec "$@"
