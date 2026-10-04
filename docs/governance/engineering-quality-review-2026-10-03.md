# Engineering quality review and remediation backlog

Review date: 2026-10-03
Reviewed commit: `685b7da` (chore: retire legacy secret migration tooling)
Classification: working design

This document records a repository-wide engineering review and the resulting
remediation backlog. It is an **input to implementation planning**, not an
acceptance record. Nothing here is provider-backed, live, recovery, or
production evidence; those remain exclusive to
[the acceptance matrix](acceptance-matrix.md). Source-completion authority
remains [package-completion.md](package-completion.md).

No infrastructure mutation, plan, apply, or secret operation was performed to
produce this review.

## 1. Summary

The repository's security architecture is strong and internally consistent. The
findings below are concentrated in three areas:

1. **Verification depth** — the checks on the checks are thinner than the code
   they protect.
2. **Dev feedback-loop integrity** — the test suite cannot be run to a clean
   signal on a non-Linux operator workstation.
3. **Process and documentation hygiene** — orphan code, duplicated templates,
   and governance citations that imply precision they do not have.

Observed scale: 135 Python files, 28 shell scripts, 82 test modules /
696 tests / 17.2k test lines, ~4,753 documentation lines, ~49k tracked source
lines.

## 2. Confirmed strengths that must not regress

These were specifically examined and found sound. Refactors that simplify or
"clean up" these paths are net-negative changes.

| Area | Evidence |
| --- | --- |
| Filesystem atomicity | `scripts/atomic_output.py` uses `renameat2(RENAME_EXCHANGE)` through a raw `ctypes` syscall; all operations are descriptor-relative |
| TOCTOU defence | `scripts/private_files.py` and `scripts/execution-snapshot.py` hold descriptors and never re-resolve paths; identity re-verified via `st_dev`/`st_ino` around the swap |
| State safety | Saved-plan metadata binding; execution snapshot verified three times in `scripts/apply-infra.sh` (pre-mutation, immediately before `tofu apply`, post-mutation); plan artifacts removed by EXIT trap |
| Secret hygiene | `scripts/secret_provider.py` never echoes SOPS stdout/stderr; `SOPS_AGE_KEY` stripped from the child environment; recipients validated against site-local policy; placeholder recipient explicitly rejected |
| Supply chain | Digest-pinned base image, SHA256-pinned binaries, `--require-hashes` pip locks; `infra/ansible/tasks/reviewed-artifact-cache.yml` is an out-of-band read-only cache with checksum assertion; images pinned `repository@sha256:digest` |
| Provider boundary | No `local-exec` for service configuration; DNS synchronization stays in Ansible |
| Test intent | Adversarial tests such as `test_verify_rejects_valid_attacker_snapshot_after_ancestor_is_replaced`, not smoke tests |

## 3. Findings

Severity: **P1** high value / medium effort, **P2** high value / low effort,
**P3** moderate, **P4** minor.

---

### P1-1 Static analysis is nominal rather than substantive

**Location:** `scripts/validate-public.sh:114-116`

```bash
black --check --diff "${quality_files[@]}"   # 4 of ~90 Python files
ruff check --select=E9,F63,F7,F82 ...        # syntax + a few pyflakes names only
mypy --follow-imports=skip ... scripts/canonical_values.py scripts/service_catalog.py
```

`tools/python-format-files.txt` self-describes as a "ratcheted" list containing
only four test files. The selected ruff rules detect syntax errors and undefined
names; they include **no security rules, no unused imports, no complexity, and
no bugbear checks**. For a repository whose blast radius is production
infrastructure state, the current gate gives an appearance of coverage that it
does not provide.

**Recommendation**

1. Expand ruff to `E,F,W,I,B,UP,S,PERF,C4,SIM`. The `S` (bandit) family in
   particular should be triaged against `scripts/update.py` (outbound
   `urllib` calls) and `scripts/secret_provider.py` (subprocess invocation).
2. Replace the ratchet list with a **compatibility floor**: run `black --check`
   across all files, allowing failure only via a machine-readable baseline file
   that must shrink, or explicit per-file opt-out markers.
3. Run mypy across all of `scripts/` under `--strict`, staged incrementally and
   beginning with the mutation-critical modules listed in P2-2.
4. Enable ruff `T20` so an accidental `print` of a secret value fails at lint
   time rather than at review time.

**Acceptance:** ruff runs the expanded rule set in `scripts/validate-public.sh`;
`black --check` covers `scripts/` and `tests/` in full; any residual baseline is
a committed, size-tracked artifact with a documented ratchet rule.

---

