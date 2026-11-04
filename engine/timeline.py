"""Declarative timeline (projects/<slug>/timeline.json) -> finished, mastered render.

Pipeline (each stage is a separate, inspectable ffmpeg job; artefacts in cache/<slug>/render/):
  1. plan   : resolve media, compute frame-exact timing for every clip and transition
  2. audio  : place clip audio + tracks on buses, duck music under dialogue -> mix.wav (32f)
  3. master : static gain + 4x-oversampled true-peak limiting to the preset target -> master.wav
  4. video  : fit/grade/transition every clip in 10-bit, overlays, titles, fades, encode + mux

Timing is computed in integer frames, so long edits never drift out of sync.
See docs/timeline.md for the full schema.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import audio as audiomod
from . import ff, loudness, titles, video
from .paths import Project, next_version, run_dir
from .presets import Preset, load as load_preset
from .probe import MediaInfo, probe

TRANSITION_ALIASES = {
    "crossfade": "fade", "dissolve": "fade", "pixel-dissolve": "dissolve", "dip": "fadeblack", "dip-to-black": "fadeblack",
    "dip-to-white": "fadewhite", "flash": "fadewhite", "blur": "hblur", "zoom": "zoomin",
    "slide-left": "slideleft", "slide-right": "slideright", "slide-up": "slideup", "slide-down": "slidedown",
    "wipe-left": "wipeleft", "wipe-right": "wiperight", "smooth-left": "smoothleft", "smooth-right": "smoothright",
    "smooth-up": "smoothup", "smooth-down": "smoothdown", "circle": "circleopen", "fade-grays": "fadegrays",
}
MOTIONS = {"none", "push-in", "pull-out", "pan-left", "pan-right", "pan-up", "pan-down"}
CUT_FADE = 0.012  # 12 ms micro-fades on hard audio cuts: no clicks, inaudible otherwise
ROLES = ("dialogue", "music", "ambience", "sfx", "clip")


class TimelineError(ValueError):
    pass


@dataclass
class Clip:
    idx: int
    kind: str                     # video | image | color
    src: Path | None
    info: MediaInfo | None
    frames: int                   # timeline length in frames
    src_in: float = 0.0
    speed: float = 1.0
    fit: str = "cover"
    motion: str = "none"
    zoom: float = 0.12
    ease: str = "auto"
    color: str = "#000000"
    look: str | dict | None = None
    trans: str | None = None      # xfade transition INTO this clip
    trans_frames: int = 0
    start: int = 0                # timeline start frame
    gain_db: float | None = None  # clip audio gain; None = no clip audio
    raw: dict = field(default_factory=dict)


@dataclass
class Plan:
    project: Project
    spec: dict
    preset: Preset
    width: int
    height: int
    fps: float
    total_frames: int
    clips: list[Clip]
    warnings: list[str]
    draft: bool

    @property
    def duration(self) -> float:
        return self.total_frames / self.fps

    def sec(self, frames: int) -> float:
        return frames / self.fps


# ---------------------------------------------------------------- planning

def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def load_spec(project: Project, name: str = "timeline") -> dict:
    path = project.dir / (name if name.endswith(".json") else f"{name}.json")
    if not path.exists():
        raise SystemExit(f"timeline not found: {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise TimelineError(f"{path.name}: invalid JSON at line {e.lineno} col {e.colno}: {e.msg}") from None


def plan(project: Project, spec: dict, *, draft: bool = False, preset_name: str | None = None) -> Plan:
    preset = load_preset(preset_name or spec.get("delivery", "youtube-1080p"))
    canvas = spec.get("canvas", {})
    pw, ph = preset.size or (1920, 1080)
    w, h = int(canvas.get("width", pw)), int(canvas.get("height", ph))
    fps = float(canvas.get("fps", 30))
    warnings: list[str] = []
    if preset.size and abs(w / h - pw / ph) > 0.01:
        warnings.append(f"canvas {w}x{h} aspect differs from preset {preset.name} {pw}x{ph}; output will be letterboxed")
    if draft:
        w, h = _even(w / 2), _even(h / 2)

    clips: list[Clip] = []
    cursor = 0
    clip_audio_default = spec.get("clip_audio", True)
    for i, c in enumerate(spec.get("video", [])):
        where = f"video[{i}]"
        speed = float(c.get("speed", 1.0))
        if speed <= 0:
            raise TimelineError(f"{where}: speed must be > 0")
        if "color" in c and "src" not in c:
            kind, src, info = "color", None, None
        else:
            if "src" not in c:
                raise TimelineError(f"{where}: needs 'src' or 'color'")
            src = project.resolve(c["src"])
            info = probe(src)
            kind = "image" if info.is_image else "video"
            if not info.video:
                raise TimelineError(f"{where}: {src.name} has no video stream")
        src_in = float(c.get("in", 0.0))
        if "duration" in c:
            dur = float(c["duration"])
        elif "out" in c:
            dur = (float(c["out"]) - src_in) / speed
        elif kind == "video":
            dur = (info.duration - src_in) / speed
        else:
            raise TimelineError(f"{where}: images and color clips need 'duration'")
        if dur <= 0:
            raise TimelineError(f"{where}: non-positive duration ({dur:.3f}s); check in/out")
        if kind == "video" and src_in + dur * speed > info.duration + 0.05:
            warnings.append(f"{where}: requests {src_in + dur * speed:.2f}s but {src.name} is "
                            f"{info.duration:.2f}s; last frame will be held")
        frames = max(1, round(dur * fps))

        tr = c.get("transition")
        trans, tframes = None, 0
        if tr and i > 0:
            if isinstance(tr, str):
                tr = {"type": tr}
            ttype = TRANSITION_ALIASES.get(tr.get("type", "fade"), tr.get("type", "fade"))
            if ttype != "cut":
                trans = ttype
                tframes = round(float(tr.get("duration", 0.8)) * fps)
                prev = clips[-1]
                limit = min(prev.frames - prev.trans_frames, frames) - 1
                if tframes > limit:
                    raise TimelineError(f"{where}: transition {tframes / fps:.2f}s is longer than the "
                                        f"clips it joins allow ({limit / fps:.2f}s)")
        motion = c.get("motion", "none")
        if motion not in MOTIONS:
            raise TimelineError(f"{where}: motion {motion!r} not in {sorted(MOTIONS)}")

        start = cursor - tframes
        gain = None
        if kind == "video" and info.audio and not c.get("mute", False) and (clip_audio_default or "volume" in c):
            gain = float(c.get("volume", 0.0))
        clips.append(Clip(
            idx=i, kind=kind, src=src, info=info, frames=frames, src_in=src_in, speed=speed,
            fit=c.get("fit", spec.get("fit", "cover")), motion=motion, zoom=float(c.get("zoom", 0.12)),
            ease=c.get("ease", "auto"), color=c.get("color", "#000000"), look=c.get("look"),
            trans=trans, trans_frames=tframes, start=start, gain_db=gain, raw=c,
        ))
        cursor = start + frames

    if not clips:
        raise TimelineError("timeline has no video clips")
    return Plan(project, spec, preset, w, h, fps, cursor, clips, warnings, draft)


# ---------------------------------------------------------------- video graph

def _ease(expr_p: str, ease: str) -> str:
    if ease == "linear":
        return expr_p
    if ease == "out":
        return f"sin(PI/2*{expr_p})"
    return f"(1-cos(PI*{expr_p}))/2"   # in-out


def _motion_chain(c: Clip, w: int, h: int, fps: float) -> str:
    n = c.frames
    k = max(2, min(4, round(7680 / w)))          # supersample so zoompan's integer crop never jitters
    W, H = w * k, h * k
    pre = (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags={video.SCALE_FLAGS}:"
           f"out_color_matrix=bt709:out_range=tv,crop={W}:{H},setsar=1")
    p = f"(on/{max(1, n - 1)})"
    ease = c.ease if c.ease != "auto" else ("linear" if c.motion in ("push-in", "pull-out") else "inout")
    e = _ease(p, ease)
    zmax = 1 + c.zoom
    cx, cy = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    z, x, y = f"{zmax}", cx, cy
    if c.motion == "push-in":
        z = f"1+{c.zoom}*{e}"
    elif c.motion == "pull-out":
        z = f"{zmax}-{c.zoom}*{e}"
    elif c.motion == "pan-left":
        x = f"(iw-iw/zoom)*(1-{e})"
    elif c.motion == "pan-right":
        x = f"(iw-iw/zoom)*{e}"
    elif c.motion == "pan-up":
        y = f"(ih-ih/zoom)*(1-{e})"
    elif c.motion == "pan-down":
        y = f"(ih-ih/zoom)*{e}"
    return (f"{pre},zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={w}x{h}:fps={fps},"
            f"setsar=1,format={video.WORK_PIX}")


def _clip_chain(c: Clip, label_in: str, plan_: Plan, resolve) -> str:
    w, h, fps, n = plan_.width, plan_.height, plan_.fps, c.frames
    bg = plan_.spec.get("canvas", {}).get("background", "black")
    uid = f"c{c.idx}"
    if c.kind == "color":
        body = f"format={video.WORK_PIX}"
    elif c.kind == "image":
        if c.motion != "none":
            body = _motion_chain(c, w, h, fps)
        else:
            body = (f"{video.to_709(w, h, c.fit, bg, uid)},loop=loop={n - 1}:size=1:start=0,"
                    f"setpts=N/({fps}*TB)")
    else:
        tm = video.tonemap_chain(c.info)
        speed = f"setpts=(PTS-STARTPTS)/{c.speed}" if c.speed != 1 else "setpts=PTS-STARTPTS"
        body = ",".join(x for x in (tm, speed, f"fps={fps}", video.to_709(w, h, c.fit, bg, uid)) if x)
    look = video.grade_chain(c.look, resolve)
    tail = f"tpad=stop_mode=clone:stop={n},trim=end_frame={n},settb=AVTB,setpts=N/({fps}*TB),fps={fps}"
    return f"[{label_in}]{body}{',' + look if look else ''},{tail}[v{c.idx}]"


def _video_inputs(plan_: Plan) -> tuple[list[str], dict[int, int]]:
    args: list[str] = []
    index: dict[int, int] = {}
    for c in plan_.clips:
        index[c.idx] = len(index)
        dur = c.frames / plan_.fps
        if c.kind == "color":
            args += ["-f", "lavfi", "-i",
                     f"color=c={c.color}:s={plan_.width}x{plan_.height}:r={plan_.fps}:d={dur + 0.1:.4f}"]
        elif c.kind == "image":
            args += ["-i", str(c.src)]
        else:
            args += ["-ss", f"{c.src_in:.4f}", "-t", f"{dur * c.speed + 0.25:.4f}", "-i", str(c.src)]
    return args, index


def _overlay_inputs_and_graph(plan_: Plan, base: str, n_inputs: int) -> tuple[list[str], list[str], str]:
    """Logos / graphics / picture-in-picture over the program."""
    args, graph = [], []
    cur = base
    for j, o in enumerate(plan_.spec.get("overlays", [])):
        src = plan_.project.resolve(o["src"])
        info = probe(src)
        start, end = float(o.get("start", 0)), float(o.get("end", plan_.duration))
        fade = float(o.get("fade", 0.4))
        width = int(round(float(o.get("width", 0.15)) * plan_.width / 2) * 2)
        x, y = float(o.get("x", 0.5)), float(o.get("y", 0.5))
        opacity = float(o.get("opacity", 1.0))
        if info.is_image:
            args += ["-loop", "1", "-framerate", str(plan_.fps), "-t", f"{end - start:.4f}", "-i", str(src)]
        else:
            args += ["-ss", f"{float(o.get('in', 0)):.4f}", "-t", f"{end - start:.4f}", "-i", str(src)]
        k = n_inputs + j
        graph.append(
            f"[{k}:v]fps={plan_.fps},scale={width}:-2:flags={video.SCALE_FLAGS},format=yuva444p10le,"
            f"colorchannelmixer=aa={opacity},"
            f"fade=t=in:st=0:d={fade}:alpha=1,fade=t=out:st={max(0, end - start - fade):.4f}:d={fade}:alpha=1,"
            f"setpts=PTS-STARTPTS+{start}/TB[ov{j}];"
            f"[{cur}][ov{j}]overlay=x=W*{x}-w/2:y=H*{y}-h/2:eof_action=pass:format=auto[ovo{j}]"
        )
        cur = f"ovo{j}"
    return args, graph, cur


def build_video_graph(plan_: Plan, ass_path: Path | None) -> tuple[list[str], str, str]:
    resolve = plan_.project.resolve
    inputs, index = _video_inputs(plan_)
    graph = [_clip_chain(c, f"{index[c.idx]}:v", plan_, resolve) for c in plan_.clips]

    acc = "v0"
    for c in plan_.clips[1:]:
        out = f"j{c.idx}"
        if c.trans:
            graph.append(f"[{acc}][v{c.idx}]xfade=transition={c.trans}:duration={c.trans_frames / plan_.fps:.6f}:"
                         f"offset={c.start / plan_.fps:.6f}[{out}]")
        else:
            graph.append(f"[{acc}][v{c.idx}]concat=n=2:v=1:a=0,fps={plan_.fps}[{out}]")  # concat resets the timebase
        acc = out

    spec = plan_.spec
    post = []
    g = video.grade_chain(spec.get("grade"), resolve)
    if g:
        post.append(g)
    if post:
        graph.append(f"[{acc}]{','.join(post)}[graded]")
        acc = "graded"

    ov_args, ov_graph, acc = _overlay_inputs_and_graph(plan_, acc, len(index))
    inputs += ov_args
    graph += ov_graph

    final = []
    if ass_path:
        fonts = plan_.project.font_dirs()
        fd = f":fontsdir={ff.escape_filter_path(fonts[0])}" if fonts else ""
        final.append(f"ass=filename={ff.escape_filter_path(ass_path)}{fd}:shaping=complex")
    fi, fo = float(spec.get("fade_in", 0)), float(spec.get("fade_out", 0))
    if fi:
        final.append(f"fade=t=in:st=0:d={fi}")
    if fo:
        final.append(f"fade=t=out:st={plan_.duration - fo:.4f}:d={fo}")
    if plan_.preset.size and not plan_.draft and (plan_.width, plan_.height) != plan_.preset.size:
        pw, ph = plan_.preset.size
        final.append(video.to_709(pw, ph, "contain", "black"))
    final.append(video.TAG_709)
    final.append(f"trim=end_frame={plan_.total_frames}")
    graph.append(f"[{acc}]{','.join(final)}[vout]")
    return inputs, ";".join(graph), "[vout]"


# ---------------------------------------------------------------- audio graph

def _tempo(speed: float) -> str:
    return video.retime_chain(speed=speed)[1] if speed != 1 else ""


def build_audio_graph(plan_: Plan) -> tuple[list[str], str] | None:
    sr = 48000
    items: list[tuple[str, list[str], str]] = []   # (role, input args, filter chain from [k:a])
    total = plan_.duration

    # clip audio follows its picture: same in-point, speed and transition fades
    clips = plan_.clips
    for n, c in enumerate(clips):
        if c.gain_db is None:
            continue
        dur = c.frames / plan_.fps
        fin = c.trans_frames / plan_.fps or CUT_FADE
        nxt = clips[n + 1] if n + 1 < len(clips) else None
        fout = (nxt.trans_frames / plan_.fps if nxt and nxt.trans_frames else CUT_FADE)
        chain = ",".join(x for x in (
            "asetpts=PTS-STARTPTS", _tempo(c.speed),
            f"aresample={sr}:resampler=soxr", "aformat=sample_fmts=fltp:channel_layouts=stereo",
            f"volume={c.gain_db}dB", f"apad=whole_dur={dur:.6f}", f"atrim=end={dur:.6f}",
            f"afade=t=in:d={fin:.4f}:curve=tri", f"afade=t=out:st={dur - fout:.6f}:d={fout:.4f}:curve=tri",
            f"adelay={c.start / plan_.fps * 1000:.3f}:all=1",
        ) if x)
        items.append(("clip", ["-ss", f"{c.src_in:.4f}", "-t", f"{dur * c.speed + 0.25:.4f}", "-i", str(c.src)], chain))

    for i, t in enumerate(plan_.spec.get("audio", [])):
        where = f"audio[{i}]"
        role = t.get("role", "music")
        if role not in ROLES:
            raise TimelineError(f"{where}: role {role!r} not in {ROLES}")
        src = plan_.project.resolve(t["src"])
        info = probe(src)
        if not info.audio:
            raise TimelineError(f"{where}: {src.name} has no audio")
        start = float(t.get("start", 0))
        s_in = float(t.get("in", 0))
        loop = bool(t.get("loop", False))
        if "duration" in t:
            dur = float(t["duration"])
        elif "out" in t:
            dur = float(t["out"]) - s_in
        else:
            dur = (total - start) if loop else min(info.duration - s_in, total - start)
        dur = min(dur, total - start)
        if dur <= 0:
            plan_.warnings.append(f"{where}: starts after the program ends; skipped")
            continue
        fin = float(t.get("fade_in", CUT_FADE if role != "music" else 0.0)) or CUT_FADE
        fout = float(t.get("fade_out", CUT_FADE)) or CUT_FADE
        polish = t.get("polish")
        chain = ",".join(x for x in (
            "asetpts=PTS-STARTPTS",
            f"aresample={sr}:resampler=soxr", "aformat=sample_fmts=fltp:channel_layouts=stereo",
            audiomod.voice_chain(polish if isinstance(polish, str) else "light") if polish else "",
            f"volume={float(t.get('gain', 0))}dB",
            f"atrim=end={dur:.6f}",
            f"afade=t=in:d={fin:.4f}:curve=qsin", f"afade=t=out:st={max(0, dur - fout):.6f}:d={fout:.4f}:curve=qsin",
            f"adelay={start * 1000:.3f}:all=1",
        ) if x)
        args = (["-stream_loop", "-1"] if loop else []) + ["-ss", f"{s_in:.4f}", "-t", f"{dur + 0.1:.4f}", "-i", str(src)]
        items.append((role, args, chain))

    if not items:
        return None

    inputs: list[str] = []
    graph: list[str] = []
    buses: dict[str, list[str]] = {}
    for k, (role, args, chain) in enumerate(items):
        inputs += args
        graph.append(f"[{k}:a]{chain}[a{k}]")
        buses.setdefault(role, []).append(f"a{k}")

    def mix(labels: list[str], out: str) -> None:
        if len(labels) == 1:
            graph.append(f"[{labels[0]}]anull[{out}]")
        else:
            graph.append(f"{''.join(f'[{x}]' for x in labels)}amix=inputs={len(labels)}:normalize=0:"
                         f"duration=longest:dropout_transition=0[{out}]")

    for role, labels in buses.items():
        mix(labels, f"bus_{role}")

    duck = plan_.spec.get("duck", True)
    bus_out = []
    if duck and "dialogue" in buses and ({"music", "ambience"} & buses.keys()):
        depth = float(duck.get("depth", 0.75) if isinstance(duck, dict) else 0.75)  # 0..1
        n_sc = sum(1 for r in ("music", "ambience") if r in buses)
        # pad the sidechain: sidechaincompress stops when its key input ends, which would cut the music
        graph.append(f"[bus_dialogue]apad=whole_dur={total:.6f},asplit={n_sc + 1}[dlg]{''.join(f'[sc{j}]' for j in range(n_sc))}")
        bus_out.append("dlg")
        for j, r in enumerate(x for x in ("music", "ambience") if x in buses):
            graph.append(f"[bus_{r}][sc{j}]sidechaincompress=threshold=0.025:ratio={2 + 10 * depth:.1f}:"
                         f"attack=80:release=650:knee=4:link=maximum:detection=rms[{r}_d]")
            bus_out.append(f"{r}_d")
        bus_out += [f"bus_{r}" for r in buses if r not in ("dialogue", "music", "ambience")]
    else:
        bus_out = [f"bus_{r}" for r in buses]

    fi, fo = float(plan_.spec.get("fade_in", 0)), float(plan_.spec.get("fade_out", 0))
    tail = [f"apad=whole_dur={total:.6f}", f"atrim=end={total:.6f}"]
    if fi:
        tail.append(f"afade=t=in:d={fi}:curve=qsin")
    if fo:
        tail.append(f"afade=t=out:st={total - fo:.6f}:d={fo}:curve=qsin")
    if len(bus_out) == 1:
        graph.append(f"[{bus_out[0]}]{','.join(tail)}[mix]")
    else:
        graph.append(f"{''.join(f'[{x}]' for x in bus_out)}amix=inputs={len(bus_out)}:normalize=0:"
                     f"duration=longest:dropout_transition=0,{','.join(tail)}[mix]")
    return inputs, ";".join(graph)


# ---------------------------------------------------------------- render

def render(project: Project, *, timeline: str = "timeline", draft: bool = False, gpu: bool = False,
           preset_name: str | None = None, out: Path | None = None, until: float | None = None) -> dict:
    """Render under the project lock in a private run folder (safe with parallel agents)."""
    with project.lock("render"), run_dir(project, f"render-{timeline}", keep=True) as work:
        manifest = _render(project, work, timeline=timeline, draft=draft, gpu=gpu,
                           preset_name=preset_name, out=out, until=until)
        for bulky in work.glob("*.wav"):   # keep graphs + titles for debugging, drop audio
            bulky.unlink()
        return manifest


def _render(project: Project, work: Path, *, timeline: str, draft: bool, gpu: bool,
            preset_name: str | None, out: Path | None, until: float | None) -> dict:
    t0 = time.monotonic()
    spec = load_spec(project, timeline)
    p = plan(project, spec, draft=draft, preset_name=preset_name)
    for w in p.warnings:
        print(f"  ! {w}")
    preset = p.preset

    # 1-3: audio mix + master
    master_wav = None
    report = None
    if preset.audio:
        mix_wav = work / "mix.wav"
        built = build_audio_graph(p)
        if built:
            a_in, a_graph = built
            (work / "audio.graph.txt").write_text(a_graph.replace(";", ";\n"))
            ff.run([*a_in, "-filter_complex", a_graph, "-map", "[mix]", "-c:a", "pcm_f32le", "-ar", "48000",
                    str(mix_wav)], label="audio mix")
            master_wav = work / "master.wav"
            loud = spec.get("loudness", {})
            target = float(loud.get("integrated", preset.target_lufs or -14))
            tp = float(loud.get("true_peak", preset.target_tp))
            lossy = (preset.audio or {}).get("codec") not in loudness.LOSSLESS
            report = loudness.master(mix_wav, master_wav, target_lufs=target, target_tp=tp - (0.6 if lossy else 0),
                                     sample_rate=preset.sample_rate, codec_args=["-c:a", "pcm_f32le"],
                                     label="master")
        else:
            master_wav = work / "silence.wav"
            ff.run(["-f", "lavfi", "-i", f"anullsrc=r={preset.sample_rate}:cl=stereo", "-t", f"{p.duration:.6f}",
                    "-c:a", "pcm_f32le", str(master_wav)])

    # 4: video
    ass = None
    if spec.get("titles"):  # burned in before any final rescale, so authored at canvas size
        ass = titles.write_ass(spec["titles"], p.width, p.height, work / "titles.ass")
    v_in, v_graph, v_out = build_video_graph(p, ass)
    (work / "video.graph.txt").write_text(v_graph.replace(";", ";\n"))

    if out is None:
        kind = "drafts" if draft else "renders"
        stem = f"{project.slug}" + ("" if timeline == "timeline" else f"_{timeline}")
        out = next_version(project.out(kind), stem, "mp4" if draft else preset.ext)
    a_idx = v_in.count("-i")
    args = [*v_in]
    if master_wav:
        args += ["-i", str(master_wav)]
    args += ["-filter_complex", v_graph, "-map", v_out]
    if master_wav:
        args += ["-map", f"{a_idx}:a"]
    args += preset.video_args(draft=draft, gpu=gpu) + preset.audio_args(draft=draft)
    args += preset.container_args() if not draft else ["-movflags", "+faststart"]
    dur = min(until, p.duration) if until else p.duration
    args += ["-t", f"{dur:.6f}", "-metadata", f"title={spec.get('title', project.slug)}",
             "-metadata", "encoder=SouVi Engine", str(out)]
    try:
        ff.run(args, label=f"video {'draft ' if draft else ''}{p.width}x{p.height}@{p.fps:g} -> {out.name}")
    except BaseException:
        out.unlink(missing_ok=True)  # never leave a broken file that looks like a render
        raise

    manifest = {
        "output": str(out), "preset": preset.name, "draft": draft, "duration": round(dur, 3),
        "canvas": [p.width, p.height, p.fps], "clips": len(p.clips), "warnings": p.warnings,
        "loudness": report, "elapsed_s": round(time.monotonic() - t0, 1),
        "work_dir": str(work),
        "timeline_sha1": hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12],
    }
    out.with_suffix(out.suffix + ".json").write_text(json.dumps(manifest, indent=2))
    return manifest


def promote(render_path: Path, project: Project, name: str | None = None) -> Path:
    """Copy an approved render into output/<slug>/final/ under a clean name."""
    dst = project.out("final") / (name or render_path.name.split("_v")[0] + render_path.suffix)
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}.part")
    shutil.copy2(render_path, tmp)
    os.replace(tmp, dst)  # atomic: a reader never sees a half-copied deliverable
    return dst
