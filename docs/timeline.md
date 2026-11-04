# Timeline schema (`projects/<slug>/timeline.json`)

A timeline is the complete, declarative recipe for one deliverable. `./souvi plan <slug>` validates it and
prints resolved timing; `./souvi render <slug>` produces it. Alternate cuts live beside it
(`projects/<slug>/teaser.json` → `./souvi render <slug> --timeline teaser`).

Media paths (`src`) resolve in order: absolute → `assets/<slug>/` → `assets/_shared/` → repo root.
All times are seconds. Timing is quantised to whole frames at `canvas.fps`.

```jsonc
{
  "title": "Spring Launch",              // written into file metadata
  "delivery": "youtube-1080p",           // preset in presets/delivery/ (./souvi presets)
  "canvas": {"width": 1920, "height": 1080, "fps": 30, "background": "#000000"},
  "fit": "cover",                        // default fit for clips: cover | contain | blur | stretch
  "clip_audio": true,                    // include source audio of video clips by default
  "grade": {"look": "filmic", "lut": "luts/brand.cube", "grain": 0.2, "vignette": 0.3, "sharpen": 0.2},
  "fade_in": 0.6,                        // from black + audio fade, program head
  "fade_out": 1.2,                       // to black + audio fade, program tail
  "loudness": {"integrated": -14, "true_peak": -1},   // optional override of the preset target
  "duck": {"depth": 0.75},               // music/ambience duck under dialogue; false to disable

  "video": [ /* main sequence, back to back */ ],
  "titles": [ /* typography, burned in after grading */ ],
  "overlays": [ /* logos, graphics, picture-in-picture */ ],
  "audio": [ /* music, dialogue, sfx, ambience tracks */ ]
}
```

## `video[]` — the sequence

Clips play back to back; a `transition` on a clip overlaps it with the previous one (shortening the total).

| key | meaning |
|---|---|
| `src` | video or image file. Or omit and give `color: "#0b0b10"` for a solid card |
| `in` / `out` | source in/out points (video). Default: whole clip |
| `duration` | timeline length (required for images and colour cards; overrides `out`) |
| `speed` | `0.5` = half speed (audio pitch-preserved). For smooth slow motion, pre-process with `./souvi retime` |
| `fit` | `cover` (crop to fill), `contain` (letterbox), `blur` (contained over blurred fill: vertical-in-horizontal and vice versa), `stretch` |
| `motion` | images only: `push-in`, `pull-out`, `pan-left`, `pan-right`, `pan-up`, `pan-down` (supersampled, jitter-free Ken Burns) |
| `zoom` | motion amount, default `0.12` (12%). Keep 0.06–0.18 for premium restraint |
| `ease` | `linear` (default for push/pull: constant drift across cuts), `inout` (default for pans), `out` |
| `transition` | into this clip: `"crossfade"` or `{"type": "dip-to-black", "duration": 1.0}`. Default duration 0.8 s |
| `look` | per-clip grade (same forms as top-level `grade`), applied before the global grade, e.g. to match cameras |
| `volume` | clip audio gain in dB; `mute: true` drops it |

Transitions: `cut` (default), `crossfade`/`dissolve`, `dip-to-black`, `dip-to-white`, `blur`, `zoom`,
`slide-*`, `wipe-*`, `smooth-*`, `circle`, `fade-grays`, plus any raw ffmpeg `xfade` name.
Clip audio automatically crossfades with its picture; hard cuts get inaudible 12 ms anti-click fades.

HDR sources (iPhone HLG/PQ) are tone-mapped to SDR BT.709 automatically. Everything is processed in 10-bit.

## `titles[]`

```json
{"text": "Spring Launch", "start": 1.0, "end": 4.5, "style": "hero"}
```

Styles live in `presets/titles.toml` (`hero`, `kicker`, `subtitle`, `lower-third`, `lower-third-sub`, `caption`,
`end-card`). Any style key can be overridden per title: `size` (fraction of height), `color` (`#RRGGBB[AA]`),
`font`, `tracking`, `expand`, `align` (numpad 1–9), `offset_y`, `margin_x`, `margin_y`, `fade` (`[in_ms, out_ms]`),
`drift`, `blur`, `uppercase`, `box`. Explicit position: `x`, `y` as fractions of the frame. Use `\n` for line breaks.
Fonts: any installed family, or drop files into `assets/<slug>/fonts/`.

## `overlays[]`

```json
{"src": "graphics/logo.png", "start": 0, "end": 6, "x": 0.9, "y": 0.1, "width": 0.1, "fade": 0.5, "opacity": 0.9}
```

`x`/`y` are the overlay's centre as fractions of the frame, `width` a fraction of frame width. PNG alpha is honoured.
Video overlays (picture-in-picture) accept `in`.

## `audio[]`

```json
{"src": "music/score.wav", "start": 0, "in": 12.0, "gain": -2, "fade_in": 1.5, "fade_out": 3, "role": "music"}
{"src": "voice/vo.wav", "start": 2.0, "role": "dialogue", "polish": "light"}
{"src": "sfx/whoosh_v001.wav", "start": 3.6, "role": "sfx", "gain": -4}
{"src": "ambience/room.wav", "role": "ambience", "loop": true, "gain": -8}
```

| key | meaning |
|---|---|
| `role` | `dialogue`, `music`, `ambience`, `sfx` — each its own bus; music and ambience duck under dialogue |
| `start` | timeline position |
| `in` / `out` / `duration` | source range. Default: until source or program ends |
| `gain` | dB, applied before mastering (relative balance; the master sets absolute loudness) |
| `fade_in` / `fade_out` | seconds, equal-power curves |
| `loop` | repeat the source to fill |
| `polish` | dialogue only: run the voice chain inline (`light` / `medium` / `strong` denoise) |

The whole mix is then mastered to the preset's loudness target with true-peak limiting.

## Render artefacts

Each render runs in a private folder, `cache/<slug>/runs/render-<timeline>-<time>-<pid>/`, holding
`titles.ass`, `video.graph.txt` and `audio.graph.txt` (the exact filtergraphs: read these to debug).
The render's `<file>.json` manifest (beside the output) records that folder as `work_dir`, plus timing,
preset, loudness report and warnings. Renders of one project queue on a lock; different projects run in parallel.
