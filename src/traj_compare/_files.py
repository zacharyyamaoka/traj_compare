"""Every file traj_compare writes goes to a temporary name, then ``os.replace`` moves it onto its own (NAVIGATION.md D2).

WHY (arm_motion_bench lane V, 2026-11-20): the bench rebuilds a site in a hard-linked copy of the live one
(``cp -al live staging``) and then swaps the two. Opening an existing name for writing writes through to the inode the
live site shares, so the live site would change under its viewers; a new file renamed into place gets its own inode and
leaves live's alone. And a write that is stopped (Ctrl-C, an exception) leaves each file whole and old or whole and new,
never torn. Not fsync'ed: the guarantee is against a stopped process, not a power cut, and a fsync per file would cost
the 1,500-file build more than everything else here.

A temporary name is ``.<name>.<pid>-<n>.tmp`` beside its file, so no glob for ``*.npz``, ``*.js`` or ``*.rrd`` matches
it, and a failed write deletes it.
"""

from __future__ import annotations

import itertools
import os
import shutil
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import numpy as np

_COUNT = itertools.count()  # WHY a counter beside the pid: two writers in one process (serve's threads) never share a name


def temporary_name(path: Path) -> Path:
    """The temporary name ``path`` is written under: hidden, beside it (one filesystem, so the rename is atomic)."""
    return path.with_name(f".{path.name}.{os.getpid()}-{next(_COUNT)}.tmp")


@contextmanager
def replacing(path: Path | str) -> Iterator[Path]:
    """Yield the temporary name to write ``path``'s new content to; on success it replaces ``path``, else it is deleted.

    For writers that want a path of their own (rerun, ffmpeg, pyarrow): ``with replacing(out) as temporary: ...``.
    """
    path = Path(path)
    temporary = temporary_name(path)
    try:
        yield temporary
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_text(path: Path | str, text: str) -> Path:
    """``Path.write_text`` (UTF-8) through a temporary name."""
    with replacing(path) as temporary:
        temporary.write_text(text, encoding="utf-8")
    return Path(path)


def save_npz(path: Path | str, arrays: Mapping[str, np.ndarray]) -> Path:
    """``np.savez_compressed`` through a temporary name. WHY an open file: given a name, numpy appends ``.npz`` to one
    that does not already end in it."""
    with replacing(path) as temporary, open(temporary, "xb") as handle:
        np.savez_compressed(handle, **arrays)
    return Path(path)


def copy_file(source: Path | str, path: Path | str) -> Path:
    """``shutil.copy2`` (bytes and ``mtime``) through a temporary name."""
    with replacing(path) as temporary:
        shutil.copy2(source, temporary)
    return Path(path)


def symlink(target: Path | str, path: Path | str) -> Path:
    """Point the link ``path`` at ``target``, replacing whatever link was there in one rename."""
    with replacing(path) as temporary:
        temporary.symlink_to(target)
    return Path(path)
