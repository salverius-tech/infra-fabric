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
