"""Quality control: verify a deliverable against its preset and catch defects.

FAIL  = violates the delivery spec (wrong codec/size/loudness, clipping, no faststart)
WARN  = probably a defect (black frames mid-program, long silence, frozen video)
INFO  = facts worth knowing
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

from . import ff, loudness
from .presets import Preset
from .probe import probe


@dataclass
class Check:
    level: str   # PASS | FAIL | WARN | INFO
    name: str
    detail: str

    def line(self) -> str:
        mark = {"PASS": "✔", "FAIL": "✘", "WARN": "!", "INFO": "·"}[self.level]
        return f"  {mark} {self.name:<14} {self.detail}"


def _top_atoms(path: Path) -> list[str]:
    atoms = []
    with path.open("rb") as f:
        while len(atoms) < 64:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            size, kind = struct.unpack(">I4s", hdr)
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
                f.seek(size - 16, 1)
            elif size == 0:
                atoms.append(kind.decode("latin1"))
                break
            else:
                f.seek(size - 8, 1)
            atoms.append(kind.decode("latin1"))
    return atoms


def _spans(text: str, start_key: str, end_key: str) -> list[tuple[float, float]]:
    starts = [float(x) for x in re.findall(rf"{start_key}[:=]\s*(-?[\d.]+)", text)]
    ends = [float(x) for x in re.findall(rf"{end_key}[:=]\s*(-?[\d.]+)", text)]
    return list(zip(starts, ends + [float("nan")] * (len(starts) - len(ends))))


def run_qc(path: Path, preset: Preset | None, *, detect: bool = True) -> list[Check]:
    m = probe(path)
    out: list[Check] = []
    add = lambda lvl, n, d: out.append(Check(lvl, n, d))  # noqa: E731

    add("INFO", "file", f"{m.format}, {m.duration:.3f}s, {m.size_bytes / 1e6:.1f} MB"
        + (f", {m.bitrate / 1e6:.1f} Mb/s" if m.bitrate else ""))
    if m.duration <= 0:
        add("FAIL", "duration", "zero-length media")

    pv = (preset.video if preset else None) or None
    if m.video:
        v = m.video
        if pv:
            add("PASS" if v.codec == pv["codec"].replace("lib", "").replace("x264", "h264").replace("x265", "hevc")
                .replace("svtav1", "av1").replace("prores_ks", "prores") else "FAIL",
                "video codec", v.codec)
            if preset.size:
                add("PASS" if (v.width, v.height) == preset.size else "FAIL", "resolution",
                    f"{v.width}x{v.height} (want {preset.size[0]}x{preset.size[1]})")
            add("PASS" if v.pix_fmt == pv["pix_fmt"] else "FAIL", "pixel format", f"{v.pix_fmt} (want {pv['pix_fmt']})")
        else:
            add("INFO", "video", f"{v.codec} {v.width}x{v.height} {v.pix_fmt}")
        tags = (v.color_primaries, v.color_trc, v.color_space)
        add("PASS" if all(t == "bt709" for t in tags) else "WARN", "color tags",
            "/".join(t or "unset" for t in tags) + ("" if all(tags) else " — players may shift colours"))
        add("INFO", "frame rate", f"{v.fps:g} fps" + (f", {v.frames} frames" if v.frames else ""))
        if pv and pv.get("max_fps") and v.fps > pv["max_fps"]:
            add("FAIL", "frame rate", f"{v.fps} > platform max {pv['max_fps']}")
    elif pv:
        add("FAIL", "video", "no video stream")

    if path.suffix.lower() in (".mp4", ".mov", ".m4a"):
        atoms = _top_atoms(path)
        if "moov" in atoms and "mdat" in atoms:
            fast = atoms.index("moov") < atoms.index("mdat")
            want = preset and "+faststart" in " ".join(preset.container_args())
            add("PASS" if fast else ("FAIL" if want else "INFO"), "faststart",
                "moov before mdat (streams instantly)" if fast else "moov at end (must download before play)")

    pa = preset.audio if preset else None
    if m.audio:
        a = m.audio
        if pa:
            add("PASS" if a.codec == pa["codec"].replace("lib", "").replace("mp3lame", "mp3") else "FAIL",
                "audio codec", a.codec)
            add("PASS" if a.sample_rate == int(pa.get("sample_rate", 48000)) else "FAIL", "sample rate", f"{a.sample_rate} Hz")
            if "channels" in pa:
                add("PASS" if a.channels == int(pa["channels"]) else "FAIL", "channels", str(a.channels))
        L = loudness.measure(path)
        if L.silent:
            add("INFO", "loudness", "silent audio track")
        elif preset and preset.loudness:
            ti, ttp = preset.target_lufs, preset.target_tp
            add("PASS" if abs(L.integrated - ti) <= 1.0 else "FAIL", "loudness",
                f"{L.integrated:.1f} LUFS (target {ti:g} ±1)")
            add("PASS" if L.true_peak <= ttp + 0.1 else "FAIL", "true peak", f"{L.true_peak:.1f} dBTP (max {ttp:g})")
        else:
            add("INFO", "loudness", L.line())
        add("FAIL" if L.sample_peak >= -0.01 else "PASS", "clipping",
            f"sample peak {L.sample_peak:.2f} dBFS")
        add("INFO", "dynamics", f"LRA {L.lra:.1f} LU" + ("  (very compressed)" if L.lra < 3 and not L.silent else ""))
        if abs(L.dc_offset) > 0.001:
            add("WARN", "dc offset", f"{L.dc_offset:.4f}")
    elif pa:
        add("FAIL", "audio", "no audio stream")

    if detect and m.duration > 0:
        vf = ["-vf", "blackdetect=d=0.25:pix_th=0.08,freezedetect=n=-55dB:d=2.5"] if m.video and not m.is_image else ["-vn"]
        af = ["-af", "silencedetect=n=-60dB:d=1.5"] if m.audio else ["-an"]
        err = ff.run(["-i", str(path), *vf, *af, "-f", "null", "-"], loglevel="info").stderr
        edge = 1.6  # intentional fades at head/tail are fine
        for s, e in _spans(err, "black_start", "black_end"):
            e = m.duration if e != e else e
            lvl = "INFO" if s < edge or e > m.duration - edge else "WARN"
            add(lvl, "black frames", f"{s:.2f}–{e:.2f}s")
        for s, e in _spans(err, "lavfi.freezedetect.freeze_start", "lavfi.freezedetect.freeze_end"):
            add("INFO", "static video", f"{s:.2f}–{(m.duration if e != e else e):.2f}s (fine for stills/titles)")
        for s, e in _spans(err, "silence_start", "silence_end"):
            e = m.duration if e != e else e
            lvl = "INFO" if s < edge or e > m.duration - edge else "WARN"
            add(lvl, "silence", f"{s:.2f}–{e:.2f}s")
    return out
