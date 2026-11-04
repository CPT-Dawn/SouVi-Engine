"""`./souvi` command-line interface. Run `./souvi <command> -h` for details."""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import json
import sys
from pathlib import Path

from . import __version__, audio, ff, inspect, loudness, presets, probe, qc, timeline, titles, video
from . import project as projmod
from .paths import ROOT, SHARED, Project, default_out_dir, next_version, project_from_path, run_dir


# ---------------------------------------------------------------- helpers

def _src(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.exists() and (ROOT / path).exists():
        p = ROOT / path
    if not p.exists():
        raise SystemExit(f"no such file: {path}")
    return p.resolve()


def _rel(p: Path) -> str:
    """Repo-relative inside the SouVi repo; absolute when called from another repo."""
    p = p.resolve()
    if Path.cwd().resolve() != ROOT:
        return str(p)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _derived(src: Path, tag: str, ext: str | None, out: str | None) -> Path:
    """Processed-asset path: beside the source (so it is usable as an asset), never overwriting."""
    if out:
        return Path(out).resolve()
    ext = ext or src.suffix.lstrip(".")
    base = src.parent if project_from_path(src) or src.is_relative_to(ROOT) else default_out_dir(src, None, "renders")
    return next_version(base, f"{src.stem}.{tag}", ext)


_JOBS = contextlib.ExitStack()  # private run folders, removed when the command exits


def _work(src: Path | None, project: str | None, label: str = "job") -> Path:
    """A private working folder for this command (parallel agents never share temp files)."""
    p = Project(project) if project else (project_from_path(src) if src else None)
    return _JOBS.enter_context(run_dir(p, label))


def _print_report(rep: dict) -> None:
    b, a = rep["before"], rep["after"]
    print(f"  before  I {b['integrated']:6.1f} LUFS  TP {b['true_peak']:5.1f} dBTP  LRA {b['lra']:4.1f}")
    print(f"  after   I {a['integrated']:6.1f} LUFS  TP {a['true_peak']:5.1f} dBTP  LRA {a['lra']:4.1f}"
          f"  ({rep.get('passes', 0)} pass{'es' if rep.get('passes', 0) != 1 else ''})")
    if rep.get("limiting_heavy"):
        print("  ! heavy limiting was needed — source is very dynamic; consider compression or a lower target")
    if rep.get("note"):
        print(f"  · {rep['note']}")


# ---------------------------------------------------------------- commands

def cmd_doctor(a):
    from .doctor import doctor
    return doctor()


def cmd_new(a):
    p = projmod.create(a.slug, title=a.title, preset=a.preset, fps=a.fps)
    print(f"created project '{p.slug}'")
    print(f"  plan    {_rel(p.dir)}/timeline.json, BRIEF.md")
    print(f"  assets  {_rel(p.assets)}/{{footage,images,music,voice,sfx,graphics,fonts,luts,refs}}")
    print(f"  output  {_rel(p.output)}/{{drafts,renders,final,review}}")


def cmd_projects(a):
    rows = projmod.list_projects()
    if not rows:
        print("no projects yet — souvi new <slug>")
    for r in rows:
        print(f"  {r['slug']:<28} assets {r['assets']:>4}   outputs {r['outputs']:>4}   latest {r['latest']}")


def cmd_assets(a):
    p = Project(a.slug).require()
    inv = projmod.asset_inventory(p)
    if not inv:
        print(f"no assets in {_rel(p.assets)}")
    for _, f in inv:
        try:
            m = probe.probe(f)
            line = probe.summary(m).splitlines()
            print(f"{projmod.relpath(f, p.assets)}\n" + "\n".join(line[1:]) if len(line) > 1
                  else f"{projmod.relpath(f, p.assets)}  ({m.duration:.2f}s)")
        except ff.FFError:
            print(f"{projmod.relpath(f, p.assets)}  (not media)")


def cmd_probe(a):
    for f in a.files:
        m = probe.probe(_src(f))
        print(json.dumps(m.to_dict(), indent=2) if a.json else probe.summary(m))


def cmd_render(a):
    p = Project(a.slug).require()
    man = timeline.render(p, timeline=a.timeline, draft=a.draft, gpu=a.gpu, preset_name=a.preset,
                          until=a.until, out=Path(a.out).resolve() if a.out else None)
    print(f"→ {_rel(Path(man['output']))}  ({man['duration']:.2f}s, rendered in {man['elapsed_s']}s)")
    if man.get("loudness"):
        _print_report(man["loudness"])
    if not a.draft and not a.no_qc:
        _qc_print(Path(man["output"]), presets.load(man["preset"]), detect=True)


def cmd_plan(a):
    p = Project(a.slug).require()
    pl = timeline.plan(p, timeline.load_spec(p, a.timeline), draft=False)
    print(f"{pl.width}x{pl.height} @ {pl.fps:g} fps · {pl.duration:.3f}s ({pl.total_frames} frames) · {pl.preset.name}")
    for c in pl.clips:
        name = c.src.name if c.src else c.color
        tr = f"  ⟵ {c.trans} {c.trans_frames / pl.fps:.2f}s" if c.trans else ""
        print(f"  [{c.idx:>2}] {pl.sec(c.start):7.3f} → {pl.sec(c.start + c.frames):7.3f}  {c.kind:<5} {name}"
              f"{f'  motion={c.motion}' if c.motion != 'none' else ''}{tr}")
    for t in pl.spec.get("titles", []):
        print(f"  title {float(t['start']):7.3f} → {float(t['end']):7.3f}  [{t.get('style', 'hero')}] {t['text']!r}")
    for t in pl.spec.get("audio", []):
        print(f"  audio @{float(t.get('start', 0)):7.3f}  {t.get('role', 'music'):<9} {t['src']}")
    for w in pl.warnings:
        print(f"  ! {w}")


def cmd_promote(a):
    src = _src(a.render)
    p = project_from_path(src)
    if not p:
        raise SystemExit("promote expects a file under output/<slug>/")
    dst = timeline.promote(src, p, a.name)
    print(f"→ {_rel(dst)}")
    if a.to:
        to = Path(a.to).expanduser().resolve()
        to.mkdir(parents=True, exist_ok=True)
        tmp = to / f".{dst.name}.part"
        shutil.copy2(dst, tmp)
        os.replace(tmp, to / dst.name)
        print(f"→ {to / dst.name}")


KIND_BY_EXT = {
    **dict.fromkeys(("mp4", "mov", "mkv", "webm", "avi", "m4v", "mxf", "mts"), "footage"),
    **dict.fromkeys(("png", "jpg", "jpeg", "webp", "tif", "tiff", "heic", "avif", "bmp", "exr"), "images"),
    **dict.fromkeys(("wav", "mp3", "flac", "aac", "m4a", "ogg", "opus", "aif", "aiff"), "music"),
    **dict.fromkeys(("ttf", "otf", "woff", "woff2"), "fonts"),
    **dict.fromkeys(("cube", "3dl"), "luts"),
    "svg": "graphics",
}


def cmd_import(a):
    p = Project(a.slug).require()
    for f in a.files:
        src = Path(f).expanduser().resolve()
        if not src.is_file():
            raise SystemExit(f"no such file: {f}")
        kind = a.kind or KIND_BY_EXT.get(src.suffix.lower().lstrip("."), "refs")
        dst = p.assets / kind / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() or dst.is_symlink():
            print(f"  = {kind}/{src.name} (already imported)")
            continue
        if a.link:
            dst.symlink_to(src)
        else:
            shutil.copy2(src, dst)
        print(f"  + {kind}/{src.name}")


def cmd_export(a):
    src = _src(a.file)
    pr = presets.load(a.preset)
    m = probe.probe(src)
    work = _work(src, a.project, "export")
    out = Path(a.out).resolve() if a.out else next_version(default_out_dir(src, a.project, "renders"),
                                                           f"{src.stem}.{pr.name}", pr.ext)
    args = ["-i", str(src)]
    vmap = []
    if pr.video and m.video:
        vf = [video.tonemap_chain(m)]
        if a.fps:
            vf.append(f"fps={a.fps}")
        if pr.size and not pr.video.get("keep_source_geometry"):
            vf.append(video.to_709(*pr.size, mode=a.fit))
        else:
            vf.append(f"scale=flags={video.SCALE_FLAGS}:out_color_matrix=bt709:out_range=tv,format={video.WORK_PIX}")
        vf.append(video.grade_chain(a.grade))
        vf.append(video.TAG_709)
        args += ["-filter_complex", f"[0:v]{','.join(x for x in vf if x)}[v]"]
        vmap = ["-map", "[v]"]
    master_wav = None
    if pr.audio and m.audio:
        if pr.loudness:
            master_wav = work / f"{src.stem}.export-master.wav"
            lossy = pr.audio["codec"] not in loudness.LOSSLESS
            rep = loudness.master(src, master_wav, target_lufs=pr.target_lufs,
                                  target_tp=pr.target_tp - (0.6 if lossy else 0), sample_rate=pr.sample_rate,
                                  codec_args=["-c:a", "pcm_f32le"])
            _print_report(rep)
            args += ["-i", str(master_wav)]
    if pr.audio and pr.video and not m.audio:  # platforms expect an audio track: add true silence
        args += ["-f", "lavfi", "-t", f"{m.duration:.6f}", "-i", f"anullsrc=r={pr.sample_rate}:cl=stereo"]
    amap = (["-map", "1:a"] if master_wav or (pr.audio and pr.video and not m.audio)
            else (["-map", "0:a:0"] if pr.audio and m.audio else []))
    sfmt, dither = pr.out_sample_fmt()
    af = ["-af", f"aresample={pr.sample_rate}:resampler=soxr:osf={sfmt}:dither_method={dither}"] if amap else []
    args += vmap + amap + (pr.video_args() if vmap else ["-vn"]) + (pr.audio_args() + af if amap else ["-an"])
    args += pr.container_args() + ["-metadata", "encoder=SouVi Engine", str(out)]
    ff.run(args, label=f"export {pr.name} -> {out.name}")
    print(f"→ {_rel(out)}")
    if not a.no_qc:
        _qc_print(out, pr, detect=False)


def cmd_master(a):
    src = _src(a.file)
    pr = presets.load(a.preset)
    target = a.lufs if a.lufs is not None else pr.target_lufs
    tp = a.tp if a.tp is not None else pr.target_tp
    if target is None:
        raise SystemExit(f"preset {pr.name} has no loudness target; pass --lufs")
    ext = pr.ext if not pr.video else "wav"
    out = Path(a.out).resolve() if a.out else next_version(default_out_dir(src, a.project, "renders"),
                                                           f"{src.stem}.master", ext)
    sfmt, dither = pr.out_sample_fmt() if not pr.video else ("s32", "triangular_hp")
    codec = pr.audio_args() if not pr.video else ["-c:a", "pcm_s24le", "-ar", "48000"]
    rep = loudness.master(src, out, target_lufs=target, target_tp=tp, sample_rate=pr.sample_rate,
                          codec_args=codec, sample_fmt=sfmt, dither=dither, extra_args=pr.container_args() if not pr.video else [])
    print(f"→ {_rel(out)}")
    _print_report(rep)


def cmd_voice(a):
    src = _src(a.file)
    chain = audio.voice_chain(a.denoise, presence=a.presence, deess=a.deess)
    out = _derived(src, "polished", "wav", a.out)
    rep = loudness.master(src, out, target_lufs=a.lufs, target_tp=-1.5, pre_filters=chain + ",aformat=channel_layouts=mono",
                          codec_args=["-c:a", "pcm_s24le", "-ar", "48000"], sample_fmt="s32", dither="triangular_hp",
                          label="voice")
    print(f"→ {_rel(out)}")
    _print_report(rep)


def cmd_sfx(a):
    dst_dir = Project(a.project).require().assets / "sfx" if a.project else SHARED / "sfx"
    dst_dir.mkdir(parents=True, exist_ok=True)
    work = _work(None, a.project, "sfx")
    out = Path(a.out).resolve() if a.out else next_version(dst_dir, a.name or a.kind, "wav")
    rep = audio.sfx(a.kind, out, duration=a.duration, pitch=audio.note_ratio(a.pitch), mood=a.mood,
                    space=None if a.space == "none" else a.space, work=work)
    print(f"→ {_rel(out)}")
    _print_report(rep)


def cmd_reverb(a):
    src = _src(a.file)
    out = _derived(src, f"verb-{a.space}", "wav", a.out)
    tmp = _work(src, None, "reverb") / f"{src.stem}.verb.wav"
    audio.reverb(src, tmp, space=a.space, mix=a.mix)
    ff.run(["-i", str(tmp), "-af", "aresample=48000:osf=s32:dither_method=triangular_hp", "-c:a", "pcm_s24le", str(out)])
    print(f"→ {_rel(out)}")


def _mezz_args() -> list[str]:
    return presets.load("mezzanine").video_args()


def cmd_fx(a):
    src = _src(a.file)
    m = probe.probe(src)
    out = _derived(src, a.cmd, "mov", a.out)
    work = _work(src, None, a.cmd)
    mezz = _mezz_args() + ["-c:a", "pcm_s24le"]
    if a.cmd == "stabilize":
        video.stabilize(src, out, work, smoothing=a.smoothing, zoom=a.zoom, codec_args=_mezz_args())
    elif a.cmd == "denoise":
        ff.run(["-i", str(src), "-vf", video.DENOISE_V[a.strength], *mezz, str(out)], label=f"denoise {a.strength}")
    elif a.cmd == "grade":
        chain = video.grade_chain({"look": a.look, "lut": a.lut, "grain": a.grain, "vignette": a.vignette,
                                   "sharpen": a.sharpen})
        if not chain:
            raise SystemExit("nothing to do: pass --look, --lut, --grain, --vignette or --sharpen")
        ff.run(["-i", str(src), "-vf", f"{video.tonemap_chain(m) + ',' if m.video.hdr else ''}"
                f"format={video.WORK_PIX},{chain}", *mezz, str(out)], label="grade")
    elif a.cmd == "retime":
        vf, af = video.retime_chain(fps=a.fps, speed=a.speed, smooth=not a.no_interp)
        args = ["-i", str(src)]
        if vf:
            args += ["-vf", vf]
        if af and m.audio:
            args += ["-af", af]
        ff.run([*args, *mezz, str(out)], label="retime")
    print(f"→ {_rel(out)}")


def cmd_look(a):
    src = _src(a.file)
    tag = f"{a.start:g}-{a.end:g}s" if a.end else "full"
    out = Path(a.out) if a.out else next_version(default_out_dir(src, a.project, "review"), f"{src.stem}.sheet-{tag}", "png")
    inspect.contact_sheet(src, out, cols=a.cols, rows=a.rows, start=a.start, end=a.end, tile_w=a.tile)
    print(f"→ {out.resolve()}")


def cmd_frame(a):
    src = _src(a.file)
    d = default_out_dir(src, a.project, "review")
    for t in a.at:
        out = d / f"{src.stem}.frame-{t:08.3f}s.png"
        inspect.still(src, out, t)
        print(f"→ {out.resolve()}")


def cmd_hear(a):
    src = _src(a.file)
    out = Path(a.out) if a.out else next_version(default_out_dir(src, a.project, "review"), f"{src.stem}.spectrum", "png")
    _, L = inspect.spectrogram(src, out)
    print(f"→ {out.resolve()}")
    print(f"  {L.line()}")


def cmd_loudness(a):
    for f in a.files:
        L = loudness.measure(_src(f))
        print(json.dumps(L.to_dict()) if a.json else f"{Path(f).name}: {L.line()}")


def _qc_print(path: Path, pr, detect: bool) -> bool:
    checks = qc.run_qc(path, pr, detect=detect)
    print(f"QC {path.name}" + (f" vs {pr.name}" if pr else ""))
    for c in checks:
        print(c.line())
    fails = sum(c.level == "FAIL" for c in checks)
    warns = sum(c.level == "WARN" for c in checks)
    print(f"  {'PASS' if not fails else 'FAIL'} — {fails} fail, {warns} warn")
    return not fails


def cmd_qc(a):
    ok = _qc_print(_src(a.file), presets.load(a.preset) if a.preset else None, detect=not a.fast)
    return 0 if ok else 1


def cmd_presets(a):
    print("delivery presets (--preset / timeline 'delivery'):")
    for n in presets.names():
        pr = presets.load(n)
        geo = f"{pr.size[0]}x{pr.size[1]}" if pr.size else ("source" if pr.video else "audio")
        lt = f"{pr.target_lufs:g} LUFS" if pr.loudness else "—"
        print(f"  {n:<16} {geo:<10} {lt:<10} {pr.description}")
    print("\nlooks (grade):")
    for n, l in video.looks().items():
        print(f"  {n:<16} {l.get('description', '')}")
    print("\ntitle styles:")
    print("  " + ", ".join(titles.load_styles()))
    print("\nsfx kinds:      " + ", ".join(audio.SFX))
    print("reverb spaces:  " + ", ".join(audio.SPACES))
    print("transitions:    cut, " + ", ".join(sorted(set(timeline.TRANSITION_ALIASES))) + " (+ any ffmpeg xfade name)")
    print("image motion:   " + ", ".join(sorted(timeline.MOTIONS)))


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="souvi", description="SouVi Engine — premium sound & video production.")
    ap.add_argument("--version", action="version", version=f"souvi {__version__}")
    sp = ap.add_subparsers(dest="command", required=True, metavar="<command>")

    def cmd(name, fn, help_):
        p = sp.add_parser(name, help=help_, description=help_)
        p.set_defaults(fn=fn)
        return p

    cmd("doctor", cmd_doctor, "check ffmpeg build, encoders, filters, fonts, GPU")
    p = cmd("new", cmd_new, "create a project: projects/, assets/, output/ folders + timeline")
    p.add_argument("slug"); p.add_argument("--title"); p.add_argument("--preset", default="youtube-1080p")
    p.add_argument("--fps", type=float, default=30)
    cmd("projects", cmd_projects, "list projects")
    p = cmd("assets", cmd_assets, "inventory a project's assets with media facts"); p.add_argument("slug")
    p = cmd("probe", cmd_probe, "concise media facts"); p.add_argument("files", nargs="+"); p.add_argument("--json", action="store_true")
    p = cmd("presets", cmd_presets, "list delivery presets, looks, title styles, sfx, transitions")

    p = cmd("plan", cmd_plan, "dry-run a timeline: resolved clips, timing, warnings")
    p.add_argument("slug"); p.add_argument("--timeline", default="timeline")
    p = cmd("render", cmd_render, "render a project timeline (mix, master, grade, titles, encode, QC)")
    p.add_argument("slug"); p.add_argument("--timeline", default="timeline")
    p.add_argument("--draft", action="store_true", help="half-res fast preview into output/<slug>/drafts")
    p.add_argument("--gpu", action="store_true", help="NVENC for drafts"); p.add_argument("--preset")
    p.add_argument("--until", type=float, help="render only the first N seconds")
    p.add_argument("--out"); p.add_argument("--no-qc", action="store_true")
    p = cmd("promote", cmd_promote, "copy an approved render to output/<slug>/final/ (and --to a folder)")
    p.add_argument("render"); p.add_argument("--name"); p.add_argument("--to", help="also deliver here, e.g. your repo")
    p = cmd("import", cmd_import, "bring media into assets/<slug>/ (kind from extension; audio defaults to music)")
    p.add_argument("slug"); p.add_argument("files", nargs="+")
    p.add_argument("--as", dest="kind", choices=["footage", "images", "music", "voice", "sfx", "graphics", "fonts", "luts", "refs"])
    p.add_argument("--link", action="store_true", help="symlink instead of copy (large footage)")

    p = cmd("export", cmd_export, "re-encode any file to a delivery preset (fit, color, loudness)")
    p.add_argument("file"); p.add_argument("--preset", required=True); p.add_argument("--project")
    p.add_argument("--fit", default="cover", choices=["cover", "contain", "blur", "stretch"])
    p.add_argument("--grade", help="look name"); p.add_argument("--fps", type=float); p.add_argument("--out")
    p.add_argument("--no-qc", action="store_true")
    p = cmd("master", cmd_master, "loudness-master audio to a preset (true-peak safe)")
    p.add_argument("file"); p.add_argument("--preset", default="music-master"); p.add_argument("--lufs", type=float)
    p.add_argument("--tp", type=float); p.add_argument("--project"); p.add_argument("--out")
    p = cmd("voice", cmd_voice, "polish dialogue/voice-over: denoise, EQ, de-ess, compress, level")
    p.add_argument("file"); p.add_argument("--denoise", default="light", choices=list(audio.DENOISE))
    p.add_argument("--presence", type=float, default=2.0); p.add_argument("--deess", type=float, default=0.35)
    p.add_argument("--lufs", type=float, default=-18.0, help="voice stem level (mix-ready)"); p.add_argument("--out")
    p = cmd("sfx", cmd_sfx, "synthesize sound design: whoosh, riser, impact, tick, drone")
    p.add_argument("kind", choices=list(audio.SFX)); p.add_argument("--duration", type=float)
    p.add_argument("--pitch", type=float, default=0, help="semitones"); p.add_argument("--mood", default="minor", choices=["minor", "major"])
    p.add_argument("--space", default="default", choices=["default", "none", *audio.SPACES])
    p.add_argument("--project"); p.add_argument("--name"); p.add_argument("--out")
    p = cmd("reverb", cmd_reverb, "convolution reverb with a synthesized space")
    p.add_argument("file"); p.add_argument("--space", default="hall", choices=list(audio.SPACES))
    p.add_argument("--mix", type=float, default=0.25); p.add_argument("--out")

    for name, help_ in (("stabilize", "remove camera shake (vid.stab two-pass)"),
                        ("denoise", "reduce video noise"), ("grade", "apply a look / LUT / grain / vignette"),
                        ("retime", "speed change or frame-rate conversion (motion-interpolated)")):
        p = cmd(name, cmd_fx, help_ + " -> ProRes mezzanine beside source")
        p.add_argument("file"); p.add_argument("--out"); p.set_defaults(cmd=name)
        if name == "stabilize":
            p.add_argument("--smoothing", type=int, default=18); p.add_argument("--zoom", type=float, default=0)
        if name == "denoise":
            p.add_argument("--strength", default="medium", choices=list(video.DENOISE_V))
        if name == "grade":
            p.add_argument("--look"); p.add_argument("--lut"); p.add_argument("--grain", type=float, default=0)
            p.add_argument("--vignette", type=float, default=0); p.add_argument("--sharpen", type=float, default=0)
        if name == "retime":
            p.add_argument("--fps", type=float); p.add_argument("--speed", type=float)
            p.add_argument("--no-interp", action="store_true")

    p = cmd("look", cmd_look, "contact sheet PNG of a video (read it to SEE the edit)")
    p.add_argument("file"); p.add_argument("--cols", type=int, default=4); p.add_argument("--rows", type=int, default=4)
    p.add_argument("--from", dest="start", type=float, default=0); p.add_argument("--to", dest="end", type=float)
    p.add_argument("--tile", type=int, default=480); p.add_argument("--project"); p.add_argument("--out")
    p = cmd("frame", cmd_frame, "full-resolution still(s) at given times")
    p.add_argument("file"); p.add_argument("--at", type=float, nargs="+", required=True); p.add_argument("--project")
    p = cmd("hear", cmd_hear, "spectrogram + waveform PNG and loudness stats (read it to HEAR the audio)")
    p.add_argument("file"); p.add_argument("--project"); p.add_argument("--out")
    p = cmd("loudness", cmd_loudness, "EBU R128 loudness, true peak, LRA")
    p.add_argument("files", nargs="+"); p.add_argument("--json", action="store_true")
    p = cmd("qc", cmd_qc, "verify a file against a delivery preset and detect defects")
    p.add_argument("file"); p.add_argument("--preset"); p.add_argument("--fast", action="store_true", help="skip black/silence scan")
    return ap


def main(argv: list[str] | None = None) -> int:
    if not ff.available():
        print("ffmpeg/ffprobe not found on PATH", file=sys.stderr)
        return 2
    args = build_parser().parse_args(argv)
    try:
        with _JOBS:
            rc = args.fn(args)
    except (ff.FFError, timeline.TimelineError, FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return rc or 0


