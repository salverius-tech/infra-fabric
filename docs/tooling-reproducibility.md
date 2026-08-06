# Tooling reproducibility and advisory policy

The public validation image is a reviewable Linux **amd64** artifact. Its Debian base is pinned by manifest-list digest; direct OpenTofu, TFLint, and SOPS downloads are version- and SHA-256-pinned; and Python packages are installed only from `tools/pip-bootstrap.lock` and `tools/requirements.lock` with pip `--require-hashes`.

## Architecture policy

`tools/Dockerfile` rejects a Docker-provided `TARGETARCH` other than `amd64`. This is intentional: each Python lock entry contains the actual reviewed CPython 3.11 Linux amd64 wheel hash and the direct tool checksums are amd64 release artifacts. Adding another architecture requires its own reviewed wheel/tool checksums and an explicit CI build; it must not silently reuse amd64 artifacts.

## APT reproducibility policy

The image deliberately uses the package set from the digest-pinned Debian Bookworm base's configured Debian archives, rather than pretending that unversioned `apt-get install` is byte-for-byte reproducible. The mutable APT boundary is therefore documented and monitored:

1. keep the base digest and package list under review;
2. build without cache in scheduled/manual freshness verification;
3. record the generated SBOM and fail the advisory scan under the policy below; and
4. update the base digest or package policy in a reviewed source change when Debian security updates require it.

This is a reproducibility **policy**, not a dated Debian snapshot. A future migration to snapshots must pin both snapshot timestamp and archive checks, retain the above evidence, and prove the supported build still succeeds.

## SBOM and advisory policy

The scheduled/manual `supply-chain-evidence` job is read-only: it builds the public tooling image, generates an SPDX JSON SBOM, and scans both the filesystem dependency lock and the resulting image. HIGH and CRITICAL findings fail the job, including unfixed findings. No provider, private values, credentials, plans, or live infrastructure are available to this workflow.

An exception is allowed only when a finding is documented in a reviewed public exception record with its advisory identifier, affected artifact, justified risk acceptance, owner, expiry date, and removal condition. Expired exceptions fail review and must be removed or renewed explicitly. There are currently no exceptions.

## Quality and coverage policy

Public validation compiles every repository Python file and applies Ruff's fatal parse/name-error rules to that complete set. Black checks the reviewed ratchet in `tools/python-format-files.txt`; expand that list as files are formatted instead of creating an unrelated repository-wide reformat. MyPy remains deliberately scoped to `scripts/canonical_values.py` and `scripts/service_catalog.py`. Coverage measures `scripts/` with an initial 70% threshold set below the observed 71% source-suite result; it may be raised after a later observed green run but never lowered without a reviewed explanation. Cache, bytecode, and coverage data are written beneath `/tmp/infra-fabric` in the container, not into the source mount.