### P1-2 The test suite cannot reach a clean signal off Linux

**Location:** `scripts/site_lock.py:7`, `scripts/atomic_output.py:23-51`

A native `python -m unittest discover -s tests` run on a Windows host produced:

```
Ran 696 tests — FAILED (failures=34, errors=71, skipped=44)
```

Root causes are hard POSIX dependencies with no test guard:

- `import fcntl` at module import time (`scripts/site_lock.py:7`) — collection
  failure for `test_state_snapshot`, `test_site_lock`, `test_private_files`
- `renameat2` syscall numbers `{"x86_64": 316, "aarch64": 276}`
  (`scripts/atomic_output.py:23-51`) — Linux-only, fails the ~30 atomicity
  tests

Existing guards cover only *optional* capabilities
(`skipUnless(hasattr(os, "symlink"))`) and *absent* tooling
(`TOFU_RUNTIME_AVAILABLE`). Nothing covers the POSIX baseline.

The consequence is behavioural rather than cosmetic: a developer on the wrong
host sees roughly 15% red and learns to discount the suite, which erodes the
value of the genuinely strong adversarial tests described in section 2.

**Recommendation**

1. Introduce a shared `tests/_posix.py` exposing `requires_posix_fds`, and
   apply `unittest.skipUnless` at **module level** to `test_state_snapshot`,
   `test_site_lock`, `test_private_files`, `test_execution_snapshot`, and the
   atomic-output tests.
2. Add `tests/README.md` stating the suite is POSIX-only and must be run through
   `just test`, which executes inside the pinned tooling container.
3. Add a `just test-local` recipe that runs the portable subset and reports the
   skipped count explicitly, so a non-Linux developer gets a clean, meaningful,
   honest signal.

**Acceptance:** the suite reports zero failures on a non-POSIX host, with skips
attributable to named platform requirements rather than appearing as breakage.

---

### P2-1 `justfile` inline shell is unlinted, untested, and unreadable

**Location:** `justfile:72` (`edit-secrets`, a single 1,290-character shell
line), `justfile:33` (`ssh-initialize`)

`shellcheck` in `scripts/validate-public.sh` covers only `scripts/*.sh`, and the
`bash -n` tests (`tests/test_operational_cutover.py:53`,
`tests/test_plan_projection_lifecycle.py:104`) also cover only `scripts/`.

This is the highest-risk code on the operator surface — it resolves SOPS policy
paths, performs age-key discovery, and selects the container transport fallback
— and it has **no automated checking whatsoever**.

**Recommendation**

1. Extract to `scripts/edit-secrets.sh` and `scripts/ssh-initialize.sh`. The
   recipes become single lines each, immediately gaining shellcheck coverage, a
   `bash -n` target, and a unit-testable seam.
2. Deduplicate the site-identifier idiom, which appears verbatim twice:
   `site_arg="{{SITE}}"; site="${site_arg#SITE=}"`. Accept `VALUES_SITE`
   uniformly and delegate parsing to `scripts/site-context.sh`.
3. Add a contract test asserting that every `justfile` recipe delegates to a
   `scripts/*.sh` file, preventing regression of this pattern.

**Verified non-issue:** the
`[[ -n "${sops_bin}" ]] || [[ -x "${HOME}/.local/bin/sops" ]] && sops_bin=...`
chain at `justfile:72` was executed under `set -euo pipefail` and does correctly
fall through to the container fallback when no local `sops` exists. It is not a
latent bug and must not be "fixed" as one.

**Acceptance:** no `justfile` recipe contains an inline shell program longer than
a single command; `shellcheck scripts/*.sh` covers the extracted logic.

---

### P2-2 The coverage gate is a single aggregate number

**Location:** `scripts/validate-public.sh:129` — `coverage report --fail-under=70`

One global threshold lets well-tested modules subsidize untested ones. This is
the wrong shape of gate for a repository whose highest-severity defect classes
are filesystem races and secret exposure, both of which live in a small number
of modules.

**Recommendation:** add per-module floors for the modules where a regression is
unrecoverable or silent:

- `scripts/atomic_output.py`
- `scripts/private_files.py`
- `scripts/execution-snapshot.py`
- `scripts/tfplan-metadata.py`
- `scripts/secret_provider.py`
- `scripts/site_lock.py`
- `scripts/canonical-provider-env.py`

**Acceptance:** the aggregate floor is retained; an additional stricter floor
applies to the seven modules above.

---

### P2-3 CI is a single serial job

**Location:** `.github/workflows/validate.yml`

