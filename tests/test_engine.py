"""Engine tests. Run: python3 -m unittest discover -s tests   (needs ffmpeg; ~20 s)

Each run works in a throwaway SOUVI_ROOT so the real projects/assets/output are untouched.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="souvi-test-"))
shutil.copytree(REPO / "presets", TMP / "presets")
os.environ["SOUVI_ROOT"] = str(TMP)
sys.path.insert(0, str(REPO))

from engine import loudness, presets, project, qc, timeline, titles  # noqa: E402
from engine.paths import Project, next_version  # noqa: E402


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class Pure(unittest.TestCase):
    def test_ass_color_is_bgr_with_inverted_alpha(self):
        self.assertEqual(titles._ass_color("#FF8000"), "&H000080FF")
        self.assertEqual(titles._ass_color("#00000080"), "&H7F000000")

    def test_ass_timestamp(self):
        self.assertEqual(titles._ts(3725.456), "1:02:05.46")

    def test_every_title_style_emits_a_complete_ass_style_line(self):
        styles = list(titles.load_styles())
        ass = titles.build_ass([{"text": "x", "start": 0, "end": 1, "style": s} for s in styles], 1920, 1080)
        lines = [ln for ln in ass.splitlines() if ln.startswith("Style: ")]
        self.assertEqual(len(lines), len(styles))
        for ln in lines:
            self.assertEqual(len(ln.split(",")), 23, ln)

    def test_all_presets_load_and_build_args(self):
        for name in presets.names():
            p = presets.load(name)
            self.assertTrue(p.video or p.audio, name)
            p.video_args(), p.audio_args(), p.container_args()

    def test_next_version_never_overwrites(self):
        d = TMP / "ver"
        a = next_version(d, "cut", "mp4")
        a.touch()
        self.assertEqual(next_version(d, "cut", "mp4").name, "cut_v002.mp4")


class Timeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = project.create("unit", preset="youtube-1080p", fps=25)
        ffmpeg("-f", "lavfi", "-i", "sine=f=220:d=6", "-ac", "2", str(cls.p.assets / "music" / "tone.wav"))

    def spec(self, **kw):
        s = {"delivery": "youtube-1080p", "canvas": {"width": 320, "height": 180, "fps": 25},
             "video": [{"color": "#203040", "duration": 2},
                       {"color": "#405060", "duration": 2, "transition": {"type": "crossfade", "duration": 0.4}},
                       {"color": "#605040", "duration": 1}]}
        s.update(kw)
        return s

    def test_frame_exact_timing_with_transitions(self):
        pl = timeline.plan(self.p, self.spec())
        self.assertEqual([c.start for c in pl.clips], [0, 40, 90])
        self.assertEqual(pl.total_frames, 115)          # 50 + 50 - 10 + 25
        self.assertEqual(pl.clips[1].trans, "fade")

    def test_transition_longer_than_clip_is_rejected(self):
        s = self.spec()
        s["video"][2]["transition"] = {"type": "fade", "duration": 1.5}
        with self.assertRaises(timeline.TimelineError):
            timeline.plan(self.p, s)

    def test_render_end_to_end_hits_loudness_and_passes_qc(self):
        s = self.spec(
            titles=[{"text": "Test", "start": 0.2, "end": 2, "style": "hero"}],
            audio=[{"src": "music/tone.wav", "role": "music", "fade_out": 1}],
            fade_out=0.5,
        )
        (self.p.dir / "timeline.json").write_text(json.dumps(s))
        man = timeline.render(self.p, draft=True)
        out = Path(man["output"])
        self.assertTrue(out.exists())
        self.assertAlmostEqual(man["duration"], 4.6, places=2)
        checks = qc.run_qc(out, None, detect=False)
        self.assertFalse([c for c in checks if c.level == "FAIL"], [c.line() for c in checks])
        L = loudness.measure(out)
        self.assertLess(abs(L.integrated - (-14)), 1.0)
        self.assertLessEqual(L.true_peak, -1.0)


class Mastering(unittest.TestCase):
    def test_master_reaches_target_under_ceiling(self):
        src, dst = TMP / "loud.wav", TMP / "loud.master.wav"
        ffmpeg("-f", "lavfi", "-i", "anoisesrc=c=pink:d=4:a=0.9", "-ac", "2", str(src))
        rep = loudness.master(src, dst, target_lufs=-16, target_tp=-1.5, codec_args=["-c:a", "pcm_s24le"],
                              sample_fmt="s32", dither="triangular_hp")
        self.assertTrue(rep["on_target"], rep)


if __name__ == "__main__":
    unittest.main()
