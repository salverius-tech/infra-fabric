# Development acceptance gate runbook

Ordered, exact commands for re-running the development acceptance gates from a
clean checkout on a **local-filesystem host**. Network-mounted working copies
are unsupported: atomic-rename primitives used by the renderer and guarded
snapshot tooling fail on NFS exports. Network storage is a backup target only.

Prerequisites: Linux amd64 host, Git, `just`, Docker Engine with Compose, the
selected site's private values (`values/`), SOPS policy, encrypted bundle, and
external age identity at the documented path. Every command runs from the
repository root with `VALUES_SITE=dev` exported unless stated otherwise.

Recorded exceptions: `host_identity` and the Hermes installer chain report
nonzero changes every pass by design; see the 2026-08-22 validation findings
note in `.hermes/reconciliation/` before interpreting convergence recaps.

## Gate 1 — Static validation

```bash
export VALUES_SITE=dev
just validate   # public safety, model/catalog, projections, tofu, lint, ansible
just test       # full Python suite; no values required
git diff --check
```

Pass: exit 0 everywhere, clean diff check.

## Gate 2 — Projections and protected bundle

```bash
VALUES_SITE=dev docker compose run --rm infra python scripts/verify-projections.py \
  --site-file /workspace/values/sites/dev/site.yaml \
  --generated-dir /workspace/values/sites/dev/generated
VALUES_SITE=dev docker compose run --rm infra python scripts/workspace-preflight.py \
  --require-values --require-secrets
```

Pass: projections verified; preflight passes without decryption output.

## Gate 3 — Provider plan and drift

```bash
export VALUES_SITE=dev
just plan       # review summary: create/update/replace/delete, destructive changes
```

Pass: provider refresh evaluates cleanly; summary reports zero actions and no
destructive changes. If anything is nonzero, stop: review the plan and obtain
explicit approval before any apply.

## Gate 4 — Convergence and idempotence

```bash
VALUES_SITE=dev INFRA_COPY_SSH_KEYS=true INFRA_SSH_IDENTITY_SOURCE=sops \
  scripts/run-infra.sh bash -euo pipefail -c '
  source scripts/site-context.sh
  python scripts/apply-ansible-services.py --mode parallel --log-dir /workspace/.tmp/gate4-pass1'
# run a second identical pass with a different log dir, then inspect recaps:
grep -hE "changed=[1-9]" .tmp/gate4-pass1/*.log .tmp/gate4-pass2/*.log
```

Pass: both passes succeed; nonzero changes are limited to the recorded
exceptions above. Also confirm connectivity:

```bash
VALUES_SITE=dev docker compose run --rm infra python scripts/check-direct-service-ansible.py connectivity
```

## Gate 5 — Service-state backup and restore

```bash
VALUES_SITE=dev scripts/service-state.sh backup all
# then, per enabled stateful service:
VALUES_SITE=dev scripts/service-state.sh restore-if-present <service>
```

Pass: every enabled stateful service yields a checksummed archive, restores
with an automatic pre-restore safety archive, and reports zero failures.
Re-run Gate 4 connectivity and one convergence pass afterward.

## Gate 6 — Infrastructure recovery rehearsal

Run inside one tooling container session (staging directories are
container-local; copy finished snapshots into private values afterward):

```bash
VALUES_SITE=dev INFRA_COPY_SSH_KEYS=true INFRA_SSH_IDENTITY_SOURCE=sops \
  scripts/run-infra.sh bash -euo pipefail -c '
  source scripts/site-context.sh
  rm -rf /tmp/recovery && mkdir -p /tmp/recovery/audit /tmp/recovery/state
  chmod 700 /tmp/recovery/audit /tmp/recovery/state
  # audit journal: create, verify, restore
  SNAP=$(python scripts/hermes-audit-snapshot.py create \
    --journal /workspace/.tmp/hermes-operator-audit.jsonl \
    --backup-dir /tmp/recovery/audit | sed "s/audit snapshot created: //")
  python scripts/hermes-audit-snapshot.py verify --snapshot "/tmp/recovery/audit/$SNAP"
  chmod u+w /workspace/.tmp/hermes-operator-audit.jsonl
  python scripts/hermes-audit-snapshot.py restore \
    --snapshot "/tmp/recovery/audit/$SNAP" \
    --journal /workspace/.tmp/hermes-operator-audit.jsonl --replace-existing
  # OpenTofu state: create, verify, restore through the site lock
  python scripts/state-snapshot.py create \
    --state /workspace/values/sites/dev/terraform.tfstate \
    --backup-dir /tmp/recovery/state
  SSNAP="/tmp/recovery/state/$(ls -t /tmp/recovery/state | head -1)"
  python scripts/state-snapshot.py verify --snapshot "$SSNAP"
  chmod u+w /workspace/values/sites/dev/terraform.tfstate
  python scripts/state-snapshot.py restore \
    --snapshot "$SSNAP" --state /workspace/values/sites/dev/terraform.tfstate --replace-existing
  cp -a "/tmp/recovery/audit/$SNAP" "$SSNAP" /workspace/values/sites/dev/state-backups/
  python scripts/verify-projections.py \
    --site-file /workspace/values/sites/dev/site.yaml \
    --generated-dir /workspace/values/sites/dev/generated'
```

Pass: audit chain verifies with no unresolved correlations; state snapshot
verifies and restores through the site lock; canonical projections verify
afterward. Finish with a fresh Gate 3 plan (zero-change) and Gate 4
connectivity.

## Gate 7 — Hermes read-only bridge

```bash
docker compose run --rm -e VALUES_SITE=dev infra python scripts/hermes-operator.py status
docker compose run --rm -e VALUES_SITE=dev infra python scripts/hermes-operator.py audit-verify
```

Pass: status reports the zero-change, non-destructive saved plan; audit
verification succeeds.

## Evidence recording

After all gates pass, update `.hermes/reconciliation/acceptance-matrix.md` and
its JSON companion: one row per gate at the exact commit, with procedure,
result, date, and stated boundary (development-only; cite the findings note
for the accepted imperative-bootstrap exceptions). Register any new tracked
markdown in `docs/documentation-inventory.json`. Commit the private values
repo's source-of-truth files so validated state matches committed state.
