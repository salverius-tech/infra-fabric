# Hermes Control Integration Plan

**Status:** Working design — the `infra-fabric` source contract is complete and HC-01 is complete in `hermes-control`; disposable guest lifecycle/plugin/Caddy/DNS/WebSocket smoke checks, upstream compatibility, deployed five-state/update behavior, rollback, and live acceptance remain external gates. The [package completion](../reconciliation/package-completion.md) and [acceptance matrix](../reconciliation/acceptance-matrix.md) are the active status authorities. No live or production acceptance is implied here.

## Decision

Deploy Hermes Control as a managed companion stack on the existing Hermes guest, whether its runtime is LXC or VM.

- The Control API is private, HTTPS-proxied through the Hermes guest’s service-local Caddy, and bound only to loopback.
- Task execution is **mandatory approval** in this infrastructure deployment. Read-only Control API views remain available to an authenticated mobile client without task approval.
- The Control API, bridge, and plugin are separate runtime components and are verified independently.
- Use a dedicated `hermes_control` Ansible role invoked by the existing Hermes role. Do not use manual guest installation steps.

## Why a dedicated role

A separate role isolates the Control stack’s lifecycle, source pin, Python venv, systemd services, API/bridge state, Caddy site, and secret rendering from the core Hermes runtime. The existing `hermes` role remains the owner of the Hermes account, managed Hermes runtime, gateway, dashboard, common Caddy installation, and repository operator plugin.

This is a logical boundary, not a new guest or a new control plane. The role runs on the same direct-access `hermes` inventory host, so the plan remains LXC/VM-neutral.

## Target architecture

```text
Authenticated mobile client
  -> private HTTPS Control API hostname on Hermes-local Caddy
  -> 127.0.0.1 Control API service
  -> authenticated local Unix-socket bridge service
  -> Hermes CLI under the configured hermes_runtime_user

Hermes gateway
  -> hermes-control-extension plugin
  -> authenticated localhost Control API
```

## Deployment constraints

The operator approved implementation on the active working branches. The Control source/ref and private inputs remain deployment prerequisites. Do not run manual installation commands, `just plan`, or `just apply` while preparing this work. Production deployment remains a reviewed `just plan` followed by explicit approval for `just apply`.

## Ordered tasks

The checkboxes below record completion of the public source contract only. They do not claim the guest, provider, production, rollback, or other external evidence listed in the evidence log. Use the environment-specific acceptance matrix for those gates.

### HC-01 — Enforce the infrastructure authority model in Hermes Control

- [x] Add an explicit deployment policy setting such as `CONTROL_API_REQUIRE_TASK_APPROVAL=1`.
- [x] Enforce the policy at the shared task-submission boundary, not only in mobile defaults: newly created tasks and all recovery/continuation/new-session paths must remain awaiting approval when the setting is enabled.
- [x] Keep health, diagnostics, project/session reads, task reads, and approval/rejection audit reads available to authenticated callers.
- [x] Preserve durable approval audit metadata; reject invalid state transitions.
- [x] Document that API approval is a task-execution gate, while infrastructure mutation must still pass the existing infrastructure operator’s plan/approval/destructive-stateful controls.

**Repository:** `hermes-control`.

**Evidence:** Focused API tests for create, retry, continuation, edited retry, and new-session requests that attempt `requires_approval: false`; approval/audit transition tests; full backend verifier; public-safe documentation scan.

### HC-02 — Add a dedicated `hermes_control` Ansible role

- [x] Create `infra/ansible/roles/hermes_control/` with defaults, tasks, templates, handlers, and public-safe tests.
- [x] Invoke it from the existing Hermes service configuration flow only when `hermes_control_enabled` is true.
- [x] Use `hermes_runtime_user` and its existing home/Hermes state; do not create or hard-code a second `hermes` account.
- [x] Install required OS dependencies declaratively and create an isolated venv under the managed checkout.
- [x] Keep role variables free of real URLs, hostnames, tokens, paths unique to a site, and source credentials.

**Likely paths:** `infra/ansible/playbooks/hermes.yml`, `infra/ansible/roles/hermes/tasks/main.yml`, new `infra/ansible/roles/hermes_control/`, dynamic inventory/scaffold tests as needed.

**Evidence:** Ansible syntax/lint through `just validate`; role contract tests; LXC and VM inventory coverage; `git diff --check`.

### HC-03 — Add pinned source acquisition and local plugin installation

- [x] Declare private source inputs for repository URL, immutable reviewed commit/ref, and optional read-only source credential mechanism.
- [x] Check out the exact approved revision into a fixed managed guest path; verify the checked-out commit before venv installation.
- [x] Install/enable `hermes-control-extension` from the local managed checkout using the Hermes plugin manager, under `hermes_runtime_user`.
- [x] Restart the gateway only through Ansible handlers after plugin installation/update.
- [x] Do not use floating `git pull`, an unpinned remote plugin install, or a second uncontrolled plugin checkout.

**Implemented paths:** role tasks/templates, canonical catalog/schema/projections, generated inventory/vars, and public documentation.

**Evidence:** Idempotence tests/mocks for checkout revision and plugin install invocation; plugin manifest/source verification; `HERMES_PLUGINS_DEBUG=1 hermes tools list` in disposable guest validation.

### HC-04 — Render least-privilege configuration and persistent state

