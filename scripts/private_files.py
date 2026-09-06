"""Small durable primitives for private local files.

Snapshot-specific schemas and recovery policy intentionally live in their callers.
"""

from __future__ import annotations

import contextlib
import ctypes
import errno
import hashlib
import json
import os
import secrets
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO


class PrivateFileError(RuntimeError):
    """Raised when a private file boundary is unavailable or unsafe."""


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _path_components(path: Path) -> tuple[bool, tuple[str, ...]]:
    """Return lexical components rooted at / or the current directory.

    ``abspath`` deliberately normalizes relative ``.`` and ``..`` without resolving
    links; each remaining component is subsequently opened with ``O_NOFOLLOW``.
    """
    absolute = os.path.abspath(os.fspath(path))
    return True, tuple(part for part in Path(absolute).parts if part != os.sep)


@contextlib.contextmanager
def _private_directory_fd(
    path: Path, *, create: bool, private_final: bool
) -> Iterator[int]:
    raw_path = os.fspath(path)
    proc_prefix = "/proc/self/fd/"
    held_fd: int | None = None
    if raw_path.startswith(proc_prefix):
        remainder = raw_path[len(proc_prefix) :].split("/", 1)
        if remainder[0].isdigit():
            held_fd = int(remainder[0])
            components = tuple(
                part
                for part in (remainder[1].split("/") if len(remainder) > 1 else [])
                if part
            )
        else:
            _, components = _path_components(path)
    else:
        _, components = _path_components(path)
    try:
        descriptor = (
            os.dup(held_fd)
            if held_fd is not None
            else os.open(os.sep, _directory_flags())
        )
    except (
        OSError
    ) as error:  # pragma: no cover - root directory is a platform prerequisite
        raise PrivateFileError("private directory is unavailable") from error
    try:
        for index, component in enumerate(components):
            is_final = index == len(components) - 1
            created = False
            if create:
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                    created = True
                except FileExistsError:
                    pass
                except OSError as error:
                    raise PrivateFileError(
                        "private directory is unavailable"
                    ) from error
            if created:
                _fsync_descriptor(descriptor)
            try:
                child = os.open(component, _directory_flags(), dir_fd=descriptor)
            except OSError as error:
                raise PrivateFileError("private directory is unsafe") from error
            os.close(descriptor)
            descriptor = child
            if is_final and private_final:
                os.fchmod(descriptor, 0o700)
        yield descriptor
    finally:
        os.close(descriptor)


def _fsync_descriptor(descriptor: int) -> None:
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise PrivateFileError("private directory is unavailable") from error


def fsync_directory(path: Path) -> None:
    """Durably sync an existing directory after non-file publication changes."""
    with _private_directory_fd(path, create=False, private_final=False) as descriptor:
        _fsync_descriptor(descriptor)


def ensure_private_directory(path: Path) -> None:
    """Create a private final directory without following any path component links."""
    try:
        with _private_directory_fd(path, create=True, private_final=True) as descriptor:
            _fsync_descriptor(descriptor)
    except PrivateFileError:
        raise
    except OSError as error:
        raise PrivateFileError("private directory is unavailable") from error


