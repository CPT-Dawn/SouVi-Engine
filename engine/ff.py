"""Thin, strict wrappers around ffmpeg / ffprobe.

Every engine operation funnels through `run()`, so error handling, logging and
command echo (SOUVI_SHOW_CMD=1) behave identically everywhere.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

FFMPEG = os.environ.get("SOUVI_FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("SOUVI_FFPROBE", "ffprobe")


class FFError(RuntimeError):
    """ffmpeg/ffprobe failed. Message carries the command tail and stderr tail."""


def _echo(cmd: list[str]) -> None:
    if os.environ.get("SOUVI_SHOW_CMD"):
        print("  $ " + shlex.join(cmd), file=sys.stderr)


def run(
    args: list[str],
    *,
    loglevel: str = "error",
    capture: bool = True,
    label: str | None = None,
) -> subprocess.CompletedProcess:
    """Run ffmpeg with sane global flags. Raises FFError with stderr on failure."""
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-loglevel", loglevel, "-nostats", *args]
    _echo(cmd)
    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=capture, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-25:]
        raise FFError(
            f"ffmpeg failed ({label or 'job'}), exit {proc.returncode}\n"
            f"cmd: {shlex.join(cmd)[:2000]}\n" + "\n".join(tail)
        )
    if label:
        print(f"  ✓ {label} ({time.monotonic() - t0:.1f}s)", file=sys.stderr)
    return proc


def probe_json(path: str | Path) -> dict:
    import json

    cmd = [
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    _echo(cmd)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFError(f"ffprobe failed on {path}: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def available() -> bool:
    return shutil.which(FFMPEG) is not None and shutil.which(FFPROBE) is not None


def escape_filter_path(path: str | Path) -> str:
    """Escape a filesystem path for use as a filter option value inside a filtergraph."""
    s = str(path)
    for ch in ("\\", ":", "'", ",", "[", "]", ";"):
        s = s.replace(ch, "\\" + ch)
    return s


def db_to_lin(db: float) -> float:
    return 10 ** (db / 20.0)
