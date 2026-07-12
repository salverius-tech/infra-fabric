# homelab-infra values template

This directory is a public-safe template for `values/`, the nested private Git repo that stores site values and state.

`values/` is ignored by the public runbooks repo. In normal use it has its own private remote, such as a Forgejo repository, and is committed/pushed separately from this repo.

## Files

- `.env` — local credentials and bootstrap environment variables, including Hermes Agent dashboard auth secrets.
- `terraform.tfvars` — site-specific Proxmox/LXC/OpenTofu variables, including optional per-container VLAN tags and the optional disabled-by-default Tailscale client LXC.
- Optional private artifact cache — if a future workflow caches release archives such as Technitium portable tarballs, keep those files in ignored private storage outside tracked `scaffold/`.
- `dns-records.local.json` — site-specific Technitium DNS zones and records.
- `ansible/inventory/local.yml` — site-specific Ansible inventory and role variables. The Technitium Caddy proxy uses `caddy_server_names` for DNS UI aliases such as `dns.example.internal` and `technitium.example.internal`.

## Initialize

From the runbooks repo root:

```bash
cp settings.example.json settings.local.json  # optional local setup defaults
just setup
```

Or clone an existing private values repo, such as the Forgejo-hosted values repo, during setup:

```bash
just setup git@git.example.internal:owner/homelab-infra-values.git
```

When run interactively, `just setup` starts setup wizards if private values still have scaffold placeholders. The Proxmox wizard asks for the Proxmox host, tests root SSH key access, offers an alternate key file or a command to authorize your default public SSH key if default keys fail, creates/updates a Proxmox API user/token, and stores the endpoint/token/SSH target in `.env` without printing the token secret. The domain wizard asks for your base domain plus a starting service IP, then derives static LXC addresses and names such as `dns.<domain>`, `technitium.<domain>`, `git.<domain>`, `infisical.<domain>`, and `hermes.<domain>` in the authoritative private values files. To rerun the Proxmox wizard later from the runbooks repo root:

```bash
scripts/bootstrap-pve-token.sh --force
```

To rerun the domain wizard:

```bash
scripts/python.sh scripts/bootstrap-domain.py --force
```

Container VLAN tags default to `null`, which leaves the LXC interface untagged.
Set the matching `*_vlan_id` value to a VLAN ID from 1 through 4094 when the
Proxmox bridge should tag that container interface.

## Service runtime, Forgejo database, and service storage

`service_runtime` selects the platform used to run each first-class service guest. Services default to Debian LXC when they are not listed. VM mode is available for `technitium`, `forgejo`, `tailscale_client`, `forgejo_runner`, `infisical`, and `hermes` when a service needs normal VM capabilities, such as mounting NFS directly inside the guest. `onramp_host` is VM-only.

```hcl
service_runtime = {
  forgejo = {
    type = "lxc"
  }
}
```

```hcl
service_runtime = {
  forgejo = {
    type            = "vm"
    cloud_init_user = "forgejo-admin"
  }
}
```

VM guests use `guest_vm_image_*` defaults unless they can reuse the onramp host image. If `cloud_init_user` is omitted, `guest_vm_cloud_init_user` is used.

`forgejo_database` selects Forgejo's database backend. The default keeps the simple SQLite deployment.

```hcl
forgejo_database = {
  type = "sqlite"
}
```

Use managed PostgreSQL when Forgejo data is on network storage and SQLite file locking would be risky. The PostgreSQL server runs inside the Forgejo LXC and stores its database under the guest's normal local PostgreSQL data directory. Store the password in `values/.env` as `FORGEJO_POSTGRES_PASSWORD`.

```hcl
forgejo_database = {
  type    = "postgres"
  managed = true
  name    = "forgejo"
  user    = "forgejo"
}
```

`service_storage` defines durable storage by service and logical mount name. The scaffold defaults Forgejo data to a Proxmox-managed volume so new deployments do not assume a host ZFS path.

The storage `type` describes how the service receives storage. For `bind` only, optional `host_prepare` describes how the Proxmox node prepares the bind source before OpenTofu attaches it to the LXC.

```hcl
service_storage = {
  forgejo = {
    data = {
      type       = "proxmox_volume"
      storage_id = "local-lvm"
      size_gb    = 32
      target     = "/var/lib/forgejo"
      backup     = true
    }
  }
}
```

```hcl
service_storage = {
  forgejo = {
    data = {
      type   = "bind"
      source = "/srv/homelab/forgejo"
      target = "/var/lib/forgejo"

      host_prepare = {
        type = "directory"
      }

      host_uid = 100000
      host_gid = 100000
      mode     = "0750"
    }
  }
}
```

```hcl
service_storage = {
  forgejo = {
    data = {
      type   = "bind"
      source = "/tank/forgejo"
      target = "/var/lib/forgejo"

      host_prepare = {
        type       = "zfs_dataset"
        dataset    = "tank/forgejo"
        mountpoint = "/tank/forgejo"
      }
    }
  }
}
```

