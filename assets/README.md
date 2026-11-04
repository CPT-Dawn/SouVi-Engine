# assets/

Source media, one folder per project (`assets/<slug>/`, created by `./souvi new <slug>`), plus `_shared/`
for fonts, LUTs, music, sfx and graphics reused across projects.

```
assets/<slug>/footage    video clips             assets/<slug>/graphics  logos, PNGs with alpha
assets/<slug>/images     stills                  assets/<slug>/fonts     project typefaces
assets/<slug>/music      score, songs            assets/<slug>/luts      .cube LUTs
assets/<slug>/voice      VO, dialogue            assets/<slug>/refs      reference media (style, pacing)
assets/<slug>/sfx        sound effects
```

Sources are never modified; processed versions are written beside them with a tag and version
(`interview.polished_v001.wav`). Media files are git-ignored; only the folder structure is tracked.
