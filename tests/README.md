# Test suite

The full suite is supported on Linux `amd64` and must run in the pinned tooling
container:

```bash
just test
```

This suite includes POSIX file-descriptor, `fcntl`, and Linux `renameat2`
behavior. A native run on an unsupported host is not a valid full-suite signal;
collection failures there do not indicate regressions in the supported runtime.
The repository's declared operator platform is Linux `amd64` (see the
[quick start](../docs/canonical-quick-start.md)).

For a limited host-side signal, run:

```bash
just test-local
```

This runs only the documentation inventory, relative-link, and scaffold-link
contracts. It requires Python 3 and Git, does not execute POSIX-sensitive
infrastructure tests, and is **not** a substitute for `just test`. The full
suite's unrun tests are intentionally not reported as skips because they were
not collected or executed.
