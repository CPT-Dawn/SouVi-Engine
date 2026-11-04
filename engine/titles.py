"""Timeline titles -> Advanced SubStation (.ass), rendered by libass.

libass gives subpixel positioning, proper kerning/shaping (harfbuzz), animated
tracking (\\t + \\fsp), fades and blur — far beyond drawtext.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from .paths import PRESETS

STYLE_KEYS = {
    "font", "size", "color", "tracking", "expand", "align", "fade", "shadow", "shadow_color", "blur",
    "uppercase", "offset_y", "offset_x", "margin_x", "margin_y", "drift", "outline", "outline_color",
    "box", "box_color", "bold", "italic",
}


def load_styles() -> dict[str, dict]:
    return tomllib.loads((PRESETS / "titles.toml").read_text())


def _ass_color(hex_rgba: str) -> str:
    """#RRGGBB[AA] (AA = opacity) -> &HAABBGGRR (AA = transparency)."""
    h = hex_rgba.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    opacity = int(h[6:8], 16) if len(h) >= 8 else 255
    return f"&H{255 - opacity:02X}{b}{g}{r}".upper()


def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def build_ass(titles: list[dict], width: int, height: int) -> str:
    styles = load_styles()
    k = height / 1080.0
    style_lines, events = [], []
    used: dict[str, dict] = {}

    for i, t in enumerate(titles):
        name = t.get("style", "hero")
        if name not in styles:
            raise ValueError(f"unknown title style {name!r}; available: {', '.join(styles)}")
        st = {**styles[name], **{key: v for key, v in t.items() if key in STYLE_KEYS}}
        sid = f"s{i}_{name}"
        used[sid] = st

        size = st.get("size", 0.05) * height
        spacing = st.get("tracking", 0) * k
        box = st.get("box", False)
        # box padding small enough that per-line boxes never overlap into a darker band
        outline = (size * 0.11) if box else st.get("outline", 0) * k
        style_lines.append(",".join(str(x) for x in [
            f"Style: {sid}", st.get("font", "Inter"), f"{size:.1f}",
            _ass_color(st.get("color", "#FFFFFF")), "&H000000FF",
            _ass_color(st.get("box_color", "#00000088") if box else st.get("outline_color", "#000000")),
            _ass_color(st.get("shadow_color", "#00000080")),
            -1 if st.get("bold") else 0, -1 if st.get("italic") else 0, 0, 0, 100, 100,
            f"{spacing:.2f}", 0, 3 if box else 1,  # border style 3 = opaque box per line
            f"{outline:.1f}", f"{st.get('shadow', 0) * k:.1f}",
            st.get("align", 5), 0, 0, 0, 1,
        ]))

        a = int(st.get("align", 5))
        col, row = (a - 1) % 3, (a - 1) // 3          # col 0 left..2 right; row 0 bottom..2 top
        mx, my = st.get("margin_x", 0.06) * width, st.get("margin_y", 0.08) * height
        x = [mx, width / 2, width - mx][col] + st.get("offset_x", 0) * width
        y = [height - my, height / 2, my][row] + st.get("offset_y", 0) * height
        if "x" in t:
            x = t["x"] * width
        if "y" in t:
            y = t["y"] * height

        start, end = float(t["start"]), float(t["end"])
        dur_ms = int((end - start) * 1000)
        fin, fout = st.get("fade", [400, 400])
        tags = [f"\\fad({fin},{fout})"]
        drift = st.get("drift", 0) * k
        if drift:
            tags.append(f"\\move({x:.1f},{y + drift:.1f},{x:.1f},{y:.1f},0,{int(fin * 1.6)})")
        else:
            tags.append(f"\\pos({x:.1f},{y:.1f})")
        if st.get("blur"):
            tags.append(f"\\blur{st['blur']}")
        if st.get("expand"):
            tags.append(f"\\t(0,{dur_ms},\\fsp{spacing + st['expand'] * k:.2f})")

        text = t["text"].upper() if st.get("uppercase") else t["text"]
        events.append(f"Dialogue: {t.get('layer', 0)},{_ts(start)},{_ts(end)},{sid},,0,0,0,,"
                      f"{{{''.join(tags)}}}{_escape(text)}")

    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *style_lines, "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events, "",
    ])


def write_ass(titles: list[dict], width: int, height: int, path: Path) -> Path:
    path.write_text(build_ass(titles, width, height), encoding="utf-8")
    return path
