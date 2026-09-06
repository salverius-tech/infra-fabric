# Hermes Control operations

Hermes Control is a canonical service configuration. Its source reference, source URL, control endpoint, runtime identity, protected API/bridge tokens, and enablement are declared by the selected site model and encrypted bundle.

## Configure and verify

Edit the selected canonical site and protected bundle, then run:

```bash
export VALUES_SITE=<site>
just edit-secrets SITE=<site>
just validate
just plan
```

Apply only after explicit approval:

```bash
VALUES_SITE=<site> just apply
```

The API is loopback-only inside the guest; service-local Caddy is the HTTPS exposure path. The typed Control configuration also declares the managed workspace root and the explicit approved project-root list passed to the API. Use direct service endpoints and redact all tokens from checks and logs.

## Five-state verification

Verify source identity, immutable source reference, installation/readiness, authenticated API diagnostics, and runtime/plugin health. Keep the API loopback-only. Do not expose port 8787.

Use `HERMES_PLUGINS_DEBUG=1` only for an explicitly approved diagnostic session, then remove it. `HERMES_CONTROL_SOURCE_REF` must remain an immutable reviewed reference.

## Rotation and rollback

Rotate API and bridge tokens through the encrypted canonical bundle, validate policy and required paths, apply only from a reviewed plan, then verify Control health and dependent Hermes behavior. Roll back by restoring the prior encrypted bundle and re-running the canonical validation/plan workflow.
