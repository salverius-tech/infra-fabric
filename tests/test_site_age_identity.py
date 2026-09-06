"""Integration tests for the site age-identity lifecycle.

Exercises ``scripts/site-age-identity.sh`` and the ``just site-identity``
recipe as behavioral contracts.  ``op``, ``age-keygen`` and ``sops`` are mocked
via ``PATH``; all state is fully synthetic.  No real op/sops/age/infra is
invoked and no secrets are read or printed.

Mocks encode the *real* CLI shapes:
  * age-keygen is called as ``age-keygen -y FILE`` (positional file), not the
    obsolete ``-i`` inverse form, and only accepts an exact synthetic fixture
    (a full ``AGE-SECRET-KEY-1...`` line), rejecting truncated key prefixes.
  * op item/list/get/create/edit return synthetic JSON.  IDs are a
    deterministic counter (no randomness).  Failures are injected by env knobs
    and, where order matters, by an op call counter (``OP_MOCK_FAIL_ON``).

The implementation deliberately never deletes a vault item: stores migrate the
old item under a ``.previous-*`` title instead. Tests assert the prior item's
ID/title/contents are preserved and that no ``op item delete`` is ever issued.

Windows ``python3`` (a broken store alias) skips the whole module; that is not
evidence of a passing/failing suite. On the Linux runtime, ``just`` may be
absent and its tests are skipped and reported clearly.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "site-age-identity.sh"

SENTINEL = "OP0_SENTINEL_SECRET_a9b2"
OP_VAULT = "mock-vault"


# --------------------------------------------------------------------------- #
# Runtime probes (sidecar: bash + real python3 in a subprocess) ------------- #
# --------------------------------------------------------------------------- #
def _env_has_bash() -> bool:
    try:
        return subprocess.run(["bash", "-c", "true"], timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _env_has_python3() -> bool:
    if not _env_has_bash():
        return False
    try:
        r = subprocess.run(
            ["bash", "-c", 'command -v python3 >/dev/null && python3 -c "print(1)"'],
            capture_output=True,
            timeout=15,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


BASH_AND_PY = os.name == "posix" and _env_has_bash() and _env_has_python3()
JUST_AVAILABLE = BASH_AND_PY and shutil.which("just") is not None


# --------------------------------------------------------------------------- #
# Mock executables ---------------------------------------------------------- #
# --------------------------------------------------------------------------- #
MOCK_OP = r"""#!/usr/bin/env python3
import json, os, sys

state = os.environ.get("OP_MOCK_STATE", "")
logf = os.environ.get("OP_MOCK_LOG", "")
items_dir = os.path.join(state, "items") if state else ""

# Failure injection (call-counter based when OP_MOCK_FAIL_ON is set).
FAIL_GET = os.environ.get("OP_MOCK_FAIL_GET")
FAIL_LIST = os.environ.get("OP_MOCK_FAIL_LIST")
FAIL_CREATE = os.environ.get("OP_MOCK_FAIL_CREATE")
FAIL_EDIT = os.environ.get("OP_MOCK_FAIL_EDIT")
FAIL_ON = os.environ.get("OP_MOCK_FAIL_ON")
GET_EMPTY = os.environ.get("OP_MOCK_GET_EMPTY")
CORRUPT_STAGE_GET = os.environ.get("OP_MOCK_CORRUPT_STAGE_GET")
ROTATE_PATH = os.environ.get("OP_MOCK_ROTATE_PATH")
ROTATE_CONTENT = os.environ.get("OP_MOCK_ROTATE_CONTENT")

CORRUPT_NOTE = (
    "# created: 2038-01-19T03:14:07Z\n"
    "# public key: age1mockCORRUPTREADBACK\n"
    "AGE-SECRET-KEY-1CORRUPTEDREADBACKSAMPLEQZz0\n"
)

SENTINEL = os.environ.get("OP_MOCK_SENTINEL", "OP0_SENTINEL_SECRET_a9b2")


def _read_meta(name):
    p = os.path.join(state, name)
    if state and os.path.exists(p):
        try:
            return int(open(p, encoding="utf-8").read().strip() or "0")
        except (OSError, ValueError):
            return 0
    return 0


def _write_meta(name, val):
    os.makedirs(state, exist_ok=True)
    with open(os.path.join(state, name), "w", encoding="utf-8") as fh:
        fh.write(str(val))


def bump(name):
    cur = _read_meta(name)
    _write_meta(name, cur + 1)
    return cur + 1


def log(*parts):
    if logf:
        try:
            with open(logf, "a", encoding="utf-8") as fh:
                fh.write(" ".join(str(p) for p in parts) + "\n")
        except OSError:
            pass


def loadall():
    out = []
    if not items_dir or not os.path.isdir(items_dir):
        return out
    for name in os.listdir(items_dir):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(items_dir, name), encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, ValueError):
            continue
    return out


