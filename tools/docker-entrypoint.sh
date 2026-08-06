#!/usr/bin/env bash
set -euo pipefail

container_user="${INFRA_CONTAINER_USER:-anvil}"
container_home="/home/${container_user}"
ssh_dir="${container_home}/.ssh"

if [[ -n "${INFRA_HOST_GID:-}" ]] && [[ "$(id -g "${container_user}")" != "${INFRA_HOST_GID}" ]]; then
  groupmod -o -g "${INFRA_HOST_GID}" "${container_user}"
fi

if [[ -n "${INFRA_HOST_UID:-}" ]] && [[ "$(id -u "${container_user}")" != "${INFRA_HOST_UID}" ]]; then
  usermod -o -u "${INFRA_HOST_UID}" -g "$(id -g "${container_user}")" "${container_user}"
fi

install -d -m 0755 "${container_home}"
install -d -m 0755 "${container_home}/.terraform.d" "${container_home}/.ansible"
install -d -m 0755 "${container_home}/.terraform.d/plugin-cache"
chown -R "${container_user}:${container_user}" "${container_home}/.terraform.d" "${container_home}/.ansible"

# Repair only known public runtime paths. In particular, do not traverse or
# repair ownership below a separately-mounted private values repository.
for path in /workspace/.ansible /workspace/infra/opentofu; do
  if [[ -e "${path}" ]]; then
    chown "${container_user}:${container_user}" "${path}" 2>/dev/null || true
  fi
done
find /workspace/infra/opentofu -maxdepth 2 -type d -name .terraform \
  -prune -exec chown -R "${container_user}:${container_user}" {} + 2>/dev/null || true
find /workspace/infra/opentofu -maxdepth 2 -type f \( \
  -name 'terraform.tfstate*' -o -name '*.tfstate*' -o -name '.terraform.tfstate.lock.info' \
\) -exec chown "${container_user}:${container_user}" {} + 2>/dev/null || true

cache_root=/tmp/infra-fabric
install -d -m 0755 "${cache_root}/coverage" "${cache_root}/pycache" "${cache_root}/xdg-cache"
chown -R "${container_user}:${container_user}" "${cache_root}"
export COVERAGE_FILE="${cache_root}/coverage/.coverage"
export PYTHONPYCACHEPREFIX="${cache_root}/pycache"
export XDG_CACHE_HOME="${cache_root}/xdg-cache"

if [[ -d /ssh-ro ]]; then
  install -d -m 0700 -o "${container_user}" -g "${container_user}" "${ssh_dir}"

  case "${INFRA_SSH_IDENTITY_SOURCE:-external}" in
    external|sops) ;;
    *)
      printf 'Unsupported SSH identity source.\n' >&2
      exit 2
      ;;
  esac

  if [[ "${INFRA_SSH_IDENTITY_SOURCE:-external}" == "sops" ]]; then
    if [[ "${INFRA_COPY_SSH_KEYS:-false}" != "true" ]]; then
      printf 'SOPS-backed SSH identity requires the protected SSH transport boundary.\n' >&2
      exit 2
    fi
    if [[ -z "${INFRA_VALUES_DIR:-}" || -z "${SOPS_AGE_KEY_FILE:-}" ]]; then
      printf 'SOPS-backed SSH identity inputs are unavailable.\n' >&2
      exit 2
    fi
    python3 /workspace/scripts/canonical_ssh_identity.py --destination "${ssh_dir}/canonical-bootstrap"
    export INFRA_SSH_IDENTITY_FILE=canonical-bootstrap
  fi

  for path in /ssh-ro/known_hosts /ssh-ro/config /ssh-ro/*.pub; do
    if [[ -f "${path}" ]]; then
      cp "${path}" "${ssh_dir}/"
    fi
  done

  if [[ "${INFRA_COPY_SSH_KEYS:-false}" == "true" && "${INFRA_SSH_IDENTITY_SOURCE:-external}" != "sops" ]]; then
    identity_file="${INFRA_SSH_IDENTITY_FILE:-}"
    if [[ ! "${identity_file}" =~ ^[A-Za-z0-9._-]+$ ]]; then
      printf 'INFRA_SSH_IDENTITY_FILE must name one SSH identity file when INFRA_COPY_SSH_KEYS=true.\n' >&2
      exit 2
    fi
    if [[ ! -f "/ssh-ro/${identity_file}" ]]; then
      printf 'Selected SSH identity file is not available under /ssh-ro: %s\n' "${identity_file}" >&2
      exit 2
    fi
    cp "/ssh-ro/${identity_file}" "${ssh_dir}/${identity_file}"
  fi

  chown -R "${container_user}:${container_user}" "${ssh_dir}"
  chmod 0700 "${ssh_dir}"
  find "${ssh_dir}" -type f -name '*.pub' -exec chmod 0644 {} +
  find "${ssh_dir}" -type f ! -name '*.pub' -exec chmod 0600 {} +
fi

export HOME="${container_home}"

exec gosu "${container_user}" "$@"
