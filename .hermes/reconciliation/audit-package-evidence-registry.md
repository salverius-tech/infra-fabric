# Audit finding package evidence registry

Every audit finding has a package and final disposition. `implemented-static` rows cite a current production path and focused verification; provider, live, and recovery remain blocked-external.

| Finding | Package | Disposition | Ledger record | Source claim | Package evidence |
| --- | --- | --- | --- | --- | --- |
| H1 | `S1` | `implemented-static` | `h1` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:35` | production: scripts/tfplan-metadata.py:1-120; verification: tests/test_tfplan_metadata.py:1-140 |
| H2 | `O3` | `implemented-static` | `h2` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:57` | production: infra/ansible/tasks/reviewed-artifact-cache.yml:1-62; verification: tests/test_artifact_projection.py:1-130 |
| H3 | `O2` | `implemented-static` | `h3` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:75` | production: scripts/apply-ansible-services.py:84-155; verification: tests/test_apply_ansible_services.py:20-70 |
| H4 | `R1` | `implemented-static` | `h4` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:92` | production: scripts/service-state.sh:1-80; verification: tests/test_service_state.py:1-80 |
| H5 | `R2` | `implemented-static` | `h5` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:110` | production: scripts/workspace-preflight.py:1-80; verification: tests/test_workspace_preflight.py:1-100 |
| H6 | `S1` | `implemented-static` | `h6` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:127` | production: scripts/tfplan-metadata.py:1-120; verification: tests/test_tfplan_metadata.py:1-140 |
| H7 | `S2` | `implemented-static` | `h7` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:143` | production: scripts/secret_delivery.py:1-120; verification: tests/test_secret_delivery.py:1-210 |
| H8 | `S3` | `implemented-static` | `h8` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:158` | production: scripts/execution-snapshot.py:1-120; verification: tests/test_tfplan_metadata.py:180-300 |
| H9 | `O1` | `implemented-static` | `h9` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:174` | production: infra/ansible/roles/hermes_control/tasks/main.yml:1-120; verification: tests/test_hermes_control_role.py:1-130 |
| H10 | `S2` | `implemented-static` | `h10` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:189` | production: scripts/secret_delivery.py:1-120; verification: tests/test_secret_delivery.py:1-210 |
| H11 | `O3` | `implemented-static` | `h11` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:205` | production: infra/ansible/tasks/reviewed-artifact-cache.yml:1-62; verification: tests/test_artifact_projection.py:1-130 |
| H12 | `S3` | `implemented-static` | `h12` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:222` | production: scripts/execution-snapshot.py:1-120; verification: tests/test_tfplan_metadata.py:180-300 |
| M1 | `O2` | `implemented-static` | `m1` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:240` | production: scripts/apply-ansible-services.py:84-155; verification: tests/test_apply_ansible_services.py:20-70 |
| M2 | `R2` | `implemented-static` | `m2` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:257` | production: scripts/workspace-preflight.py:1-80; verification: tests/test_workspace_preflight.py:1-100 |
| M3 | `S3` | `implemented-static` | `m3` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:274` | production: scripts/execution-snapshot.py:1-120; verification: tests/test_tfplan_metadata.py:180-300 |
| M4 | `Q1` | `implemented-static` | `m4` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:290` | production: scripts/check-direct-service-ansible.py:1-120; verification: tests/test_ansible_convergence_contract.py:1-100 |
| M5 | `Q1` | `implemented-static` | `m5` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:306` | production: scripts/check-direct-service-ansible.py:1-120; verification: tests/test_ansible_convergence_contract.py:1-100 |
| M6 | `Q2` | `implemented-static` | `m6` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:322` | production: infra/opentofu/services.tf:1-170; verification: tests/test_canonical_mapping_inventory.py:1-100 |
| M7 | `Q2` | `implemented-static` | `m7` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:338` | production: infra/opentofu/services.tf:1-170; verification: tests/test_canonical_mapping_inventory.py:1-100 |
| M8 | `O3` | `implemented-static` | `m8` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:354` | production: infra/ansible/tasks/reviewed-artifact-cache.yml:1-62; verification: tests/test_artifact_projection.py:1-130 |
| M9 | `Q3` | `implemented-static` | `m9` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:371` | production: scripts/update.py:1-100; verification: tests/test_update.py:1-230 |
| M10 | `S2` | `implemented-static` | `m10` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:383` | production: scripts/secret_delivery.py:1-120; verification: tests/test_secret_delivery.py:1-210 |
| M11 | `S2` | `implemented-static` | `m11` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:394` | production: scripts/secret_delivery.py:1-120; verification: tests/test_secret_delivery.py:1-210 |
| M12 | `R1` | `implemented-static` | `m12` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:405` | production: scripts/service-state.sh:1-80; verification: tests/test_service_state.py:1-80 |
| M13 | `S2` | `implemented-static` | `m13` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:416` | production: scripts/secret_delivery.py:1-120; verification: tests/test_secret_delivery.py:1-210 |
| M14 | `Q1` | `implemented-static` | `m14` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:427` | production: scripts/check-direct-service-ansible.py:1-120; verification: tests/test_ansible_convergence_contract.py:1-100 |
| M15 | `S1` | `implemented-static` | `m15` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:438` | production: scripts/tfplan-metadata.py:1-120; verification: tests/test_tfplan_metadata.py:1-140 |
| M16 | `S2` | `implemented-static` | `m16` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:449` | production: scripts/secret_delivery.py:1-120; verification: tests/test_secret_delivery.py:1-210 |
| M17 | `CI` | `implemented-static` | `m17` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:460` | production: tools/Dockerfile:1-60; verification: tests/test_phase7_tooling_contract.py:1-80 |
| M18 | `O1` | `implemented-static` | `m18` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:472` | production: infra/ansible/roles/hermes_control/tasks/main.yml:1-120; verification: tests/test_hermes_control_role.py:1-130 |
| L1 | `R1` | `implemented-static` | `l1` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:485` | production: scripts/service-state.sh:1-80; verification: tests/test_service_state.py:1-80 |
| L2 | `R2` | `implemented-static` | `l2` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:500` | production: scripts/workspace-preflight.py:1-80; verification: tests/test_workspace_preflight.py:1-100 |
| L3 | `O3` | `implemented-static` | `l3` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:515` | production: infra/ansible/tasks/reviewed-artifact-cache.yml:1-62; verification: tests/test_artifact_projection.py:1-130 |
| L4 | `CI` | `implemented-static` | `l4` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:529` | production: tools/Dockerfile:1-60; verification: tests/test_phase7_tooling_contract.py:1-80 |
| L5 | `R2` | `implemented-static` | `l5` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:543` | production: scripts/workspace-preflight.py:1-80; verification: tests/test_workspace_preflight.py:1-100 |
| L6 | `DOCS` | `implemented-static` | `l6` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:547` | production: docs/service-operations.md:1-70; verification: tests/test_documentation_contract.py:39-245 |
| L7 | `Q2` | `implemented-static` | `l7` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:551` | production: infra/opentofu/services.tf:1-170; verification: tests/test_canonical_mapping_inventory.py:1-100 |
| L8 | `DOCS` | `implemented-static` | `l8` | `.hermes/plans/2026-08-04-comprehensive-project-audit.md:555` | production: docs/service-operations.md:1-70; verification: tests/test_documentation_contract.py:39-245 |
