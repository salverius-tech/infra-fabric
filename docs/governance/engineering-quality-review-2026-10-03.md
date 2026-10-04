# Engineering quality review and remediation backlog

Review date: 2026-10-03 (reconducted, second pass)
Reviewed commit: `26b9be9` (branch `chore/engineering-review-remediation`)
First-pass reviewed commit: `685b7da`
Classification: working design

This document records a repository-wide engineering review and the resulting
remediation backlog. It is an **input to implementation planning**, not an
acceptance record. Nothing here is provider-backed, live, recovery, or
production evidence; those remain exclusive to
[the acceptance matrix](acceptance-matrix.md). Source-completion authority
remains [package-completion.md](package-completion.md).

No infrastructure mutation, plan, apply, teardown, or secret write was
performed to produce this review.

## 1. Summary

The repository's security architecture remains strong and internally
consistent. The reconduct confirms every structural finding of the first pass
and adds three new ones, but it also **materially reduces the estimated cost of
two of the largest items** and **downgrades one finding's severity**.

| Change from the first pass | Effect |
| --- | --- |
| Full `just validate` executed against the `dev` site in the pinned tooling container | The quality gate is confirmed working end to end, not merely read |
| Real suite size is 813 tests, not 696 | The first pass under-counted the suite by ~117 tests |
| Aggregate coverage measured at 74% against a 70% floor | The margin is 4 points, not a comfortable one |
| `ruff` expanded rule set measured: 2,592 findings, 386 after excluding policy noise | The gate can be widened substantially without a triage swamp |
| `mypy --strict` across all 46 script modules: 50 errors | The type-checking recommendation is a short task, not a multi-cycle project |
| `black --check` across all 135 files: 116 would be reformatted | Mass formatting is the single largest mechanical cost |
| Whole validation gate runs in ~2m48s, not "well over ten minutes" | The CI-split rationale must be re-based on image build cost, not gate cost |
| The repository already declares Linux `amd64` as a supported platform | P1-2 is a declared-contract enforcement gap, not a portability defect |

Observed scale: 135 Python files (46 in `scripts/`, 4 under
`infra/ansible/scripts/`), 18 shell scripts under `scripts/`, 82 test modules /
813 tests, ~4,753 documentation lines.

## 2. Method and evidence

Commands executed on the review host (Linux 6.8, `sops` 3.13.3, `age` 1.1.1,
Docker 29.8.2, `just` 1.46.0):

| Command | Result |
| --- | --- |
| `VALUES_SITE=dev just validate` | exit 0; all seven stages PASS |
| `just test` equivalent (`coverage run -m unittest discover`) | `Ran 813 tests ... OK` |
| `coverage report` | `TOTAL 7828 2030 74%` |
| `black --check` over all Python files | 116 reformat, 19 unchanged |
| `ruff check --select=E9,F63,F7,F82` (current gate) | `All checks passed!` |
| `ruff check --select=E,F,W,I,B,UP,S,PERF,C4,SIM,T20` | 2,592 findings; 386 with `E501,T201,S101` excluded; 142 auto-fixable |
| `mypy` current gate, all scripts, and `--strict` | clean; 23 errors; 50 errors |
| `docker compose build infra` | cached, 1.9s |
| SOPS branch probe for the `edit-secrets` fallback | both branches behave correctly |

Stage timings from the timed validation run: preflight <1s, opentofu ~3s,
shell ~1s, python-quality ~50s, contracts ~72s (64s of it the test suite),
ansible ~41s.

`just validate` decrypts the selected site's protected values transiently inside
the container as part of secret-set verification. No decrypted value, key, path
to private material, or endpoint was printed or recorded during this review.

## 3. Corrections to the first pass

These are corrections of record. The first pass was produced on a Windows host
without the repository's tooling, and several of its observations were
environment artifacts rather than repository properties.

**C-1 — The suite is 813 tests, and it passes.** The first pass recorded
`Ran 696 tests — FAILED (failures=34, errors=71, skipped=44)`. That count is a
Windows-host artifact: collection errors mean whole modules never contributed
tests. In the pinned container the suite is green. Any remediation sized against
"696 tests, ~15% red" is sized against a number that does not exist.

