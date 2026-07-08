# Documentation Index

Public-safe documentation for this homelab infrastructure runbook.

## Operator and platform docs

- [Hermes operator pilot PRD](hermes-operator-pilot-prd.md) defines the Hermes cockpit requirements, safety boundaries, and SearXNG pilot classification.
- [Onramp app-platform contract](onramp-app-platform-contract.md) defines the `homelab-infra`, `onramp-vNext`, and Hermes ownership split for onramp-host services.
- [Onramp SearXNG handoff](onramp-searxng-handoff.md) gives `onramp-vNext` the public-safe SearXNG-on-Podman implementation contract.
- [App-host runbook](onramp-host-runbook.md) covers onramp_host enable/disable, rollback, and future live deployment validation.

## Workflow reminder

Use the repository workflow from the main [README](../README.md): validate with `just validate`, review infrastructure changes with `just plan`, and apply only after explicit approval with `just apply`.
