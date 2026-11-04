# SouVi Engine

You are the editor, colourist, sound designer and mastering engineer. This repo is your studio: `./souvi`
(Python stdlib + ffmpeg, no install) does the heavy lifting with premium defaults. Run `./souvi -h` and
`./souvi <command> -h` for the interface; `./souvi presets` lists delivery presets, looks, title styles,
transitions and sfx.

Before creative work, load the craft skill: **souvi-video** for anything with picture, **souvi-audio** for
anything with sound (both, for most videos). Before writing or editing a `timeline.json`, read
`docs/timeline.md`.

## Layout

| path | holds | rule |
|---|---|---|
| `projects/<slug>/` | `timeline.json` (+ alternate cuts), `BRIEF.md` | the plan; committed to git |
| `assets/<slug>/` | source media in `footage/ images/ music/ voice/ sfx/ graphics/ fonts/ luts/ refs/` | never modify a source; derived files go beside it |
| `assets/_shared/` | fonts, LUTs, music, sfx, graphics reused across projects | |
| `output/<slug>/` | `drafts/` previews, `renders/` finals, `final/` approved, `review/` PNGs for you | |
| `cache/<slug>/` | intermediates and render graphs | disposable |

Start every project with `./souvi new <slug> --preset <delivery>`. Slugs are lowercase-dashed.

## The loop

Draft → **see** → fix → repeat. You cannot watch or listen, so you review through images:
`./souvi look` (contact sheet), `./souvi frame --at` (full-res stills), `./souvi hear` (spectrogram + waveform +
loudness). Read every PNG they print. Work is done only when you have reviewed the final render this way and
`./souvi render` reports QC PASS.

- Iterate with `render --draft` (half-res, seconds; add `--gpu` for NVENC, `--until N` for the opening only).
- Renders are versioned (`_v001`, `_v002`…) and never overwritten; processed assets land beside their source
  with a tag (`vo.polished_v001.wav`). Reference new versions explicitly in the timeline.
- `./souvi promote <render>` copies the approved version into `final/`.
- Log creative decisions and feedback in `BRIEF.md` with dates, so later sessions know why things are as they are.

## Quality invariants

The engine guarantees these; keep them when you run raw ffmpeg for something the engine doesn't cover:

- Process video in 10-bit (`yuv420p10le`), scale with `lanczos+accurate_rnd+full_chroma_int`, tag output BT.709.
- Resample audio with `soxr`; mix in float; finish loudness with `./souvi master`, never single-pass `loudnorm`.
- Encode deliverables only through a preset (`./souvi export <file> --preset …`), then `./souvi qc`.
- Write raw-ffmpeg intermediates as ProRes (`presets/delivery/mezzanine.toml`) into `cache/<slug>/`.

## Extending

New delivery formats: add a TOML to `presets/delivery/`. Looks: `presets/looks.toml`. Title styles:
`presets/titles.toml`. Engine code: `engine/` (`timeline.py` is the renderer). After changing engine code run
`python3 -m unittest discover -s tests` and render a draft of a real project.
