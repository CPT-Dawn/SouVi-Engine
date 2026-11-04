"""Repository layout and path resolution.

    projects/<slug>/   project.toml, timeline.json, NOTES.md   (the plan)
    assets/<slug>/     source media for that project            (the inputs)
    assets/_shared/    reusable fonts, luts, music, sfx, graphics
    output/<slug>/     drafts/, renders/, final/, review/      (the results)
    cache/<slug>/      intermediates, safe to delete            (gitignored)
"""

from __future__ import annotations

import atexit
import contextlib
import fcntl
import os
import re
import shutil
import sys
import tempfile
import time
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

    @contextlib.contextmanager
    def lock(self, what: str = "render"):
        """Serialise heavy jobs per project: a second render waits instead of fighting for CPU."""
        self.cache.mkdir(parents=True, exist_ok=True)
        with open(self.cache / f".{what}.lock", "w") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(f"  … another {what} of '{self.slug}' is running; waiting", file=sys.stderr)
                fcntl.flock(fh, fcntl.LOCK_EX)
            yield

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


_reserved: list[Path] = []


def next_version(directory: Path, stem: str, ext: str) -> Path:
    """output/<slug>/renders/<stem>_v003.mp4 — never overwrite an earlier render.

    The name is reserved atomically (O_EXCL placeholder), so parallel jobs never pick the same
    version. Placeholders still empty when the process exits (failed job) are removed.
    """
    directory.mkdir(parents=True, exist_ok=True)
    pat = re.compile(rf"^{re.escape(stem)}_v(\d{{3}})\.")
    n = max((int(m.group(1)) for f in directory.iterdir() if (m := pat.match(f.name))), default=0) + 1
    while True:
        path = directory / f"{stem}_v{n:03d}.{ext}"
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
        except FileExistsError:
            n += 1
            continue
        _reserved.append(path)
        return path


@atexit.register
def _drop_empty_reservations() -> None:
    for p in _reserved:
        with contextlib.suppress(OSError):
            if p.stat().st_size == 0:
                p.unlink()


@contextlib.contextmanager
def run_dir(project: "Project | None", label: str, *, keep: bool = False):
    """A private working folder for one job: cache/<slug>/runs/<label>-<time>-<pid>/.

    Unique per process, so any number of agents can work at once. Removed afterwards unless
    `keep` (renders keep their graphs for debugging; bulky audio is pruned by the caller).
    """
    base = (project.cache if project else CACHE / "_scratch") / "runs"
    base.mkdir(parents=True, exist_ok=True)
    d = Path(tempfile.mkdtemp(prefix=f"{label}-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-", dir=base))
    try:
        yield d
    finally:
        if not keep:
            shutil.rmtree(d, ignore_errors=True)


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