def save(item):
    os.makedirs(items_dir, exist_ok=True)
    with open(os.path.join(items_dir, item["id"] + ".json"), "w", encoding="utf-8") as fh:
        json.dump(item, fh)


def resolve(ref):
    items = loadall()
    byid = [i for i in items if i["id"] == ref]
    if byid:
        return byid[0]
    bytitle = [i for i in items if i["title"] == ref]
    if len(bytitle) == 1:
        return bytitle[0]
    return "AMBIGUOUS" if bytitle else None


def notes_value(item):
    if GET_EMPTY:
        return ""
    for fld in item.get("fields", []):
        if fld.get("id") == "notesPlain" or fld.get("label") == "notes":
            return fld.get("value") or ""
    return ""


def opt(args, flag):
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            return args[i + 1]
    return ""


def has_json(args):
    if "--json" in args:
        return True
    for i, a in enumerate(args):
        if a in ("--format", "-f") and i + 1 < len(args) and args[i + 1] == "json":
            return True
    return False


def nonflag(args):
    for a in args:
        if not a.startswith("--"):
            return a
    return ""


def err(msg, code=1):
    sys.stderr.write(msg + " " + SENTINEL + "\n")
    sys.exit(code)


def want_fail(flag, cn):
    if FAIL_ON:
        try:
            return int(FAIL_ON) == cn
        except ValueError:
            return False
    return bool(flag)


def call_no():
    return bump("callno")


log("op", *sys.argv[1:])
args = sys.argv[1:]
if not args:
    err("op mock: no command", 2)
cn = call_no()

if args[0] == "whoami":
    sys.stdout.write("mock-user\n")
    sys.exit(0)

if args[0] != "item":
    err("op: unsupported command %r" % args[0], 2)

sub = args[1] if len(args) > 1 else ""
tail = args[2:]

if sub == "list":
    if want_fail(FAIL_LIST, cn):
        err("op: item list failed (mocked)", 4)
    # Test-only concurrent rotation: list occurs after store's local snapshot.
    if ROTATE_PATH and ROTATE_CONTENT is not None:
        replacement = ROTATE_PATH + ".rotating"
        with open(replacement, "w", encoding="utf-8") as fh:
            fh.write(ROTATE_CONTENT)
        os.chmod(replacement, 0o600)
        os.replace(replacement, ROTATE_PATH)
    if has_json(tail):
        print(json.dumps(loadall()))
    else:
        for it in loadall():
            print("\t".join([it["id"], it["title"], it.get("category", "SECURE_NOTE")]))
    sys.exit(0)

if sub == "create":
    if want_fail(FAIL_CREATE, cn):
        err("op: item create failed (mocked)", 4)
    template_p = opt(tail, "--template")
    explicit_title = opt(tail, "--title")
    data = {}
    if template_p:
        with open(template_p, encoding="utf-8") as fh:
            data = json.load(fh)
    item = {
        "id": "c" + str(_read_meta("idc")).zfill(25),
        "title": data.get("title") or explicit_title or "",
        "category": data.get("category") or "SECURE_NOTE",
        "fields": data.get("fields") or [],
    }
    _write_meta("idc", _read_meta("idc") + 1)
    save(item)
    print(json.dumps(item))
    sys.exit(0)

if sub == "get":
    if want_fail(FAIL_GET, cn):
        err("op: item get failed (mocked)", 4)
    ref = nonflag(tail)
    item = resolve(ref)
    if isinstance(item, str):
        err("op: ambiguous or missing reference", 1 if item is None else 5)
    if has_json(tail):
        fields = item.get("fields", [])
        if CORRUPT_STAGE_GET and ".stage-" in item.get("title", ""):
            # Simulate a corrupted readback: a valid identity that does NOT
            # match what was written, so byte-compare fails after create.
            fields = [{"id": "notesPlain", "type": "STRING", "purpose": "NOTES",
                       "value": CORRUPT_NOTE, "label": "notes"}]
        print(json.dumps({"id": item["id"], "title": item["title"], "fields": fields}))
    else:
        print("ID:\t%s\nTITLE:\t%s" % (item["id"], item["title"]))
    sys.exit(0)

if sub == "edit":
    if want_fail(FAIL_EDIT, cn):
        err("op: item edit failed (mocked)", 4)
    ref = nonflag(tail)
    new_title = opt(tail, "--title")
    item = resolve(ref)
    if isinstance(item, str):
        err("op: reference unresolved", 1)
    item["title"] = new_title
    save(item)
    sys.exit(0)

if sub == "delete":
    err("op: delete called (tests require no deletion)", 9)

err("op: unsupported item subcommand %r" % sub, 2)
"""

MOCK_AGE_KEYGEN = r"""#!/usr/bin/env bash
set -euo pipefail

# Age keys look like:  AGE-SECRET-KEY-1 + 30 base32 chars.  We accept only an
# exact synthetic fixture with a full body, and reject any truncated prefix.
VALID_KEY_LINE='^AGE-SECRET-KEY-1[A-Za-z0-9]{20,}$'

