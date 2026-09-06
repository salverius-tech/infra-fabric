"""Static and rendered-shell contracts for SSSF managed deployment."""

import os
from pathlib import Path
import pwd
import subprocess
import tempfile
import threading
import time
from typing import Callable, cast
import unittest

from jinja2 import Environment, StrictUndefined
import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "infra/ansible/roles/sssf"
DEFAULTS = ROLE / "defaults/main.yml"
TASKS = ROLE / "tasks/main.yml"
INIT = ROLE / "templates/sssf-init"
CONFIG = ROLE / "templates/sssf.config.yaml.j2"
UNIT = ROLE / "templates/sssf-visualizer.service.j2"
ENV = ROLE / "templates/sssf.env.j2"
HEALTH = ROLE / "templates/sssf-health"


class SssfSupplyChainTests(unittest.TestCase):
    def test_runtime_pins_are_complete_and_checksum_shaped(self) -> None:
        defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
        self.assertEqual(defaults["sssf_artifact_path"], "/var/lib/infra-fabric/artifacts/sssf")
        for tool in ("uv", "pi", "bun", "just"):
            self.assertRegex(defaults[f"sssf_{tool}_version"], r"^\d+\.\d+\.\d+$")
            self.assertRegex(defaults[f"sssf_{tool}_sha256"], r"^[0-9a-f]{64}$")

    def test_role_requires_controller_cached_checksum_verified_archives(self) -> None:
        text = TASKS.read_text(encoding="utf-8")
        tasks = yaml.safe_load(text)
        self.assertNotIn("astral.sh/uv/install.sh", text)
        self.assertNotIn("pi.dev/install.sh", text)
        self.assertNotIn("bun.sh/install", text)
        self.assertNotRegex(text, r"curl[^\n|]*[|]\s*(?:ba)?sh\b")
        self.assertIn("delegate_to: localhost", text)
        self.assertIn("checksum_algorithm: sha256", text)
        self.assertIn("item.stat.checksum == item.item.checksum", text)
        self.assertIn("uv-x86_64-unknown-linux-gnu.tar.gz", text)
        self.assertIn("pi-linux-x64.tar.gz", text)
        self.assertIn("bun-linux-x64.zip", text)
        self.assertIn("just-{{ sssf_just_version }}-amd64", text)
        self.assertIn("dest: /usr/local/bin/just", text)
        self.assertIn("ansible_architecture == 'x86_64'", text)
        self.assertIn("item.tool != 'bun' or sssf_visualizer_enabled | bool", text)
        self.assertIn("not item.skipped | default(false)", text)
        self.assertTrue(any(task.get("name") == "Extract checksum-verified Bun runtime" for task in tasks))

    def test_reviewed_upstream_checkout_is_immutable_to_runtime_user(self) -> None:
        tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
        directories = next(task for task in tasks if task.get("name") == "Ensure SSSF directories exist")
        by_path = {item["path"]: item for item in directories["loop"]}
        for path in ("{{ sssf_data_dir }}", "{{ sssf_data_dir }}/upstream"):
            self.assertEqual(by_path[path]["owner"], "root")
            self.assertEqual(by_path[path]["group"], "root")
        self.assertEqual(by_path["{{ sssf_data_dir }}/factory"]["owner"], "{{ sssf_runtime_user }}")
        checkout = next(task for task in tasks if task.get("name") == "Initialize SSSF upstream checkout")
        command = checkout["ansible.builtin.shell"]
        self.assertIn("git -c safe.directory=\"${upstream}\" -C \"${upstream}\" clean -ffdx", command)
        self.assertIn("chown -R root:root", command)
        self.assertNotIn("chown -R {{ sssf_runtime_user", command)
        self.assertIn("status --porcelain", command)

    def test_visualizer_build_uses_runtime_copy_not_reviewed_checkout(self) -> None:
        tasks = TASKS.read_text(encoding="utf-8")
        unit = UNIT.read_text(encoding="utf-8")
        runtime = "{{ sssf_data_dir }}/factory/visualizer"
        self.assertIn("Copy pinned SSSF visualizer source to runtime directory", tasks)
        self.assertGreaterEqual(tasks.count(runtime), 3)
        self.assertIn(f"WorkingDirectory={runtime}", unit)
        self.assertNotIn("WorkingDirectory={{ sssf_data_dir }}/upstream", unit)

    def test_health_requires_just_for_upstream_workspace_recipes(self) -> None:
        self.assertIn("[ -x /usr/local/bin/just ]", HEALTH.read_text(encoding="utf-8"))

    def test_role_installs_static_empty_pi_custom_model_registry(self) -> None:
        tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
        names = {task.get("name") for task in tasks}
        self.assertNotIn("Refresh Pi model catalog for SSSF runtime", names)
        self.assertNotIn("Generate the model registry expected by SSSF ADWs", names)
        self.assertNotIn(". /etc/sssf/env", TASKS.read_text(encoding="utf-8"))
        registry = next(task for task in tasks if task.get("name") == "Install empty Pi custom model registry")
        copy = registry["ansible.builtin.copy"]
        self.assertEqual(copy["dest"], "/home/{{ sssf_runtime_user }}/.pi/agent/models.json")
        self.assertEqual(copy["content"], '{"providers": {}}\n')
        self.assertEqual(copy["owner"], "{{ sssf_runtime_user }}")
        self.assertEqual(copy["mode"], "0600")

    def test_data_disk_mount_replaces_stale_uuid_and_fails_closed(self) -> None:
        defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
        self.assertEqual(
            defaults["sssf_data_device"],
            "/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi1",
        )
        tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
        source_task = next(task for task in tasks if task.get("name") == "Detect existing SSSF data mount source")
        self.assertEqual(
            source_task["ansible.builtin.command"]["argv"],
            ["findmnt", "-no", "SOURCE", "--mountpoint", "{{ sssf_data_dir }}"],
        )
        normalize_task = next(task for task in tasks if task.get("name") == "Normalize existing SSSF data mount sources")
        normalized = normalize_task["ansible.builtin.set_fact"]["sssf_existing_data_mount_sources"]
        self.assertIn("unique", normalized)
        source_guard = next(task for task in tasks if task.get("name") == "Require at most one SSSF data mount source")
        self.assertIn("length <= 1", "\n".join(source_guard["ansible.builtin.assert"]["that"]))
        effective_task = next(task for task in tasks if task.get("name") == "Select effective SSSF data device")
        self.assertIn("sssf_existing_data_mount_sources", effective_task["ansible.builtin.set_fact"]["sssf_effective_data_device"])
        resolve_task = next(task for task in tasks if task.get("name") == "Resolve effective SSSF data device")
        self.assertEqual(
            resolve_task["ansible.builtin.command"]["argv"],
            ["readlink", "-e", "{{ sssf_effective_data_device }}"],
        )
        guard_task = next(task for task in tasks if task.get("name") == "Reject the root filesystem as SSSF data storage")
        self.assertIn("'/' not in", "\n".join(guard_task["ansible.builtin.assert"]["that"]))
        mkfs_task = next(task for task in tasks if task.get("name") == "Create SSSF data disk filesystem when absent")
        self.assertIn("sssf_existing_data_mount_sources | length == 0", mkfs_task["when"])
        uuid_task = next(task for task in tasks if task.get("name") == "Resolve SSSF data disk UUID")
        self.assertEqual(
            uuid_task["ansible.builtin.command"]["argv"],
            ["blkid", "-s", "UUID", "-o", "value", "{{ sssf_effective_data_device_path.stdout | trim }}"],
        )
        remove_task = next(task for task in tasks if task.get("name") == "Remove stale SSSF data mount entries")
        remove_line = remove_task["ansible.builtin.lineinfile"]
        self.assertEqual(remove_line["state"], "absent")
        self.assertIn("{{ sssf_data_dir | regex_escape }}", remove_line["regexp"])
        self.assertEqual(remove_task["when"], "sssf_existing_data_mount_sources | length == 0")
        persist_task = next(task for task in tasks if task.get("name") == "Persist SSSF data disk mount")
        mount_line = persist_task["ansible.builtin.lineinfile"]
        self.assertTrue(mount_line["line"].startswith("UUID={{ sssf_data_uuid.stdout | trim }} "))
        self.assertEqual(mount_line["insertafter"], "EOF")
        self.assertNotIn("regexp", mount_line)
        self.assertEqual(persist_task["when"], "sssf_existing_data_mount_sources | length == 0")
        mount_task = next(task for task in tasks if task.get("name") == "Mount SSSF data disk")
        self.assertNotEqual(mount_task.get("failed_when"), False)
        self.assertEqual(mount_task["when"], "sssf_existing_data_mount_sources | length == 0")

    def test_init_stamps_factory_then_installs_managed_config_in_upstream_location(self) -> None:
        text = INIT.read_text(encoding="utf-8")
        pinned_skill = "{{ (sssf_data_dir ~ '/upstream/.claude/skills/sssf') | tojson }}"
        installer = "{{ (sssf_data_dir ~ '/upstream/.claude/skills/sssf/scripts/install.py') | tojson }}"
        managed_config = 'workspace / "adws/adw_sssf_config/sssf.config.yaml"'
        self.assertIn(pinned_skill, text)
        self.assertIn('workspace / ".claude/skills/sssf"', text)
        self.assertIn('run([UV, "run", INSTALLER]', text)
        self.assertIn(installer, text)
        self.assertIn(managed_config, text)
        self.assertLess(text.index(installer), text.index(managed_config))
        self.assertNotIn("--force", text)
        self.assertNotIn('workspace / "sssf.config.yaml"', text)

    def test_init_requires_the_non_root_runtime_user_without_privileged_reownership(self) -> None:
        text = INIT.read_text(encoding="utf-8")
        self.assertIn("pwd.getpwuid(os.geteuid()).pw_name != RUNTIME_USER", text)
        self.assertIn("sssf-init must be run as", text)
        self.assertNotIn("runuser", text)
        self.assertNotIn("chown", text)
        self.assertNotIn("install -D", text)
        self.assertNotIn(" -o ", text)
        self.assertNotIn(" -g ", text)

    def test_init_links_managed_environment_and_uses_workspace_config(self) -> None:
        init = INIT.read_text(encoding="utf-8")
        env = ENV.read_text(encoding="utf-8")
        tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
        self.assertIn('environment_link.symlink_to("/etc/sssf/env")', init)
        self.assertIn("workspace .env exists and is not the managed SSSF environment link", init)
        self.assertNotIn("SSSF_CONFIG=", env)
        environment_task = next(task for task in tasks if task.get("name") == "Install SSSF environment file")
        environment_template = environment_task["ansible.builtin.template"]
        self.assertEqual(environment_template["dest"], "/etc/sssf/env")
        self.assertEqual(environment_template["owner"], "root")
        self.assertEqual(environment_template["group"], "{{ sssf_runtime_user }}")
        self.assertEqual(environment_template["mode"], "0640")
        self.assertTrue(environment_task["no_log"])
        for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "FIREWORKS_API_KEY"):
            self.assertIn(key + "=", env)
        self.assertEqual(env.count("| tojson"), 4)

    def test_managed_config_db_matches_visualizer_db(self) -> None:
        template = Environment(undefined=StrictUndefined).from_string(CONFIG.read_text(encoding="utf-8"))
        config = yaml.safe_load(template.render(sssf_provider="openrouter", sssf_data_dir="/var/lib/sssf"))
        self.assertEqual(config["defaults"]["data_dir"], "/var/lib/sssf/factory/adw_data")
        self.assertEqual(config["observability"]["db"], "/var/lib/sssf/factory/adw_data/sssf.db")
        self.assertIn("SSSF_DB={{ sssf_data_dir }}/factory/adw_data/sssf.db", UNIT.read_text(encoding="utf-8"))

    def test_init_workspace_is_single_safe_name_and_blocks_symlink_escape(self) -> None:
        text = INIT.read_text(encoding="utf-8")
        self.assertIn('workspace_name = sys.argv[2] if len(sys.argv) == 3 else normalized.rsplit("/", 1)[-1]', text)
        self.assertIn("workspace name must be a single safe name", text)
        self.assertIn("os.O_NOFOLLOW | os.O_DIRECTORY", text)
        self.assertIn("dir_fd=workspace_root_fd", text)
        self.assertIn('run(["git", "remote", "get-url", "origin"]', text)
        self.assertIn("existing workspace origin does not match", text)
        self.assertNotIn("realpath", text)

    def test_init_rejects_symlinks_in_every_upstream_installer_managed_path(self) -> None:
        text = INIT.read_text(encoding="utf-8")
        self.assertNotIn("rmtree", text)
        self.assertIn("os.walk(adws, followlinks=False)", text)
        for path in (".gitignore", ".env.sample", "justfile"):
            self.assertIn(f'"{path}"', text)
        self.assertIn("installer-managed workspace paths must not contain symlinks", text)
        self.assertIn("existing SSSF skill differs from the reviewed pin", text)

    def test_init_pins_workspace_descriptors_and_landlock_confines_mutations(self) -> None:
        text = INIT.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/usr/bin/env python3\n"))
        self.assertIn("os.O_NOFOLLOW | os.O_DIRECTORY", text)
        self.assertIn("dir_fd=workspace_root_fd", text)
        self.assertIn("pass_fds=(workspace_fd,)", text)
        self.assertIn("LANDLOCK_RULE_PATH_BENEATH", text)
        self.assertIn("landlock_restrict_self", text)
        self.assertIn('cwd=f"/proc/self/fd/{workspace_fd}"', text)
        self.assertIn("def open_absolute_directory_nofollow(path: str) -> int:", text)
        self.assertIn('descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)', text)
        self.assertIn("dir_fd=descriptor", text)

    def test_workspace_root_descriptor_walk_rejects_ancestor_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            safe_parent = root / "safe-parent"
            parked_parent = root / "safe-parent-held"
            external_parent = root / "external-parent"
            safe_workspace_root = safe_parent / "workspaces"
            external_workspace_root = external_parent / "workspaces"
            safe_workspace_root.mkdir(parents=True)
            external_workspace_root.mkdir(parents=True)
            safe_inode = safe_workspace_root.stat().st_ino
            rendered = Environment(undefined=StrictUndefined).from_string(INIT.read_text(encoding="utf-8")).render(
                sssf_runtime_user=pwd.getpwuid(os.geteuid()).pw_name,
                sssf_workspace_root=str(safe_workspace_root),
                sssf_data_dir=str(root),
                sssf_uv_path="/bin/false",
                sssf_config_path=str(root / "config"),
                sssf_allowed_repositories=[],
            )
            namespace = {"__name__": "sssf_init_test"}
            exec(compile(rendered, "sssf-init", "exec"), namespace)
            open_root = cast(Callable[[str], int], namespace["open_absolute_directory_nofollow"])
            stop = threading.Event()

            def swap_ancestor() -> None:
                while not stop.is_set():
                    try:
                        safe_parent.rename(parked_parent)
                        safe_parent.symlink_to(external_parent, target_is_directory=True)
                        safe_parent.unlink()
                        parked_parent.rename(safe_parent)
                    except FileNotFoundError:
                        continue

            racer = threading.Thread(target=swap_ancestor)
            racer.start()
            opened = 0
            try:
                for _ in range(500):
                    try:
                        descriptor = open_root(str(safe_workspace_root))
                    except (FileNotFoundError, NotADirectoryError, OSError):
                        continue
                    try:
                        opened += 1
                        self.assertEqual(os.fstat(descriptor).st_ino, safe_inode)
                    finally:
                        os.close(descriptor)
            finally:
                stop.set()
                racer.join(timeout=5)
            self.assertFalse(racer.is_alive())
            self.assertGreater(opened, 0)

    def test_init_workspace_entry_swap_cannot_modify_external_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspaces = root / "workspaces"
            external = root / "external"
            reviewed_skill = root / "reviewed-skill"
            source = root / "source.git"
            workspaces.mkdir()
            external.mkdir()
            reviewed_skill.mkdir()
            sentinel = external / "sentinel"
            sentinel.write_text("unchanged", encoding="utf-8")
            subprocess.run(["git", "init", "--bare", str(source)], check=True, capture_output=True)
            installer = reviewed_skill / "scripts/install.py"
            installer.parent.mkdir()
            installer.write_text(
                "import pathlib, time\n"
                "time.sleep(0.5)\n"
                "pathlib.Path('adws/adw_sssf_config').mkdir(parents=True, exist_ok=True)\n",
                encoding="utf-8",
            )
            uv = root / "uv"
            uv.write_text("#!/bin/sh\n[ \"$1\" = run ] || exit 2\nshift\nexec python3 \"$@\"\n", encoding="utf-8")
            uv.chmod(0o755)
            managed_config = root / "sssf.config.yaml"
            managed_config.write_text("defaults: {}\n", encoding="utf-8")
            runtime_user = pwd.getpwuid(os.geteuid()).pw_name
            rendered = Environment(undefined=StrictUndefined).from_string(INIT.read_text(encoding="utf-8")).render(
                sssf_runtime_user=runtime_user,
                sssf_workspace_root=str(workspaces),
                sssf_data_dir=str(root),
                sssf_uv_path=str(uv),
                sssf_config_path=str(managed_config),
                sssf_allowed_repositories=[str(source)],
            )
            # The reviewed skill is addressed through sssf_data_dir in production.
            expected_skill = root / "upstream/.claude/skills/sssf"
            expected_skill.parent.mkdir(parents=True)
            reviewed_skill.rename(expected_skill)
            script = root / "sssf-init"
            script.write_text(rendered, encoding="utf-8")
            script.chmod(0o755)
            workspace = workspaces / "race"
            parked = workspaces / "race-held"

            def swap_entry() -> None:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if (workspace / ".git").exists():
                        workspace.rename(parked)
                        workspace.symlink_to(external, target_is_directory=True)
                        return
                    time.sleep(0.005)

            racer = threading.Thread(target=swap_entry)
            racer.start()
            result = subprocess.run(
                [str(script), str(source), "race"],
                text=True,
                capture_output=True,
                env={**os.environ, "USER": runtime_user, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
            )
            racer.join(timeout=6)
            self.assertFalse(racer.is_alive())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")
            self.assertFalse((external / "adws").exists())
            self.assertFalse((external / ".git").exists())
            self.assertIn(result.returncode, {0, 1})
            if result.returncode == 0:
                self.assertTrue((parked / "adws/adw_sssf_config/sssf.config.yaml").is_file())

    def test_managed_roster_is_complete_provider_qualified_and_has_boundaries(self) -> None:
        template = Environment(undefined=StrictUndefined).from_string(CONFIG.read_text(encoding="utf-8"))
        expected_models = {
            "openrouter": "openrouter/google/gemini-3.6-flash",
            "openai": "openai/gpt-5.6-terra",
            "fireworks": "fireworks/accounts/fireworks/models/kimi-k3",
        }
        for provider, model in expected_models.items():
            config = yaml.safe_load(template.render(sssf_provider=provider, sssf_data_dir="/var/lib/sssf"))
            defaults = config["defaults"]
            self.assertEqual(defaults["model"], model)
            self.assertTrue(defaults["model"].startswith(f"{provider}/"))
            self.assertEqual(
                [agent["name"] for agent in config["agents"]],
                ["planner", "builder", "scout", "reviewer", "documenter"],
            )
            self.assertTrue(all("model" not in agent for agent in config["agents"]))
            by_name = {agent["name"]: agent for agent in config["agents"]}
            self.assertEqual(by_name["scout"]["writes"], [])
            self.assertEqual(by_name["reviewer"]["writes"], [])
            self.assertEqual(by_name["documenter"]["writes"], ["app_docs/", "docs/", "**/*.md", "*.md"])
            self.assertNotIn("writes", by_name["builder"])
            self.assertNotIn("edit", by_name["reviewer"]["tools"])
            self.assertIn("write", by_name["scout"]["tools"])
            self.assertIn("subagent_create", by_name["planner"]["tools"])
            self.assertIn("subagent_create", by_name["scout"]["tools"])

    def test_visualizer_builds_ui_and_runs_upstream_server_with_db_and_port(self) -> None:
        tasks = TASKS.read_text(encoding="utf-8")
        unit = UNIT.read_text(encoding="utf-8")
        self.assertIn("Build SSSF visualizer UI", tasks)
        self.assertIn("- build", tasks)
        self.assertIn("SSSF_DB={{ sssf_data_dir }}/factory/adw_data/sssf.db", unit)
        self.assertIn("PORT={{ sssf_visualizer_port }}", unit)
        self.assertIn("bun run server/index.ts", unit)
        self.assertIn("IPAddressDeny=any", unit)
        self.assertIn("IPAddressAllow=localhost", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", unit)
        self.assertNotIn(" bun run --cwd", unit)
        self.assertNotIn(" vite", unit)

    def test_visualizer_health_checks_the_upstream_api(self) -> None:
        health = HEALTH.read_text(encoding="utf-8")
        self.assertIn("/api/health", health)
        self.assertIn('payload.get("ok") is not True', health)
        tasks = (ROLE / "tasks/main.yml").read_text(encoding="utf-8")
        self.assertIn("Run SSSF health check", tasks)
        self.assertIn("argv: [/usr/local/bin/sssf-health]", tasks)
        self.assertIn("changed_when: false", tasks)

    def test_role_has_no_unsupported_concurrency_or_command_knobs(self) -> None:
        defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
        specs = yaml.safe_load((ROLE / "meta/argument_specs.yml").read_text(encoding="utf-8"))
        options = specs["argument_specs"]["main"]["options"]
        for key in ("sssf_max_concurrent_runs", "sssf_visualizer_command"):
            self.assertNotIn(key, defaults)
            self.assertNotIn(key, options)
            self.assertNotIn(key, TASKS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
