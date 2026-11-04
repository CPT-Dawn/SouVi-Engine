# SouVi Engine

A sound & video production engine built for **Claude Code**. You describe what you want; Claude plans the
edit as a declarative timeline and the engine renders it with broadcast-grade defaults: 10-bit processing,
frame-exact timing, libass typography, sidechain-ducked mixes, true-peak-safe loudness mastering, automatic QC.

Pure Python standard library + ffmpeg. No virtualenv, no pip install.

```sh
./souvi doctor                                   # verify ffmpeg, encoders, fonts, GPU
./souvi new spring-launch --preset social-vertical
# drop media into assets/spring-launch/{footage,images,music,voice,...}
./souvi assets spring-launch                     # inventory with media facts
$EDITOR projects/spring-launch/timeline.json     # or ask Claude to cut it
./souvi plan spring-launch                       # validate + resolved timing
./souvi render spring-launch --draft             # fast half-res preview
./souvi look output/spring-launch/drafts/spring-launch_v001.mp4   # contact sheet PNG
./souvi render spring-launch                     # final: mix → master → grade → titles → encode → QC
./souvi promote output/spring-launch/renders/spring-launch_v001.mp4
```

## Layout

```
projects/<slug>/   timeline.json, BRIEF.md     the plan (tracked in git)
assets/<slug>/     footage images music voice sfx graphics fonts luts refs
assets/_shared/    reusable fonts, LUTs, music, sfx, graphics
output/<slug>/     drafts/ renders/ final/ review/
cache/<slug>/      intermediates (disposable, ignored)
presets/           delivery formats, colour looks, title styles
engine/            the engine (timeline.py is the renderer)
docs/timeline.md   timeline schema
.claude/skills/    craft standards Claude loads for video and audio work
```

## Capabilities

| area | commands |
|---|---|
| edit | `render` / `plan` — cuts, 40+ transitions, speed, cover/contain/blur fit, jitter-free Ken Burns, overlays, titles, fades, HDR→SDR |
| colour | `grade` — looks (filmic, teal-orange, golden, steel, noir, pastel, neutral), LUTs, grain, vignette |
| repair | `stabilize` (vid.stab), `denoise`, `retime` (motion-interpolated slow-mo / fps conversion) |
| sound | `voice` (dialogue polish), `master` (true-peak safe loudness), `reverb` (convolution), `sfx` (whoosh, riser, impact, tick, drone) |
| deliver | `export` to presets: YouTube 4K/1080p, social vertical/square, web AV1, web hero loop, ProRes master, music, podcast, broadcast R128 |
| review | `look` (contact sheets), `frame`, `hear` (spectrogram + waveform), `loudness`, `qc`, `probe` |

## Development

```sh
python3 -m unittest discover -s tests            # ~5 s, uses a throwaway root
SOUVI_SHOW_CMD=1 ./souvi render <slug> --draft   # echo every ffmpeg command
```

Requires Python ≥ 3.11 and an ffmpeg build with libx264/libx265, libass, libzimg, libvidstab, libsoxr
(`./souvi doctor` checks everything).
