---
name: souvi-video
description: Craft standards and edit workflow for producing video with the SouVi engine. Use when editing, cutting, grading, titling, or recreating any video, reel, trailer, promo, or slideshow.
---

# Premium video craft

The bar is **restraint**: every cut, move, title and grade must feel intended. Premium reads as calm, precise
and confident; cheap reads as busy. When in doubt, remove.

## Workflow

1. **Brief.** Fill `projects/<slug>/BRIEF.md`: purpose, audience, platform, length, feeling, references.
   Done when the delivery preset and target length are decided.
2. **Inventory.** `./souvi assets <slug>`, then `./souvi look <file>` on every clip you might use.
   Done when you have noted, per clip, the usable in/out ranges and its best moment (`./souvi frame --at`).
3. **Structure.** Write the timeline: hook in the first 2 s, a clear arc (setup → build → payoff → resolve),
   end on the strongest image. Pick the music first when there is music: cut to it.
   Run `./souvi plan <slug>` until it is clean.
4. **Draft + review.** `./souvi render <slug> --draft`, then `look` the draft (full sheet, then dense sheets
   around every transition with `--from/--to`) and `hear` it. Critique against the checklist below and revise.
   Done when a full pass of the checklist finds nothing.
5. **Final.** `./souvi render <slug>` (auto-QC must PASS), review once more, log decisions in BRIEF.md,
   `./souvi promote <render>`.

## Rhythm and cutting

- Cut on beats or phrases of the music. At 120 BPM a beat is 0.5 s; shot lengths of 2, 4 or 8 beats feel musical.
- Shot length tracks energy: 3–6 s for calm/luxury, 1–2 s for high energy. Vary it; a uniform cadence is robotic.
- Hard cuts are the default. Crossfades signal time passing or mood shifts: use 0.6–1.2 s and use them sparingly.
  `dip-to-black` for chapter breaks and the ending. Flashy transitions (slides, wipes, zooms) almost never read premium.
- Start each clip slightly into motion and leave before the motion resolves; trim dead heads/tails.
- Give the final image room: 1.5–3 s hold, then a fade out.

## Images and motion

- Every still gets motion (`push-in` default, `zoom` 0.06–0.12). Alternate direction between neighbouring
  stills. Never stack two different moves on one image.
- Use `fit: blur` when aspect ratios differ; never stretch.

## Colour

- Match first, look second: per-clip `look` to make clips agree, then one global `grade`.
- Keep grades subtle (`filmic`, `neutral`, `golden`); fine `grain` 0.1–0.25 adds texture and hides banding.
- Skin must stay natural; check a face frame at full resolution after grading.

## Typography

- One family per piece (Inter by default), two weights at most. Light weights + generous tracking = premium.
- Titles need room: centred hero on a calm shot, or lower thirds on the left third. Avoid busy backgrounds;
  if unavoidable, pick a darker moment or use `box`.
- On-screen time ≥ 1 s per 3 words plus 1 s. Fades 0.4–0.9 s. Nothing within 5% of the frame edge;
  for `social-vertical`, keep text out of the top 12% and bottom 20%.
- Sentence case or small-caps kicker (`uppercase` + tracking). Never all-caps body text.

## Review checklist

Every item must be checked against the actual frames (`look`, `frame`), not your memory of the timeline:

- [ ] First 2 s hook; no black or static opening beyond an intentional fade
- [ ] Every cut lands on a beat or a motion; no jump cuts, no flash frames (dense sheet around each cut)
- [ ] Transitions overlap clean picture (no source black or slates leaking in)
- [ ] Titles readable: contrast, size, duration, safe zone; no typos
- [ ] Colour consistent across shots; skin natural; blacks not crushed, highlights not clipped
- [ ] Audio: music phrase ends with the picture; dialogue intelligible over music; no clicks (see souvi-audio)
- [ ] Ending: held final image, fade, music resolves
- [ ] QC PASS with zero WARN you cannot explain
