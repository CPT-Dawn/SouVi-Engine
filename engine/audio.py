"""Audio craft: voice polish, convolution reverb, procedural sound design.

All synthesis is pure ffmpeg (lavfi sources + expression filters), so nothing
beyond ffmpeg is required. Generated sounds are rendered at 48 kHz float and
then mastered to a sensible mixing level, leaving headroom for the mix.
"""

from __future__ import annotations

import math
from pathlib import Path

from . import ff, loudness

SR = 48000
WAV24 = ["-c:a", "pcm_s24le", "-ar", str(SR)]

# ---------------------------------------------------------------- voice polish

DENOISE = {
    "off": "",
    "light": "afftdn=nr=8:nf=-45:tn=1",
    "medium": "afftdn=nr=14:nf=-40:tn=1",
    "strong": "afftdn=nr=22:nf=-35:tn=1,anlmdn=s=0.0005:p=0.002:r=0.006",
}


def voice_chain(denoise: str = "light", *, warmth: float = 1.0, presence: float = 2.0, air: float = 1.5,
                deess: float = 0.35, comp: bool = True) -> str:
    """Broadcast-style dialogue chain: HPF -> denoise -> de-mud -> presence -> air -> de-ess -> glue."""
    parts = [
        "highpass=f=75:poles=2",
        DENOISE[denoise],
        "equalizer=f=280:t=q:w=1.1:g=-2.5",             # clear mud / boxiness
        f"equalizer=f=140:t=q:w=0.9:g={warmth:.2f}",     # chest warmth
        f"equalizer=f=3800:t=q:w=1.3:g={presence:.2f}",  # intelligibility
        f"highshelf=f=10000:g={air:.2f}",                # air
        f"deesser=i={deess:.2f}:m=0.5:f=0.55:s=o" if deess > 0 else "",
        "acompressor=threshold=-21dB:ratio=3:attack=8:release=140:knee=6:makeup=2" if comp else "",
        "alimiter=limit=0.89:attack=2:release=40:level=0",  # catch plosive spikes before mastering
    ]
    return ",".join(p for p in parts if p)


# ---------------------------------------------------------------- reverb

SPACES = {  # name: (RT60 seconds, damping lowpass Hz, predelay ms)
    "room": (0.6, 7000, 8),
    "studio": (0.9, 9000, 12),
    "hall": (2.2, 6500, 22),
    "cathedral": (4.5, 4500, 35),
    "plate": (1.6, 11000, 0),
}


def make_ir(path: Path, space: str = "hall") -> Path:
    rt, damp, pre = SPACES[space]
    dur = rt * 1.2
    k = 6.91 / rt  # exp(-k t) reaches -60 dB at RT60
    pre_s = pre / 1000
    env = f"if(lt(t,{pre_s}),0,exp(-{k:.4f}*(t-{pre_s})))"
    expr = f"(random(0)*2-1)*{env}|(random(1)*2-1)*{env}"
    ff.run([
        "-f", "lavfi", "-i", f"aevalsrc=exprs='{expr}':s={SR}:d={dur:.3f}",
        "-af", f"highpass=f=180,lowpass=f={damp},lowpass=f={damp * 1.4:.0f}",
        "-c:a", "pcm_f32le", str(path),
    ])
    return path


def reverb(src: Path, dst: Path, *, space: str = "hall", mix: float = 0.22, work: Path) -> Path:
    ir = make_ir(work / f"ir_{space}.wav", space)
    tail = SPACES[space][0] * 1.2
    graph = (
        f"[0:a]aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo,apad=pad_dur={tail:.2f},asplit=2[dry][toverb];"
        f"[toverb][1:a]afir=dry=1:wet=1:irnorm=1:gtype=peak[wet];"
        f"[dry][wet]amix=inputs=2:weights='{1 - mix:.3f} {mix:.3f}':normalize=0:duration=longest[out]"
    )
    ff.run(["-i", str(src), "-i", str(ir), "-filter_complex", graph, "-map", "[out]",
            "-c:a", "pcm_f32le", str(dst)], label=f"reverb {space}")
    return dst


# ---------------------------------------------------------------- sound design

def _stereo_noise(color: str, d: float) -> str:
    return (f"anoisesrc=c={color}:r={SR}:a=0.5:d={d}:s=11[n1];"
            f"anoisesrc=c={color}:r={SR}:a=0.5:d={d}:s=29[n2];"
            f"[n1][n2]join=inputs=2:channel_layout=stereo")


def _sweep(fc_expr: str, width: float) -> str:
    """Time-varying spectral bandpass on noise: Gaussian in log-frequency around fc(t)."""
    f = "(b*sr/(2*nb)+1)"
    g = f"exp(-pow(log({f})-log({fc_expr}),2)/{2 * width * width:.4f})"
    return f"afftfilt=real='re*{g}':imag='im*{g}':win_size=2048:overlap=0.75"


