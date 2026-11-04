"""Make media *visible* to Claude: contact sheets, stills, spectrograms.

Claude cannot watch or listen. These commands turn time-based media into PNGs
(read them with the Read tool) plus numbers, so every edit can be reviewed.
"""

from __future__ import annotations

from pathlib import Path

from . import ff, loudness
from .probe import probe

MONO_FONT = "JetBrains Mono"


def contact_sheet(src: Path, dst: Path, *, cols: int = 4, rows: int = 4, start: float = 0.0,
                  end: float | None = None, tile_w: int = 480) -> Path:
    info = probe(src)
    if not info.video:
        raise SystemExit(f"{src.name} has no video stream")
    end = min(end or info.duration, info.duration) if info.duration else end or 1.0
    span = max(0.04, end - start)
    n = cols * rows
    step = span / n
    label = (f"drawtext=font='{MONO_FONT}':text='%{{pts\\:hms\\:{start:.4f}}}':x=10:y=h-th-10:"
             f"fontsize={max(14, tile_w // 26)}:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=6")
    vf = (f"select='gte(t\\,{step / 2:.6f}+selected_n*{step:.6f})',scale={tile_w}:-2:flags=lanczos,"
          f"{label},tile={cols}x{rows}:padding=6:margin=6:color=0x101012")
    ff.run(["-ss", f"{start:.4f}", "-t", f"{span:.4f}", "-i", str(src), "-vf", vf, "-fps_mode", "passthrough",
            "-frames:v", "1", "-update", "1", str(dst)], label=f"contact sheet {cols}x{rows} {start:.2f}-{end:.2f}s")
    return dst


def still(src: Path, dst: Path, at: float) -> Path:
    ff.run(["-ss", f"{at:.4f}", "-i", str(src), "-frames:v", "1", "-update", "1", str(dst)],
           label=f"frame @ {at:.3f}s")
    return dst


def spectrogram(src: Path, dst: Path, *, width: int = 1600) -> tuple[Path, loudness.Loudness]:
    """Log-frequency spectrogram (with axes) stacked over a per-channel waveform."""
    work = dst.with_suffix("")
    spec, wave = Path(f"{work}_spec.png"), Path(f"{work}_wave.png")
    ff.run(["-i", str(src), "-filter_complex",
            f"[0:a]aformat=channel_layouts=stereo,showspectrumpic=s={width}x520:legend=1:fscale=log:"
            f"scale=log:color=fiery:gain=1.4:drange=110", "-frames:v", "1", "-update", "1", str(spec)],
           label="spectrogram")
    sw = probe(spec).video.width
    ff.run(["-i", str(src), "-filter_complex",
            f"[0:a]aformat=channel_layouts=stereo,showwavespic=s={width}x260:split_channels=1:scale=sqrt:"
            f"colors=0x7dd3fc|0xfda4af:draw=full,format=rgba,"
            f"pad={sw}:ih+16:{(sw - width) // 2}:8:color=0x000000", "-frames:v", "1", "-update", "1", str(wave)],
           label="waveform")
    ff.run(["-i", str(spec), "-i", str(wave), "-filter_complex", "[0][1]vstack=inputs=2,format=rgb24",
            "-frames:v", "1", "-update", "1", str(dst)])
    spec.unlink(missing_ok=True)
    wave.unlink(missing_ok=True)
    return dst, loudness.measure(src)
