---
name: souvi-audio
description: Mixing, mastering and sound-design standards for the SouVi engine. Use when working on music, voice-over, dialogue, podcasts, sound effects, soundtracks, or any mix or master.
---

# Premium sound craft

Audio is half of perceived quality. The bar is **clarity**: every element has its own space, dialogue is always
intelligible, nothing clicks, pumps or clips, and loudness matches the platform exactly.

## Levels (pre-master balance)

Set `gain` per track so the mix *balances*; the master then sets absolute loudness. Typical balance:

| element | relative level |
|---|---|
| dialogue / VO | reference (0 dB). Polish it: `./souvi voice` or `"polish": "light"` |
| music under dialogue | ducked automatically; set its own `gain` so it sits ~12–18 dB under voice in gaps |
| music alone | the star: 0 to −3 dB |
| ambience | barely noticed: −18 to −25 dB, `loop: true` |
| sfx accents | felt not heard: −4 to −10 dB; whoosh 0.1–0.2 s *before* the cut it accompanies |

## Delivery targets

The preset carries the target; use `./souvi presets` to see them. Streaming/social −14 LUFS / −1 dBTP;
podcast −16 / −1.5; broadcast EBU R128 −23 / −1. `./souvi master` and `render` measure, apply one static gain,
limit at 4× oversampling, re-measure and iterate. If the report says *heavy limiting*, the source is too dynamic:
compress the offending stem instead of letting the limiter work harder.

## Music editing

- Cut music on bar lines; let the final chord ring out (`fade_out` 2–4 s) rather than chopping mid-phrase.
- To fit length, edit out a repeated section (in/out on two music tracks with a crossfade on a downbeat) instead of fading early.
- Find the drop/downbeat with `./souvi hear` (energy is visible in the spectrogram) and align the visual payoff to it.

## Voice

- Chain: high-pass → denoise → de-mud (−2.5 dB @ 280 Hz) → presence (+2 dB @ 3.8 kHz) → air → de-ess → gentle compression.
- Denoise `light` first; `strong` leaves artifacts (watery, metallic). Compare spectrograms before and after.
- Breaths: reduce, don't delete. Gaps between sentences: 0.3–0.6 s.

## Sound design

`./souvi sfx whoosh|riser|impact|tick|drone` synthesizes (`--pitch` semitones, `--duration`, `--space`, `--mood`).
Generate variations rather than reusing one sound twice in a row. Riser → impact on the payoff cut.
`./souvi reverb` places dry sounds in a shared space so elements glue together.

## Review checklist

Check each item against `./souvi hear` output and numbers, not assumptions:

- [ ] Spectrogram: no hard vertical lines (clicks) at edits; no hum lines (50/60 Hz); no empty high end on voice
- [ ] Waveform: no flat-topped peaks; no unintended gaps
- [ ] Dialogue clearly above music everywhere it speaks; music comes back up in gaps
- [ ] Head and tail: fades, no abrupt starts/stops
- [ ] QC: loudness on target, true peak under ceiling, no clipping, LRA sensible (music 4–10 LU, speech 3–8 LU)