```hcl
service_storage = {
  forgejo = {
    data = {
      type   = "bind"
      source = "/mnt/storage/forgejo"
      target = "/var/lib/forgejo"

      host_prepare = {
        type       = "host_nfs_mount"
        server     = "storage.example.internal"
        export     = "/exports/forgejo"
        mountpoint = "/mnt/storage/forgejo"
        options    = ["rw", "nfsvers=4.2", "_netdev", "nofail"]
      }
    }
  }
}
```

```hcl
service_storage = {
  forgejo = {
    data = {
      type    = "guest_nfs"
      server  = "storage.example.internal"
      export  = "/exports/forgejo"
      target  = "/var/lib/forgejo"
      options = ["rw", "nfsvers=4.2", "hard", "_netdev", "nofail"]
      owner   = "git"
      group   = "git"
    }
  }
}
```

```hcl
service_storage = {
  forgejo = {
    data = {
      type             = "guest_cifs"
      server           = "storage.example.internal"
      share            = "forgejo"
      target           = "/var/lib/forgejo"
      credentials_file = "/etc/homelab/storage/forgejo-cifs.credentials"
      options          = ["rw", "vers=3.1.1", "_netdev", "nofail"]
    }
  }
}
```

```hcl
service_storage = {
  searxng_onramp = {
    cache = {
      type = "none"
    }
  }
}
```

Use `bind` when the Proxmox host exposes a path to an LXC. `host_prepare.type` may be `none`, `directory`, `zfs_dataset`, `host_nfs_mount`, or `host_cifs_mount`. Use `proxmox_volume` when Proxmox should provision the volume from a configured storage ID. Use `guest_nfs` or `guest_cifs` when the service guest should mount network storage directly. When mounting all Forgejo data on NFS, prefer `forgejo_database.type = "postgres"` so SQLite is not stored on network storage. Do not put CIFS credentials in `terraform.tfvars`; keep secrets in private ignored values files or a secret manager and reference only the guest credentials path here.

Hermes and the optional onramp host use `anvil` as their non-root runtime/deploy user by default. Add real public SSH keys to `lxc_ssh_public_keys`; the onramp cloud-init keys fall back to that list when `onramp_host_ssh_public_keys` is empty. Hermes managed runtime activation is intended for Debian 13 amd64 guests with Python 3.13 and uses hash-locked dashboard plus messaging dependencies, verified Node.js, and disabled runtime lazy installs. Set `hermes_runtime_passwordless_sudo: true` only when Hermes setup requires unattended sudo; this makes the runtime user root-equivalent inside the Hermes guest.

Technitium update management is intended to use private version/checksum pins and, if needed, cached release archives in ignored private storage. Keep live cached tarballs and checksums out of tracked source.

After editing the copied files, run the normal validation entry point:

```bash
just validate
```

Keep `.env` in dotenv-style `KEY=value` or `export KEY=value` format. The runbooks parse it as data and reject shell execution patterns.

Optional EdgeRouter access uses `EDGEROUTER_ADDR` (for example, `firewall.example.internal`) and `EDGEROUTER_USER` (for example, `ubnt`). Configure that account for key-based, read-only SSH access. Do not store `EDGEROUTER_PASS`.

For Hermes dashboard form login, store `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH`, not a plaintext password. Generate it with:

```bash
python scripts/hermes-password-hash.py
```

For Forgejo Actions deployment, set the persistent Forgejo security secrets (`FORGEJO_SECRET_KEY`, `FORGEJO_INTERNAL_TOKEN`, `FORGEJO_OAUTH2_JWT_SECRET`, and `FORGEJO_LFS_JWT_SECRET`), admin credentials (`FORGEJO_ADMIN_USERNAME`, `FORGEJO_ADMIN_EMAIL`, `FORGEJO_ADMIN_PASSWORD`), repository-owner credentials (`FORGEJO_REPO_OWNER_EMAIL`, `FORGEJO_REPO_OWNER_PASSWORD`), and `FORGEJO_RUNNER_REGISTRATION_SECRET` in `values/.env`. The default admin username is `anvil`; override `FORGEJO_ADMIN_USERNAME` if needed. The runner registration secret must be exactly 40 hex characters.

When `forgejo` or `forgejo_runner` is enabled, `scripts/migrate-values.py` fills missing Forgejo secrets and writes explicit bootstrap inventory values. If `forgejo_runner_scope` is missing or still set to the scaffold placeholder, migration tries to infer `owner/repo` from the private `values` Git remote and records that value in `values/ansible/inventory/local.yml`. Future applies use the recorded inventory value, not the Git remote dynamically.

The Forgejo role bootstraps a dedicated admin user and a separate repository-owner user derived from `forgejo_runner_scope`, then creates the runner repository under that owner. If you want the runner scoped to an organization, create the organization/repository manually and set `forgejo_bootstrap_enabled: false` after the initial Forgejo install.
