# Audio craft

The bar is **clarity**: every element has its own space, dialogue is always intelligible, nothing
clicks, pumps or clips, and loudness matches the platform exactly.

## Balance (timeline `gain`; the master sets absolute loudness)

| element | level |
|---|---|
| dialogue / VO | reference 0 dB; polish with `souvi voice` or `"polish": "light"` |
| music under dialogue | auto-ducked; its `gain` should sit ~12–18 dB under voice in gaps |
| music alone | 0 to −3 dB |
| ambience | −18 to −25 dB, `loop: true` |
| sfx accents | −4 to −10 dB; a whoosh starts 0.1–0.2 s before its cut |

## Loudness

Targets come from the preset (streaming/social −14 LUFS/−1 dBTP, podcast −16/−1.5, broadcast −23/−1).
`render` and `master` apply a static gain plus oversampled true-peak limiting and verify. A "heavy
limiting" warning means the source is too dynamic: compress that stem rather than push the limiter.

## Music

- Edit on bar lines; let the last chord ring (`fade_out` 2–4 s) instead of cutting mid-phrase.
- To shorten, remove a repeated section (two music tracks, crossfaded on a downbeat) rather than fade early.
- Find drops and downbeats in `souvi hear` (energy is visible) and land the visual payoff on them.

## Voice

- `souvi voice`: high-pass → denoise → de-mud → presence → air → de-ess → gentle compression.
- Start with `--denoise light`; `strong` turns watery or metallic. Compare spectrograms before and after.
- Reduce breaths, don't delete them; leave 0.3–0.6 s between sentences.

## Sound design

`souvi sfx whoosh|riser|impact|tick|drone` (`--pitch` semitones, `--duration`, `--space`, `--mood`).
Generate variations instead of repeating one sound; riser → impact on the payoff cut; `souvi reverb`
puts dry elements in one shared space.

## Review checklist

Check against `souvi hear` images and numbers:

- [ ] No vertical lines (clicks) at edits; no 50/60 Hz hum lines; voice has high-end air
- [ ] No flat-topped peaks; no unintended gaps
- [ ] Dialogue clearly above music wherever it speaks; music recovers in the gaps
- [ ] Clean head and tail: fades, no abrupt starts or stops
- [ ] QC: loudness on target, true peak under ceiling, no clipping; LRA 4–10 LU music, 3–8 LU speech
