# Environment-specific acceptance matrix

Development evidence is recorded only in the development row. No row implies evidence in another environment.

| Environment | plan | apply | health-idempotence | service-restore | infrastructure-recovery | hermes-integration | rollback |
| --- | --- | --- | --- | --- | --- | --- | --- |
| development | evidenced | evidenced | evidenced | evidenced | not-evidenced | not-evidenced | not-evidenced |
| isolated-recovery | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced |
| production | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced | not-evidenced |

Development evidence source: `.hermes/plans/2026-08-04-combined-remediation-and-backlog-reconciliation.md:10`. This source does not establish recovery or production evidence.
