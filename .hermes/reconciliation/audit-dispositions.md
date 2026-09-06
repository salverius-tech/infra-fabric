# Original audit finding dispositions

All 38 original findings retain package, disposition, and current production/verification citations. External evidence remains in the acceptance matrix.

| Finding | Package | Disposition | Audit source | Evidence |
| --- | --- | --- | --- | --- |
| H1 | S1 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:7` | production: `scripts/tfplan-metadata.py:1-120`; verification: `tests/test_tfplan_metadata.py:1-140` |
| H2 | O3 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:8` | production: `infra/ansible/tasks/reviewed-artifact-cache.yml:1-62`; verification: `tests/test_artifact_projection.py:1-130` |
| H3 | O2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:9` | production: `scripts/apply-ansible-services.py:84-155`; verification: `tests/test_apply_ansible_services.py:20-70` |
| H4 | R1 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:10` | production: `scripts/service-state.sh:1-80`; verification: `tests/test_service_state.py:1-80` |
| H5 | R2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:11` | production: `scripts/workspace-preflight.py:1-80`; verification: `tests/test_workspace_preflight.py:1-100` |
| H6 | S1 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:12` | production: `scripts/tfplan-metadata.py:1-120`; verification: `tests/test_tfplan_metadata.py:1-140` |
| H7 | S2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:13` | production: `scripts/secret_delivery.py:1-120`; verification: `tests/test_secret_delivery.py:1-210` |
| H8 | S3 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:14` | production: `scripts/execution-snapshot.py:1-120`; verification: `tests/test_tfplan_metadata.py:180-300` |
| H9 | O1 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:15` | production: `infra/ansible/roles/hermes_control/tasks/main.yml:1-120`; verification: `tests/test_hermes_control_role.py:1-130` |
| H10 | S2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:16` | production: `scripts/secret_delivery.py:1-120`; verification: `tests/test_secret_delivery.py:1-210` |
| H11 | O3 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:17` | production: `infra/ansible/tasks/reviewed-artifact-cache.yml:1-62`; verification: `tests/test_artifact_projection.py:1-130` |
| H12 | S3 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:18` | production: `scripts/execution-snapshot.py:1-120`; verification: `tests/test_tfplan_metadata.py:180-300` |
| M1 | O2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:19` | production: `scripts/apply-ansible-services.py:84-155`; verification: `tests/test_apply_ansible_services.py:20-70` |
| M2 | R2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:20` | production: `scripts/workspace-preflight.py:1-80`; verification: `tests/test_workspace_preflight.py:1-100` |
| M3 | S3 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:21` | production: `scripts/execution-snapshot.py:1-120`; verification: `tests/test_tfplan_metadata.py:180-300` |
| M4 | Q1 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:22` | production: `scripts/check-direct-service-ansible.py:1-120`; verification: `tests/test_ansible_convergence_contract.py:1-100` |
| M5 | Q1 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:23` | production: `scripts/check-direct-service-ansible.py:1-120`; verification: `tests/test_ansible_convergence_contract.py:1-100` |
| M6 | Q2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:24` | production: `infra/opentofu/services.tf:1-170`; verification: `tests/test_canonical_service_authority.py:1-180` |
| M7 | Q2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:25` | production: `infra/opentofu/services.tf:1-170`; verification: `tests/test_canonical_service_authority.py:1-180` |
| M8 | O3 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:26` | production: `infra/ansible/tasks/reviewed-artifact-cache.yml:1-62`; verification: `tests/test_artifact_projection.py:1-130` |
| M9 | Q3 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:27` | production: `scripts/update.py:1-100`; verification: `tests/test_update.py:1-230` |
| M10 | S2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:28` | production: `scripts/secret_delivery.py:1-120`; verification: `tests/test_secret_delivery.py:1-210` |
| M11 | S2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:29` | production: `scripts/secret_delivery.py:1-120`; verification: `tests/test_secret_delivery.py:1-210` |
| M12 | R1 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:30` | production: `scripts/service-state.sh:1-80`; verification: `tests/test_service_state.py:1-80` |
| M13 | S2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:31` | production: `scripts/secret_delivery.py:1-120`; verification: `tests/test_secret_delivery.py:1-210` |
| M14 | Q1 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:32` | production: `scripts/check-direct-service-ansible.py:1-120`; verification: `tests/test_ansible_convergence_contract.py:1-100` |
| M15 | S1 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:33` | production: `scripts/tfplan-metadata.py:1-120`; verification: `tests/test_tfplan_metadata.py:1-140` |
| M16 | S2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:34` | production: `scripts/secret_delivery.py:1-120`; verification: `tests/test_secret_delivery.py:1-210` |
| M17 | CI | implemented-static | `.hermes/reconciliation/audit-dispositions.md:35` | production: `tools/Dockerfile:1-60`; verification: `tests/test_phase7_tooling_contract.py:1-80` |
| M18 | O1 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:36` | production: `infra/ansible/roles/hermes_control/tasks/main.yml:1-120`; verification: `tests/test_hermes_control_role.py:1-130` |
| L1 | R1 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:37` | production: `scripts/service-state.sh:1-80`; verification: `tests/test_service_state.py:1-80` |
| L2 | R2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:38` | production: `scripts/workspace-preflight.py:1-80`; verification: `tests/test_workspace_preflight.py:1-100` |
| L3 | O3 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:39` | production: `infra/ansible/tasks/reviewed-artifact-cache.yml:1-62`; verification: `tests/test_artifact_projection.py:1-130` |
| L4 | CI | implemented-static | `.hermes/reconciliation/audit-dispositions.md:40` | production: `tools/Dockerfile:1-60`; verification: `tests/test_phase7_tooling_contract.py:1-80` |
| L5 | R2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:41` | production: `scripts/workspace-preflight.py:1-80`; verification: `tests/test_workspace_preflight.py:1-100` |
| L6 | DOCS | implemented-static | `.hermes/reconciliation/audit-dispositions.md:42` | production: `docs/service-operations.md:1-70`; verification: `tests/test_documentation_contract.py:39-245` |
| L7 | Q2 | implemented-static | `.hermes/reconciliation/audit-dispositions.md:43` | production: `infra/opentofu/services.tf:1-170`; verification: `tests/test_canonical_service_authority.py:1-180` |
| L8 | DOCS | implemented-static | `.hermes/reconciliation/audit-dispositions.md:44` | production: `docs/service-operations.md:1-70`; verification: `tests/test_documentation_contract.py:39-245` |
