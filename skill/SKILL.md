---
name: souvi
description: Create and edit video and audio with the SouVi Engine (`souvi` CLI) — edits, reels, trailers, slideshows, grading, titles, voice-over, music, mixing, mastering, sound design, format exports. Use whenever the user mentions SouVi or asks for video or audio output.
---

# SouVi Engine

`souvi` is on PATH and works from any directory. The engine lives at `/home/cptdawn/Kode/SouVi-Engine`
(below: `$SOUVI`). `souvi <cmd> -h` gives flags; `souvi presets` lists delivery formats, looks, title
styles, transitions and sfx.

## Workspace

Each deliverable set is a project in `$SOUVI`:

- `projects/<slug>/` — `timeline.json` (the edit) and `BRIEF.md` (brief + dated decisions log)
- `assets/<slug>/{footage,images,music,voice,sfx,graphics,fonts,luts,refs}/` — sources, never modified
- `output/<slug>/{drafts,renders,final,review}/` — results, versioned `_vNNN`, never overwritten

Called from another repo: slug = that repo's folder name (suffix it for a separate deliverable, e.g.
`myapp-teaser`). Import media with `souvi import <slug> <files…>` (`--as voice|sfx` for non-music audio,
`--link` for large footage); deliver with `souvi promote <render> --to <folder in the calling repo>`.
Leave git in `$SOUVI` alone unless the user asks.

Parallel agents are safe: every job runs in a private folder and renders of one project queue on a
lock. Give each agent's deliverable its own slug.

## Loop

1. `souvi new <slug> --preset <delivery>`; write the brief into `BRIEF.md`.
2. `souvi import …`, `souvi assets <slug>`, then `souvi look <clip>` on every candidate source.
3. Write `timeline.json` after reading `$SOUVI/docs/timeline.md`; run `souvi plan <slug>` until clean.
4. `souvi render <slug> --draft` (`--gpu`, `--until N`), review, revise.
5. `souvi render <slug>` (QC must PASS), review, `souvi promote <render> [--to …]`.

**Review** — you cannot watch or listen, so read the PNGs these print: `souvi look <video>` (contact
sheet; `--from/--to` for dense sheets around cuts), `souvi frame <video> --at <t…>`, `souvi hear <file>`
(spectrogram, waveform, loudness). Work is done when the final render passes this review and QC.

## Craft

Before creative decisions, read [video.md](video.md) for picture and [audio.md](audio.md) for sound.
Apply every item of their review checklists.

## Single-file tools

`export --preset`, `master`, `voice`, `sfx`, `reverb`, `stabilize`, `denoise`, `grade`, `retime`, `qc`,
`loudness`, `probe`. Processed files land beside their source as `<name>.<tag>_vNNN.<ext>`.
For anything else, raw ffmpeg is fine when it keeps 10-bit processing, lanczos scaling, BT.709 tags and
soxr resampling; finish loudness with `souvi master` and encode deliverables with `souvi export`.
