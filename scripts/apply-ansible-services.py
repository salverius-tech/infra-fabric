#!/usr/bin/env python3
"""Run enabled service Ansible playbooks, optionally in dependency-safe parallel waves."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

REPO = Path(__file__).resolve().parents[1]
SETTINGS_SPEC = importlib.util.spec_from_file_location("settings", REPO / "scripts" / "settings.py")
if SETTINGS_SPEC is None or SETTINGS_SPEC.loader is None:
    raise RuntimeError("cannot load scripts/settings.py")
settings = importlib.util.module_from_spec(SETTINGS_SPEC)
SETTINGS_SPEC.loader.exec_module(settings)
try:
    from canonical_projections import render_ansible_inventory, render_ansible_vars, render_dns_records, render_opentofu_variables, verify_cross_projection_identity
    from canonical_values import load_site, model_digest
    from projection_manifest import verify_manifest
    from secret_delivery import deliver, deliver_services_environment, operator_password_requirements, root_password_requirements, without_protected_environment
    from secret_provider import SopsAgeProvider
    from service_catalog import load_catalog
    from values_context import from_environment
except ModuleNotFoundError:  # pragma: no cover - direct import in test loaders
    sys.path.insert(0, str(REPO / "scripts"))
    from canonical_projections import render_ansible_inventory, render_ansible_vars, render_dns_records, render_opentofu_variables, verify_cross_projection_identity
    from canonical_values import load_site, model_digest
    from projection_manifest import verify_manifest
    from secret_delivery import deliver, deliver_services_environment, operator_password_requirements, root_password_requirements, without_protected_environment
    from secret_provider import SopsAgeProvider
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


def canonical_enabled_services(context: object, service: str = "") -> list[str]:
    site_file = getattr(context, "canonical_site_path", None)
    if site_file is None:
        raise RuntimeError("canonical Ansible execution requires a selected canonical site")
    model = load_site(site_file, expected_site=getattr(context, "site", None), catalog_path=REPO / "infra" / "services.json")
    services = [name for name, definition in model.services.items() if definition.enabled]
    if service:
        if service not in services:
            raise RuntimeError(f"service is not enabled in the canonical site: {service}")
        return [service]
    return services


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


def execution_resource_keys(services: Iterable[str], model: object | None = None) -> dict[str, str]:
    """Return one validated scheduler key per service without inventing host ownership."""
    keys: dict[str, str] = {}
    canonical_services = getattr(model, "services", {}) if model is not None else {}
    for service in services:
        canonical = canonical_services.get(service) if hasattr(canonical_services, "get") else None
        resource = str(getattr(canonical, "resource", "") or "").strip()
        inventory_host = str(settings.SERVICES[service].get("execution_resource", "")).strip()
        key = resource or inventory_host
        if not key:
            raise settings.SettingsError(f"service has no execution resource: {service}")
        keys[service] = key
    return keys


def execution_resource_waves(services: Iterable[str], resources: Mapping[str, str]) -> list[list[str]]:
    """Split dependency-ready services so each batch has one service per host/resource."""
    batches: list[list[str]] = []
    for ready in dependency_waves(services):
        pending = list(ready)
        while pending:
            used: set[str] = set()
            batch: list[str] = []
            deferred: list[str] = []
            for service in pending:
                resource = str(resources.get(service, "")).strip()
                if not resource:
                    raise settings.SettingsError(f"service has no execution resource: {service}")
                if resource in used:
                    deferred.append(service)
                else:
                    used.add(resource)
                    batch.append(service)
            batches.append(batch)
            pending = deferred
    return batches


def inventory_args(inventories: Iterable[str]) -> list[str]:
    args: list[str] = []
    for inventory in inventories:
        args.extend(["-i", inventory])
    return args


def canonical_identity_extra_args() -> tuple[str, ...]:
    identity = os.environ.get("INFRA_SSH_IDENTITY_FILE", "")
    args: list[str] = []
    if identity and re.fullmatch(r"[A-Za-z0-9._-]+", identity):
        args.extend(("-e", f"ansible_ssh_private_key_file={Path.home() / '.ssh' / identity}"))
    if os.environ.get("INFRA_HOST_IDENTITY_SKIP_ROOT", "").strip().lower() != "false":
        args.extend(("-e", "infra_host_identity_skip_root=true"))
    return tuple(args)


def load_env_file(path: Path) -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("parse_env_script", REPO / "scripts" / "parse-env.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load scripts/parse-env.py")
    parse_env_script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parse_env_script)
    return parse_env_script.parse_env(path)


def refresh_env_from_file(env_file: Path, env: dict[str, str]) -> None:
    env.update(load_env_file(env_file))


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
    verify_cross_projection_identity(
        site=model.site.name,
        opentofu=projections["terraform.auto.tfvars.json"],
        inventory=projections["ansible-inventory.json"],
        ansible_vars=projections["ansible-vars.json"],
    )
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
    technitium = model.resources.guests.get("technitium")
    if technitium is None or not getattr(technitium.network, "address", ""):
        raise RuntimeError("canonical Technitium guest address is unavailable")
    technitium_address = technitium.network.address.split("/", 1)[0]
    return {
        "DNS_RECORDS_FILE": str(dns_path),
        "TECHNITIUM_API_URL": f"http://{technitium_address}:5380",
    }


def canonical_bootstrap_targets(context: object) -> tuple[tuple[str, str], ...]:
    """Return unique canonical resource IDs and inventory hosts for enabled services."""
    site_file = getattr(context, "canonical_site_path", None)
    if site_file is None:
        raise RuntimeError("canonical bootstrap requires a selected canonical site")
    catalog_path = REPO / "infra" / "services.json"
    model = load_site(site_file, expected_site=getattr(context, "site", None), catalog_path=catalog_path)
    catalog = load_catalog(catalog_path)
    selected_resource = os.environ.get("INFRA_HOST_IDENTITY_ONLY", "").strip()
    targets: dict[str, str] = {}
    for service_name, service in model.services.items():
        if not service.enabled or service.resource is None:
            continue
        if selected_resource and service.resource != selected_resource:
            continue
        host = str(catalog.get(service_name).inventory.get("host", service.resource))
        existing = targets.get(service.resource)
        if existing is not None and existing != host:
            raise RuntimeError(f"canonical resource maps to multiple bootstrap hosts: {service.resource}")
        targets[service.resource] = host
    return tuple(sorted(targets.items()))


def run_canonical_bootstrap(
    context: object,
    inventories: tuple[str, ...],
    log_dir: Path,
    base_env: dict[str, str],
    extra_args: tuple[str, ...] = (),
    runner: RunCommand | None = None,
) -> int:
    """Deliver and rotate one host credential at a time for canonical execution."""
    try:
        bundle_path = getattr(context, "path")("secrets.sops.yaml")
    except (AttributeError, TypeError, ValueError) as error:
        raise RuntimeError("canonical secret bundle path is unavailable") from error
    if not bundle_path.is_file():
        raise RuntimeError("canonical bootstrap secret bundle is unavailable")
    provider = SopsAgeProvider(bundle_path)
    site_file = getattr(context, "canonical_site_path", None)
    if site_file is None:
        raise RuntimeError("canonical bootstrap requires a selected canonical site")
    model = load_site(site_file, expected_site=getattr(context, "site", None), catalog_path=REPO / "infra" / "services.json")
    policy = model.bootstrap.root_password
    runner = runner or default_runner
    for resource_id, host in canonical_bootstrap_targets(context):
        requirements = root_password_requirements(
            [resource_id],
            default_secret=policy.default_secret,
            host_overrides=policy.host_overrides,
        )
        delivered = deliver(provider, path=requirements[0].path, consumer="ansible-bootstrap", requirements=requirements)
        rc = run_bootstrap_host(
            host,
            inventories,
            log_dir,
            base_env,
            {delivered.environment_name: delivered.value},
            runner,
            extra_args,
        )
        if rc != 0:
            return rc
    return 0


def run_canonical_host_identity(
    context: object,
    inventories: tuple[str, ...],
    log_dir: Path,
    base_env: dict[str, str],
    extra_args: tuple[str, ...] = (),
    runner: RunCommand | None = None,
) -> int:
    """Converge canonical accounts before any service role executes."""
    try:
        bundle_path = getattr(context, "path")("secrets.sops.yaml")
    except (AttributeError, TypeError, ValueError) as error:
        raise RuntimeError("canonical host identity secret bundle path is unavailable") from error
    if not bundle_path.is_file():
        raise RuntimeError("canonical host identity secret bundle is unavailable")
    provider = SopsAgeProvider(bundle_path)
    runner = runner or default_runner
    operator_requirement = operator_password_requirements()[0]
    site_file = getattr(context, "canonical_site_path")
    model = load_site(site_file, expected_site=getattr(context, "site", None), catalog_path=REPO / "infra" / "services.json")
    resources = {**model.resources.guests, **model.resources.shared_hosts}
    for resource_id, host in canonical_bootstrap_targets(context):
        resource = resources[resource_id]
        root_requirements = root_password_requirements(
            [resource_id],
            default_secret=model.bootstrap.root_password.default_secret,
            host_overrides=model.bootstrap.root_password.host_overrides,
            consumer="ansible-host-identity",
        )
        operator_delivered = deliver(
            provider,
            path=operator_requirement.path,
            consumer="ansible-host-identity",
            requirements=(operator_requirement,),
        )
        skip_root = os.environ.get("INFRA_HOST_IDENTITY_SKIP_ROOT", "").strip().lower() != "false"
        if resource.type == "lxc" and skip_root:
            phases = (("infra", True),)
        else:
            phases = (("root", False), ("infra", True)) if resource.type == "lxc" else (("infra", True),)
        for connection_user, cleanup_root in phases:
            env = dict(base_env)
            root_environment_name: str | None = None
            env[operator_delivered.environment_name] = operator_delivered.value
            if cleanup_root:
                root_delivered = deliver(
                    provider,
                    path=root_requirements[0].path,
                    consumer="ansible-host-identity",
                    requirements=root_requirements,
                )
                root_environment_name = root_delivered.environment_name
                env[root_delivered.environment_name] = root_delivered.value
            command = [
                "ansible-playbook",
                *inventory_args(inventories),
                *extra_args,
                "-e",
                "host_identity_enabled=true",
                "-e",
                f"host_identity_root_recovery_enabled={'true' if cleanup_root else 'false'}",
                "-e",
                f"ansible_user={connection_user}",
                "--limit",
                host,
                "infra/ansible/playbooks/host-identity.yml",
            ]
            try:
                rc = runner(command, log_dir / f"host-identity-{host}-{connection_user}.log", env)
            finally:
                env.pop(operator_delivered.environment_name, None)
                if root_environment_name is not None:
                    env.pop(root_environment_name, None)
            if rc != 0:
                return rc
    return 0


def run_canonical_direct_access_ready(
    context: object,
    inventories: tuple[str, ...],
    log_dir: Path,
    base_env: dict[str, str],
    extra_args: tuple[str, ...] = (),
    enroll_only: bool = False,
    runner: RunCommand | None = None,
) -> int:
    """Enroll and verify guest SSH trust before the first canonical connection."""
    runner = runner or default_runner
    known_hosts = getattr(context, "path")("ansible/known_hosts")
    ready_hosts = "all:!proxmox"
    selected_resource = os.environ.get("INFRA_HOST_IDENTITY_ONLY", "").strip()
    if selected_resource:
        selected_targets = dict(canonical_bootstrap_targets(context))
        ready_hosts = selected_targets.get(selected_resource, ready_hosts)
    command = [
        "ansible-playbook",
        *inventory_args(inventories),
        *extra_args,
        "-e",
        f"direct_access_ready_hosts={ready_hosts}",
        "-e",
        f"direct_access_ready_known_hosts_file={known_hosts}",
    ]
    if os.environ.get("INFRA_ACCEPT_CHANGED_HOST_KEYS", "").lower() == "true":
        command.extend(("-e", "direct_access_ready_accept_host_key_change=true"))
    if enroll_only:
        command.extend(("-e", "direct_access_ready_enroll_only=true"))
    command.append("infra/ansible/playbooks/direct-access-ready.yml")
    return runner(command, log_dir / "direct-access-ready.log", dict(base_env))


def canonical_ansible_transport(context: object, log_dir: Path, services: list[str] | tuple[str, ...]) -> CanonicalAnsibleTransport | None:
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
    flattened: dict[str, object] = {
        key: value for key, value in projection.items() if key != "services"
    }
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
        extra_args=("-e", f"@{vars_path}", *canonical_identity_extra_args()),
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


def run_bootstrap_host(
    host: str,
    inventories: tuple[str, ...],
    log_dir: Path,
    base_env: dict[str, str],
    bootstrap_env: dict[str, str],
    runner: RunCommand = default_runner,
    extra_args: tuple[str, ...] = (),
) -> int:
    """Run one host bootstrap with a transient, host-scoped secret environment."""
    env = dict(base_env)
    env.update(bootstrap_env)
    command = [
        "ansible-playbook",
        *inventory_args(inventories),
        *extra_args,
        "--limit",
        host,
        "infra/ansible/playbooks/bootstrap-root-password.yml",
    ]
    try:
        return runner(command, log_dir / f"bootstrap-{host}.log", env)
    finally:
        for name in bootstrap_env:
            env.pop(name, None)


def run_service(
    service: str,
    inventories: tuple[str, ...],
    log_dir: Path,
    env_file: Path,
    base_env: dict[str, str],
    runner: RunCommand = default_runner,
    extra_args: tuple[str, ...] = (),
    service_environment: Mapping[str, str] | None = None,
) -> ServiceResult:
    playbooks = tuple(settings.SERVICES[service]["playbooks"])
    log_path = log_dir / f"{service}.log"
    env = dict(base_env)
    if service_environment:
        env.update(service_environment)
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
    service_environments: Mapping[str, Mapping[str, str]] | None = None,
) -> list[ServiceResult]:
    results: list[ServiceResult] = []
    for service in services:
        print(f"==> ansible service {service}", flush=True)
        result = run_service(
            service,
            inventories,
            log_dir,
            env_file,
            base_env,
            runner,
            extra_args,
            (service_environments or {}).get(service),
        )
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
    service_environments: Mapping[str, Mapping[str, str]] | None = None,
    execution_resources: Mapping[str, str] | None = None,
) -> list[ServiceResult]:
    results: list[ServiceResult] = []
    resources = dict(execution_resources or execution_resource_keys(services))
    for index, wave in enumerate(execution_resource_waves(services, resources), 1):
        print(f"==> ansible wave {index}: {', '.join(wave)}", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(wave))) as executor:
            future_map = {
                executor.submit(
                    run_service,
                    service,
                    inventories,
                    log_dir,
                    env_file,
                    base_env,
                    runner,
                    extra_args,
                    (service_environments or {}).get(service),
                ): service
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

    context = from_environment(REPO)
    try:
        services = (
            canonical_enabled_services(context, args.service)
            if args.canonical_ansible
            else enabled_services(args.settings, args.service)
        )
    except (settings.SettingsError, RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
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
    transport: CanonicalAnsibleTransport | None = None
    execution_resources: dict[str, str] = {}
    try:
        execution_resources = execution_resource_keys(services)
        if args.canonical_ansible:
            transport = canonical_ansible_transport(context, log_dir, services)
            if transport is None:
                raise RuntimeError("--canonical-ansible requires a selected canonical site")
            base_env.update(transport.environment)
            inventories = (transport.inventory,)
            extra_args = transport.extra_args
        else:
            base_env.update(canonical_dns_environment(context))
            extra_args = ()
        if args.canonical_ansible:
            direct_access_rc = run_canonical_direct_access_ready(
                context,
                inventories,
                log_dir,
                base_env,
                extra_args=extra_args,
                enroll_only=True,
            )
            if direct_access_rc != 0:
                print(f"canonical direct access readiness failed with exit code {direct_access_rc}", file=sys.stderr)
                return 1
            host_identity_rc = run_canonical_host_identity(context, inventories, log_dir, base_env, extra_args=extra_args)
            if host_identity_rc != 0:
                print(f"canonical host identity convergence failed with exit code {host_identity_rc}", file=sys.stderr)
                return 1
            direct_access_rc = run_canonical_direct_access_ready(
                context,
                inventories,
                log_dir,
                base_env,
                extra_args=extra_args,
            )
            if direct_access_rc != 0:
                print(f"canonical direct service readiness failed with exit code {direct_access_rc}", file=sys.stderr)
                return 1
            if os.environ.get("INFRA_HOST_IDENTITY_ONLY", "").strip():
                print("host-identity-only recovery completed; skipping service apply")
                return 0
            provider = SopsAgeProvider(context.path("secrets.sops.yaml"))
            site_file = context.canonical_site_path
            if site_file is None:
                raise RuntimeError("canonical Ansible execution requires a selected canonical site")
            model = load_site(
                site_file,
                expected_site=context.site,
                catalog_path=REPO / "infra" / "services.json",
            )
            catalog = load_catalog(REPO / "infra" / "services.json")
            execution_resources = execution_resource_keys(services, model)
            service_environments = {
                selected_service: deliver_services_environment(
                    provider,
                    catalog,
                    model.services,
                    selected_services=[selected_service],
                )
                for selected_service in services
            }
            base_env = without_protected_environment(base_env, catalog)
        else:
            service_environments = None
        if args.mode == "sequential":
            results = run_sequential(
                services,
                inventories,
                log_dir,
                env_file,
                base_env,
                extra_args=extra_args,
                service_environments=service_environments,
            )
        else:
            results = run_parallel(
                services,
                inventories,
                log_dir,
                env_file,
                base_env,
                max(1, args.max_workers),
                extra_args=extra_args,
                service_environments=service_environments,
                execution_resources=execution_resources,
            )
        if args.canonical_ansible:
            print("==> canonical host bootstrap", flush=True)
            bootstrap_rc = run_canonical_bootstrap(context, inventories, log_dir, base_env, extra_args=extra_args)
            if bootstrap_rc != 0:
                print(f"canonical host bootstrap failed with exit code {bootstrap_rc}", file=sys.stderr)
                return 1
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