**C-2 — The native failure mode on Linux is different, and also a real gap.**
A native run on this Linux host yields `Ran 562 tests ... FAILED (errors=18)`,
and all 18 errors are import failures from a missing third-party dependency
(`pydantic`, imported by `scripts/canonical_values.py`). This is not a platform
problem, but it *is* an undocumented one: nothing outside the container declares
the suite's dependency set.

**C-3 — P1-2 is a declared-contract gap, not a portability defect.**
`README.md:27` and `docs/canonical-quick-start.md:7` both state that a Linux
`amd64` host is required and that other architectures are unsupported.
`scripts/atomic_output.py:26` accordingly supports only `x86_64` and `aarch64`.
The repository already declares the constraint the first pass treated as a
surprise. Severity is reduced accordingly; see P1-2.

**C-4 — The CI-split rationale is misstated.** P2-3 claimed the serial job means
"well over ten minutes to first signal". Measured, the entire validation gate is
~2m48s. The real CI cost is the uncached tooling image build, which was not
measured here because the local layer cache was fully warm.

**C-5 — Effort estimates for lint and typing were pessimistic.** See P1-1: the
type-checking work is 50 errors, and the substantive lint work is 386 findings
once line-length, `print`, and test-`assert` policy noise is excluded.

**C-6 — Template digests in P3-2 do not reproduce.** The first pass cited
8-character digests; the byte-identity relationships it described are confirmed,
but the digests themselves are not reproducible and are replaced with full
SHA-256 values.

## 4. Strengths confirmed on this host

Re-verified directly on this pass:

| Area | Evidence |
| --- | --- |
| Secret hygiene in the SOPS subprocess | `scripts/secret_provider.py:97` pops `SOPS_AGE_KEY` from the child environment before invoking SOPS |
| Error hygiene | Every `raise SecretProviderError` site in `scripts/secret_provider.py` carries a path, policy, or availability description; none interpolates secret material |
| Validation gate integrity | `just validate` passes all seven stages against `dev`, including `tofu validate`, `tflint`, `shellcheck`, `ansible-lint` at the `production` profile, and the contract checks |
| Test intent | `813` tests pass in-container; adversarial cases such as `test_verify_rejects_valid_attacker_snapshot_after_ancestor_is_replaced` are present |
| Retirement discipline | `tests/test_operational_cutover.py:78` asserts retired entry points stay deleted, an established pattern for further retirement work |
| Documentation contract | `tests/test_documentation_contract.py` enforces inventory coverage, link resolution, and heading anchors |

Carried forward unverified from the first pass (static reading only, not
re-examined here): filesystem atomicity via `renameat2(RENAME_EXCHANGE)`,
descriptor-relative TOCTOU defence, saved-plan metadata binding and the
three-times snapshot verification in `scripts/apply-infra.sh`, provider boundary
rules, and the supply-chain pinning discipline.

## 5. Findings

Severity: **P1** high value / medium effort, **P2** high value / low effort,
**P3** moderate, **P4** minor. "Size" is the measured remediation cost from this
pass.

---

### P1-1 Static analysis is narrow, and widening it is now cheap

**Location:** `scripts/validate-public.sh:114-116`

```bash
black --check --diff "${quality_files[@]}"   # 4 of 135 Python files
ruff check --select=E9,F63,F7,F82 ...        # syntax + a few pyflakes names
mypy --follow-imports=skip ... scripts/canonical_values.py scripts/service_catalog.py
```

All three line citations are accurate. `tools/python-format-files.txt` contains
exactly four test files and describes itself as a ratchet. The current ruff gate
passes cleanly, so the gate is not broken; it is thin.

**Measured sizing**

| Change | Cost |
| --- | --- |
| `mypy` over all 46 `scripts/` modules, current flags | 23 errors |
| `mypy --strict` over all 46 `scripts/` modules | 50 errors |
| ruff with `E,F,W,I,B,UP,S,PERF,C4,SIM,T20` | 2,592 findings |
| the same, excluding `E501` (1,997), `T201` (145), `S101` (64) | 386 findings, 142 auto-fixable |

The 1,997 `E501` findings are an artefact of running with default settings
against a codebase whose de-facto width is wider: 1,996 lines exceed 88
characters, 960 exceed 100, and 259 exceed 120. `T201` is expected in scripts
and tests where `print` is the interface. `S101` is `assert` in test modules.

