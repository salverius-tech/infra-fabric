# Bounded legacy recovery-tool inventory

**Status:** Historical retirement record. The legacy compatibility surface was retired on 2026-08-12 after the recorded disposable-development controller/infrastructure recovery rehearsal and authorized removal scope.

This document preserves the former P10-E compatibility boundary and the retirement decision. The normal operator lifecycle is canonical-only. No legacy importer, forensic report, static tfvars/inventory fixture, mapping parser, or forwarding shim remains available.

## Authority and prohibition

Decision D5 originally quarantined bounded forensic discovery/recovery tooling pending a caller inventory and recovery evidence. The development controller/infrastructure recovery rehearsal was completed and recorded on 2026-08-12; the authorized removal scope then retired the implementation as one package.

Do not recreate these tools as a fallback from `setup`, `validate`, `plan`, `apply`, teardown, Ansible orchestration, or runtime service workflows. Canonical selected-site recovery remains the only operator path.

## Retired surface

| Retired artifact family | Replacement / disposition |
| --- | --- | --- | --- |
| `just recover-legacy-values-forensics`, wrapper, and Compose service | Deleted; `tests/test_operational_cutover.py` asserts no entrypoint remains. |
| Root/site migration, discovery, semantic-discovery, remote-discovery, and migration-backup scripts | Deleted with their focused tests; no forwarding aliases remain. |
| `scripts/migrate-secret-bundle.py` | Deleted; canonical encrypted-bundle primitives remain in `scripts/secret_bundle_migration.py`. |
| `scripts/canonical-mapping-inventory.py` and mapping test | Deleted; canonical projections and `tests/test_canonical_service_authority.py` are the active contract. |
| Static `scaffold/terraform.tfvars` and `scaffold/ansible/inventory/local.yml` | Deleted; `scripts/validate-public.sh` renders and verifies an ephemeral canonical public fixture. |

## Retained canonical recovery boundary

`scripts/secret_bundle_migration.py`, `scripts/recover-canonical-secrets.py`, guarded state snapshots, site locking, and selected-site SOPS transport remain. The bounded `recover-canonical-secrets.py` command may read one allow-listed historical dotenv from private Git only when an operator invokes it explicitly; no normal workflow or tracked scaffold parses or authors dotenv/tfvars/static-inventory inputs. These are canonical recovery primitives, not legacy-layout fallback paths.

## Retirement verification

The retirement package rendered a temporary canonical fixture from `scaffold/sites/_template/site.yaml`, verified its projections, exercised OpenTofu and selected Ansible static consumers, and removed the compatibility source/test/entrypoint families. Focused contracts, reconciliation generation/check, public validation, selected-site validation, and whitespace checks are required evidence. Historical plans preserve old references only as provenance; they do not expose a runnable legacy workflow.
