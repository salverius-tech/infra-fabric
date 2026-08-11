# Package source completion

Active authority for source-package completion only. Static repository evidence does not establish provider, live-service, recovery, or production acceptance; lossless per-claim provenance is frozen in Git history.

Frozen lossless provenance: `git show e04aed2ef2f0133368cdd26ed57d9c9ba3b2a548:.hermes/reconciliation/design-implementation-ledger.json` (919 records).

| Package | Title | Source completion | Evidence |
| --- | --- | --- | --- |
| R1 | Canonical service-state recovery correctness | source-complete | production: `scripts/service-state.sh:1-80`; verification: `tests/test_service_state.py:1-80` |
| R2 | Fresh-site validation and scaffold correctness | source-complete | production: `scripts/workspace-preflight.py:1-80`; verification: `tests/test_workspace_preflight.py:1-100` |
| S1 | Canonical service and stateful ownership | source-complete | production: `scripts/tfplan-metadata.py:1-120`; verification: `tests/test_tfplan_metadata.py:1-140` |
| S2 | Unified secret contract and preflight | source-complete | production: `scripts/secret_delivery.py:1-120`; verification: `tests/test_secret_delivery.py:1-210` |
| S3 | Plan/apply/teardown integrity and state protection | source-complete | production: `scripts/execution-snapshot.py:1-120`; verification: `tests/test_tfplan_metadata.py:180-300` |
| O1 | Hermes Control readiness and role contracts | source-complete | production: `infra/ansible/roles/hermes_control/tasks/main.yml:1-120`; verification: `tests/test_hermes_control_role.py:1-130` |
| O2 | Host-aware Ansible scheduling | source-complete | production: `scripts/apply-ansible-services.py:84-155`; verification: `tests/test_apply_ansible_services.py:20-70` |
| O3 | Immutable runtime and image supply chain | source-complete | production: `infra/ansible/tasks/reviewed-artifact-cache.yml:1-62`; verification: `tests/test_artifact_projection.py:1-130` |
| Q1 | Ansible convergence and check mode | source-complete | production: `scripts/check-direct-service-ansible.py:1-120`; verification: `tests/test_ansible_convergence_contract.py:1-100` |
| Q2 | OpenTofu module and projection contracts | source-complete | production: `infra/opentofu/services.tf:1-170`; verification: `tests/test_canonical_mapping_inventory.py:1-100` |
| Q3 | Update workflow parity | source-complete | production: `scripts/update.py:1-100`; verification: `tests/test_update.py:1-230` |
| DOCS | Documentation authority and operations | source-complete | production: `docs/service-operations.md:1-70`; verification: `tests/test_documentation_contract.py:39-245` |
| CI | Tooling, CI, and quality gates | source-complete | production: `tools/Dockerfile:1-60`; verification: `tests/test_phase7_tooling_contract.py:1-80` |

## Source frontier

No incomplete source packages remain. External acceptance is tracked only in the acceptance matrix.