**Recommendation**

1. Adopt rules per family with explicit scope, not wholesale. Start with `F401`
   (12), `B` (19), `I001` (71), and `UP` (46), which are mechanical or
   auto-fixable, and triage `S` against `scripts/update.py`,
   `scripts/secret_provider.py`, and `scripts/secret_delivery.py` by hand. Record
   per-rule, per-path ignores as configuration, not as deletions.
2. Set an explicit line-length policy before touching `black` (see P3-8), then
   expand `black --check` with a machine-readable baseline whose size must
   shrink. Do not mass-format as part of a behavioural change.
3. Enable `T20` only for `scripts/`, not `tests/`.
4. Extend `mypy` to all of `scripts/` under the existing flags immediately
   (23 errors), then move the mutation-critical modules to `--strict`.

**Acceptance:** the expanded rule set runs in `scripts/validate-public.sh` with
configuration committed under version control; any baseline is a size-tracked
artifact with a documented ratchet rule.

---

### P1-3 The coverage gate is structurally blind to the modules that matter most

**Location:** `scripts/validate-public.sh:128-129`

```bash
coverage run --source=scripts -m unittest discover -s tests
coverage report --fail-under=70
```

Three distinct blind spots, all confirmed by measurement:

1. **Subprocess-executed scripts report 0% even when heavily tested.**
   `scripts/canonical-render.py` shows 0% coverage while 14 test modules invoke
   it, because `coverage run` does not instrument child processes and no
   subprocess support is configured. At least ten entry points are affected:
   `canonical-render.py`, `canonical-values.py`, `flatten-ansible-vars.py`,
   `hermes-audit-snapshot.py`, `report-plan-equivalence.py`,
   `validate-service-contracts.py`, `render-site-template.py`,
   `compare-plans.py`, `hermes-password-hash.py`, and `public-safety-check.py`
   below 70%.
2. **Ansible-side Python is outside the gate entirely.** `--source=scripts`
   covers only the top-level directory, so the 686 lines across
   `infra/ansible/scripts/*.py` are unmeasured.
3. **The one module that wraps every state mutation has no test at all.**
   `scripts/canonical-provider-env.py` is 0% with zero references anywhere in
   `tests/`, yet it is the credential handoff for every `tofu plan`, `apply`,
   and `destroy` (`scripts/plan-infra.sh:120`, `scripts/apply-infra.sh:152`,
   `scripts/teardown-infra.sh:47` and `:86`).

The aggregate 74% against a 70% floor is therefore less reassuring than it
appears: it is computed over in-process modules only, while the uncovered
surface includes the mutation-critical entry point.

**Recommendation**

1. Enable subprocess measurement (`coverage` process-startup support via
   `COVERAGE_PROCESS_START` and a `sitecustomize` hook) before adding any
   per-module floor, or the floors will be enforced against meaningless numbers.
2. Add `infra/ansible/scripts` to the measured source set.
3. Add a direct test suite for `scripts/canonical-provider-env.py` covering: no
   canonical site selected, empty command, delivery failure, and the exact
   environment handed to the child (asserted by variable name, never value).

**Acceptance:** the coverage report attributes subprocess-executed modules;
`scripts/canonical-provider-env.py` has direct tests and a non-zero floor.

---

### P1-2 → P2-6 The declared platform contract is unenforced and the failure is unexplained

**Location:** `scripts/site_lock.py:7`, `scripts/atomic_output.py:25-27`

`import fcntl` executes at module import time, and `renameat2` syscall numbers
are hard-coded for `x86_64` and `aarch64`. The repository declares Linux `amd64`
support in `README.md` and `docs/canonical-quick-start.md`, so this is not a
portability defect. It is an enforcement and communication gap.

The existing guards cover optional or absent capabilities only: 28 guards for
`hasattr(os, "symlink")`, 3 for `TOFU_RUNTIME_AVAILABLE`, 4 for absent tooling
(`JUST_AVAILABLE`, `BASH_AND_PY`). **No guard covers the POSIX baseline.**

