# Development validation findings — 2026-08-22

Value-free record of findings from the development-site validation cycle at
public commit `5991165` and the follow-up remediation commits. Operational
evidence rows remain recorded separately in the acceptance matrix when gates
are re-run clean.

## Findings and dispositions

1. **Technitium service bounce (fixed).** The stop/restart tasks bracketing the
   `dns-server` service-account change fired whenever the service was active,
   bouncing DNS on every convergence pass. Fixed by registering the account
   task result and gating both systemd tasks on an actual change; live
   convergence verified at zero changes afterward.

2. **NFS atomic-operation constraint (environment).** The development checkout
   resided on an NFS 4.2 mount whose server does not implement `renameat2`
   (`RENAME_NOREPLACE` / `RENAME_EXCHANGE`). This blocks the canonical renderer
   and guarded private-file snapshot tooling against paths on that mount.
   Resolution is environmental: primary work moves to a local-filesystem host;
   network storage remains a backup target only. Atomic-failure diagnostics
   were improved so future occurrences name the unsupported operation.

3. **Accepted imperative bootstrap behavior (documented).** Two roles report
   nonzero change counts on every pass by design:
   - `host_identity`: re-applies a pinned dotfiles revision each pass through
     an external installer; treated as intentional drift correction.
   - `hermes_control` / `hermes` runtime bundles: installer steps declare
     `changed_when: true`; downstream template/unit alignment detects the
     resulting churn legitimately.
   Evidence boundaries for convergence idempotence should state these
   exceptions rather than expect blanket zero-change recaps.

4. **Stale projections (fixed).** Tracked generated projections had drifted
   from the selected dev site model; regenerated and verified.

## Follow-ups

- Re-run all development acceptance gates from a local-filesystem host and
  record fresh matrix cells at the final commit.
- Commit strategy for the private values repo executed: source-of-truth files
  committed; transient operational artifacts remain untracked under the
  documented backup procedure.

## Destructive-rebuild rehearsal addendum — 2026-08-23

A model-driven catastrophic-recovery exercise was executed on disposable
development after the initial gate re-run, with operator approval: one
stateless guest (forgejo_runner) and one stateful guest (technitium) were each
fully destroyed through a reviewed plan and recreated from the committed
canonical model alone, with the technitium DNS zones restored from a guarded
pre-destruction backup and verified record-for-record against canonical
configuration. Both guests converged to idempotence afterward and provider
plans returned to zero-change. This demonstrates guest-level recovery from
model plus backups; it does not establish full-site teardown/rebuild,
off-controller reconstruction, or isolated-recovery acceptance.

The rehearsal surfaced four wrapper-contract defects, fixed and verified:

1. Site-lock acquisition was not reentrant within a process and did not
   recognize an outer holder across the wrapped tooling session boundary, so
   guarded state-snapshot restores self-deadlocked (fixed in `6628142`).
2. `restore-if-present` selected manifestless pre-restore safety archives as
   restore candidates, failing archive validation on every post-restore
   invocation (fixed in `6628142`).
3. The Technitium DNS sync never matched existing records because record
   values are nested under the API's `rData` shape, re-upserting every pass
   (fixed in `6628142`).
4. `INFRA_ALLOW_DESTROY` was not forwarded into the tooling container, making
   retained-stateful disables unplannable through the supported workflow
   (fixed in `ae916c5`).

Two service-model findings were also recorded: forgejo bootstrap consumed a
compatibility variable owned by forgejo_runner, silently coupling their
lifecycles — fixed by binding the bootstrap repository scope to forgejo's own
canonical configuration with a fail-closed divergence check (`fc752da`) — and
the ACME health-check budget was widened after first certificate issuance on
a fresh guest exceeded the previous window (`57d2b2f`). The sanctioned host-
trust procedure after intentional guest replacement is now documented in
[canonical troubleshooting](../../docs/canonical-troubleshooting.md).

## Full-site teardown and rebuild rehearsal — 2026-08-23

With operator approval, the entire disposable development site was destroyed
through the guarded teardown path (`teardown-plan`, reviewed destroy plan of
11 resources including all stateful guests, `teardown-apply --approve` with
the stateful batch acknowledgement) after fresh guarded backups of all seven
service states, the audit journal, and the OpenTofu state. The site was then
rebuilt from the committed canonical model alone through the supported apply
workflow.

Recovery sequence exercised and verified:

1. All eleven resources recreated from model-pinned identity (same VMIDs,
   hostnames, addresses); provider plan converged to zero-change afterward.
2. Controller trust re-enrollment for all recreated guests followed the
   documented attribution-and-replacement procedure.
3. First-boot identity recovery ran per resource class: root phase then infra
   phase for LXC guests, infra phase via cloud-init for VMs; all converged.
4. Full service convergence configured all eight enabled services.
5. Stateful data was restored into the rebuilt guests from pre-teardown
   guarded archives with automatic safety archives; Technitium DNS zones
   verified record-for-record against canonical configuration.
6. Final verification battery passed: convergence idempotence limited to the
   accepted exceptions, direct-service connectivity pass, Hermes read-only
   bridge healthy, zero-change provider plan.

One recovery-sequence finding emerged: restoring a service-state archive
reverts the guest's credential store to the archive era, invalidating any API
token bootstrapped between rebuild and restore. The pipeline already handles
this — re-running the apply rotates the token against the restored service —
but operators must know that a stateful restore requires one more apply
afterward. This is documented here as rehearsal evidence rather than a code
defect.

Boundary: same-host full-site rebuild only. It does not establish
off-controller reconstruction, independent external durability of retained
recovery artifacts, isolated-recovery acceptance, or production acceptance.
