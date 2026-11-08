# SouVi Engine

This repo is the engine. How to *use* it lives in the `souvi` skill (`skill/SKILL.md`, symlinked to
`~/.claude/skills/souvi` by `scripts/install.sh`). Load that skill for any media work, here or anywhere.

## Developing the engine

- Code: `engine/` (`timeline.py` renderer, `loudness.py` mastering, `cli.py` commands). Pure stdlib + ffmpeg.
- Presets: `presets/delivery/*.toml`, `presets/looks.toml`, `presets/titles.toml`. Schema: `docs/timeline.md`.
- Concurrency contract: jobs write only to `paths.run_dir(...)` folders and version outputs via
  `paths.next_version` (atomic); renders hold `Project.lock`. Shared caches are written atomically.
- After engine changes: `python3 -m unittest discover -s tests`, then render a draft of a real project
  and review it with `souvi look`.
- Skill or agent changes: keep `skill/SKILL.md` short; detail goes in its sibling files.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `CPT-Dawn/SouVi-Engine` (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
