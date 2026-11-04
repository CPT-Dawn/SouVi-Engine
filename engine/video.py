"""Video building blocks shared by the timeline renderer and single-file commands."""

from __future__ import annotations

import tomllib
from pathlib import Path

from . import ff
from .paths import PRESETS
from .probe import MediaInfo

WORK_PIX = "yuv420p10le"  # everything is processed in 10-bit: no banding in fades, skies, gradients
SCALE_FLAGS = "lanczos+accurate_rnd+full_chroma_int"
# encoders take colour metadata from frames: stamp BT.709 explicitly so players never guess
TAG_709 = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"


def looks() -> dict[str, dict]:
    return tomllib.loads((PRESETS / "looks.toml").read_text())


def grade_chain(spec: str | dict | None, resolve=None) -> str:
    """Build a grade filter chain.

    spec: look name, or {"look": name, "lut": path, "lut_mix": 0..1, "grain": 0..1,
                          "vignette": 0..1, "sharpen": 0..1}
    """
    if not spec:
        return ""
    if isinstance(spec, str):
        spec = {"look": spec}
    parts = []
    if spec.get("lut"):
        lut = resolve(spec["lut"]) if resolve else Path(spec["lut"])
        parts.append(f"lut3d=file={ff.escape_filter_path(lut)}:interp=tetrahedral")
    if spec.get("look"):
        all_looks = looks()
        if spec["look"] not in all_looks:
            raise ValueError(f"unknown look {spec['look']!r}; available: {', '.join(all_looks)}")
        parts.append(all_looks[spec["look"]]["filter"])
    if spec.get("sharpen"):
        parts.append(f"unsharp=5:5:{0.6 * spec['sharpen']:.2f}:5:5:0")
    if spec.get("vignette"):
        parts.append(f"vignette=angle={0.15 + 0.5 * spec['vignette']:.3f}:mode=forward")
    if spec.get("grain"):
        parts.append(f"noise=c0s={max(1, int(14 * spec['grain']))}:c0f=t+u")
    return ",".join(parts)


def tonemap_chain(info: MediaInfo | None) -> str:
    """HDR (PQ/HLG, e.g. iPhone footage) -> SDR BT.709 with Hable tone mapping."""
    if not info or not info.video or not info.video.hdr:
        return ""
    return ("zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,"
            "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv")


def to_709(w: int, h: int, mode: str = "cover", background: str = "black", uid: str = "x") -> str:
    """Scale/fit any source to WxH, converting to BT.709 limited range, 10-bit."""
    common = f"flags={SCALE_FLAGS}:out_color_matrix=bt709:out_range=tv:force_divisible_by=2"
    if mode == "cover":
        return f"scale={w}:{h}:force_original_aspect_ratio=increase:{common},crop={w}:{h},setsar=1,format={WORK_PIX}"
    if mode == "contain":
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease:{common},"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={background},setsar=1,format={WORK_PIX}")
    if mode == "stretch":
        return f"scale={w}:{h}:{common},setsar=1,format={WORK_PIX}"
    if mode == "blur":
        # contained foreground over a soft, darkened, cover-filled copy (vertical-video standard)
        bw, bh = max(2, w // 8 // 2 * 2), max(2, h // 8 // 2 * 2)
        return (f"split=2[{uid}bgsrc][{uid}fgsrc];"
                f"[{uid}bgsrc]scale={w}:{h}:force_original_aspect_ratio=increase:{common},crop={w}:{h},"
                f"scale={bw}:{bh}:flags=area,gblur=sigma=6,scale={w}:{h}:flags=bicubic,"
                f"eq=brightness=-0.06:saturation=0.85[{uid}bg];"
                f"[{uid}fgsrc]scale={w}:{h}:force_original_aspect_ratio=decrease:{common}[{uid}fg];"
                f"[{uid}bg][{uid}fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format={WORK_PIX}")
    raise ValueError(f"unknown fit mode {mode!r} (cover|contain|blur|stretch)")


# ---------------------------------------------------------------- single-file fx

def stabilize(src: Path, dst: Path, work: Path, *, smoothing: int = 18, zoom: float = 0,
              codec_args: list[str]) -> Path:
    trf = work / f"{src.stem}.trf"
    ff.run(["-i", str(src), "-vf", f"vidstabdetect=shakiness=6:accuracy=15:result={ff.escape_filter_path(trf)}",
            "-f", "null", "-"], label="stabilize: analyse motion")
    ff.run(["-i", str(src), "-vf",
            f"vidstabtransform=input={ff.escape_filter_path(trf)}:smoothing={smoothing}:optzoom={'0' if zoom else '1'}"
            f":zoom={zoom}:interpol=bicubic,unsharp=5:5:0.4:3:3:0",
            *codec_args, "-c:a", "copy", str(dst)], label="stabilize: transform")
    return dst


DENOISE_V = {
    "light": "hqdn3d=1.5:1.5:4:4",
    "medium": "hqdn3d=3:2.5:6:5",
    "strong": "nlmeans=s=3.5:p=7:r=15",
}


def retime_chain(*, fps: float | None = None, speed: float | None = None, smooth: bool = True) -> tuple[str, str]:
    """(video filter, audio filter) for speed change and/or frame-rate conversion."""
    vf, af = [], []
    if speed and speed != 1:
        vf.append(f"setpts=PTS/{speed}")
        s, chain = speed, []
        while s > 2.0:
            chain.append("atempo=2.0"); s /= 2.0
        while s < 0.5:
            chain.append("atempo=0.5"); s /= 0.5
        chain.append(f"atempo={s:.6f}")
        af += chain
    if fps:
        vf.append(f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" if smooth
                  else f"fps={fps}")
    return ",".join(vf), ",".join(af)