The affected surface is wider than the first pass listed. Eight test modules
reference POSIX-dependent scripts: `test_state_snapshot`, `test_site_lock`,
`test_private_files`, `test_execution_snapshot`, `test_canonical_values`,
`test_hermes_runtime`, `test_plan_projection_lifecycle`, and `test_run_infra`.

The first pass's headline number was a symptom of an undeclared dependency set
as much as of platform (see C-2), which is why this is now P2.

**Recommendation**

1. Add `tests/README.md` stating that the suite is POSIX-only, that the supported
   path is `just test` inside the pinned container, and that a native run is not
   a supported signal. Register the file in the documentation inventory (P3-8).
2. Add `just test-local` for a portable subset that reports its skip count
   explicitly, so a developer on an unsupported host gets an honest, explained
   result instead of unexplained red.
3. Name the platform requirement at the point of failure rather than relying on
   collection errors.

**Acceptance:** on an unsupported host the suite reports zero failures with skips
attributable to a named platform requirement.

---

### P2-1 `justfile` inline shell is unlinted, untested, and unreadable

**Location:** `justfile:72` (1,290 characters, confirmed by measurement),
`justfile:33` (559 characters)

`shellcheck` in `scripts/validate-public.sh` covers `scripts/*.sh` and
`tools/docker-entrypoint.sh` only. The `bash -n` test at
`tests/test_operational_cutover.py:45` covers four named scripts only. No
`justfile` recipe body is linted, parsed, or executed by any test.

**Re-verified non-issue.** The `sops_bin` fallback chain at `justfile:72` was
executed under `set -euo pipefail` in both conditions: with `sops` on `PATH` the
local branch is selected, and with `sops` absent and no `~/.local/bin/sops` the
container fallback is selected. Both exit 0. This is not a latent bug and must
not be "fixed" as one.

**Recommendation**

1. Extract to `scripts/edit-secrets.sh` and `scripts/ssh-initialize.sh`.
2. Deduplicate the site-identifier idiom, which appears verbatim twice:
   `site_arg="{{SITE}}"; site="${site_arg#SITE=}"`. Accept `VALUES_SITE`
   uniformly and delegate to `scripts/site-context.sh`.
3. Extend the existing retirement-contract pattern at
   `tests/test_operational_cutover.py:78` into a recipe-delegation contract,
   scoped to recipes that contain shell logic rather than to every recipe.

**Acceptance:** no recipe containing shell logic exceeds a single command;
`shellcheck scripts/*.sh` covers the extracted logic.

---

### P2-2 Per-module coverage floors, once the measurement is trustworthy

**Location:** `scripts/validate-public.sh:129`

Measured coverage for the seven modules named in the first pass:

| Module | Coverage |
| --- | --- |
| `scripts/canonical-provider-env.py` | **0%** |
| `scripts/site_lock.py` | 63% |
| `scripts/tfplan-metadata.py` | 69% |
| `scripts/execution-snapshot.py` | 73% |
| `scripts/private_files.py` | 85% |
| `scripts/secret_provider.py` | 86% |
| `scripts/atomic_output.py` | 87% |

This is the clearest vindication of the first pass's argument: an aggregate
74% conceals a 0% module and two modules below the aggregate floor, all in the
silent, hard-to-reverse class.

Floors cannot be set before P1-3 is resolved. Ordering is a hard dependency, not
a preference.

**Acceptance:** the aggregate floor is retained; a stricter per-module floor
applies to the seven modules above, expressed in configuration and enforced by a
check that names the offending module.

---

### P2-5 The provider credential handoff does not strip age key material

**Location:** `scripts/canonical-provider-env.py:44-49`

```python
environment = dict(os.environ)
environment.update(
    deliver_environment(provider, consumer="opentofu-provider", requirements=provider_requirements(args.provider))
)
os.execvpe(command[0], command, environment)
```

`scripts/secret_provider.py:97` deliberately pops `SOPS_AGE_KEY` before invoking
SOPS. The provider handoff applies no equivalent stripping: it copies the entire
operator environment into the `tofu` process. An operator who exports
`SOPS_AGE_KEY` rather than using the key-file convention therefore propagates raw
age key material into `tofu plan`, `tofu apply`, and `tofu destroy`, from where
it is inherited by provider plugins.

