#!/usr/bin/env python3
"""Plan or perform migration from legacy values files into a site directory."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from values_context import SITE_NAME_RE
from migration_backup import BackupManifestError, build_manifest, expand_backup_paths
from legacy_values_discovery import DiscoveryError, build_candidate_site, discover_legacy, runtime_importer_admission


class SiteMigrationError(ValueError):
    pass


MIGRATED_FILES = (
    Path(".env"),
    Path("terraform.tfvars"),
    Path("dns-records.local.json"),
    Path("ansible/inventory/local.yml"),
    Path("ansible/known_hosts"),
    Path("plans"),
    Path("backups"),
    Path("artifacts"),
)
SENSITIVE_MIGRATION_ROOTS = {
    Path("ansible/known_hosts"),
    Path("terraform.tfstate"),
    Path("terraform.tfstate.backup"),
    Path("backups"),
    Path("service-backups"),
}
GENERATED_PROJECTIONS = {Path(".env"), Path("terraform.tfvars"), Path("dns-records.local.json"), Path("ansible/inventory/local.yml")}


def artifact_disposition(relative: Path) -> tuple[str, str]:
    if relative in GENERATED_PROJECTIONS:
        return "generated-projection", "canonical site values"
    return "operational-artifact", "private migration/recovery workflow"


def migration_manifest(site: str, items: list[tuple[Path, Path]], values_root: Path) -> dict[str, Any]:
    operations: list[dict[str, str]] = []
    for source, destination in items:
        relative = source.relative_to(values_root)
        disposition, owner = artifact_disposition(relative)
        operations.append(
            {
                "source": relative.as_posix(),
                "destination": destination.relative_to(values_root).as_posix(),
                "disposition": disposition,
                "owner": owner,
                "action": "move-for-compatibility",
                "rollback": "restore-from-private-backup",
            }
        )
    if (values_root.parent / "settings.local.json").is_file():
        operations.append(
            {
                "source": "settings.local.json",
                "destination": "settings.local.json",
                "disposition": "operational-artifact",
                "owner": "private operator/workspace configuration",
                "action": "remove-services-after-migration",
                "rollback": "restore-from-private-backup",
            }
        )
    return {
        "schema_version": 1,
        "source": "legacy-values",
        "canonical_destination": f"sites/{site}",
        "operations": operations,
        "secret_values_included": False,
    }


def site_metadata(repo: Path, site: str, site_class: str, lifecycle: str, allow_apply: bool, allow_destroy: bool) -> dict[str, Any]:
    settings_path = repo / "settings.local.json"
    services: list[str] = []
    if settings_path.is_file():
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SiteMigrationError(f"invalid operator settings: {settings_path}") from error
        candidate = raw.get("services", [])
        if isinstance(candidate, list) and all(isinstance(item, str) for item in candidate):
            services = candidate
    return {
        "name": site,
        "class": site_class,
        "lifecycle": lifecycle,
        "allow_apply": allow_apply,
        "allow_destroy": allow_destroy,
        "services": services,
    }


def migration_items(values_root: Path, target: Path) -> list[tuple[Path, Path]]:
    items: list[tuple[Path, Path]] = []
    for relative in MIGRATED_FILES:
        source = values_root / relative
        if source.is_file() or source.is_dir():
            items.append((source, target / relative))
    for source in sorted(values_root.glob("terraform.tfstate*")):
        if source.is_file():
            items.append((source, target / source.name))
    backups = values_root / "service-backups"
    if backups.is_dir():
        items.append((backups, target / "service-backups"))
    return items


SITE_ARTIFACT_ROOTS = (
    (Path(".env"), "dotenv"),
    (Path("terraform.tfvars"), "tfvars"),
    (Path("ansible/inventory/local.yml"), "inventory"),
    (Path("ansible/known_hosts"), "known-hosts"),
    (Path("dns-records.local.json"), "dns"),
    (Path("terraform.tfstate"), "state"),
    (Path("terraform.tfstate.backup"), "state-backup"),
    (Path("plans"), "plan"),
    (Path("backups"), "backup"),
    (Path("service-backups"), "service-backup"),
    (Path("artifacts"), "artifact"),
)


def site_artifact_inventory(target: Path) -> list[dict[str, str]]:
    inventory: list[dict[str, str]] = []
    for relative, kind in SITE_ARTIFACT_ROOTS:
        path = target / relative
        if path.is_file():
            inventory.append({"path": relative.as_posix(), "kind": kind, "type": "file"})
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and not child.is_symlink():
                    inventory.append({"path": child.relative_to(target).as_posix(), "kind": kind, "type": "file"})
    return inventory
def sensitive_migration_paths(items: list[tuple[Path, Path]], values_root: Path) -> list[str]:
    paths: list[str] = []
    for source, _ in items:
        relative = source.relative_to(values_root)
        if relative in SENSITIVE_MIGRATION_ROOTS:
            paths.append(relative.as_posix())
    return paths
def inspect_existing_site(target: Path, site: str, metadata: dict[str, Any]) -> list[str]:
    site_json = target / "site.json"
    manifest_json = target / "migration-manifest.json"
    if not site_json.is_file() or not manifest_json.is_file():
        raise SiteMigrationError(f"existing site target is incomplete: {target}")
    try:
        existing_metadata = json.loads(site_json.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SiteMigrationError(f"existing site target metadata is invalid: {target}") from error
    if existing_metadata != metadata:
        raise SiteMigrationError(f"existing site target metadata conflicts: {target}")
    if manifest.get("canonical_destination") != f"sites/{site}" or manifest.get("secret_values_included") is not False:
        raise SiteMigrationError(f"existing site target manifest conflicts: {target}")
    artifacts = site_artifact_inventory(target)
    return [
        f"existing site target verified: {target}",
        f"site artifact inventory: {len(artifacts)} files",
        "no-op: site migration is already complete",
    ]
def validate_request(values_root: Path, site: str, metadata: dict[str, Any]) -> tuple[Path, list[tuple[Path, Path]]]:
    if not SITE_NAME_RE.fullmatch(site) or ".." in site:
        raise SiteMigrationError("site must be a simple site identifier")
    if not values_root.is_dir():
        raise SiteMigrationError(f"values root does not exist: {values_root}")
    if (values_root / ".terraform.tfstate.lock.info").exists():
        raise SiteMigrationError("values root has an active Terraform state lock")
    target = values_root / "sites" / site
    if target.exists():
        raise SiteMigrationError(f"site target already exists: {target}")
    items = migration_items(values_root, target)
    if not items:
        raise SiteMigrationError("no legacy values files were found to migrate")
    if not isinstance(metadata.get("services"), list):
        raise SiteMigrationError("site services must be a list")
    return target, items


def remove_services_from_root_settings(repo: Path) -> None:
    path = repo / "settings.local.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("services", None)
    content = json.dumps(data, indent=2, sort_keys=True) + "\n"
    mode = path.stat().st_mode & 0o777
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.name}.migration-", delete=False, encoding="utf-8") as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.chmod(mode)
    try:
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _load_candidate_base(path: Path) -> dict[str, Any]:
    try:
        from ruamel.yaml import YAML

        document = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SiteMigrationError(f"invalid canonical candidate base: {path}") from error
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise SiteMigrationError("canonical candidate base must be a schema_version 1 mapping")
    return document


def _write_candidate(path: Path, candidate: dict[str, Any]) -> None:
    from ruamel.yaml import YAML

    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            YAML().dump(candidate, handle)
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def rollback_migration(
    target: Path,
    moved: list[tuple[Path, Path]],
    settings_path: Path,
    original_settings: bytes | None,
) -> None:
    if original_settings is None:
        settings_path.unlink(missing_ok=True)
    else:
        settings_path.write_bytes(original_settings)
    for source, destination in reversed(moved):
        if destination.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destination), str(source))
    if target.exists():
        shutil.rmtree(target)


def migrate(
    values_root: Path,
    repo: Path,
    site: str,
    site_class: str,
    lifecycle: str,
    allow_apply: bool,
    allow_destroy: bool,
    apply: bool,
    canonical_base: Path | None = None,
    allow_sensitive_artifacts: bool = False,
) -> list[str]:
    metadata = site_metadata(repo, site, site_class, lifecycle, allow_apply, allow_destroy)
    target = values_root / "sites" / site
    if target.exists() and not apply:
        if not SITE_NAME_RE.fullmatch(site) or ".." in site:
            raise SiteMigrationError("site must be a simple site identifier")
        return inspect_existing_site(target, site, metadata)
    target, items = validate_request(values_root, site, metadata)
    sensitive_paths = sensitive_migration_paths(items, values_root)
    if (site_class == "development" or lifecycle == "disposable") and sensitive_paths and not allow_sensitive_artifacts:
        raise SiteMigrationError(
            "development migration refuses sensitive artifacts without explicit opt-in: " + ", ".join(sensitive_paths)
        )
    backup_paths = [source.relative_to(values_root).as_posix() for source, _ in items]
    try:
        backup_manifest = build_manifest(values_root, expand_backup_paths(values_root, backup_paths))
    except BackupManifestError as error:
        raise SiteMigrationError(f"migration backup preflight failed: {error}") from error
    settings_path = repo / "settings.local.json"
    original_settings = settings_path.read_bytes() if settings_path.is_file() else None
    actions = [
        f"preflight private backup manifest for {len(backup_manifest['entries'])} files",
        f"create {target}/site.json",
        f"create {target}/migration-manifest.json",
    ]
    candidate: dict[str, Any] | None = None
    if canonical_base is not None:
        try:
            report = discover_legacy(values_root)
            candidate = build_candidate_site(
                report,
                base_document=_load_candidate_base(canonical_base),
                site_name=site,
                runtime_importer_admission=runtime_importer_admission(report),
            )
        except (DiscoveryError, OSError, SiteMigrationError) as error:
            raise SiteMigrationError(f"canonical candidate generation blocked: {error}") from error
        actions.append(f"create {target}/site.yaml")
    actions.extend(f"move {source} -> {destination}" for source, destination in items)
    if (repo / "settings.local.json").is_file():
        actions.append("remove services from settings.local.json")
    if not apply:
        return actions

    target.mkdir(parents=True)
    moved: list[tuple[Path, Path]] = []
    try:
        (target / "site.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (target / "migration-manifest.json").write_text(
            json.dumps(migration_manifest(site, items, values_root), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if candidate is not None:
            _write_candidate(target / "site.yaml", candidate)
        for source, destination in items:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved.append((source, destination))
        remove_services_from_root_settings(repo)
    except Exception as error:
        try:
            rollback_migration(target, moved, settings_path, original_settings)
        except Exception as rollback_error:
            raise SiteMigrationError(
                "site migration and rollback both failed; restore from the private values backup before retrying"
            ) from rollback_error
        raise SiteMigrationError("site migration failed and was rolled back") from error
    return actions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values-dir", type=Path, default=Path("values"))
    parser.add_argument("--site", required=True)
    parser.add_argument("--class", dest="site_class", default=None)
    parser.add_argument("--lifecycle", default=None)
    parser.add_argument("--allow-destroy", action="store_true")
    parser.add_argument("--allow-sensitive-artifacts", action="store_true", help="allow state, backups, and known-hosts in a development migration")
    parser.add_argument("--canonical-base", type=Path, help="approved canonical YAML base for explicit candidate generation")
    parser.add_argument("--apply", action="store_true", help="perform the migration; default is dry-run")
    args = parser.parse_args(argv)

    disposable_site = args.site == "dev" or args.site.endswith("-dev")
    site_class = args.site_class or ("development" if disposable_site else "production")
    lifecycle = args.lifecycle or ("disposable" if disposable_site else "persistent")
    # Migrating an existing production values tree must not silently disable
    # normal applies; destruction remains opt-in for persistent sites.
    allow_apply = True
    allow_destroy = args.allow_destroy or disposable_site
    try:
        actions = migrate(
            args.values_dir,
            Path.cwd(),
            args.site,
            site_class,
            lifecycle,
            allow_apply,
            allow_destroy,
            args.apply,
            args.canonical_base,
            args.allow_sensitive_artifacts,
        )
    except (OSError, SiteMigrationError, json.JSONDecodeError) as error:
        print(f"site migration failed: {error}", file=sys.stderr)
        return 1
    print("site migration plan:" if not args.apply else "site migration applied:")
    for action in actions:
        print(f"- {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
