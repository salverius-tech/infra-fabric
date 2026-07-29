# Canonical Values Ansible Inventory Audit

**Status:** audit complete; reduction deferred until paired canonical invocation parity is proven

`scaffold/ansible/inventory/local.yml` is not currently an Ansible-only override
file. It mixes four different classes of data:

- **Connection data:** the Proxmox host, connection user, and static inventory
  shape.
- **Infrastructure inputs:** VMIDs, addresses, runtime types, DNS addresses,
  storage-related values, and service resource settings.
- **Service configuration:** domains, release versions, image digests, ports,
  bootstrap switches, feature flags, and application settings.
- **Secret transport:** Ansible `lookup('env', ...)` expressions for logical
  secret names. The file does not contain secret values, but it still defines
  consumer secret wiring.

## Safe reduction boundary

The canonical paired mode is the only path authorized to replace the
infrastructure and service configuration classes. It consumes the verified
`ansible-inventory.json` projection together with flattened compatibility vars
from `ansible-vars.json`:

```bash
scripts/python.sh scripts/apply-ansible-services.py \
  --canonical-ansible \
  --mode sequential
```

Do not remove or silently override legacy entries until representative parity
has been demonstrated for:

- host identity, address, VMID, runtime type, and connection user;
- service domains, versions, image digests, ports, and feature switches;
- storage, DNS, Caddy, bootstrap, and runtime settings; and
- secret-dependent tasks with logical secret names only and no secret values in
  generated metadata or logs.

## Reduction order

1. Keep genuine Ansible-only connection overrides in a minimal static inventory.
2. Move infrastructure and service configuration to the canonical paired
   inventory/vars transport after parity evidence is accepted.
3. Keep secret delivery separate from non-secret compatibility vars; preserve
   task-local environment injection and protected temporary material.
4. Remove duplicated legacy entries only after rollback and legacy-versus-
   canonical execution evidence exists.

Until then, `local.yml` remains a compatibility input. The default Ansible
workflow remains legacy; `--canonical-ansible` is opt-in and rejects explicit
mixed inventory arguments.
