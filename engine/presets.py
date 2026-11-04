"""Delivery presets (presets/delivery/*.toml) -> ffmpeg encoder arguments.

A preset fully describes a deliverable: geometry, codec, pixel format, audio
format, loudness target, container. Render/export/QC all read the same preset,
so what gets encoded is exactly what gets verified.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .paths import PRESETS

DELIVERY = PRESETS / "delivery"
BT709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


@dataclass
class Preset:
    name: str
    description: str = ""
    video: dict | None = None
    audio: dict | None = None
    loudness: dict | None = None
    container: dict = field(default_factory=lambda: {"ext": "mp4", "params": []})

    @property
    def ext(self) -> str:
        return self.container.get("ext", "mp4")

    @property
    def size(self) -> tuple[int, int] | None:
        if self.video and "width" in self.video and "height" in self.video:
            return int(self.video["width"]), int(self.video["height"])
        return None

    @property
    def target_lufs(self) -> float | None:
        return float(self.loudness["integrated"]) if self.loudness else None

    @property
    def target_tp(self) -> float:
        return float(self.loudness.get("true_peak", -1.0)) if self.loudness else -1.0

    @property
    def sample_rate(self) -> int:
        return int((self.audio or {}).get("sample_rate", 48000))

    def video_args(self, *, draft: bool = False, gpu: bool = False) -> list[str]:
        if not self.video:
            return ["-vn"]
        if draft:
            if gpu:
                return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "24", "-pix_fmt", "yuv420p", *BT709]
            return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", *BT709]
        v = self.video
        args = ["-c:v", v["codec"], "-pix_fmt", v["pix_fmt"]]
        if "crf" in v:
            args += ["-crf", str(v["crf"])]
        if "preset" in v:
            args += ["-preset", str(v["preset"])]
        args += list(v.get("params", []))
        return args + BT709

    def audio_args(self, *, draft: bool = False) -> list[str]:
        if not self.audio:
            return ["-an"]
        a = self.audio
        if draft and self.video:
            return ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
        args = ["-c:a", a["codec"]]
        if "bitrate" in a:
            args += ["-b:a", a["bitrate"]]
        args += ["-ar", str(a.get("sample_rate", 48000))]
        if "channels" in a:
            args += ["-ac", str(a["channels"])]
        return args

    def container_args(self) -> list[str]:
        return list(self.container.get("params", []))

    def out_sample_fmt(self) -> tuple[str, str]:
        """(sample_fmt, dither) the master chain should end in for this preset's codec."""
        codec = (self.audio or {}).get("codec", "aac")
        if codec in ("pcm_s24le", "pcm_s32le", "flac"):
            return "s32", "triangular_hp"
        if codec == "pcm_s16le":
            return "s16", "triangular_hp"
        if codec == "libmp3lame":
            return "fltp", "none"
        return "flt", "none"


def names() -> list[str]:
    return sorted(p.stem for p in DELIVERY.glob("*.toml"))


def load(name: str) -> Preset:
    path = Path(name) if name.endswith(".toml") else DELIVERY / f"{name}.toml"
    if not path.exists():
        raise SystemExit(f"unknown preset '{name}'. Available: {', '.join(names())}")
    data = tomllib.loads(path.read_text())
    return Preset(
        name=path.stem,
        description=data.get("description", ""),
        video=data.get("video"),
        audio=data.get("audio"),
        loudness=data.get("loudness"),
        container=data.get("container", {"ext": "mp4", "params": []}),
    )