- [x] Deliver separate API bearer and bridge tokens from the selected site's encrypted canonical bundle; delivery is transient and never logged.
- [x] Render three root-owned, runtime-user-readable environment views:
  - API: API bearer token, bridge token/socket, task DB, Hermes home, managed workspace and approved project roots, mandatory-approval policy.
  - bridge: bridge token/socket, managed Hermes command, Hermes home, runtime PATH/node environment.
  - gateway plugin: localhost API URL and API bearer token only.
- [x] Create persistent Control API state with restrictive ownership/mode.
- [x] Ensure the bridge command uses the managed Hermes runtime and prevents recursive plugin loading; do not rely on disabled child rules for infrastructure safety.

**Implemented paths:** role templates, catalog-declared canonical secret bindings, canonical projections, and related tests.

**Evidence:** No-secret output tests; mode/ownership/template contract tests; successful Control API diagnostics in a disposable guest; public-safety check.

### HC-05 — Install separately supervised bridge and API services

- [x] Template the bridge and API units with the configured `hermes_runtime_user`, managed checkout path, environment files, runtime directory, loopback binding, restart policy, and least necessary write paths.
- [x] Keep the bridge outside the gateway process so gateway reload/restart does not own or orphan mobile task IPC.
- [x] Configure ordering and handlers so bridge/API restart after a source, environment, or unit change; gateway restart remains independent.
- [x] Verify real Unix-socket connection readiness, not merely the socket pathname.

**Likely paths:** new role systemd templates/handlers and test coverage.

**Evidence:** Unit-template assertions; service lifecycle test in a disposable guest; bridge real-connection smoke test; API `/health` and authenticated `/diagnostics` smoke tests.

### HC-06 — Expose the API privately through Hermes-local Caddy and DNS

- [x] Extend the existing Hermes Caddy configuration using a dedicated private Control API hostname, not an exposed port and not a public default route.
- [x] Preserve dashboard routing and WebSocket behavior; Caddy `reverse_proxy` must carry `/ws/events` upgrades.
- [x] Add the corresponding DNS record through existing service/DNS orchestration, using public-safe scaffold placeholders and private values for the actual name.
- [x] Validate Caddy before reload and define both local-loopback and private-HTTPS health checks; live endpoint evidence remains external.

**Likely paths:** Hermes Caddy templates, inventory/scaffold settings, DNS record generation/orchestration, documentation, Caddy tests.

**Evidence:** Caddy validation; DNS contract tests; HTTPS health and authenticated diagnostics checks from an approved private endpoint; WebSocket handshake smoke test without logging credentials.

### HC-07 — Add deployment and upgrade verification

- [x] Add a redacted status/verification procedure that reports separately: gateway running, plugin installed/enabled, plugin loaded/registered, bridge ready, and API ready.
- [x] Add source-revision, API process-start/PID freshness, and authenticated diagnostics checks after an update.
- [x] Document API-token rotation, bridge-token rotation, rollback to the previous source ref, plugin refresh, and safe failure recovery.
- [x] Preserve the existing infrastructure operator plugin's hard read-only behavior; deployed coexistence remains an external acceptance gate.

**Likely paths:** Hermes runbook/PRD, role verification tasks where appropriate, test fixtures, and documentation index.

**Evidence:** Focused role/contract tests; Hermes Control canonical verifier; `just validate`; a disposable-guest deployment smoke test; `git diff --check`.

## Private input contract

The private values repository will need only deployment-specific values such as the Control source URL/ref, private Control API hostname, and generated secrets. Public scaffold files must use placeholders. No token, real hostname, source credential, API response, or private inventory belongs in tracked source or reports.

## Explicit non-goals

- No new Proxmox LXC/VM or separate ingress host.
- No public exposure of the Control API or port `8787`.
- No direct mobile access to Proxmox, SSH, provider credentials, Caddy credentials, or bridge credentials.
- No custom Hermes release channel.
- No bypass of `just validate`, `just plan`, saved-plan verification, explicit apply approval, stateful/destructive gates, or output redaction.
- No use of the Control API’s optional approval default in this deployment.

## Verification evidence log

| Task | Required evidence | Status |
|---|---|---|
| HC-01 | Mandatory-approval API regression coverage | Complete — backend approval-path coverage and docs in `hermes-control` |
| HC-02 | Role contract and LXC/VM inventory coverage | Source complete; external disposable LXC/VM smoke pending |
| HC-03 | Pinned checkout and local plugin-install checks | Source complete; external disposable plugin-manager smoke pending |
| HC-04 | Secret/mode/template contract tests | Source complete; external guest diagnostics pending |
| HC-05 | Bridge/API unit and real socket/API smoke evidence | Source complete; external protocol/lifecycle guest smoke pending |
| HC-06 | Caddy/DNS/HTTPS/WebSocket evidence | Source complete; external WebSocket and deployed DNS smoke pending |
| HC-07 | Five-state verification and rollback documentation | Source complete; external deployed five-state/update verification pending |

## Decision log

- 2026-07-22: Operator approved mandatory server-enforced task approval for Hermes Control in this infrastructure deployment.
- 2026-07-22: Operator approved the dedicated Ansible-role approach in principle.
- 2026-08-13: Public source tasks are complete. Unchecked live claims were removed from the source checklist; the evidence log and acceptance matrix retain all external gates.