**Verified, not inferred.** A probe harness stubbed only the credential source
(no SOPS execution, no real secret material) and executed the module's `main()`
against a child that printed environment variable **names** only. With
`SOPS_AGE_KEY` set in the parent environment, the child observed both
`SOPS_AGE_KEY` and an unrelated operator variable.

The repository's own convention is the key *file* (`SOPS_AGE_KEY_FILE`, set by
`scripts/site-context.sh:16` and `justfile:33`), so the documented path is not
affected. No code path in this repository sets `SOPS_AGE_KEY`; it only ever pops
it. The exposure requires operator-set key material.

This finding compounds P1-3: the module is the credential boundary for every
mutation and has no tests.

**Recommendation:** strip `SOPS_AGE_KEY` from the child environment in
`canonical-provider-env.py`, exactly as `secret_provider.py` does for SOPS, and
cover it with the test suite required by P1-3.

**Acceptance:** a test asserts the child environment contains no `SOPS_AGE_KEY`
even when the parent exports one.

---

### P2-3 CI job structure and pull-request dependency scanning

**Location:** `.github/workflows/validate.yml`

Both structural claims are confirmed: a single `validate-public` job performs the
image build, tofu, tflint, shellcheck, black/ruff/mypy, contract checks, the
full 813-test suite, and Ansible syntax-check plus lint serially; and
`supply-chain-evidence` is gated on
`github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'`,
so no dependency scan runs on a pull request.

The first pass's timing premise was wrong (C-4). Measured stage costs are
python-quality ~50s, contracts ~72s, ansible ~41s — about 2m48s of gate work in
total. The dominant CI cost is the uncached tooling image build, which was not
measured here.

**Recommendation**

1. Split into `unit` (tests, ruff, mypy, reusing a cached image) and `full`
   (tofu, tflint, shellcheck, ansible). Cache the image keyed on
   `tools/Dockerfile` and `tools/requirements.lock`, since that pair is what
   determines the image.
2. Move the trivy filesystem scan of `tools/` into `pull_request`. Keep the image
   scan and SBOM scheduled, as they require `--no-cache`.
3. Measure the cold image build in CI before finalising the split, so the
   caching strategy is based on a number rather than an assumption.

**Acceptance:** a failing unit test fails the run without waiting for Ansible
lint; a vulnerable hash-locked dependency fails a pull request.

---

### P2-4 Tests assert on `justfile` source text

**Location:** `tests/test_operational_cutover.py:65`, `:74`, `:80-81`;
`tests/test_plan_projection_lifecycle.py:17-18`

```python
setup_recipe = justfile.split("# Initialize the selected canonical site's bootstrap SSH identity", 1)[0]
```

The first pass identified two sites; there are five, plus a `JUSTFILE` constant at
`tests/test_ssh_key_handling.py:9`. Two of them assert on a *comment* string,
so reformatting or rewording a comment fails a test while changing a recipe's
behaviour does not.

**Recommendation:** parse `just --dump` and assert on recipe names, parameters,
and dependencies. Negative assertions such as
`assertNotIn("recover-legacy-values-forensics", justfile)` are appropriate as
retirement contracts and may stay text-based.

---

### P3-1 Two scripts are orphaned

Confirmed: `git grep` finds **zero** references to either
`scripts/compare-plans.py` or `scripts/hermes-password-hash.py` anywhere in
tracked source, tests, documentation, or the `justfile`. Both also report 0%
coverage, which is expected for unreferenced code and is not additional
evidence of a defect.

**Recommendation:** delete `scripts/compare-plans.py`, superseding it with
`scripts/report-plan-equivalence.py` and `scripts/plan_equivalence.py`; document
`scripts/hermes-password-hash.py` in `docs/hermes-control-operations.md` or
remove it. Add both paths to the retirement contract in
`tests/test_operational_cutover.py:78` so they cannot silently return.

---

### P3-2 Duplicated Caddy templates have already diverged

**Location:** `infra/ansible/roles/*/templates/`

```
efaf03d4…a36e8ac3  caddy-override.conf.j2   caddy_proxy, forgejo, hermes, infisical
9a7eb4c7…7f3002f  caddy-override.conf.j2   onramp_host            <- already forked
9941cecb…4ba4c  caddy.env.j2               all five roles
```