One job performs the tooling image build, then tofu init/validate/fmt, tflint,
shellcheck, black/ruff/mypy, contract checks, the **entire 696-test suite**, and
Ansible syntax-check plus lint — all serially. Expect well over ten minutes to
first signal.

The `supply-chain-evidence` job (trivy + SBOM) is gated on
`github.event_name == 'schedule' || workflow_dispatch`, so dependency scanning
never runs on pull requests.

**Recommendation**

1. Split into a `unit` job (test suite plus ruff/mypy, reusing a cached image)
   and a `full` job (tofu, tflint, shellcheck, ansible), with `full` depending on
   `unit`. Fast failure should surface in roughly two minutes.
2. Move the trivy **fs** scan of `tools/` — which covers the hash-locked
   dependency set and needs no image build — into `pull_request`. Keep the image
   scan and SBOM generation scheduled, since they require `--no-cache`.

**Acceptance:** a failing unit test fails the run without waiting for the
tooling image build or Ansible lint; a vulnerable hash-locked dependency fails a
pull request.

---

### P2-4 Tests assert on `justfile` source text

**Location:** `tests/test_operational_cutover.py:74`,
`tests/test_plan_projection_lifecycle.py:17-18`

```python
self.assertIn("rehearse-development-rollback approval=\"\":", justfile)
setup_recipe = justfile.split("# Initialize the selected canonical site's bootstrap SSH identity", 1)[0]
```

These couple tests to `justfile` formatting. Reformatting a recipe breaks the
tests; changing a recipe's behaviour does not.

**Recommendation:** parse `just --dump` (or evaluate via `just --evaluate`) and
assert on recipe names, parameters, and dependencies rather than on substrings
of the recipe file.

---

### P3-1 Two scripts are orphaned

Zero references in code, documentation, tests, or the `justfile`:

- `scripts/compare-plans.py` — superseded by `scripts/report-plan-equivalence.py`
  and `scripts/plan_equivalence.py`
- `scripts/hermes-password-hash.py` — a legitimate operator tool that is not
  surfaced in any runbook

**Recommendation:** delete `scripts/compare-plans.py`; document
`scripts/hermes-password-hash.py` in `docs/hermes-control-operations.md` or
remove it.

Note: `scripts/render-site-template.py` and the `*_equivalence` /
`*_snapshot` modules were checked and are genuinely referenced.

---

### P3-2 Duplicated Caddy templates have already diverged

**Location:** `infra/ansible/roles/*/templates/`

```
caddy-override.conf.j2  ec75b50d  byte-identical: caddy_proxy, forgejo, hermes, infisical
caddy.env.j2            ee7f0aae  byte-identical: all five roles including onramp_host
caddy-override.conf.j2  e099058a  onramp_host  <- already forked
```

Byte-identical copies that have already drifted once are an abstraction waiting
to be extracted.

**Recommendation:** move `caddy.env.j2` and `caddy-override.conf.j2` into
`roles/caddy_proxy/files/` (or a shared `lookup('template', ...)`) and have
service roles consume them via `include_role: caddy_proxy`.

**Acceptance:** no two roles ship separate copies of these files.

---

### P3-3 Oversized Ansible roles

**Location:** `infra/ansible/roles/hermes/tasks/main.yml` (872 lines),
`forgejo/tasks/main.yml` (615), `sssf/tasks/main.yml` (605),
`technitium/tasks/main.yml` (543)

The repository already uses a better decomposition elsewhere:
`hermes/tasks/bootstrap-state.yml`, `hermes/tasks/managed-runtime.yml`,
`technitium/tasks/health.yml`.

**Recommendation:** apply that split consistently as
`preflight.yml` / `install.yml` / `configure.yml` / `verify.yml`, which also
yields natural tag boundaries for the convergence checker in
`scripts/check-direct-service-ansible.py`.

---

### P3-4 `require_canonical_authority()` is an identity function

**Location:** `scripts/site-context.sh:24-27`

```bash
require_canonical_authority() {
  local values_path
  values_path="$(site_values_dir)" || return
  require_site_context
}
```

The local is unused and the body is equivalent to `require_site_context`, yet
it has eight call sites: `scripts/apply-infra.sh:6`,
`scripts/plan-infra.sh:6`, `scripts/teardown-infra.sh:6`,
`scripts/validate-values.sh:6`, `scripts/service-state.sh:191`, `:218`, `:235`,
`justfile:72`, `justfile:82`.

This is a vestige of the retired legacy-values model. A reader currently cannot
determine whether it enforces anything.

**Recommendation:** either restore its meaning (for example, explicitly
rejecting non-canonical `site.json` / `site.yml` layouts) or delete it and its
eight call sites.