case "${1:-}" in
  -y)
    file="${2:-}"
    # REAL age-keygen syntax is '-y FILE'; never -i.  If the argument is the
    # obsolete '-i' (or not an existing readable file) reject it.
    if [[ "${file}" == "-i" || ! -f "${file}" || ! -r "${file}" ]]; then
      printf 'age-keygen: invalid identity source: %s\n' "${file}" >&2
      exit 2
    fi
    if ! grep -qE "${VALID_KEY_LINE}" "${file}"; then
      printf 'age-keygen: not a valid synthetic age secret key\n' >&2
      exit 2
    fi
    printf 'age1mockpublickeyzSAMPLE00000000000000000000000000000\n'
    ;;
  -o)
    out="${2:?age-keygen -o FILE}"
    mkdir -p "$(dirname "${out}")"
    cat > "${out}" <<'ENE'
# created: 2038-01-19T03:14:07Z
# public key: age1POPCK0000000000000000SSSS0000000000000000000000SAMPLE
AGE-SECRET-KEY-1SAMPLEKEYMOCKQ3aX4y4pSAMPLEQZz0
ENE
    ;;
  *)
    printf 'age-keygen mock: unsupported args: %s\n' "$*" >&2
    exit 3
    ;;
esac
"""

MOCK_SOPS = "#!/usr/bin/env bash\nexit 0\n"


def _install(bin_dir: Path, name: str, source: str) -> None:
    p = bin_dir / name
    p.write_text(source, encoding="utf-8")
    p.chmod(0o755)


# Synthetic age secret fixture: header + one valid key line. The key body is
# exactly the length the mock accepts; truncating it (see tests) must be
# rejected by age-keygen.
def _age_secret(marker: str) -> str:
    body = (marker.replace("_", "").replace("-", "") + "SAMPLEKEYBODY" * 4)[:24]
    return (
        "# created: 2038-01-19T03:14:07Z\n"
        "# public key: age1mock%s\n"
        "AGE-SECRET-KEY-1%s\n"
        "# tail\n"
    ) % (marker, body)


def _truncated_secret(marker: str) -> str:
    body = (marker.replace("-", "") + "SAMPLEKEYBODY" * 4)[:7]  # short => invalid
    return (
        "AGE-SECRET-KEY-1%s\n" % body
    )


def _note(title: str, notes: str, include_notes: bool = True) -> dict:
    fields = []
    if include_notes:
        fields.append(
            {
                "id": "notesPlain",
                "type": "STRING",
                "purpose": "NOTES",
                "value": notes,
                "label": "notes",
            }
        )
    return {"title": title, "category": "SECURE_NOTE", "fields": fields}


def _canonical_title(site: str) -> str:
    return f"infra-fabric-site-age-identity-{site}"


class SiteAgeIntegrationBase(unittest.TestCase):
    maxDiff = 8000

    def setUp(self) -> None:
        if not BASH_AND_PY:
            self.skipTest("requires a functional python3 in a bash subprocess")
        self._tmp = tempfile.TemporaryDirectory(prefix="site-id-test-")
        self.td = Path(self._tmp.name)
        self.home = self.td / "home"
        self.home.mkdir()
        self.bin = self.td / "bin"
        self.bin.mkdir()
        self.runtime = self.td / "runtime"
        self.runtime.mkdir()
        self.vault = self.td / "vault"
        self.vault.mkdir()
        (self.vault / "items").mkdir()
        self.log_file = self.td / "op.calls"
        for name, src in (("op", MOCK_OP), ("age-keygen", MOCK_AGE_KEYGEN), ("sops", MOCK_SOPS)):
            _install(self.bin, name, src)

    def tearDown(self) -> None:
        if self._tmp is not None:
            try:
                self._tmp.cleanup()
            except OSError:
                pass

    # -- site layout ------------------------------------------------------- #
    def keys_dir(self, site: str) -> Path:
        return self.home / ".config" / "infra-fabric" / "keys" / site

    def make_site(self, site: str) -> None:
        vals = self.td / "vals" / "sites" / site
        vals.mkdir(parents=True, exist_ok=True)
        (vals / "site.yaml").write_text(f"schema_version: 1\nname: {site}\n", encoding="utf-8")
        (vals / ".sops.yaml").write_text("creation_rules: []\n", encoding="utf-8")
        (vals / "secrets.sops.yaml").write_text("ENC[AGE]--\n", encoding="utf-8")
        self.keys_dir(site).mkdir(parents=True, exist_ok=True)

    def identity_file(self, site: str) -> Path:
        return self.keys_dir(site) / "site.age"

    def seed_identity(self, site: str, content: str, mode: int = 0o600) -> Path:
        p = self.identity_file(site)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        p.chmod(mode)
        return p

    # -- synthetic 1Password vault ----------------------------------------- #
    def seed_vault(self, title: str, notes: str, include_notes: bool = True) -> dict:
        item = _note(title, notes, include_notes)
        item["id"] = "s" + str(len(self.items_json())).zfill(25)
        with open(self.vault / "items" / f"{item['id']}.json", "w", encoding="utf-8") as fh:
            json.dump(item, fh)
        return item

    def seed_canonical(self, site: str, notes: str, include_notes: bool = True) -> dict:
        return self.seed_vault(_canonical_title(site), notes, include_notes)

    def items_json(self) -> list[dict]:
        out = []
        for p in sorted((self.vault / "items").glob("*.json")):
            out.append(json.loads(p.read_text(encoding="utf-8")))
        return out

    def find_by_title(self, title: str) -> list[dict]:
        return [i for i in self.items_json() if i["title"] == title]

    def notes_of(self, item: dict) -> str:
        for fld in item.get("fields", []):
            if fld.get("id") == "notesPlain" or fld.get("label") == "notes":
                return fld.get("value") or ""
        return ""

    def op_calls(self) -> list[str]:
        if not self.log_file.exists():
            return []
        return self.log_file.read_text(encoding="utf-8").splitlines()

    def delete_issued(self) -> list[str]:
        return [line for line in self.op_calls() if " delete " in line or " delete" in line]

    def assert_op_called(self, *parts: str) -> None:
        calls = [c.split()[1:] for c in self.op_calls()]
        self.assertTrue(
            any(call[: len(parts)] == list(parts) for call in calls),
            f"expected op {' '.join(parts)} to be attempted; got {self.op_calls()}",
        )

    def staging_leftovers(self) -> list[str]:
        found = []
        for root, dirs, files in os.walk(self.td):
            for d in dirs:
                if d.startswith(".staging") or d == "site-identity":
                    found.append(os.path.join(root, d))
        return found

    def assert_no_staging(self) -> None:
        self.assertEqual(self.staging_leftovers(), [], "sensitive staging dirs leaked")

    # -- environment / subprocess ------------------------------------------ #
    def base_env(self, site: str | None, extra: dict | None = None) -> dict:
        env = {
            "HOME": str(self.home),
            "PATH": str(self.bin) + os.pathsep + (os.environ.get("PATH") or ""),
            "VALUES_DIR": str(self.td / "vals"),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "OP_VAULT": OP_VAULT,
            "OP_MOCK_STATE": str(self.vault),
            "OP_MOCK_LOG": str(self.log_file),
            "OP_MOCK_SENTINEL": SENTINEL,
            "LANG": "C",
        }
        if site:
            env["VALUES_SITE"] = site
        for key, val in (extra or {}).items():
            if val is None:
                env.pop(key, None)
            else:
                env[str(key)] = str(val)
        return env

    def run_helper(self, site, action, *args, cwd=None, extra_env=None) -> subprocess.CompletedProcess[str]:
        env = self.base_env(site, extra_env)
        return subprocess.run(
            [str(HELPER), action, *args],
            cwd=cwd or ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=60,
        )

    def run_just(self, action, *args, site=None, extra_env=None, just_vars=None) -> subprocess.CompletedProcess[str]:
        base = self.base_env(site, extra_env)
        cmd = ["just"]
        for k, v in (just_vars or {}).items():
            cmd.append(f"{k}={v}")
        cmd += ["site-identity", action, *args]
        return subprocess.run(cmd, cwd=ROOT, env=base, text=True, capture_output=True, timeout=60)


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #
@unittest.skipUnless(BASH_AND_PY, "requires bash + functional python3 in a subprocess")
class SiteAgeFetchTests(SiteAgeIntegrationBase):
    def test_mock_op_embeds_valid_python(self) -> None:
        compile(MOCK_OP, "<mock op>", "exec")

    def test_fetch_get_failure_preserves_original(self) -> None:
        # fetch reads the canonical item via `op item get` (never the obsolete
        # `op read`). Inject the failure, seed the vault AND an existing local
        # identity, and require get to actually be attempted.
        site, marker = "acme", "PRESERVE"
        self.make_site(site)
        original = _age_secret(marker)
        self.seed_identity(site, original)
        self.seed_canonical(site, _age_secret("STORED"))
        result = self.run_helper(site, "fetch", "--force", extra_env={"OP_MOCK_FAIL_GET": "1"})
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_op_called("item", "get")
        self.assertEqual(self.identity_file(site).read_text(encoding="utf-8"), original)
        self.assertEqual(stat.S_IMODE(self.identity_file(site).stat().st_mode), 0o600)
        self.assertNotIn(SENTINEL, result.stdout + result.stderr)

    def test_fetch_get_failure_leaves_fresh_absent(self) -> None:
        site = "acme"
        self.make_site(site)
        self.seed_canonical(site, _age_secret("NEW"))
        r = self.run_helper(site, "fetch", "--force", extra_env={"OP_MOCK_FAIL_GET": "1"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_op_called("item", "get")
        self.assertFalse(self.identity_file(site).exists())
        self.assertNotIn(SENTINEL, r.stdout + r.stderr)

    def test_fetch_default_refuses_to_overwrite_existing(self) -> None:
        site = "acme"
        self.make_site(site)
        original = _age_secret("KEEP")
        self.seed_identity(site, original)
        self.seed_canonical(site, _age_secret("NEW"))
        r = self.run_helper(site, "fetch")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("force", (r.stdout + r.stderr).lower())
        self.assertEqual(self.identity_file(site).read_text(encoding="utf-8"), original)

    def test_fetch_success_exact_bytes_mode_0600_and_suppressed_sentinel(self) -> None:
        site = "acme"
        self.make_site(site)
        notes = _age_secret("FETCHED") + "# extra-line\n"
        self.seed_canonical(site, notes)
        r = self.run_helper(site, "fetch", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        p = self.identity_file(site)
        self.assertEqual(p.read_text(encoding="utf-8"), notes)
        self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        self.assertNotIn(SENTINEL, r.stdout + r.stderr)

    def test_fetch_corrupt_readback_fails_and_preserves_original(self) -> None:
        site = "acme"
        self.make_site(site)
        original = _age_secret("ORIG")
        self.seed_identity(site, original)
        self.seed_canonical(site, "this is absolutely not an age secret key\n")
        r = self.run_helper(site, "fetch", "--force")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.identity_file(site).read_text(encoding="utf-8"), original)
        self.assertNotIn(SENTINEL, r.stdout + r.stderr)

    def test_fetch_missing_notesPlain_fails(self) -> None:
        site = "acme"
        self.make_site(site)
        original = _age_secret("ORIG2")
        self.seed_identity(site, original)
        self.seed_canonical(site, _age_secret("HIDDEN"), include_notes=False)
        r = self.run_helper(site, "fetch", "--force")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.identity_file(site).read_text(encoding="utf-8"), original)

    def test_fetch_missing_item_fails_closed(self) -> None:
        site = "acme"
        self.make_site(site)
        original = _age_secret("ORIG3")
        self.seed_identity(site, original)
        r = self.run_helper(site, "fetch", "--force")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.identity_file(site).read_text(encoding="utf-8"), original)
        self.assertNotIn(SENTINEL, r.stdout + r.stderr)

    def test_fetch_force_rejects_symlink_destination_preserves_target(self) -> None:
        # A symlink at the identity path must be rejected by force fetch, and
        # the symlink target must be left untouched (never followed/overwritten).
        site = "acme"
        self.make_site(site)
        self.seed_canonical(site, _age_secret("STORED"))
        target = self.td / "outside-target"
        target.write_text(_age_secret("TARGET"), encoding="utf-8")
        link = self.identity_file(site)
        link.symlink_to(target)
        r = self.run_helper(site, "fetch", "--force")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(link.is_symlink(), "symlink must remain in place")
        self.assertEqual(target.read_text(encoding="utf-8"), _age_secret("TARGET"))
        self.assertNotIn(SENTINEL, r.stdout + r.stderr)

    def test_fetch_duplicate_ambiguous_title_fails(self) -> None:
        site = "acme"
        self.make_site(site)
        title = _canonical_title(site)
        self.seed_vault(title, _age_secret("copy-a"))
        self.seed_vault(title, _age_secret("copy-b"))
        r = self.run_helper(site, "fetch", "--force")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.identity_file(site).exists())

    def test_fetch_truncated_key_prefix_rejected(self) -> None:
        site = "acme"
        self.make_site(site)
        original = _age_secret("ORIG")
        self.seed_identity(site, original)
        self.seed_canonical(site, _truncated_secret("TRUNC"))
        r = self.run_helper(site, "fetch", "--force")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.identity_file(site).read_text(encoding="utf-8"), original)

    def test_fetch_failure_cleans_staging_entire_tree(self) -> None:
        site = "acme"
        self.make_site(site)
        self.seed_identity(site, _age_secret("S"))
        self.seed_canonical(site, _age_secret("STORED"))
        r = self.run_helper(site, "fetch", "--force", extra_env={"OP_MOCK_FAIL_GET": "1"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_op_called("item", "get")
        self.assert_no_staging()


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #
@unittest.skipUnless(BASH_AND_PY, "Bash + python3 subprocess")
class SiteAgeStoreTests(SiteAgeIntegrationBase):
    def test_store_success_publishes_canonical_exact_bytes(self) -> None:
        site = "acme"
        self.make_site(site)
        new = _age_secret("NEW")
        self.seed_identity(site, new)
        r = self.run_helper(site, "store")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        matches = self.find_by_title(_canonical_title(site))
        self.assertEqual(len(matches), 1)
        self.assertEqual(self.notes_of(matches[0]), new)
        self.assertEqual(self.delete_issued(), [], "store must never delete an item")
        self.assertNotIn(SENTINEL, r.stdout + r.stderr)

    def test_store_uses_initial_snapshot_when_identity_rotates_during_list(self) -> None:
        site = "acme"
        self.make_site(site)
        initial, rotated = _age_secret("INITIAL"), _age_secret("ROTATED")
        identity = self.seed_identity(site, initial)
        r = self.run_helper(site, "store", extra_env={
            "OP_MOCK_ROTATE_PATH": str(identity),
            "OP_MOCK_ROTATE_CONTENT": rotated,
        })
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        canonical = self.find_by_title(_canonical_title(site))
        self.assertEqual(len(canonical), 1)
        self.assertEqual(self.notes_of(canonical[0]), initial)
        self.assertEqual(identity.read_text(encoding="utf-8"), rotated)
        self.assert_no_staging()
        self.assertNotIn(SENTINEL, r.stdout + r.stderr)

    def test_store_missing_or_symlink_identity_fails_closed(self) -> None:
        site = "acme"
        self.make_site(site)
        missing = self.run_helper(site, "store")
        self.assertNotEqual(missing.returncode, 0, missing.stdout + missing.stderr)
        target = self.td / "identity-target"
        target.write_text(_age_secret("TARGET"), encoding="utf-8")
        self.identity_file(site).symlink_to(target)
        linked = self.run_helper(site, "store")
        self.assertNotEqual(linked.returncode, 0, linked.stdout + linked.stderr)
        self.assertEqual(target.read_text(encoding="utf-8"), _age_secret("TARGET"))
        self.assertNotIn(SENTINEL, missing.stdout + missing.stderr + linked.stdout + linked.stderr)

    def test_store_readback_failure_keeps_prior_retains_staged(self) -> None:
        # A failed readback after create must leave the prior canonical item
        # byte-identical. The staged item may remain (store never deletes), so
        # we assert preservation of old id+title+contents, not a bare count.
        site = "acme"
        self.make_site(site)
        old = _age_secret("OLD")
        old_item = self.seed_canonical(site, old)
        self.seed_identity(site, _age_secret("NEW"))
        r = self.run_helper(site, "store", "--force", extra_env={"OP_MOCK_FAIL_ON": "4"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_op_called("item", "get")
        current = [i for i in self.items_json() if i["title"] == _canonical_title(site)]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["id"], old_item["id"])
        self.assertEqual(current[0]["title"], _canonical_title(site))
        self.assertEqual(self.notes_of(current[0]), old)
        self.assertEqual(self.delete_issued(), [])

    def test_store_without_force_refuses_existing_vault_no_create_edit(self) -> None:
        # Existing canonical item + no --force must refuse without issuing any
        # create or edit, leaving the vault item byte-identical.
        site = "acme"
        self.make_site(site)
        old = _age_secret("OLD")
        old_item = self.seed_canonical(site, old)
        self.seed_identity(site, _age_secret("NEW"))
        r = self.run_helper(site, "store")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(" create ", " ".join(self.op_calls()) + " ")
        self.assertNotIn(" edit ", " ".join(self.op_calls()) + " ")
        current = self.find_by_title(_canonical_title(site))
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["id"], old_item["id"])
        self.assertEqual(self.notes_of(current[0]), old)
        self.assertEqual(self.delete_issued(), [])

    def test_store_corrupt_stage_readback_preserves_old_before_rename(self) -> None:
        # A corrupted readback of the freshly created staged item (mock get
        # returns a valid-but-wrong identity) must abort BEFORE any rename, so
        # the old canonical item keeps its id/title/contents.
        site = "acme"
        self.make_site(site)
        old = _age_secret("OLD")
        old_item = self.seed_canonical(site, old)
        self.seed_identity(site, _age_secret("NEW"))
        r = self.run_helper(site, "store", "--force",
                            extra_env={"OP_MOCK_CORRUPT_STAGE_GET": "1"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_op_called("item", "get")
        current = self.find_by_title(_canonical_title(site))
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["id"], old_item["id"])
        self.assertEqual(current[0]["title"], _canonical_title(site))
        self.assertEqual(self.notes_of(current[0]), old)
        self.assertEqual(self.delete_issued(), [])

    def test_store_list_error_fails_closed(self) -> None:
        site = "acme"
        self.make_site(site)
        old_item = self.seed_canonical(site, _age_secret("OLD"))
        self.seed_identity(site, _age_secret("NEW"))
        r = self.run_helper(site, "store", "--force", extra_env={"OP_MOCK_FAIL_LIST": "1"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_op_called("item", "list")
        self.assertEqual([i for i in self.items_json() if i.get("title") == _canonical_title(site)][0]["id"],
                         old_item["id"])
        self.assertEqual(self.delete_issued(), [])

    def test_store_duplicate_canonical_fails_closed(self) -> None:
        site = "acme"
        self.make_site(site)
        title = _canonical_title(site)
        a = self.seed_vault(title, _age_secret("dupA"))
        b = self.seed_vault(title, _age_secret("dupB"))
        self.seed_identity(site, _age_secret("NEW"))
        r = self.run_helper(site, "store", "--force")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_op_called("item", "list")
        by_title = self.find_by_title(title)
        self.assertEqual({i["id"] for i in by_title}, {a["id"], b["id"]})
        self.assertEqual(self.delete_issued(), [])

    def test_store_forced_archives_old_and_publishes_new(self) -> None:
        site = "acme"
        self.make_site(site)
        title = _canonical_title(site)
        old = _age_secret("OLD")
        old_item = self.seed_canonical(site, old)
        new = _age_secret("NEW")
        self.seed_identity(site, new)
        r = self.run_helper(site, "store", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        items = self.items_json()
        self.assertEqual(len(items), 2, [i["title"] for i in items])
        canonical = self.find_by_title(title)
        self.assertEqual(len(canonical), 1)
        self.assertEqual(self.notes_of(canonical[0]), new)
        archived = [i for i in items if i["title"] != title]
        self.assertEqual(len(archived), 1)
        self.assertEqual(self.notes_of(archived[0]), old)
        # the archived item keeps the OLD id (renamed, never deleted).
        self.assertEqual(archived[0]["id"], old_item["id"])
        self.assertNotIn(SENTINEL, r.stdout + r.stderr)

    def test_store_edit_archive_failure_keeps_old_and_does_not_delete(self) -> None:
        # Call 5 = rename_item(current -> backup). On failure the old canonical
        # item must be untouched byte-for-byte and nothing deleted.
        site = "acme"
        self.make_site(site)
        old = _age_secret("OLD")
        old_item = self.seed_canonical(site, old)
        new = _age_secret("NEW")
        self.seed_identity(site, new)
        r = self.run_helper(site, "store", "--force", extra_env={"OP_MOCK_FAIL_ON": "5"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_op_called("item", "edit")
        target = self.find_by_title(_canonical_title(site))
        self.assertEqual(len(target), 1)
        self.assertEqual(target[0]["id"], old_item["id"])
        self.assertEqual(self.notes_of(target[0]), old)
        self.assertEqual(self.delete_issued(), [])
        staged = [i for i in self.items_json() if ".stage-" in i["title"] or ".previous-" in i["title"]]
        self.assertTrue(staged, "a staged copy might remain by design; never delete")

    def test_store_edit_promotion_failure_preserves_old_under_backup(self) -> None:
        # call 6 = second rename (staged->canonical). The old canonical was
        # already archived to .previous-* at call 5, so on promotion failure it
        # stays under the backup title (old id + contents intact), NOT canonical.
        site = "acme"
        self.make_site(site)
        old = _age_secret("OLD")
        old_item = self.seed_canonical(site, old)
        self.seed_identity(site, _age_secret("NEW"))
        r = self.run_helper(site, "store", "--force", extra_env={"OP_MOCK_FAIL_ON": "6"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_op_called("item", "edit")
        items = self.items_json()
        backup = [i for i in items if ".previous-" in i["title"]]
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0]["id"], old_item["id"])
        self.assertEqual(self.notes_of(backup[0]), old)
        self.assertEqual(self.delete_issued(), [])

    def test_store_final_verify_failure_preserves_old_under_backup(self) -> None:
        # call #7 = final get readback/byte-compare (after both renames). The
        # old canonical item was renamed to .previous-* with its id + contents
        # intact; nothing is deleted.
        site = "acme"
        self.make_site(site)
        old = _age_secret("OLD")
        old_item = self.seed_canonical(site, old)
        self.seed_identity(site, _age_secret("NEW"))
        r = self.run_helper(site, "store", "--force", extra_env={"OP_MOCK_FAIL_ON": "7"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_op_called("item", "get")
        items = self.items_json()
        backup = [i for i in items if ".previous-" in i["title"]]
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0]["id"], old_item["id"])
        self.assertEqual(self.notes_of(backup[0]), old)
        self.assertEqual(self.delete_issued(), [])

    def test_store_create_failure_cleans_staging_entire_tree(self) -> None:
        site = "acme"
        self.make_site(site)
        self.seed_identity(site, _age_secret("NEW"))
        r = self.run_helper(site, "store", extra_env={"OP_MOCK_FAIL_CREATE": "1"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_op_called("item", "create")
        self.assert_no_staging()

    def test_store_generic_op_error_fails_closed_preserves_old(self) -> None:
        site = "acme"
        self.make_site(site)
        old = _age_secret("OLD")
        old_item = self.seed_canonical(site, old)
        self.seed_identity(site, _age_secret("NEW"))
        r = self.run_helper(site, "store", "--force", extra_env={"OP_MOCK_FAIL_CREATE": "1"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_op_called("item", "create")
        target = self.find_by_title(_canonical_title(site))
        self.assertEqual([i["id"] for i in target], [old_item["id"]])
        self.assertEqual([self.notes_of(i) for i in target], [old])
        self.assertEqual(self.delete_issued(), [])


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #
@unittest.skipUnless(BASH_AND_PY, "Bash + python3 subprocess")
class SiteVerifyTests(SiteAgeIntegrationBase):
    def test_verify_creates_no_pre_verify_backup_and_leaves_identity(self) -> None:
        site = "acme"
        self.make_site(site)
        self.seed_identity(site, _age_secret("VERIFY"))
        # Seed an existing backup so a naive "make a .pre-verify copy" step
        # would be caught by stray-new-file assertions below.
        pre = self.identity_file(site).parent / "site.age.backup"
        pre.write_text(_age_secret("BACKUP"), encoding="utf-8")
        before = {p.name: p.read_bytes() for p in self.identity_file(site).parent.iterdir()}
        r = self.run_helper(site, "verify")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = {p.name for p in self.identity_file(site).parent.iterdir()}
        self.assertNotIn(".pre-verify", "".join(after))
        self.assertEqual(before, {name: self.identity_file(site).parent.joinpath(name).read_bytes()
                                  for name in after})
        self.assertIn("site.age", after)


# --------------------------------------------------------------------------- #
# just recipe argument handling
# --------------------------------------------------------------------------- #
@unittest.skipUnless(JUST_AVAILABLE, "requires just + bash + functional python3")
class SiteAgeJustTests(SiteAgeIntegrationBase):
    def test_just_fetch_force_explicit_site_with_existing_key(self) -> None:
        # `just fetch --force SITE=acme` with an existing local identity must
        # replace it with the stored vault copy (explicit SITE routing).
        site = "acme"
        self.make_site(site)
        self.seed_canonical(site, _age_secret("NEW"))
        self.seed_identity(site, _age_secret("OLD"))
        r = self.run_just("fetch", "--force", "SITE=%s" % site,
                          just_vars={"VAULT": OP_VAULT})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.identity_file(site).read_text(encoding="utf-8"), _age_secret("NEW"))

    def test_just_env_only_force_replaces_existing_identity(self) -> None:
        site = "acme"
        self.make_site(site)
        self.seed_canonical(site, _age_secret("NEW"))
        self.seed_identity(site, _age_secret("OLD"))
        r = self.run_just("fetch", "--force", site=site, just_vars={"VAULT": OP_VAULT})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.identity_file(site).read_text(encoding="utf-8"), _age_secret("NEW"))

    def test_just_explicit_site_overrides_env(self) -> None:
        self.make_site("acme"); self.make_site("dev")
        self.seed_canonical("dev", _age_secret("DEVNEW"))
        self.seed_canonical("acme", _age_secret("ACMENEW"))
        self.seed_identity("acme", _age_secret("acme-old"))
        r = self.run_just("fetch", "SITE=acme", "--force", site="dev", just_vars={"VAULT": OP_VAULT})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.identity_file("acme").read_text(encoding="utf-8"), _age_secret("ACMENEW"))
        self.assertFalse(self.identity_file("dev").exists())

    def test_just_unknown_argument_metachars_remain_inert(self) -> None:
        site = "acme"
        self.make_site(site)
        self.seed_canonical(site, _age_secret("NEW"))
        self.seed_identity(site, _age_secret("OLD"))
        payload = "$(touch %s)" % (self.td / "pwned")
        r = self.run_just("fetch", "SITE=%s" % site, payload, "--force", just_vars={"VAULT": OP_VAULT})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.td / "pwned").exists(), "shell metachars must not be evaluated")
        self.assertTrue(self.identity_file(site).exists(), "existing identity must be preserved")
        self.assertEqual(self.identity_file(site).read_text(encoding="utf-8"), _age_secret("OLD"))

    def test_just_generate_rejects_force(self) -> None:
        site = "acme"
        self.make_site(site)
        r = self.run_just("generate", "SITE=%s" % site, "--force", just_vars={"VAULT": OP_VAULT})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.identity_file(site).exists(),
                         "generate must reject --force and must not create an identity")

    def test_just_verify_rejects_force(self) -> None:
        site = "acme"
        self.make_site(site)
        self.seed_identity(site, _age_secret("V"))
        r = self.run_just("verify", "SITE=%s" % site, "--force", just_vars={"VAULT": OP_VAULT})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_just_missing_site_never_implicitly_defaults(self) -> None:
        self.make_site("dev")
        self.seed_canonical("dev", _age_secret("DEV"))
        r = self.run_just("fetch", just_vars={"VAULT": OP_VAULT})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.identity_file("dev").exists(),
                         "missing SITE must not default to a site")

    def test_just_generate_explicit_site_routes_correctly(self) -> None:
        site = "acme"
        self.make_site(site)
        self.make_site("dev")
        r = self.run_just("generate", "SITE=%s" % site, just_vars={"VAULT": OP_VAULT})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.identity_file(site).exists())
        self.assertFalse(self.identity_file("dev").exists())
        self.assertNotIn(SENTINEL, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()