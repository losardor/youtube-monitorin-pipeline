"""
Advisory lock shared by the daily run and the backfill.

Both processes write the same SQLite file. WAL allows concurrent readers but
still only one writer, and the backfill holds its transaction for hours, so
the two are serialised at the process level instead of fighting over the
database.

The lock file path must be identical to the one the cron wrapper passes to
`flock -n`, because fcntl.flock and flock(1) take the same kernel lock on the
same inode: that is what makes a shell-level backfill and a Python daily run
contend with each other rather than both proceeding.

Default path: data/.ytmon.lock
"""

from __future__ import annotations

import errno
import fcntl
import logging
import os
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_LOCK_PATH = 'data/.ytmon.lock'


class LockUnavailable(RuntimeError):
    """Another process holds the lock and blocking was not requested."""


@contextmanager
def advisory_lock(path: str = DEFAULT_LOCK_PATH, blocking: bool = False):
    """
    Hold an exclusive advisory lock for the duration of the block.

    Args:
        path: Lock file path. Must match the cron wrapper's flock target.
        blocking: Wait for the lock instead of failing immediately. The daily
            run passes False: colliding with a multi-hour backfill should exit
            and be reported, not queue.

    Raises:
        LockUnavailable: non-blocking and the lock is held elsewhere.
    """
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB

    try:
        try:
            fcntl.flock(fd, flags)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EAGAIN):
                os.close(fd)
                raise LockUnavailable(
                    f"{lock_path} is held by another process "
                    f"(a backfill is probably running)"
                ) from e
            os.close(fd)
            raise

        # Recorded for humans reading the file during an incident; the lock
        # itself is the flock, not the contents.
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
            os.fsync(fd)
        except OSError:
            pass

        logger.debug(f"acquired lock {lock_path} (pid {os.getpid()})")
        yield fd

    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)
        logger.debug(f"released lock {lock_path}")
