# Canonical site template

Copy `site.yaml` into `values/sites/<site>/site.yaml`, replace the `example` identity and every example platform, resource, network, storage, service, endpoint, release, and state value, then create the matching encrypted `secrets.sops.yaml` and private `.sops.yaml` policy.

The template is the complete public-safe starting shape for the canonical site model. It demonstrates:

- site lifecycle and mutation policy;
- bootstrap and operator identity declarations;
- Proxmox, network, image, and storage defaults;
- dedicated guests and shared-host resources;
- service selection, dependencies, endpoints, releases, configuration, and state policy;
- disabled service entries that make the catalog surface explicit.

It has `allow_apply: false` and `allow_destroy: false`. It is a starting shape, not permission to apply. Complete all required fields, establish the private SOPS policy/bundle and external age identity, then run the canonical validation and selected-site plan workflows.

Do not edit generated projections. Do not put age identities, recipients, passwords, tokens, real endpoints, state, plans, or backups in this directory.
