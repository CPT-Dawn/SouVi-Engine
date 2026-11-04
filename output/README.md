# output/

Everything the engine produces, one folder per project (`output/<slug>/`):

```
drafts/    half-res previews from `./souvi render <slug> --draft`
renders/   full-quality, QC'd renders and exports (versioned _v001, _v002 — never overwritten)
final/     approved deliverables (`./souvi promote <render>`)
review/    contact sheets, stills and spectrograms used to review the work
```

Each render has a `.json` manifest beside it (preset, timing, loudness report, warnings).
Files made without a project (e.g. `./souvi export ~/clip.mov`) land in `output/_scratch/`.
