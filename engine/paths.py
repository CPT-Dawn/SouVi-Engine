"""Repository layout and path resolution.

    projects/<slug>/   project.toml, timeline.json, NOTES.md   (the plan)
    assets/<slug>/     source media for that project            (the inputs)
    assets/_shared/    reusable fonts, luts, music, sfx, graphics
    output/<slug>/     drafts/, renders/, final/, review/      (the results)
    cache/<slug>/      intermediates, safe to delete            (gitignored)
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(os.environ.get("SOUVI_ROOT", Path(__file__).resolve().parent.parent))
PROJECTS = ROOT / "projects"
ASSETS = ROOT / "assets"
SHARED = ASSETS / "_shared"
OUTPUT = ROOT / "output"
CACHE = ROOT / "cache"
PRESETS = ROOT / "presets"

ASSET_DIRS = ["footage", "images", "music", "voice", "sfx", "graphics", "fonts", "luts", "refs"]
OUTPUT_DIRS = ["drafts", "renders", "final", "review"]
SHARED_DIRS = ["fonts", "luts", "music", "sfx", "graphics"]

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class Project:
    def __init__(self, slug: str):
        if not SLUG_RE.match(slug):
            raise ValueError(f"invalid project slug {slug!r}: use lowercase letters, digits, dashes")
        self.slug = slug
        self.dir = PROJECTS / slug
        self.assets = ASSETS / slug
        self.output = OUTPUT / slug
        self.cache = CACHE / slug

    @property
    def exists(self) -> bool:
        return self.dir.is_dir()

    def require(self) -> "Project":
        if not self.exists:
            raise SystemExit(f"project '{self.slug}' not found. Create it: ./souvi new {self.slug}")
        return self

    def out(self, kind: str) -> Path:
        d = self.output / kind
        d.mkdir(parents=True, exist_ok=True)
        return d

    def work(self, *parts: str) -> Path:
        d = self.cache.joinpath(*parts)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def resolve(self, ref: str) -> Path:
        """Resolve a media reference: absolute, project-asset-relative, shared, or repo-relative."""
        p = Path(ref).expanduser()
        if p.is_absolute():
            candidates = [p]
        else:
            candidates = [self.assets / p, SHARED / p, ROOT / p, Path.cwd() / p]
        for c in candidates:
            if c.exists():
                return c.resolve()
        tried = "\n  ".join(str(c) for c in candidates)
        raise FileNotFoundError(f"media not found: {ref}\n  tried:\n  {tried}")

    def font_dirs(self) -> list[Path]:
        return [d for d in (self.assets / "fonts", SHARED / "fonts") if d.is_dir()]


def next_version(directory: Path, stem: str, ext: str) -> Path:
    """output/<slug>/renders/<stem>_v003.mp4 — never overwrite an earlier render."""
    directory.mkdir(parents=True, exist_ok=True)
    pat = re.compile(rf"^{re.escape(stem)}_v(\d{{3}})\.")
    taken = [int(m.group(1)) for f in directory.iterdir() if (m := pat.match(f.name))]
    return directory / f"{stem}_v{(max(taken) + 1 if taken else 1):03d}.{ext}"


def project_from_path(path: Path) -> Project | None:
    """Infer the owning project of a file under assets/<slug>/ or output/<slug>/."""
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) >= 2 and parts[0] in ("assets", "output", "projects", "cache") and SLUG_RE.match(parts[1]):
        return Project(parts[1])
    return None


def default_out_dir(src: Path, project: str | None, kind: str) -> Path:
    if project:
        return Project(project).out(kind)
    p = project_from_path(src)
    if p:
        return p.out(kind)
    d = OUTPUT / "_scratch" / kind
    d.mkdir(parents=True, exist_ok=True)
    return d