---

### P3-5 Governance evidence carries false precision

**Location:** `docs/governance/audit-dispositions.md`,
`docs/governance/audit-dispositions.json`

All 38 findings are mapped to coarse, frequently identical ranges:

| Findings | Shared citation |
| --- | --- |
| H1, H6, H15 | `scripts/tfplan-metadata.py:1-120` |
| H7, H10, M10, M11, M13, M16 | `scripts/secret_delivery.py:1-120` |
| H4, R1 | `scripts/service-state.sh:1-80` |

Six findings pointing at "lines 1-120" of a 553-line file is a placeholder
formatted as evidence. It gives false assurance that fixes are traceable.

**Recommendation:** cite the specific function or test name
(`tfplan-metadata.py::classify_destructive_changes`), or collapse the `.md` and
`.json` pair into one summary table that points at test identifiers.

---

### P3-6 Missing standard repository hygiene files

Absent: `LICENSE`, `CONTRIBUTING.md`, `CODEOWNERS`, `SECURITY.md`,
`.editorconfig`.

Because `AGENTS.md` and `docs/governance/` are this repository's governance
model, the absence of `CODEOWNERS` is the material gap — protection currently
depends on individual discipline rather than repository configuration.

**Recommendation:** add `CODEOWNERS` covering `tools/Dockerfile`,
`tools/*.lock`, `scripts/site-context.sh`, `scripts/apply-infra.sh`, and
`docs/governance/**`; add `SECURITY.md` describing private disclosure (this
repository handles credentials by design); add `.editorconfig` for LF, UTF-8,
and two-space indentation consistent with `.gitattributes`.

---

### P3-7 Nothing keeps the pinned versions fresh

The pin discipline is excellent: checksum-pinned `ARG`s in `tools/Dockerfile`,
`tools/requirements.lock`, `infra/opentofu/.terraform.lock.hcl`, and
`scripts/update.py` with a 48-hour safety hold. However, nothing schedules
`just update`. Pinned digests silently age into known-CVE territory, and the
weekly CI job only scans — it never proposes.

**Recommendation:** add a weekly workflow running `just update --dry-run` and
opening (or commenting on) a pin-bump pull request. This converts an existing,
well-designed mechanism from "documented" to "operating", consistent with the
policy in [service-update-policy.md](../service-update-policy.md).

---

### P4-1 `compose.yaml` mounts `${HOME}/.ssh` unconditionally

**Location:** `compose.yaml:12`

```yaml
- ${HOST_SSH_DIR:-${HOME}/.ssh}:/ssh-ro:ro
```

If `HOME` is unset (systemd units, CI, some `sudo` contexts), Docker creates an
empty directory mount and the operator gets a confusing "no key" failure at
apply time rather than a clear setup error. Contrast
`tools/docker-entrypoint.sh:66-77`, which does fail closed on a bad
`INFRA_SSH_IDENTITY_FILE`.

**Recommendation:** fail closed in `just setup` and `scripts/run-infra.sh` when
neither `HOST_SSH_DIR` nor `HOME` resolves to a readable directory containing
the expected keys.

## 4. Suggested implementation order

**Immediate — high value, low effort**

1. P1-1 ruff security and bugbear rules, triaged
2. P1-2 POSIX test guards
3. P2-2 per-module coverage floors
4. P2-1 extract `edit-secrets` and `ssh-initialize` into linted scripts

**Next cycle**

5. P2-3 split CI into fast and long jobs; enable pull-request dependency scan
6. P3-1 orphan cleanup, P3-2 Caddy template de-duplication, P3-3 role splitting
7. P3-6 `CODEOWNERS`, `SECURITY.md`, `.editorconfig`
8. P3-4 resolve `require_canonical_authority`
9. P2-4 replace `justfile` text assertions with behavioural tests

**Ongoing**

10. P3-7 weekly `just update --dry-run` workflow
11. P3-5 rewrite governance citations to real symbols, or collapse the
    duplicate JSON/Markdown pair

## 5. Verification limits

Recorded so these findings are not over-read:

- `just validate` and full container validation were **not** run; the Docker
  daemon was unavailable on the review host. All findings derive from static
  reading plus a native, partial test run.
- `just plan` and `just apply` were **not** exercised. They require the private
  `values/` site tree and a SOPS age identity. No infrastructure mutation was
  attempted.
- The actual current coverage percentage was **not** measured; `coverage` is not
  installed natively.
- Findings describe the repository at commit `685b7da`. Pin ages, CI behaviour,
  and file locations should be re-confirmed before each remediation item is
  implemented.