The byte-identity relationships are confirmed; the first pass's digests are not
reproducible (C-6).

**Recommendation:** move both templates into `roles/caddy_proxy/files/` (or a
shared `lookup('template', ...)`) and have service roles consume them through
`include_role: caddy_proxy`. The forked `onramp_host` copy must be reconciled
deliberately, not overwritten.

---

### P3-3 Oversized Ansible roles

Confirmed exactly: `hermes/tasks/main.yml` 872 lines, `forgejo` 615, `sssf` 605,
`technitium` 543, against a 5,023-line total across all role task files.

**Recommendation:** apply the decomposition the repository already uses
elsewhere (`hermes/tasks/bootstrap-state.yml`, `managed-runtime.yml`,
`technitium/tasks/health.yml`) as `preflight` / `install` / `configure` /
`verify`, which also yields the tag boundaries `scripts/check-direct-service-ansible.py`
expects.

---

### P3-4 `require_canonical_authority()` is an identity function, and a test depends on it

**Location:** `scripts/site-context.sh:24-27`

```bash
require_canonical_authority() {
  local values_path
  values_path="$(site_values_dir)" || return
  require_site_context
}
```

The first pass counted eight call sites; the measured count is **nine**
(`scripts/apply-infra.sh:6`, `plan-infra.sh:6`, `teardown-infra.sh:6`,
`validate-values.sh:6`, `service-state.sh` ×3, `justfile` ×2), plus the
definition, two references in `tests/test_compatibility_boundary.py`, and three
in this document.

The additional reference matters for sequencing: the vestigial function is
pinned by a test, so deletion is not a mechanical change and must be planned
with that test.

**Recommendation:** either restore its meaning by explicitly rejecting
non-canonical `site.json` / `site.yml` layouts, or delete it together with its
nine call sites and the test that pins it.

---

### P3-5 Governance evidence carries false precision

**Location:** `docs/governance/audit-dispositions.md` and `.json`

Confirmed by parsing the JSON: 38 findings, and citation reuse is heavy.

| Findings | Shared citation | Count |
| --- | --- | --- |
| H7, H10, M10, M11, M13, M16 | `scripts/secret_delivery.py:1-120` | 6 |
| H1, H6, H15 | `scripts/tfplan-metadata.py:1-120` | 3 |

Six findings pointing at "lines 1-120" of a much longer file is a placeholder
formatted as evidence.

One further observation from parsing the ledger: **all 38 findings carry the
disposition `implemented-static`.** The ledger already records that none of them
carries live or provider-backed evidence, which is consistent with this
document's classification and with the acceptance matrix.

**Recommendation:** cite the specific function or test name, or collapse the
Markdown/JSON pair into one summary table pointing at test identifiers. Because
symbol citations also go stale, state the maintenance expectation explicitly.

---

### P3-6 Missing standard repository hygiene files

Confirmed absent: `LICENSE`, `CONTRIBUTING.md`, `CODEOWNERS` (including
`.github/CODEOWNERS`), `SECURITY.md`, `.editorconfig`.

Note a coupling the first pass missed: `tests/test_documentation_contract.py`
requires every tracked Markdown file to appear in
`docs/documentation-inventory.json` with a classification from a fixed enum.
Adding `SECURITY.md` therefore also requires an inventory entry.

**Recommendation:** add `CODEOWNERS` covering `tools/Dockerfile`,
`tools/*.lock`, `scripts/site-context.sh`, `scripts/apply-infra.sh`, and
`docs/governance/**`; add `SECURITY.md` with an approved private-reporting
channel and a corresponding inventory entry; add `.editorconfig` consistent with
`.gitattributes`. A disclosure policy that names no channel is worse than none.

---

### P3-7 Nothing keeps the pinned versions fresh

Confirmed: the only workflow is `validate.yml`, whose scheduled run scans but
never proposes. `scripts/update.py` already supports `dry_run` (lines 302, 383,
403) and `just update` already documents `--dry-run`.

**Recommendation:** add a weekly workflow running `just update --dry-run` and
reporting eligibility. Opening or commenting on a pull request is an external
side effect requiring repository credentials and an agreed automation policy;
keep it out of scope until that policy exists.

