# Tooling reproducibility and advisory policy

The public validation image is a reviewable Linux **amd64** artifact. Its Debian base is pinned by manifest-list digest; direct OpenTofu, TFLint, SOPS, and Just downloads are version- and SHA-256-pinned; and Python packages are installed only from `tools/pip-bootstrap.lock` and `tools/requirements.lock` with pip `--require-hashes`.

Just is pinned to 1.46.0 using the Linux amd64 musl release archive. The checksum, `79966e6e353f535ee7d1c6221641bcc8e3381c55b0d0a6dc6e54b34f9db36eaa`, is the entry for `just-1.46.0-x86_64-unknown-linux-musl.tar.gz` in the [official Just 1.46.0 `SHA256SUMS` release asset](https://github.com/casey/just/releases/download/1.46.0/SHA256SUMS). The Docker build verifies the downloaded archive before extracting `just`.

A host still needs Just to invoke public `just` recipes. The tooling image supplies Just for CLI regression tests, so public validation does not require a private Compose bind override or a host-mounted Just binary.

## Architecture policy

`tools/Dockerfile` rejects a Docker-provided `TARGETARCH` other than `amd64`. This is intentional: each Python lock entry contains the actual reviewed CPython 3.11 Linux amd64 wheel hash and the direct tool checksums are amd64 release artifacts. Adding another architecture requires its own reviewed wheel/tool checksums and an explicit CI build; it must not silently reuse amd64 artifacts.

## APT reproducibility policy

The image deliberately uses the package set from the digest-pinned Debian Bookworm base's configured Debian archives, rather than pretending that unversioned `apt-get install` is byte-for-byte reproducible. The mutable APT boundary is therefore documented and monitored:

1. keep the base digest and package list under review;
2. build without cache in scheduled/manual freshness verification;
3. record the generated SBOM and fail the advisory scan under the policy below; and
4. update the base digest or package policy in a reviewed source change when Debian security updates require it.

This is a reproducibility **policy**, not a dated Debian snapshot. A future migration to snapshots must pin both snapshot timestamp and archive checks, retain the above evidence, and prove the supported build still succeeds. An uncached local tooling-image build completed in 42 seconds on 2026-10-04; this is a runner-specific observation, not a CI timing guarantee.

### Bandit scope decision

The initial full-S-family exploratory scan (Ruff, 2026-10-04) found 223 diagnostics. Production assertions were replaced; test assertions and reviewed test fixtures have narrow file-scoped exceptions; the 3 SQL findings are limited to bounded integers or source constants and have inline rationales. The residual broad scan now reports 104 subprocess diagnostics (S603 60, S606 1, S607 43): these are direct argv execution and PATH resolution boundaries that require call-site review before gating. All other observed S rules are selected, with explicit per-file exceptions recorded in `pyproject.toml` for test fixtures, logical secret-reference names, local API URLs, and temporary-directory policy. No rule family is globally suppressed.

## SBOM and advisory policy

The pull-request/push `dependency-scan` job is read-only and scans the hash-locked filesystem dependencies. The scheduled/manual `supply-chain-evidence` job builds the public tooling image, runs weekly `just update --dry-run` eligibility reporting with a disposable scaffold-only site fixture, generates an SPDX JSON SBOM, and scans the resulting image. HIGH and CRITICAL findings fail the relevant job, including unfixed findings. No provider, private values, credentials, plans, or live infrastructure are available to these workflows.

An exception is allowed only when a finding is documented in a reviewed public exception record with its advisory identifier, affected artifact, justified risk acceptance, owner, expiry date, and removal condition. Expired exceptions fail review and must be removed or renewed explicitly. There are currently no exceptions.

## Quality and coverage policy

Public validation compiles every repository Python file, applies Ruff checks to that complete set, and runs Black over every Python source. Ruff enables the E/F/W, import, bugbear, modern-Python, comprehension, performance, simplification, and targeted Bandit rules S101/S102/S104/S105/S106/S107/S108/S201/S301/S310/S324/S501/S506/S608/S701. Per-path exceptions cover reviewed tests, logical secret-reference identifiers, the configured local Technitium API, and secure temporary-file usage. S603/S606/S607 remain unselected pending manual review of subprocess and executable-path boundaries. `tools/python-format-files.txt` is the complete formatting inventory; a contract test requires it to match the source tree exactly. MyPy checks all 50 Python modules under `scripts/` and `infra/ansible/scripts`, with imports checked silently to avoid duplicate third-party diagnostics. Coverage includes `scripts/` and `infra/ansible/scripts`, collects subprocess data, enforces an aggregate 70% threshold and named per-module floors. Cache, bytecode, and coverage data are written beneath `/tmp/infra-fabric` in the container, not into the source mount.
