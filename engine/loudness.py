"""Loudness measurement (EBU R128 / ITU-R BS.1770) and deterministic mastering.

Mastering strategy (why not plain `loudnorm`): single-pass loudnorm rides gain
dynamically and pumps. Instead we apply ONE static gain to hit the integrated
target, then catch peaks with a brick-wall limiter running at 4x oversampling
(192 kHz) so the ceiling approximates *true* peak, then resample back with soxr
and dither. We measure the actual encoded deliverable and iterate (max 4 passes)
until integrated loudness is within ±0.3 LU and true peak is under the ceiling.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from . import ff

LOSSLESS = {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "flac", "alac"}
SILENT_LUFS = -70.0


@dataclass
class Loudness:
    integrated: float      # LUFS
    true_peak: float       # dBTP
    lra: float             # LU
    threshold: float       # LUFS (gating)
    sample_peak: float     # dBFS
    rms: float             # dBFS
    dc_offset: float

    @property
    def silent(self) -> bool:
        return self.integrated <= SILENT_LUFS or math.isinf(self.integrated)

    def to_dict(self) -> dict:
        return asdict(self)

    def line(self) -> str:
        return (f"I {self.integrated:6.1f} LUFS | TP {self.true_peak:5.1f} dBTP | LRA {self.lra:4.1f} LU"
                f" | peak {self.sample_peak:5.1f} dBFS | RMS {self.rms:5.1f} dBFS")


def _f(x: str) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("-inf")


def measure(path: str | Path, *, pre_filters: str = "") -> Loudness:
    chain = ",".join(x for x in (
        pre_filters,
        "astats=measure_perchannel=none:measure_overall=Peak_level+RMS_level+DC_offset",
        "loudnorm=print_format=json",
    ) if x)
    proc = ff.run(["-i", str(path), "-vn", "-sn", "-af", chain, "-f", "null", "-"], loglevel="info")
    err = proc.stderr
    m = re.search(r"\{\s*\"input_i\".*?\}", err, re.S)
    if not m:
        raise ff.FFError(f"could not parse loudness of {path}")
    j = json.loads(m.group(0))

    def stat(name: str) -> float:
        mm = re.findall(rf"{name}:\s*(-?[\d.]+|-?inf)", err)
        return _f(mm[-1]) if mm else float("nan")

    return Loudness(
        integrated=_f(j["input_i"]),
        true_peak=_f(j["input_tp"]),
        lra=_f(j["input_lra"]),
        threshold=_f(j["input_thresh"]),
        sample_peak=stat("Peak level dB"),
        rms=stat("RMS level dB"),
        dc_offset=stat("DC offset"),
    )


def master_chain(gain_db: float, ceiling_dbtp: float, sr: int, sample_fmt: str, dither: str) -> str:
    limit = max(0.0625, min(1.0, ff.db_to_lin(ceiling_dbtp)))
    return ",".join([
        f"volume={gain_db:.3f}dB",
        "aresample=192000:resampler=soxr:precision=28",
        f"alimiter=limit={limit:.6f}:attack=0.8:release=60:level=0:latency=1:asc=1:asc_level=0.4",
        f"aresample={sr}:resampler=soxr:precision=28:osf={sample_fmt}:dither_method={dither}",
    ])


def master(
    src: str | Path,
    dst: str | Path,
    *,
    target_lufs: float,
    target_tp: float = -1.0,
    sample_rate: int = 48000,
    codec_args: list[str] | None = None,
    sample_fmt: str = "flt",
    dither: str = "none",
    pre_filters: str = "",
    extra_args: list[str] | None = None,
    label: str = "master",
) -> dict:
    """Master `src` to `dst` at the target loudness. Returns a report dict."""
    codec_args = codec_args or ["-c:a", "pcm_f32le"]
    codec = codec_args[codec_args.index("-c:a") + 1] if "-c:a" in codec_args else "pcm_f32le"
    before = measure(src, pre_filters=pre_filters)
    if before.silent and before.true_peak > -60:
        # shorter than the 400 ms gating block (ticks, clicks): peak-normalise instead
        gain = target_tp - 0.5 - before.true_peak
        chain = ",".join(x for x in (pre_filters, f"volume={gain:.3f}dB",
                                      f"aresample={sample_rate}:resampler=soxr:osf={sample_fmt}:dither_method={dither}") if x)
        ff.run(["-i", str(src), "-vn", "-af", chain, *codec_args, *(extra_args or []), str(dst)], label=f"{label} (peak)")
        after = measure(dst)
        return {"before": before.to_dict(), "after": after.to_dict(), "gain_db": round(gain, 2), "passes": 1,
                "on_target": True, "note": "too short for LUFS gating; peak-normalised to the true-peak ceiling"}
    if before.silent:
        ff.run(["-i", str(src), "-vn", *codec_args, *(extra_args or []), str(dst)], label=f"{label} (silent source)")
        return {"before": before.to_dict(), "after": before.to_dict(), "passes": 0, "note": "source is silent"}

    margin = 0.3 if codec in LOSSLESS else 0.9          # lossy codecs overshoot true peak
    gain = target_lufs - before.integrated
    ceiling = target_tp - margin
    after = before
    passes = 0
    for passes in range(1, 5):
        chain = ",".join(x for x in (pre_filters, master_chain(gain, ceiling, sample_rate, sample_fmt, dither)) if x)
        ff.run(["-i", str(src), "-vn", "-sn", "-af", chain, *codec_args, *(extra_args or []), str(dst)],
               label=f"{label} pass {passes}")
        after = measure(dst)
        di = target_lufs - after.integrated
        tp_over = after.true_peak - target_tp
        if abs(di) <= 0.3 and tp_over <= 0.05:
            break
        if tp_over > 0.05:
            ceiling -= tp_over + 0.1
        gain += di
    return {
        "before": before.to_dict(),
        "after": after.to_dict(),
        "gain_db": round(gain, 2),
        "ceiling_dbtp": round(ceiling, 2),
        "passes": passes,
        "on_target": abs(target_lufs - after.integrated) <= 0.5 and after.true_peak <= target_tp + 0.1,
        "limiting_heavy": gain - (target_lufs - before.integrated) > 3 or (before.true_peak + gain - ceiling) > 6,
    }