---

### P3-8 There is no Python tool configuration at all

**Location:** repository root — no `pyproject.toml`, `ruff.toml`, `mypy.ini`,
`setup.cfg`, or `.flake8`

Every Python quality tool therefore runs on its defaults. This is the root cause
behind two separate problems in P1-1:

- `black` and `ruff` both default to 88 columns, while the codebase's de-facto
  width is wider (960 lines exceed 100 characters, 259 exceed 120). Any `black`
  expansion is thus also a mass reformat of 116 of 135 files — the single largest
  mechanical cost in this backlog.
- There is nowhere to record the per-rule and per-path exceptions that the
  widened rule set requires.

**Recommendation:** add a minimal `pyproject.toml` declaring an explicit line
length, the ruff selection with its ignores, and mypy settings, before widening
any rule set. Decide the line-length policy first; it determines the size of the
formatting change.

---

### P4-1 `compose.yaml` mounts `${HOME}/.ssh` unconditionally

**Location:** `compose.yaml:12`

```yaml
- ${HOST_SSH_DIR:-${HOME}/.ssh}:/ssh-ro:ro
```

If `HOME` is unset, Docker creates an empty directory mount and the operator
meets a confusing "no key" failure at apply time. `tools/docker-entrypoint.sh:53`
already fails closed on a missing `INFRA_VALUES_DIR` or `SOPS_AGE_KEY_FILE`,
which is the contrasting behaviour.

**Recommendation:** fail closed in `just setup` and `scripts/run-infra.sh` when
neither `HOST_SSH_DIR` nor `HOME` resolves to a readable directory containing the
expected keys.

## 6. Implementation constraints discovered during the reconduct

These are not findings but constraints that any remediation must respect. None
appear in the first pass.

1. **Documentation inventory is enforced.** Any new Markdown file, including
   `tests/README.md` (P1-2) and `SECURITY.md` (P3-6), requires an entry in
   `docs/documentation-inventory.json`, and relative links and heading anchors in
   maintained documents are checked.
2. **Platform support is a documented contract.** `README.md:27` and
   `docs/canonical-quick-start.md:7` already declare Linux `amd64`. Remediation
   should enforce that declaration rather than quietly widen support.
3. **Retirement contracts already exist.** `tests/test_operational_cutover.py:78`
   is the established place to assert that deleted entry points stay deleted; use
   it for P3-1 and the P2-1 delegation contract.
4. **`tests/test_compatibility_boundary.py` pins `require_canonical_authority`**,
   so P3-4 is a coordinated change, not a deletion.
5. **`values/sites/dev/generated/` is derived** and was not hand-edited; `just
   validate` re-rendered and verified projections as part of this review.

## 7. Suggested implementation order

Revised using measured costs. The ordering constraint that matters most is
P1-3 before P2-2.

**Immediate — high value, low effort**

1. P1-3 subprocess coverage and a direct test suite for
   `scripts/canonical-provider-env.py` (0% on the mutation boundary)
2. P2-5 strip `SOPS_AGE_KEY` from the provider child environment, with a test
3. P3-8 add `pyproject.toml` with an explicit line-length and tool policy
4. P1-1 extend `mypy` to all of `scripts/` (23 errors), then widen ruff per
   family with configuration-backed ignores
5. P2-1 extract `edit-secrets` and `ssh-initialize` into linted scripts

**Next cycle**

6. P2-2 per-module coverage floors, after P1-3
7. P2-3 split CI, measure the cold image build, enable pull-request scanning
8. P3-1 orphan cleanup with a retirement contract; P3-2 Caddy template
   de-duplication; P3-3 role splitting
9. P3-6 `CODEOWNERS`, `SECURITY.md`, `.editorconfig`, inventory entries
10. P1-2 (as P2-6) platform contract enforcement, `tests/README.md`,
    `just test-local`
11. P3-4 resolve `require_canonical_authority` together with its test
12. P2-4 replace `justfile` text assertions with behavioural assertions

**Ongoing**

13. P3-7 weekly `just update --dry-run` reporting workflow
14. P3-5 rewrite governance citations to real symbols, or collapse the duplicate
    JSON/Markdown pair
15. P1-1 black baseline expansion, sized after the line-length decision

