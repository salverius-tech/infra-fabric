"""Transactional replacement of a generated output directory."""

from __future__ import annotations

import ctypes
import errno
import os
import platform
import secrets
import stat
from collections.abc import Callable
from pathlib import Path

from private_files import PrivateFileError, _private_directory_fd, _remove_tree


class AtomicOutputError(OSError):
    """Raised when an output directory cannot be replaced safely."""


def _sync(descriptor: int) -> None:
    os.fsync(descriptor)


def _renameat2(parent_fd: int, source: str, destination: str, flags: int) -> None:
    numbers = {"x86_64": 316, "aarch64": 276}
    number = numbers.get(platform.machine())
    syscall = getattr(ctypes.CDLL(None, use_errno=True), "syscall", None)
    if number is None or syscall is None:
        raise AtomicOutputError("atomic directory replacement is unavailable")
    result = syscall(
        number,
        parent_fd,
        os.fsencode(source),
        parent_fd,
        os.fsencode(destination),
        flags,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise AtomicOutputError(
            "output directory already exists; explicit replacement acknowledgement is required"
        )
    raise AtomicOutputError("atomic directory replacement is unavailable")


def _identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def atomic_output_directory(output_dir: Path, populate: Callable[[Path], None]) -> None:
    """Populate and atomically install a directory through one held parent FD.

    Every security-relevant operation is descriptor-relative. Existing output is
    exchanged atomically with the completed stage, then removed through the same
    held parent. A destination created concurrently is preserved and rejected.
    """
    output_dir = Path(output_dir)
    parent = output_dir.parent
    destination = output_dir.name
    if destination in {"", ".", ".."} or "/" in destination:
        raise AtomicOutputError(f"invalid output directory: {output_dir}")

    try:
        with _private_directory_fd(
            parent, create=True, private_final=False
        ) as parent_fd:
            existing: tuple[int, int] | None
            try:
                metadata = os.stat(destination, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            else:
                if not stat.S_ISDIR(metadata.st_mode):
                    raise AtomicOutputError(
                        f"output path is not a directory: {output_dir}"
                    )
                existing = _identity(metadata)

            stage = f".{destination}.tmp-{secrets.token_hex(16)}"
            os.mkdir(stage, 0o700, dir_fd=parent_fd)
            created_stage = _identity(
                os.stat(stage, dir_fd=parent_fd, follow_symlinks=False)
            )
            _sync(parent_fd)
            staged = Path(f"/proc/self/fd/{parent_fd}/{stage}")
            installed = False
            try:
                populate(staged)
                stage_metadata = os.stat(stage, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(stage_metadata.st_mode)
                    or _identity(stage_metadata) != created_stage
                ):
                    raise AtomicOutputError(
                        "generated output stage changed during population"
                    )

                if existing is None:
                    _renameat2(parent_fd, stage, destination, 1)  # RENAME_NOREPLACE
                else:
                    _renameat2(parent_fd, stage, destination, 2)  # RENAME_EXCHANGE
                    moved = os.stat(stage, dir_fd=parent_fd, follow_symlinks=False)
                    if _identity(moved) != existing:
                        _renameat2(parent_fd, stage, destination, 2)
                        _sync(parent_fd)
                        raise AtomicOutputError(
                            "output directory changed during replacement"
                        )
                _sync(parent_fd)
                installed = True
            finally:
                try:
                    os.stat(stage, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    _remove_tree(parent_fd, stage)
                    _sync(parent_fd)
                if not installed:
                    # A concurrent destination remains untouched; only our stage is removed.
                    pass
    except (AtomicOutputError, OSError):
        raise
    except PrivateFileError as error:
        raise AtomicOutputError(
            f"cannot replace generated output directory: {output_dir}"
        ) from error


__all__ = ["AtomicOutputError", "atomic_output_directory"]