def sfx_graph(kind: str, d: float, pitch: float = 1.0, mood: str = "minor") -> str:
    """Return a filter_complex graph whose final label is [out]."""
    if kind == "whoosh":
        # an object passing by: band rises & falls, bell envelope peaks at 55%, pans L->R
        p = f"(pts/sr/{d})"
        fc = f"(250*{pitch}*pow(16,sin(PI*min(1,{p}))))"
        env = f"pow(sin(PI*pow(t/{d},0.85)),2.2)"
        return (f"{_stereo_noise('pink', d)},{_sweep(fc, 0.55)},"
                f"aeval=exprs='val(0)*{env}*(1.15-0.6*t/{d})|val(1)*{env}*(0.55+0.6*t/{d})',"
                f"highpass=f=90,lowpass=f=12000[out]")
    if kind == "riser":
        p = f"(pts/sr/{d})"
        fc = f"(300*{pitch}*pow(30,pow(min(1,{p}),1.6)))"
        f0, f1 = 110 * pitch, 880 * pitch
        k = (f1 - f0) / (2 * d)
        tone = f"0.35*sin(2*PI*({f0}*t+{k:.4f}*t*t))*pow(t/{d},2)"
        tone2 = f"0.18*sin(2*PI*({f0 * 1.5}*t+{k * 1.5:.4f}*t*t))*pow(t/{d},2.5)"
        return (f"{_stereo_noise('white', d)},{_sweep(fc, 0.5)},"
                f"aeval=exprs='val(0)*pow(t/{d},2.4)|val(1)*pow(t/{d},2.4)'[nz];"
                f"aevalsrc=exprs='{tone}+{tone2}|{tone}+{tone2}':s={SR}:d={d}[tn];"
                f"[nz][tn]amix=inputs=2:weights='0.8 0.6':normalize=0,"
                f"afade=t=out:st={d - 0.03:.3f}:d=0.03[out]")
    if kind == "impact":
        f_end, f_drop = 38 * pitch, 70 * pitch
        sub = f"0.9*sin(2*PI*({f_end}*t+{f_drop}*(1-exp(-9*t))/9))*exp(-2.6*t)"
        return (f"aevalsrc=exprs='{sub}|{sub}':s={SR}:d={d}[sub];"
                f"{_stereo_noise('brown', d)},aeval=exprs='val(0)*exp(-22*t)*1.6|val(1)*exp(-22*t)*1.6',"
                f"lowpass=f=4500[hit];"
                f"[sub][hit]amix=inputs=2:normalize=0,afade=t=in:d=0.002,"
                f"afade=t=out:st={d * 0.7:.3f}:d={d * 0.3:.3f}[out]")
    if kind == "tick":
        f = 2400 * pitch
        x = f"0.7*sin(2*PI*{f}*t)*exp(-95*t)+0.3*sin(2*PI*{f * 2.01}*t)*exp(-160*t)"
        return f"aevalsrc=exprs='{x}|{x}':s={SR}:d={d}[out]"
    if kind == "drone":
        root = 55 * pitch
        third = 1.1892 if mood == "minor" else 1.2599
        ratios = [1, 2, 3, 2 * third * 1.0, 4 * 1.4983, 8 * third]
        amps = [0.30, 0.22, 0.12, 0.10, 0.06, 0.03]
        partials = []
        for i, (r, a) in enumerate(zip(ratios, amps)):
            f = root * r
            lfo = f"(1+0.25*sin(2*PI*{0.05 + 0.031 * i:.3f}*t+{i}))"
            partials.append(f"{a}*{lfo}*(sin(2*PI*{f:.3f}*t)+0.6*sin(2*PI*{f * 1.0035:.3f}*t+{i}))")
        left = "+".join(partials)
        right = left.replace("t+", "t+0.7+")  # phase-offset right channel = width
        return (f"aevalsrc=exprs='{left}|{right}':s={SR}:d={d},lowpass=f=2600,"
                f"afade=t=in:d={min(3, d / 3):.2f}:curve=qsin,"
                f"afade=t=out:st={d - min(4, d / 3):.2f}:d={min(4, d / 3):.2f}:curve=qsin[out]")
    raise ValueError(f"unknown sfx kind {kind!r}")


SFX = {  # kind: (default duration, mix level LUFS, true-peak ceiling, reverb space or None)
    "whoosh": (1.2, -20.0, -3.0, "studio"),
    "riser": (4.0, -20.0, -3.0, "hall"),
    "impact": (2.5, -16.0, -1.5, "hall"),
    "tick": (0.12, -24.0, -6.0, None),
    "drone": (20.0, -26.0, -6.0, "cathedral"),
}


def sfx(kind: str, dst: Path, *, duration: float | None = None, pitch: float = 1.0,
        mood: str = "minor", space: str | None = "default", work: Path) -> dict:
    d0, lufs, tp, default_space = SFX[kind]
    d = duration or d0
    raw = work / f"sfx_{kind}_raw.wav"
    ff.run(["-filter_complex", sfx_graph(kind, d, pitch, mood), "-map", "[out]",
            "-c:a", "pcm_f32le", "-ar", str(SR), str(raw)], label=f"synth {kind}")
    space = default_space if space == "default" else space
    src = raw
    if space:
        src = reverb(raw, work / f"sfx_{kind}_verb.wav", space=space, mix=0.18 if kind != "drone" else 0.35, work=work)
    return loudness.master(src, dst, target_lufs=lufs, target_tp=tp, sample_rate=SR,
                           codec_args=["-c:a", "pcm_s24le"], sample_fmt="s32", dither="triangular_hp",
                           label=f"level {kind}")


def note_ratio(semitones: float) -> float:
    return math.pow(2, semitones / 12)
