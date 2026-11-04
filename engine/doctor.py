"""Environment check: is this machine able to produce premium output?"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys

from . import ff

REQUIRED_FILTERS = ["loudnorm", "alimiter", "afftdn", "deesser", "acompressor", "sidechaincompress", "afir",
                    "afftfilt", "aeval", "xfade", "zoompan", "zscale", "tonemap", "ass", "lut3d", "curves",
                    "vidstabdetect", "minterpolate", "blackdetect", "silencedetect", "showspectrumpic"]
ENCODERS = {"libx264": True, "libx265": True, "prores_ks": True, "aac": True, "pcm_s24le": True,
            "libsvtav1": False, "libopus": False, "libmp3lame": False, "h264_nvenc": False, "hevc_nvenc": False}
FONTS = ["Inter", "Inter Display", "JetBrains Mono"]


def _out(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def doctor() -> int:
    bad = 0

    def row(ok: bool | None, name: str, detail: str = ""):
        nonlocal bad
        mark = "✔" if ok else ("·" if ok is None else "✘")
        bad += ok is False
        print(f"  {mark} {name:<22} {detail}")

    print("SouVi doctor")
    row(sys.version_info >= (3, 11), "python", sys.version.split()[0] + ("" if sys.version_info >= (3, 11) else " (need 3.11+)"))
    if not ff.available():
        row(False, "ffmpeg", "not on PATH — install ffmpeg (Arch: pacman -S ffmpeg)")
        return 1
    ver = _out([ff.FFMPEG, "-hide_banner", "-version"]).splitlines()[0]
    row(True, "ffmpeg", ver.split()[2] if len(ver.split()) > 2 else ver)

    filters = set(re.findall(r"^\s*[T.][S.][C.]?\s+(\w+)", _out([ff.FFMPEG, "-hide_banner", "-filters"]), re.M))
    missing = [f for f in REQUIRED_FILTERS if f not in filters]
    row(not missing, "filters", "all present" if not missing else "missing: " + ", ".join(missing))

    enc = _out([ff.FFMPEG, "-hide_banner", "-encoders"])
    for name, required in ENCODERS.items():
        present = re.search(rf"^\s*\S+\s+{name}\s", enc, re.M) is not None
        row(present if (required or present) else None, f"encoder {name}", "" if present else
            ("REQUIRED" if required else "optional, not available"))

    if "h264_nvenc" in enc:
        try:
            ff.run(["-f", "lavfi", "-i", "testsrc2=s=256x144:d=0.2", "-c:v", "h264_nvenc", "-f", "null", "-"])
            row(True, "nvenc (GPU drafts)", "working — use `render --draft --gpu`")
        except ff.FFError:
            row(None, "nvenc (GPU drafts)", "encoder present but GPU unusable")

    fc = _out(["fc-list", ":", "family"]) if shutil.which("fc-list") else ""
    for f in FONTS:
        ok = any(f in line.split(",") for line in fc.splitlines())
        row(ok or None, f"font {f}", "" if ok else "missing — titles fall back to a default font")

    for tool, why in (("rubberband", "high-quality pitch/time (optional)"), ("magick", "image prep (optional)")):
        row(True if shutil.which(tool) else None, tool, why)
    print("  ready." if not bad else f"  {bad} problem(s) above.")
    return 1 if bad else 0