## 8. Verification limits

Recorded so these findings are not over-read:

- `just validate` was run against the **`dev` site only**, and passed. The
  `prod` site was not selected, read, or validated.
- `just plan`, `just apply`, `just teardown-plan`, and `just teardown-apply` were
  **not** run. No provider-backed planning and no infrastructure mutation were
  attempted.
- Ansible was exercised only through `syntax-check` and `ansible-lint`. No
  playbook was executed against a host.
- The tooling image build was **fully cached** (1.9s). Pin freshness was
  therefore not re-verified against upstream, and the cold build cost is
  unmeasured.
- Section 2 coverage figures describe the initial reconduct baseline. The
  current working branch enables subprocess instrumentation and includes
  `infra/ansible/scripts`; the progress table records the updated result.
- The credential-propagation probe in P2-5 stubbed the credential source and
  printed environment variable **names** only. No secret value was read,
  decrypted, or emitted. It demonstrates environment propagation, not the
  behaviour of the real SOPS provider.
- Strengths in section 4 that are marked "carried forward" were not re-verified
  in this pass.
- Findings describe the repository at `26b9be9`. Re-confirm locations before
  implementing each item, as the first pass correctly advised.

## 9. Remediation progress on the working branch

Initial implementation has started on `chore/engineering-review-remediation`.
This section records source changes, not acceptance evidence.

| Finding | Progress |
| --- | --- |
| P1-3 | Added subprocess coverage collection and included `infra/ansible/scripts` in the source set. Confirmed subprocess attribution: `canonical-provider-env.py` now measures 97%. |
| P1-1 | Broadened Ruff to E/F/W/I/B/UP/C4/PERF/SIM plus targeted S107; added a clean mypy gate for nine core modules. Formatted all 139 Python files with Black and made the inventory exact. Broader security-rule triage and all-script typing remain outstanding. |
| P2-2 | Added `tools/coverage-floors.json` and a named per-module floor check for all seven critical modules. |
| P2-3 | Split validation into cached-image `unit` and dependent `full` jobs; moved the filesystem dependency scan to pull-request/push events. Unit/full modes both pass locally; hosted cache and cold-build timing remain unverified. |
| P3-7 | Added weekly/manual update eligibility reporting via `just update --dry-run` against a disposable scaffold-only site fixture; no private site values or PR side effects are used. |
| P2-6 | Added `tests/README.md` and `just test-local` for host-portable documentation contracts; registered and documented the recipe. |
| P2-5 | Provider child environment now removes `SOPS_AGE_KEY`; five direct tests cover propagation, failure paths, and the no-site case. |
| P2-1 | Extracted `edit-secrets` and `ssh-initialize` shell logic into linted scripts; recipes delegate to those scripts and a contract test checks the delegation. |
| P2-4 | Positive recipe assertions now use `just --dump` and behavioral checks rather than justfile comments/source formatting. |
| P3-1 | Deleted `compare-plans.py`; documented `hermes-password-hash.py` and added a retirement/documentation contract. |
| P3-2 | Consolidated duplicate Caddy templates under `caddy_proxy`; preserved the `onramp_host` systemd difference as an explicit template variable and added tests. |
| P3-3 | Split the large Hermes task list into ordered preflight, host-runtime, application-runtime, configuration, and verification imports. Updated static contracts to resolve imports; full Ansible validation passes. |
| P3-6 | Added `CODEOWNERS`, `SECURITY.md`, `.editorconfig`, and the inventory entry. GitHub private-reporting availability still requires repository-settings verification. |
| P3-4 | Removed the identity function and its call sites; callers now invoke `require_site_context` directly, and compatibility tests exercise that contract. |
| P3-8 | Added `pyproject.toml` with explicit Black/Ruff line length, Ruff rules/ignores, mypy scope, and subprocess-aware coverage configuration. Black now checks every listed Python source. |
| P4-1 | Added fail-closed SSH mount directory validation to `just setup` and `scripts/run-infra.sh`. |

After these changes, `VALUES_SITE=dev just validate` passes all stages;
834 tests pass, aggregate coverage is 77%, and all seven per-module floors pass.
No plan, apply, or teardown command was run. Remaining recommendations are not
considered complete by this progress entry.
