# Hermes tuning

The Hermes role manages a small set of non-secret `config.yaml` tuning values
through the official `hermes config set` command.

Defaults in the scaffold:

```yaml
hermes_compression_threshold: 0.75
hermes_max_concurrent_children: 5
hermes_max_spawn_depth: 2
```

These render to Hermes as:

```yaml
compression:
  enabled: true
  threshold: 0.75

delegation:
  max_concurrent_children: 5
  max_spawn_depth: 2
```

Rationale:

- `compression.threshold: 0.75` delays automatic compression until more of the
  model context is used.
- `max_concurrent_children: 5` allows modest parallel subagent fan-out without
  the cost multiplier of very high concurrency.
- `max_spawn_depth: 2` allows one nested helper level while avoiding deep agent
  trees. Hermes supports up to `3`, but use that only for deliberate batch work.

Do not enable subagent auto-approval or YOLO mode by default in this infra repo.
Those modes reduce review friction but are not appropriate for infrastructure
changes that can affect DNS, secrets, service access, or deployment state.
