#!/usr/bin/env python3
"""Run enabled service Ansible playbooks, optionally in dependency-safe parallel waves."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

REPO = Path(__file__).resolve().parents[1]
SETTINGS_SPEC = importlib.util.spec_from_file_location("settings", REPO / "scripts" / "settings.py")
if SETTINGS_SPEC is None or SETTINGS_SPEC.loader is None:
    raise RuntimeError("cannot load scripts/settings.py")
settings = importlib.util.module_from_spec(SETTINGS_SPEC)
SETTINGS_SPEC.loader.exec_module(settings)
try:
    from canonical_projections import render_ansible_inventory, render_ansible_vars, render_dns_records, render_opentofu_variables
    from canonical_values import load_site, model_digest
    from projection_manifest import verify_manifest
    from service_catalog import load_catalog
    from values_context import from_environment
except ModuleNotFoundError:  # pragma: no cover - direct import in test loaders
    sys.path.insert(0, str(REPO / "scripts"))
    from canonical_projections import render_ansible_inventory, render_ansible_vars, render_dns_records, render_opentofu_variables
    from canonical_values import load_site, model_digest
    from projection_manifest import verify_manifest
    from service_catalog import load_catalog
    from values_context import from_environment
DEFAULT_INVENTORY = ("infra/ansible/inventory/tfvars.py",)
RunCommand = Callable[[list[str], Path, dict[str, str]], int]


@dataclass(frozen=True)
class ServiceResult:
    service: str
    playbooks: tuple[str, ...]
    returncode: int
    log_path: Path


@dataclass(frozen=True)
class CanonicalAnsibleTransport:
    inventory: str
    extra_args: tuple[str, ...]
    vars_path: Path
    environment: dict[str, str]


def enabled_services(settings_path: Path | None = None, service: str = "") -> list[str]:
    services = settings.load_settings(settings_path)["services"]
    if not service:
        return services
    if service not in services:
        raise settings.SettingsError(f"service is not enabled: {service}")
    return [service]


def dependency_waves(services: Iterable[str]) -> list[list[str]]:
    pending = list(services)
    enabled = set(pending)
    completed: set[str] = set()
    waves: list[list[str]] = []
    while pending:
        ready = [
            service
            for service in pending
            if set(settings.SERVICES[service]["dependencies"]) & enabled <= completed
        ]
        if not ready:
            unresolved = ", ".join(pending)
            raise settings.SettingsError(f"cannot resolve service dependency order: {unresolved}")
        waves.append(ready)
        completed.update(ready)
        pending = [service for service in pending if service not in ready]
    return waves


def inventory_args(inventories: Iterable[str]) -> list[str]:
    args: list[str] = []
    for inventory in inventories:
        args.extend(["-i", inventory])
    return args


def load_env_file(path: Path) -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("parse_env_script", REPO / "scripts" / "parse-env.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load scripts/parse-env.py")
    parse_env_script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parse_env_script)
    return parse_env_script.parse_env(path)


def refresh_env_from_file(env_file: Path, env: dict[str, str]) -> None:
    env.update(load_env_file(env_file))


def refresh_root_password_from_tfvars(tfvars_file: Path, env: dict[str, str]) -> None:
    if not tfvars_file.exists():
        return
    try:
        import hcl2
    except ModuleNotFoundError:
        return
    with tfvars_file.open(encoding="utf-8") as handle:
        values = hcl2.load(handle)
    password = values.get("lxc_root_password")
    if isinstance(password, str) and password:
        env["TF_VAR_lxc_root_password"] = password


def canonical_dns_environment(context: object) -> dict[str, str]:
    """Return a verified canonical DNS projection transport when available."""
    site_file = getattr(context, "canonical_site_path", None)
    if site_file is None:
        return {}
    catalog_path = REPO / "infra" / "services.json"
    model = load_site(site_file, expected_site=getattr(context, "site", None), catalog_path=catalog_path)
    catalog = load_catalog(catalog_path)
    expected_projections = {
        "terraform.auto.tfvars.json": render_opentofu_variables(model),
        "ansible-inventory.json": render_ansible_inventory(model, catalog),
        "ansible-vars.json": render_ansible_vars(model, catalog),
        "dns-records.json": render_dns_records(model),
    }
    generated_path = getattr(context, "generated_path")
    projections: dict[str, object] = {}
    try:
        for name in expected_projections:
            path = generated_path(name)
            projections[name] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("canonical generated projection is unavailable or invalid") from error
    if projections != expected_projections:
        raise RuntimeError("canonical generated projection does not match the selected model")
    manifest_path = getattr(context, "projection_manifest_path")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("canonical projection manifest is unavailable") from error
    verify_manifest(
        manifest,
        site=model.site.name,
        model_digest=model_digest(model),
        secret_digest=None,
        projections=projections,
    )
    dns_path = generated_path("dns-records.json")
    if not dns_path.is_file():
        raise RuntimeError("canonical DNS projection is unavailable")
    return {"DNS_RECORDS_FILE": str(dns_path)}


def canonical_ansible_transport(context: object, log_dir: Path) -> CanonicalAnsibleTransport | None:
    """Build an opt-in paired inventory/vars transport from verified projections."""
    if getattr(context, "canonical_site_path", None) is None:
        return None
    environment = canonical_dns_environment(context)
    generated_path = getattr(context, "generated_path")
    inventory_path = generated_path("ansible-inventory.json")
    vars_projection_path = generated_path("ansible-vars.json")
    try:
        projection = json.loads(vars_projection_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("canonical Ansible vars projection is unavailable") from error
    services = projection.get("services") if isinstance(projection, dict) else None
    if not isinstance(services, dict):
        raise RuntimeError("canonical Ansible vars projection has an invalid shape")
    flattened: dict[str, object] = {}
    for service, values in sorted(services.items()):
        legacy_vars = values.get("legacy_vars", {}) if isinstance(values, dict) else None
        if not isinstance(legacy_vars, dict):
            raise RuntimeError(f"canonical Ansible compatibility vars are invalid: {service}")
        for key, value in legacy_vars.items():
            if not isinstance(key, str):
                raise RuntimeError(f"canonical Ansible compatibility key is invalid: {service}")
            if key in flattened and flattened[key] != value:
                raise RuntimeError(f"conflicting canonical Ansible compatibility var: {key}")
            flattened[key] = value
    file_descriptor, vars_name = tempfile.mkstemp(
        prefix=".canonical-ansible-vars-",
        suffix=".json",
        dir=log_dir,
        text=True,
    )
    vars_path = Path(vars_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(flattened, handle, sort_keys=True)
            handle.write("\n")
        os.chmod(vars_path, 0o600)
    except BaseException:
        os.close(file_descriptor)
        vars_path.unlink(missing_ok=True)
        raise
    return CanonicalAnsibleTransport(
        inventory=str(inventory_path),
        extra_args=("-e", f"@{vars_path}"),
        vars_path=vars_path,
        environment=environment,
    )


def bootstrap_technitium_token(env_file: Path, log_path: Path, env: dict[str, str], runner: RunCommand) -> int:
    rc = runner(
        ["python", "scripts/bootstrap-technitium-api-token.py", "--env-file", str(env_file)],
        log_path,
        env,
    )
    if rc == 0:
        refresh_env_from_file(env_file, env)
    return rc


def default_runner(command: list[str], log_path: Path, env: dict[str, str]) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        log.write(("$ " + " ".join(command) + "\n").encode("utf-8"))
        process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, check=False)
        log.write((f"\nexit_code={process.returncode}\n").encode("utf-8"))
        return process.returncode


def run_service(
    service: str,
    inventories: tuple[str, ...],
    log_dir: Path,
    env_file: Path,
    base_env: dict[str, str],
    runner: RunCommand = default_runner,
    extra_args: tuple[str, ...] = (),
) -> ServiceResult:
    playbooks = tuple(settings.SERVICES[service]["playbooks"])
    log_path = log_dir / f"{service}.log"
    env = dict(base_env)
    for playbook in playbooks:
        if playbook == "infra/ansible/playbooks/technitium-dns.yml":
            rc = bootstrap_technitium_token(env_file, log_path, env, runner)
            if rc != 0:
                return ServiceResult(service, playbooks, rc, log_path)
        command = ["ansible-playbook", *inventory_args(inventories), *extra_args, playbook]
        rc = runner(command, log_path, env)
        if rc != 0:
            return ServiceResult(service, playbooks, rc, log_path)
    return ServiceResult(service, playbooks, 0, log_path)


def run_sequential(
    services: list[str],
    inventories: tuple[str, ...],
    log_dir: Path,
    env_file: Path,
    base_env: dict[str, str],
    runner: RunCommand = default_runner,
    extra_args: tuple[str, ...] = (),
) -> list[ServiceResult]:
    results: list[ServiceResult] = []
    for service in services:
        print(f"==> ansible service {service}", flush=True)
        result = run_service(service, inventories, log_dir, env_file, base_env, runner, extra_args)
        results.append(result)
        if result.returncode != 0:
            break
        print(f"<== ansible service {service} ok", flush=True)
    return results


def run_parallel(
    services: list[str],
    inventories: tuple[str, ...],
    log_dir: Path,
    env_file: Path,
    base_env: dict[str, str],
    max_workers: int,
    runner: RunCommand = default_runner,
    extra_args: tuple[str, ...] = (),
) -> list[ServiceResult]:
    results: list[ServiceResult] = []
    for index, wave in enumerate(dependency_waves(services), 1):
        print(f"==> ansible wave {index}: {', '.join(wave)}", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(wave))) as executor:
            future_map = {
                executor.submit(run_service, service, inventories, log_dir, env_file, base_env, runner, extra_args): service
                for service in wave
            }
            wave_results: list[ServiceResult] = []
            for future in concurrent.futures.as_completed(future_map):
                result = future.result()
                wave_results.append(result)
                status = "ok" if result.returncode == 0 else f"failed rc={result.returncode}"
                print(f"<== ansible service {result.service} {status}", flush=True)
        wave_results.sort(key=lambda item: wave.index(item.service))
        results.extend(wave_results)
        if any(result.returncode != 0 for result in wave_results):
            break
    return results


def summarize_results(services: list[str], results: list[ServiceResult]) -> None:
    by_service = {result.service: result for result in results}
    print("Ansible service apply summary:", flush=True)
    for service in services:
        result = by_service.get(service)
        if result is None:
            print(f"  {service}: not attempted", flush=True)
        elif result.returncode == 0:
            print(f"  {service}: configured", flush=True)
        else:
            print(f"  {service}: failed; log {result.log_path}", flush=True)


def summarize_failures(results: list[ServiceResult]) -> int:
    failed = [result for result in results if result.returncode != 0]
    if not failed:
        return 0
    print("Ansible service configuration failed:", file=sys.stderr)
    for result in failed:
        print(f"  {result.service}: exit {result.returncode}; log {result.log_path}", file=sys.stderr)
    print("Review the log file(s), fix the failure, rerun just plan if needed, then rerun just apply.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=None)
    parser.add_argument("--inventory", action="append", default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--mode", choices=("parallel", "sequential"), default=os.environ.get("INFRA_APPLY_ANSIBLE_MODE", "parallel"))
    parser.add_argument("--service", default="")
    parser.add_argument("--max-workers", type=int, default=int(os.environ.get("INFRA_APPLY_ANSIBLE_MAX_WORKERS", "4")))
    parser.add_argument("--log-dir", type=Path, default=None)
    parser.add_argument("--canonical-ansible", action="store_true", help="use the verified canonical inventory and vars pair")
    args = parser.parse_args(argv)

    try:
        services = enabled_services(args.settings, args.service)
    except settings.SettingsError as error:
        print(error, file=sys.stderr)
        return 1
    context = from_environment(REPO)
    if args.canonical_ansible and args.inventory:
        print("--canonical-ansible cannot be combined with --inventory", file=sys.stderr)
        return 1
    inventories = tuple(args.inventory or (str(context.path("ansible/inventory/local.yml")), *DEFAULT_INVENTORY))
    env_file = args.env_file or context.path(".env")
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_dir = args.log_dir or Path(".tmp") / f"apply-ansible-{timestamp.replace(':', '')}"
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"Ansible service apply mode: {args.mode}; started {timestamp}; logs: {log_dir}", flush=True)
    base_env = dict(os.environ)
    refresh_root_password_from_tfvars(context.path("terraform.tfvars"), base_env)
    transport: CanonicalAnsibleTransport | None = None
    try:
        if args.canonical_ansible:
            transport = canonical_ansible_transport(context, log_dir)
            if transport is None:
                raise RuntimeError("--canonical-ansible requires a selected canonical site")
            base_env.update(transport.environment)
            inventories = (transport.inventory,)
            extra_args = transport.extra_args
        else:
            base_env.update(canonical_dns_environment(context))
            extra_args = ()
        if args.mode == "sequential":
            results = run_sequential(services, inventories, log_dir, env_file, base_env, extra_args=extra_args)
        else:
            results = run_parallel(services, inventories, log_dir, env_file, base_env, max(1, args.max_workers), extra_args=extra_args)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"canonical Ansible projection verification failed: {error}", file=sys.stderr)
        return 1
    finally:
        if transport is not None:
            transport.vars_path.unlink(missing_ok=True)
    summarize_results(services, results)
    return summarize_failures(results)


if __name__ == "__main__":
    raise SystemExit(main())
