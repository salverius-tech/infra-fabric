# Hermes state backup and restore

Hermes runtime state lives on the Hermes service host under `/root/.hermes`.
That directory includes local memory/soul files such as `SOUL.md`, history,
logs, and Hermes-managed backups.

Backups are private operational state. Store them under the ignored nested
private values repo, not in tracked source:

```bash
scripts/hermes-state.sh backup
```

The command writes:

```text
values/hermes-backups/hermes-state-<timestamp>.tar.gz
values/hermes-backups/hermes-state-<timestamp>.tar.gz.sha256
```

To restore a saved archive:

```bash
scripts/hermes-state.sh restore values/hermes-backups/hermes-state-<timestamp>.tar.gz
```

Restore stops `hermes-dashboard`, preserves the current `/root/.hermes` as a
pre-restore archive on the Hermes host, restores the selected archive, and
restarts the dashboard.

After a successful backup, review and commit/push the private `values/` repo if
you want the archive stored in the private remote.
