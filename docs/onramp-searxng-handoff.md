# Onramp SearXNG handoff

SearXNG is a shared-host service contract. The canonical service model declares its placement, endpoint, release, health, dependency on the shared host, and protected secret paths.

## Canonical lifecycle

```bash
export VALUES_SITE=<site>
just validate
just plan
# apply only after explicit approval
just apply
```

Keep the shared host enabled whenever the SearXNG service is enabled. The canonical model owns the host/service relationship; generated projections provide the consumer inputs and must not be edited.

## Ownership target

The shared-host application owner is responsible for the container definition, reverse proxy snippet, app deployment workflow, app-level health checks, and app lifecycle. This repository owns the substrate and the explicitly documented temporary service contract until the ownership transfer is implemented and accepted.

## Verification

Verify the direct SearXNG endpoint, intended HTTPS route, DNS projection, secret delivery, rootless runtime health, and a repeat plan. Do not print query credentials, tokens, private URLs, or certificate material.
