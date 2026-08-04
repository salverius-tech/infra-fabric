# Canonical site template

Copy `site.yaml` into `values/sites/<site>/site.yaml`, replace the `example` site identity and every example resource/service value, then create the matching encrypted `secrets.sops.yaml` and `.sops.yaml` privately.

This template is public-safe and has `allow_apply: false` and `allow_destroy: false`. It is a starting shape, not permission to apply. Run the canonical schema validation and selected-site plan after completing all fields.

Do not edit generated projections. Do not put age identities, recipients, passwords, tokens, real endpoints, or state in this directory.
