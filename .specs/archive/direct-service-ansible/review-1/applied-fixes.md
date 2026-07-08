# Applied Fix Plan

| Finding | Category | Plan section(s) to edit | Edit intent | Checklist impact |
|---------|----------|-------------------------|-------------|------------------|
| Invalid `caddy_proxy` direct target | substantive defect | Context, MVP Boundary, Task Breakdown, Execution Waves, Success Criteria | Treat Caddy proxy as Technitium-hosted role (`hosts: technitium`) unless a future alias is explicitly added | Update T3/T4/T6 wording; no new checklist item |
| Hard-coded service loops ignore settings | process defect | Automation Plan, Execution Waves, Success Criteria, Validation Contract | Add requirement to create/use settings-aware validation helper with sanitized checked/skipped output | Add/rename T2 to include helper; update checks |
| Regex-only `pct` checks miss argv YAML | substantive defect | Automation Plan, Execution Waves, Success Criteria, Validation Contract | Require YAML-aware policy tests for forbidden `pct` argv and pve role placement | Update T2/T8 acceptance criteria |
| Forgejo Runner includes Proxmox-host tasks | substantive defect | Task Breakdown, Execution Waves, Handoff Notes | Split service-direct tasks from pve-boundary trust/authorization tasks; do not move wholesale | Update T5 scope |
| Direct SSH/bootstrap/become prerequisite missing | substantive defect | Automation Plan, Execution Waves, Validation Contract | Add direct SSH/Python/become gate and gated bootstrap/recovery decision tree | Add T1 acceptance criteria; no extra task |
| Validation can pass while pve configures services | substantive defect | Execution Waves, Success Criteria | Require YAML-aware tests proving pve plays limited to lifecycle/bootstrap/storage and service roles run in direct plays | Update T2/T3/V gates |
| Secret handling/evidence redaction underspecified | process defect | Automation Plan, Execution Waves, Telemetry/Evidence, Validation Contract | Require final-path templating with owner/mode/no_log and sanitized evidence artifacts | Update T4/T5/V gates |
| Long duplicated commands | hardening | Automation Plan, Execution Waves, Success Criteria | Use one tracked helper script rather than repeated one-liners | T2 creates helper; validations use helper |
| Standalone blocker: T1 depended on helper before T2 created it | process defect | Execution Checklist, Task Breakdown, Execution Waves, Dependency Graph | Reorder waves so T2 helper creation is Wave 1 and T1 direct-access verification is Wave 2 | Added V4 and updated dependencies/checklist; no work marked complete |
| Bare host Python commands | hardening | Execution Waves, Success Criteria | Replace with `scripts/python.sh` or unit tests | Update commands |
| Check-mode/dry-run missing | hardening | Execution Waves, Validation Contract | Add per-service direct check-mode/diff where safe, with exceptions | Update V2/V3 |
| Live rollout rollback weak | hardening | Deployment validation, Handoff Notes | Keep deployment out of MVP; if approved, require serial per-service rollout with backups/health checks | No checklist change |
| Stale tests name Proxmox tasks | hardening | Execution Waves | Require semantic test updates rather than stale task-name assertions | Update T2/T5/T8 |
