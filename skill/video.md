# Video craft

The bar is **restraint**: every cut, move, title and grade must feel intended. Premium reads calm,
precise and confident; cheap reads busy. When in doubt, remove.

## Structure and rhythm

- Hook in the first 2 s; a clear arc (setup → build → payoff → resolve); end on the strongest image.
- With music, pick it first and cut to it: cuts land on beats or phrase starts (120 BPM = 0.5 s/beat;
  2, 4 or 8 beats per shot feel musical).
- Shot length tracks energy: 3–6 s calm/luxury, 1–2 s high energy. Vary it; uniform cadence is robotic.
- Enter each shot slightly into its motion and leave before the motion resolves; trim dead heads/tails.
- Hard cuts by default. Crossfades (0.6–1.2 s) mark time passing or mood shifts, sparingly;
  `dip-to-black` for chapter breaks and the ending. Slides, wipes and zooms rarely read premium.
- Hold the final image 1.5–3 s, then fade out.

## Images

- Every still gets motion: `push-in` default, `zoom` 0.06–0.12, alternating direction between neighbours.
- Mismatched aspect ratios use `fit: blur`; never stretch.

## Colour

- Match first (per-clip `look`), then one global `grade`. Keep it subtle (`filmic`, `neutral`, `golden`);
  `grain` 0.1–0.25 adds texture and hides banding.
- Skin stays natural: check a face at full resolution (`souvi frame`) after grading.

## Typography

- One family (Inter by default), at most two weights; light weights with generous tracking read premium.
- Hero titles on calm shots; lower thirds on the left third. On busy frames pick a darker moment or `box`.
- On screen ≥ 1 s per 3 words + 1 s; fades 0.4–0.9 s; nothing within 5% of the edge.
  `social-vertical`: keep text out of the top 12% and bottom 20%.
- Sentence case; uppercase only for small tracked kickers.

## Review checklist

Check every item against frames (`look`, `frame`), not against the timeline:

- [ ] First 2 s hook; no black or static opening beyond an intentional fade
- [ ] Every cut on a beat or motion; no jump cuts or flash frames (dense sheet around each cut)
- [ ] Transitions overlap clean picture (no source black or slates leaking in)
- [ ] Titles readable (contrast, size, duration, safe zone) and free of typos
- [ ] Colour consistent across shots; skin natural; no crushed blacks or clipped highlights
- [ ] Ending: held final image, fade, music resolves with it
- [ ] QC PASS; every WARN explained
