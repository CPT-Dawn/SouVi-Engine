"""Project scaffolding and listing."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .paths import ASSET_DIRS, OUTPUT_DIRS, PROJECTS, Project
from .presets import load as load_preset


def create(slug: str, *, title: str | None = None, preset: str = "youtube-1080p", fps: float = 30) -> Project:
    p = Project(slug)
    if p.exists:
        raise SystemExit(f"project '{slug}' already exists at {p.dir}")
    pr = load_preset(preset)
    w, h = pr.size or (1920, 1080)
    try:
        p.dir.mkdir(parents=True)
    except FileExistsError:  # another agent created it a moment ago
        raise SystemExit(f"project '{slug}' already exists at {p.dir}") from None
    for d in ASSET_DIRS:
        (p.assets / d).mkdir(parents=True, exist_ok=True)
        (p.assets / d / ".gitkeep").touch()
    for d in OUTPUT_DIRS:
        (p.output / d).mkdir(parents=True, exist_ok=True)
        (p.output / d / ".gitkeep").touch()

    timeline = {
        "title": title or slug.replace("-", " ").title(),
        "delivery": preset,
        "canvas": {"width": w, "height": h, "fps": fps, "background": "#000000"},
        "grade": None,
        "fade_in": 0.6,
        "fade_out": 1.2,
        "video": [],
        "titles": [],
        "overlays": [],
        "audio": [],
    }
    (p.dir / "timeline.json").write_text(json.dumps(timeline, indent=2) + "\n")
    (p.dir / "BRIEF.md").write_text(f"""# {timeline['title']}

Created {dt.date.today().isoformat()} · delivery `{preset}` · {w}x{h} @ {fps:g} fps

## Brief
<!-- What is this, who is it for, where will it play, how long, what should it feel like? -->

## References
<!-- Put reference media in assets/{slug}/refs/ and describe what to take from each. -->

## Decisions log
<!-- Dated notes: creative choices, feedback received, what changed between versions. -->
""")
    return p


def list_projects() -> list[dict]:
    rows = []
    for d in sorted(PROJECTS.iterdir()) if PROJECTS.exists() else []:
        if not d.is_dir() or d.name.startswith((".", "_")):
            continue
        p = Project(d.name)
        n_assets = sum(1 for f in p.assets.rglob("*") if f.is_file() and f.name != ".gitkeep") if p.assets.exists() else 0
        outs = sorted((f for f in p.output.rglob("*") if f.is_file() and f.suffix not in (".json", "") and
                       f.name != ".gitkeep"), key=lambda f: f.stat().st_mtime) if p.output.exists() else []
        rows.append({"slug": p.slug, "assets": n_assets, "outputs": len(outs),
                     "latest": str(outs[-1].relative_to(p.output)) if outs else "-"})
    return rows


def asset_inventory(p: Project) -> list[tuple[str, Path]]:
    return [(f.parent.name, f) for f in sorted(p.assets.rglob("*")) if f.is_file() and f.name != ".gitkeep"]


def relpath(f: Path, base: Path) -> str:
    try:
        return str(f.relative_to(base))
    except ValueError:
        return str(f)


