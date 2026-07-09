# Service update policy

Managed services should use deterministic version pins and the normal reviewed workflow:

```bash
just update
just validate
just plan
just apply
```

`just update` applies the release-age safety hold before changing supported pins. After any update, review the diff and plan before applying.

## Managed pins

A service belongs in `just update` when the repo can identify a specific upstream release and update a deterministic local pin. Examples include Forgejo and Forgejo runner.

For downloadable tools or archives, prefer a version plus checksum. If upstream artifacts are mutable or unversioned, cache the reviewed artifact in ignored private storage and install from that cache during `just apply`.

## Technitium target model

Technitium DNS is critical infrastructure and should not be upgraded by rerunning the upstream installer as an ad hoc command. The desired model is:

- Read latest release metadata from `TechnitiumSoftware/DnsServer`.
- Apply the same `just update` release-age hold used for other managed pins.
- Pin the desired Technitium DNS Server version and portable tarball SHA256 in private values.
- Optionally cache the reviewed tarball under `values/artifacts/technitium/`.
- Let Ansible compare the installed marker with the desired pin, unpack the verified artifact, restart `dns.service`, and verify DNS/UI health.

The upstream portable tarball URL is currently unversioned, so checksum pinning and/or private artifact caching is required for reproducible updates.

## Unmanaged software

If a component is not yet in `just update`, document that explicitly and avoid inventing one-off upgrade commands. Add managed update support before making routine version changes.