@contextlib.contextmanager
def open_private_directory(path: Path, label: str) -> Iterator[int]:
    """Hold a private directory FD; callers must perform child work relative to it."""
    try:
        with _private_directory_fd(
            path, create=False, private_final=False
        ) as descriptor:
            metadata = os.fstat(descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise PrivateFileError(f"{label} is not a safe directory")
            if metadata.st_mode & 0o077:
                raise PrivateFileError(f"{label} permissions are not private")
            yield descriptor
    except PrivateFileError:
        raise
    except OSError as error:
        raise PrivateFileError(f"{label} is not a safe directory") from error


@contextlib.contextmanager
def open_regular_child(parent_fd: int, name: str, label: str) -> Iterator[BinaryIO]:
    """Open a regular, non-symlink child through an already-held directory FD."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise PrivateFileError(f"{label} must be a regular non-symlink file")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                yield handle
        finally:
            os.close(descriptor)
    except PrivateFileError:
        raise
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise PrivateFileError(
                f"{label} must be a regular non-symlink file"
            ) from error
        raise PrivateFileError(f"{label} is unavailable") from error


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns


@contextlib.contextmanager
def open_regular_file(
    path: Path,
    label: str,
    *,
    expected_identity: tuple[int, int, int, int] | None = None,
) -> Iterator[BinaryIO]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        # The complete ancestor walk and final open share held descriptors.  Do not
        # lstat then reopen a string path: that creates the very replacement gap this
        # boundary exists to prevent.
        with _private_directory_fd(
            path.parent, create=False, private_final=False
        ) as parent_fd:
            descriptor = os.open(path.name, flags, dir_fd=parent_fd)
            try:
                actual = os.fstat(descriptor)
                if not stat.S_ISREG(actual.st_mode):
                    raise PrivateFileError(
                        f"{label} must be a regular non-symlink file"
                    )
                if (
                    expected_identity is not None
                    and _identity(actual) != expected_identity
                ):
                    raise PrivateFileError(f"{label} changed while opening")
                with os.fdopen(descriptor, "rb", closefd=False) as handle:
                    yield handle
            finally:
                os.close(descriptor)
    except PrivateFileError:
        raise
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise PrivateFileError(
                f"{label} must be a regular non-symlink file"
            ) from error
        raise PrivateFileError(f"{label} changed while opening") from error


def stream_sha256(path: Path, label: str = "private file") -> str:
    digest = hashlib.sha256()
    with open_regular_file(path, label) as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stream_sha256_handle(handle: BinaryIO) -> str:
    """Hash an already-held regular source without a second pathname lookup."""
    digest = hashlib.sha256()
    handle.seek(0)
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    handle.seek(0)
    return digest.hexdigest()


def _temporary_file(parent_fd: int, prefix: str) -> tuple[int, str]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for _ in range(100):
        name = f"{prefix}{secrets.token_hex(16)}"
        try:
            return os.open(name, flags, 0o600, dir_fd=parent_fd), name
        except FileExistsError:
            continue
        except OSError as error:
            raise PrivateFileError("cannot create private temporary file") from error
    raise PrivateFileError("cannot create private temporary file")


class StagingDirectory:
    """A private staging directory whose parent descriptor stays pinned until publish."""

    def __init__(self, parent_fd: int, parent: Path, name: str) -> None:
        self._parent_fd = parent_fd
        self._parent = parent
        # This is intentionally only a convenience spelling while parent_fd is held.
        self.path = Path(f"/proc/self/fd/{parent_fd}/{name}")
        self._name = name
        self._published = False

    def publish(self, destination_name: str, *, replace_existing: bool = False) -> Path:
        if self._published:
            raise PrivateFileError("private directory installation is unavailable")
        try:
            if replace_existing:
                os.replace(
                    self._name,
                    destination_name,
                    src_dir_fd=self._parent_fd,
                    dst_dir_fd=self._parent_fd,
                )
            else:
                _rename_noreplace(self._parent_fd, self._name, destination_name)
            _fsync_descriptor(self._parent_fd)
        except OSError as error:
            raise PrivateFileError(
                "private directory installation is unavailable"
            ) from error
        self._published = True
        # Capture the kernel's current spelling before the held descriptor closes.
        # It remains useful when an ancestor was renamed during this transaction.
        try:
            return (
                Path(os.readlink(f"/proc/self/fd/{self._parent_fd}")) / destination_name
            )
        except OSError:
            return self._parent / destination_name

    def prune(self, *, prefix: str, retain: int) -> None:
        """Remove old completed directories relative to the pinned parent only."""
        entries: list[str] = []
        for name in os.listdir(self._parent_fd):
            try:
                metadata = os.stat(name, dir_fd=self._parent_fd, follow_symlinks=False)
            except OSError:
                continue
            if name.startswith(prefix) and stat.S_ISDIR(metadata.st_mode):
                entries.append(name)
        for name in sorted(entries, reverse=True)[retain:]:
            _remove_tree(self._parent_fd, name)
        if entries[retain:]:
            _fsync_descriptor(self._parent_fd)


def _remove_tree(parent_fd: int, name: str) -> None:
    """No-follow recursive removal rooted at a held descriptor."""
    try:
        fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as error:
        raise PrivateFileError("private directory cleanup is unavailable") from error
    try:
        os.fchmod(fd, 0o700)
        for child in os.listdir(fd):
            metadata = os.stat(child, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                _remove_tree(fd, child)
            else:
                # Unlink through the held directory descriptor; file modes do not
                # govern unlink permission, and chmod with dir_fd/follow_symlinks is
                # unsupported on Python's Linux wrapper for symlink children.
                os.unlink(child, dir_fd=fd)
    finally:
        os.close(fd)
    os.rmdir(name, dir_fd=parent_fd)


def _rename_noreplace(parent_fd: int, source: str, destination: str) -> None:
    """Linux renameat2(RENAME_NOREPLACE), failing closed when unavailable."""
    libc = ctypes.CDLL(None, use_errno=True)
    syscall = getattr(libc, "syscall", None)
    # x86_64 and aarch64 Linux syscall numbers; this project runs Linux only.
    numbers = {"x86_64": 316, "aarch64": 276}
    import platform

    number = numbers.get(platform.machine())
    if syscall is None or number is None:
        raise PrivateFileError(
            "atomic no-replace directory installation is unavailable"
        )
    result = syscall(
        number, parent_fd, os.fsencode(source), parent_fd, os.fsencode(destination), 1
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise PrivateFileError(
            "private directory already exists; explicit replacement acknowledgement is required"
        )
    raise PrivateFileError(
        f"atomic no-replace directory installation is unavailable: renameat2 failed with "
        f"{errno.errorcode.get(error, str(error))} ({error}); the filesystem may not support atomic operations"
    )


@contextlib.contextmanager
def staging_directory(
    destination_root: Path, *, prefix: str
) -> Iterator[StagingDirectory]:
    """Create a 0700 staging directory through a pinned verified root descriptor."""
    with _private_directory_fd(
        destination_root, create=True, private_final=True
    ) as parent_fd:
        for _ in range(100):
            name = f"{prefix}{secrets.token_hex(16)}"
            try:
                os.mkdir(name, 0o700, dir_fd=parent_fd)
                _fsync_descriptor(parent_fd)
                staging = StagingDirectory(parent_fd, destination_root, name)
                break
            except FileExistsError:
                continue
            except OSError as error:
                raise PrivateFileError(
                    "cannot create private staging directory"
                ) from error
        else:
            raise PrivateFileError("cannot create private staging directory")
        try:
            yield staging
        finally:
            if not staging._published:
                try:
                    _remove_tree(parent_fd, staging._name)
                    _fsync_descriptor(parent_fd)
                except (OSError, PrivateFileError) as error:
                    raise PrivateFileError(
                        "private directory cleanup is unavailable"
                    ) from error


def atomic_copy(
    source: Path | BinaryIO,
    destination: Path,
    *,
    label: str,
    expected_identity: tuple[int, int, int, int] | None = None,
    expected_sha256: str | None = None,
    replace_existing: bool = True,
) -> None:
    """Copy a stable regular source from byte zero through a verified parent FD.

    A caller-owned source handle remains open. Its final cursor position is
    unspecified; callers must seek before reusing it.
    """
    try:
        with _private_directory_fd(
            destination.parent, create=True, private_final=True
        ) as parent_fd:
            temporary: str | None = None
            try:
                source_context: Any = (
                    contextlib.nullcontext(source)
                    if hasattr(source, "fileno")
                    else open_regular_file(
                        source, label, expected_identity=expected_identity
                    )
                )
                with source_context as input_file:
                    before = os.fstat(input_file.fileno())
                    if not stat.S_ISREG(before.st_mode):
                        raise PrivateFileError(
                            f"{label} must be a regular non-symlink file"
                        )
                    if (
                        expected_identity is not None
                        and _identity(before) != expected_identity
                    ):
                        raise PrivateFileError(f"{label} changed during copy")
                    if (
                        expected_sha256 is not None
                        and stream_sha256_handle(input_file) != expected_sha256
                    ):
                        raise PrivateFileError(f"{label} changed during copy")
                    descriptor, temporary = _temporary_file(
                        parent_fd, f".{destination.name}."
                    )
                    digest = hashlib.sha256()
                    with os.fdopen(descriptor, "wb") as output_file:
                        os.fchmod(output_file.fileno(), 0o600)
                        input_file.seek(0)
                        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                            digest.update(chunk)
                            output_file.write(chunk)
                        output_file.flush()
                        os.fsync(output_file.fileno())
                    after = os.fstat(input_file.fileno())
                    if _identity(before) != _identity(after) or (
                        expected_sha256 is not None
                        and (
                            digest.hexdigest() != expected_sha256
                            or stream_sha256_handle(input_file) != expected_sha256
                        )
                    ):
                        raise PrivateFileError(f"{label} changed during copy")
                os.chmod(temporary, 0o600, dir_fd=parent_fd, follow_symlinks=False)
                if replace_existing:
                    os.replace(
                        temporary,
                        destination.name,
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                    )
                else:
                    try:
                        os.link(
                            temporary,
                            destination.name,
                            src_dir_fd=parent_fd,
                            dst_dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                    except FileExistsError as error:
                        raise PrivateFileError(
                            f"{label} already exists; explicit replacement acknowledgement is required"
                        ) from error
                    os.unlink(temporary, dir_fd=parent_fd)
                temporary = None
                _fsync_descriptor(parent_fd)
            finally:
                if temporary is not None:
                    try:
                        os.unlink(temporary, dir_fd=parent_fd)
                        _fsync_descriptor(parent_fd)
                    except OSError as error:
                        raise PrivateFileError(
                            "private temporary cleanup is unavailable"
                        ) from error
    except PrivateFileError:
        raise
    except OSError as error:
        raise PrivateFileError(f"cannot atomically install {label}") from error


def write_private_manifest(path: Path, manifest: object) -> Path:
    try:
        with _private_directory_fd(
            path.parent, create=True, private_final=True
        ) as parent_fd:
            temporary: str | None = None
            try:
                descriptor, temporary = _temporary_file(parent_fd, f".{path.name}.")
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    os.fchmod(handle.fileno(), 0o600)
                    handle.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temporary, 0o600, dir_fd=parent_fd, follow_symlinks=False)
                os.replace(
                    temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd
                )
                temporary = None
                _fsync_descriptor(parent_fd)
            finally:
                if temporary is not None:
                    try:
                        os.unlink(temporary, dir_fd=parent_fd)
                        _fsync_descriptor(parent_fd)
                    except OSError as error:
                        raise PrivateFileError(
                            "private temporary cleanup is unavailable"
                        ) from error
        return path
    except (OSError, TypeError, ValueError) as error:
        raise PrivateFileError("cannot durably write private manifest") from error
