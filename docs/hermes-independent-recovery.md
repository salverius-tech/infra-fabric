# Hermes-independent controller recovery

Hermes is an operator surface, not a recovery dependency. If Hermes is unavailable,
a trusted operator must recover the canonical controller workflow directly and restore
Hermes last.

This is a public-safe procedure. It does not authorize provider contact, infrastructure
mutation, secret editing, state replacement, host-key acceptance, or service restore.
Each mutating step requires its own reviewed plan and explicit approval.

## Recovery order

1. **Establish a trusted controller.** Use a known-good administrative workstation or
   replacement controller. Confirm repository identity, branch, remote, tooling image,
   clock, file permissions, and the single-controller/single-writer boundary. Stop all
   other mutation-capable controllers before touching state.
2. **Restore public source.** Clone or restore the approved `infra-fabric` revision.
   Verify the expected remote and commit before using any workflow. Do not restore
   generated projections, plans, state, credentials, or host trust from public source.
3. **Restore private site inputs.** Obtain the selected site's `site.yaml`, `.sops.yaml`,
   and `secrets.sops.yaml` from the protected private repository. Obtain the site and
   recovery age identities through the approved protected key-management path. Inspect
   only metadata and logical paths until the policy, recipient set, and permissions are
   verified.
4. **Restore audit continuity.** Recover the private Hermes operator journal and its
   protected backup, if available. Run `scripts/hermes-operator.py audit-verify --json`
   with `HERMES_OPERATOR_AUDIT_PATH` pointed at that journal. A malformed or broken
   hash chain is a stop condition; retain it for investigation and use a separately
   protected emergency journal rather than overwriting history.
5. **Restore state and trust metadata.** Recover the private OpenTofu state snapshot,
   execution snapshots, service-state archives, known-hosts material, and controller
   identities separately. Verify checksums, site identity, permissions, and scope.
   Never accept a changed guest host key from scanning alone; verify it through the
   approved Proxmox or guest-side evidence path.
6. **Run non-mutating checks.** Build the pinned tooling image, run public validation,
   validate the selected canonical site, verify projections and Ansible inventory, and
   inspect the private bundle's logical-path readiness without printing values.
7. **Re-establish infrastructure control.** Only after the preceding checks pass, obtain
   a fresh provider-backed plan for the approved site. Review resource scope, stateful
   changes, replacements, destroys, host identities, and rollback evidence. Apply only
   through the canonical wrapper after separate approval.
8. **Converge services and recover Hermes last.** Verify direct-access readiness first,
   then restore or converge stateful services in dependency order. Restore Hermes only
   after the controller workflow, audit continuity, repository identities, host trust,
   and required service dependencies are operational. Verify the Hermes operator journal
   again after recovery.

## Stop conditions

Stop and escalate if any of the following occurs:

- the controller, repository, selected site, or state identity cannot be established;
- the private SOPS policy or recipient metadata does not match the selected site;
- required logical secret paths are absent or empty;
- the audit journal is malformed, tampered, or unavailable without a protected backup;
- state checksum, scope, or site identity verification fails;
- a host key changes without independent guest or Proxmox evidence;
- a provider plan differs from the reviewed recovery scope; or
- recovery would require bypassing a wrapper, lock, saved-plan check, approval gate, or
  strict host-key policy.

## Evidence record

Record each phase separately and keep evidence value-free:

- controller and repository identity verification;
- private policy, recipient, and logical-path status;
- audit journal verification result and backup identifier;
- state, service-archive, and host-trust verification results;
- public validation and projection/inventory results;
- provider plan summary and approval identifier;
- direct-access, service-health, restore, rollback, and Hermes recovery results.

A successful public validation or plan is not evidence of live health, restore success,
rollback readiness, or complete controller recovery.
