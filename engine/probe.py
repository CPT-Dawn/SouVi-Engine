"""Compact, decision-ready media facts (instead of raw ffprobe walls)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path

from . import ff

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".avif", ".jxl", ".exr"}
HDR_TRC = {"smpte2084", "arib-std-b67"}


@dataclass
class VideoInfo:
    codec: str
    width: int
    height: int
    fps: float
    pix_fmt: str
    bit_depth: int
    color_space: str | None
    color_primaries: str | None
    color_trc: str | None
    color_range: str | None
    rotation: int = 0
    frames: int | None = None
    bitrate: int | None = None

    @property
    def hdr(self) -> bool:
        return (self.color_trc or "") in HDR_TRC


@dataclass
class AudioInfo:
    codec: str
    sample_rate: int
    channels: int
    layout: str | None
    sample_fmt: str | None
    bitrate: int | None = None


@dataclass
class MediaInfo:
    path: str
    format: str
    duration: float
    size_bytes: int
    bitrate: int | None
    is_image: bool
    video: VideoInfo | None = None
    audio: AudioInfo | None = None
    audio_streams: int = 0
    subtitle_streams: int = 0
    tags: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.video:
            d["video"]["hdr"] = self.video.hdr
        return d


def _rate(s: str | None) -> float:
    if not s or s in ("0/0", "0"):
        return 0.0
    try:
        return float(Fraction(s))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _depth(pix_fmt: str, raw: str | None) -> int:
    if raw and raw.isdigit():
        return int(raw)
    for d in (16, 14, 12, 10):
        if f"p{d}" in pix_fmt or f"{d}le" in pix_fmt or f"{d}be" in pix_fmt:
            return d
    return 8


def probe(path: str | Path) -> MediaInfo:
    path = Path(path)
    data = ff.probe_json(path)
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    a_all = [s for s in streams if s.get("codec_type") == "audio"]
    a = a_all[0] if a_all else None

    is_image = path.suffix.lower() in IMAGE_EXT or (
        v is not None and fmt.get("format_name", "").endswith("_pipe")
    )

    vinfo = None
    if v:
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        rot = int(v.get("tags", {}).get("rotate", rot))
        fps = _rate(v.get("avg_frame_rate")) or _rate(v.get("r_frame_rate"))
        pix = v.get("pix_fmt", "")
        vinfo = VideoInfo(
            codec=v.get("codec_name", "?"),
            width=int(v.get("width", 0)),
            height=int(v.get("height", 0)),
            fps=round(fps, 3),
            pix_fmt=pix,
            bit_depth=_depth(pix, v.get("bits_per_raw_sample")),
            color_space=v.get("color_space"),
            color_primaries=v.get("color_primaries"),
            color_trc=v.get("color_transfer"),
            color_range=v.get("color_range"),
            rotation=rot,
            frames=int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else None,
            bitrate=int(v["bit_rate"]) if str(v.get("bit_rate", "")).isdigit() else None,
        )

    ainfo = None
    if a:
        ainfo = AudioInfo(
            codec=a.get("codec_name", "?"),
            sample_rate=int(a.get("sample_rate", 0)),
            channels=int(a.get("channels", 0)),
            layout=a.get("channel_layout"),
            sample_fmt=a.get("sample_fmt"),
            bitrate=int(a["bit_rate"]) if str(a.get("bit_rate", "")).isdigit() else None,
        )

    dur = float(fmt.get("duration") or 0.0)
    if not dur and v and v.get("duration"):
        dur = float(v["duration"])

    return MediaInfo(
        path=str(path),
        format=fmt.get("format_name", "?"),
        duration=round(dur, 3),
        size_bytes=int(fmt.get("size") or 0),
        bitrate=int(fmt["bit_rate"]) if str(fmt.get("bit_rate", "")).isdigit() else None,
        is_image=is_image,
        video=vinfo,
        audio=ainfo,
        audio_streams=len(a_all),
        subtitle_streams=sum(1 for s in streams if s.get("codec_type") == "subtitle"),
        tags={k: v for k, v in (fmt.get("tags") or {}).items() if k.lower() in ("title", "artist", "creation_time", "encoder")},
    )


def summary(m: MediaInfo) -> str:
    lines = [f"{Path(m.path).name}  [{m.format}]  {m.duration:.3f}s  {m.size_bytes / 1e6:.1f} MB"]
    if m.video:
        v = m.video
        color = "/".join(x or "?" for x in (v.color_primaries, v.color_trc, v.color_space, v.color_range))
        kind = "image" if m.is_image else f"{v.fps:g} fps"
        lines.append(
            f"  video  {v.codec} {v.width}x{v.height} {kind} {v.pix_fmt} ({v.bit_depth}-bit) "
            f"color={color}{' HDR' if v.hdr else ''}{f' rot={v.rotation}' if v.rotation else ''}"
            f"{f' {v.bitrate / 1e6:.1f} Mb/s' if v.bitrate else ''}"
        )
    if m.audio:
        a = m.audio
        lines.append(
            f"  audio  {a.codec} {a.sample_rate} Hz {a.channels}ch ({a.layout or '?'}) {a.sample_fmt or ''}"
            f"{f' {a.bitrate // 1000} kb/s' if a.bitrate else ''}"
            f"{f'  (+{m.audio_streams - 1} more)' if m.audio_streams > 1 else ''}"
        )
    return "\n".join(lines)
