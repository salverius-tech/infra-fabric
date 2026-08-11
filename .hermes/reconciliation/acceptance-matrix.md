# Environment-specific acceptance matrix

Active authority for environment-specific external acceptance only. An evidenced cell applies only to its exact environment, audited commit, procedure, result, citation, date, and stated boundary; source completion does not populate this matrix.

| Environment | plan | apply | health-idempotence | service-restore | infrastructure-recovery | hermes-integration | rollback |
| --- | --- | --- | --- | --- | --- | --- | --- |
| development | evidenced | evidenced | evidenced | evidenced | not-evidenced | not-evidenced | not-evidenced |
| isolated-recovery | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced |
| production | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced |

## Evidence records

- `development/plan` — commit `d88a66a65675a920f4930d0cbb6c470a9a49a9a1`; procedure `phase-9-gate-1`; result `passed` on `2026-08-09`; evidence `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:635-648`; boundary: Disposable development plan only; no prior normalized baseline established semantic equivalence.
- `development/apply` — commit `d88a66a65675a920f4930d0cbb6c470a9a49a9a1`; procedure `phase-9-gate-2`; result `passed` on `2026-08-09`; evidence `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:635-648`; boundary: Reviewed disposable development apply only; no isolated-recovery or production acceptance.
- `development/health-idempotence` — commit `d88a66a65675a920f4930d0cbb6c470a9a49a9a1`; procedure `phase-9-gate-3`; result `passed` on `2026-08-09`; evidence `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:635-648`; boundary: Direct development health and second-run idempotence only.
- `development/service-restore` — commit `d88a66a65675a920f4930d0cbb6c470a9a49a9a1`; procedure `phase-9-gate-4`; result `passed` on `2026-08-09`; evidence `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:635-648`; boundary: Enabled disposable development stateful services only; not controller or infrastructure recovery.

Historical development evidence source: `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:635-648`. This source does not establish isolated-recovery or production acceptance.
