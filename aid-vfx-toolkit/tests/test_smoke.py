"""Smoke tests for the AID VFX Toolkit command-line tools.

Run from the toolkit folder:  python -m unittest discover -s tests -v

All inputs are synthetic clips generated with ffmpeg lavfi. No model weights
are downloaded: the ONNX depth session and the MediaPipe landmarkers are
replaced with fakes, and any accidental download attempt fails the test.
After Effects behaviour cannot be exercised here; the JSX files are only
syntax-checked with Node and the shared JSON parser is run under Node.
"""
import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
NODE = shutil.which("node")


def _has(module):
    return importlib.util.find_spec(module) is not None


HAS_CV = _has("cv2") and _has("numpy")
HAS_MP = _has("mediapipe")
HAS_ORT = _has("onnxruntime")


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main(module, argv):
    """Call module.main() with argv, returning captured stdout."""
    out = io.StringIO()
    with mock.patch.object(sys, "argv", [module.__name__] + [str(a) for a in argv]), contextlib.redirect_stdout(out):
        module.main()
    return out.getvalue()


def make_clip(path, size="160x90", rate=12, seconds=1, extra=(), source=None):
    source = source or "testsrc2=size=%s:rate=%d" % (size, rate)
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    source, "-t", str(seconds), *extra, str(path)], check=True)
    return path


def probe(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                          "stream=width,height,nb_read_frames,codec_name", "-of", "json", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)["streams"][0]


def write_depth_pngs(directory, count, width, height):
    import cv2
    import numpy as np
    directory.mkdir(parents=True, exist_ok=True)
    ramp = np.tile(np.linspace(0, 65535, width), (height, 1)).astype(np.uint16)
    for i in range(count):
        cv2.imwrite(str(directory / ("depth_%05d.png" % i)), ramp)


def no_network(*_args, **_kwargs):
    raise AssertionError("smoke tests must not download model files")


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(mock.patch.stopall)
        mock.patch("urllib.request.urlretrieve", side_effect=no_network).start()


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg/ffprobe not installed")
class DitherSmoke(TempDirTest):
    def test_dither_cli_renders_h264_clip(self):
        clip = make_clip(self.tmp / "input.mp4", extra=("-c:v", "mpeg4"))
        out = self.tmp / "output" / "dither.mp4"
        res = subprocess.run([sys.executable, str(ROOT / "dither" / "render.py"), str(clip), str(out), "--colors", "8"],
                             check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(res.stdout)["output"], str(out))
        info = probe(out)
        self.assertEqual((info["codec_name"], info["width"], info["height"]), ("h264", 160, 90))
        self.assertEqual(int(info["nb_read_frames"]), 12)


@unittest.skipUnless(FFMPEG and FFPROBE and HAS_CV, "ffmpeg or opencv-contrib-python/numpy not installed")
class PointcloudSmoke(TempDirTest):
    def render(self, clip, depth_dir, *extra):
        out = self.tmp / "output" / "pointcloud.mp4"
        res = subprocess.run([sys.executable, str(ROOT / "pointcloud" / "render.py"), str(clip), str(depth_dir), str(out), *extra],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout), probe(out)

    def test_pointcloud_cli_with_synthetic_depth(self):
        clip = make_clip(self.tmp / "input.mp4", extra=("-c:v", "mpeg4"))
        write_depth_pngs(self.tmp / "depth", 12, 160, 90)
        meta, info = self.render(clip, self.tmp / "depth", "--scan")
        self.assertEqual((meta["frames"], meta["size"]), (12, [160, 90]))
        self.assertEqual((info["width"], info["height"], int(info["nb_read_frames"])), (160, 90, 12))

    def test_pointcloud_odd_frame_size(self):
        # Regression: libx264/yuv420p rejects odd sizes, so ffmpeg died and the
        # script crashed with BrokenPipeError. Output is now padded to even.
        clip = make_clip(self.tmp / "odd.mkv", extra=("-vf", "scale=161:91", "-c:v", "ffv1"))
        write_depth_pngs(self.tmp / "depth", 12, 161, 91)
        meta, info = self.render(clip, self.tmp / "depth")
        self.assertEqual(meta["frames"], 12)
        self.assertEqual((info["width"], info["height"]), (162, 92))

    def test_pointcloud_rejects_mismatched_depth(self):
        clip = make_clip(self.tmp / "input.mp4", extra=("-c:v", "mpeg4"))
        write_depth_pngs(self.tmp / "depth", 2, 80, 45)
        res = subprocess.run([sys.executable, str(ROOT / "pointcloud" / "render.py"), str(clip), str(self.tmp / "depth"),
                              str(self.tmp / "pc.mp4")], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Depth/frame mismatch at 0", res.stderr)


class FakeDepthSession:
    """Stands in for onnxruntime.InferenceSession: no model file is read."""

    def __init__(self, path, providers=None):
        self.calls = 0

    def get_inputs(self):
        return [types.SimpleNamespace(name="pixel_values")]

    def run(self, _outputs, feeds):
        import numpy as np
        (tensor,) = feeds.values()
        assert tensor.shape[:2] == (1, 3) and tensor.dtype == np.float32
        size = tensor.shape[-1]
        self.calls += 1
        return [np.tile(np.linspace(0, 10 + self.calls, size, dtype=np.float32), (1, size, 1))]


@unittest.skipUnless(FFMPEG and HAS_CV and HAS_ORT, "ffmpeg, opencv-contrib-python or onnxruntime not installed")
class DepthSmoke(TempDirTest):
    def test_depth_pipeline_with_fake_model_then_pointcloud(self):
        import cv2
        depth = load("depth/depth.py", "aid_depth")
        mock.patch.object(depth, "ensure_model", return_value=self.tmp / "fake.onnx").start()
        mock.patch.object(depth.ort, "InferenceSession", FakeDepthSession).start()
        clip = make_clip(self.tmp / "input.mp4", rate=6, extra=("-c:v", "mpeg4"))
        out = self.tmp / "output" / "depth"
        run_main(depth, [clip, out, "--size", "28"])
        meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual((meta["width"], meta["height"], meta["frame_count"]), (160, 90, 6))
        pngs = sorted(out.glob("depth_*.png"))
        self.assertEqual(len(pngs), 6)
        self.assertEqual(list(out.glob("raw_*.npy")), [])
        img = cv2.imread(str(pngs[0]), cv2.IMREAD_UNCHANGED)
        self.assertEqual((img.dtype.name, img.shape), ("uint16", (90, 160)))
        self.assertLess(int(img[45, 2]), int(img[45, 157]))  # ramp preserved, near = white
        if FFPROBE:
            res = subprocess.run([sys.executable, str(ROOT / "pointcloud" / "render.py"), str(clip), str(out),
                                  str(self.tmp / "pc.mp4"), "--scan"], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(json.loads(res.stdout)["frames"], 6)

    def test_depth_size_must_be_multiple_of_14(self):
        depth = load("depth/depth.py", "aid_depth_size")
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(io.StringIO()):
            run_main(depth, [self.tmp / "x.mp4", self.tmp / "out", "--size", "500"])
        self.assertEqual(ctx.exception.code, 2)


@unittest.skipUnless(FFMPEG and HAS_CV and HAS_MP, "ffmpeg, opencv-contrib-python or mediapipe not installed")
class TrackSmoke(TempDirTest):
    def track(self, clip, out, *extra):
        res = subprocess.run([sys.executable, str(ROOT / "track" / "track.py"), str(clip), str(out), *extra],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(out.read_text(encoding="utf-8"))

    def moving_box_clip(self):
        # Grey background with a textured 30x30 square moving right at 120 px/s.
        graph = ("color=c=gray:s=160x90:r=12:d=1[bg];testsrc2=s=30x30:r=12[fg];"
                 "[bg][fg]overlay=x='10+t*120':y=30:shortest=1")
        return make_clip(self.tmp / "box.mp4", source=graph, extra=("-c:v", "mpeg4", "-q:v", "2"))

    def test_blob_mode_without_models(self):
        clip = self.moving_box_clip()
        data = self.track(clip, self.tmp / "out" / "tracking.json", "--mode", "blobs", "--min-area", "200")
        self.assertEqual((data["width"], data["height"], data["frame_count"]), (160, 90, 12))
        self.assertEqual(data["tracking_method"], "MOG2 motion blobs")
        self.assertEqual(len(data["frames"]), 12)
        self.assertTrue(all("objects" in f and "hands" not in f for f in data["frames"]))
        detected = [o for f in data["frames"] for o in f["objects"]]
        self.assertTrue(detected, "moving square should be detected as a blob")
        self.assertTrue(all(set(o) >= {"id", "box", "centroid", "area"} for o in detected))

    def test_seeded_csrt_tracking(self):
        clip = self.moving_box_clip()
        data = self.track(clip, self.tmp / "seed.json", "--mode", "blobs", "--seed", "10", "30", "30", "30")
        self.assertEqual(data["tracking_method"], "CSRT seeded ROI")
        self.assertEqual(data["seed"], [10, 30, 30, 30])
        first, last = data["frames"][0]["objects"][0], data["frames"][-1]["objects"]
        self.assertEqual(first["box"], [10, 30, 30, 30])
        self.assertTrue(last and last[0]["centroid"][0] > first["centroid"][0] + 40, "seeded box should follow motion")

    def test_landmark_mode_with_fake_detectors(self):
        track = load("track/track.py", "aid_track")
        lm = lambda x, y, **kw: types.SimpleNamespace(x=x, y=y, z=0.01, **kw)
        result = types.SimpleNamespace(
            handedness=[[types.SimpleNamespace(category_name="Left")]],
            hand_landmarks=[[lm(0.5, 0.5)] * 21],
            pose_landmarks=[[lm(0.25, 0.75, visibility=0.9)] * 33],
            face_landmarks=[[lm(0.1, 0.2)] * 468],
        )
        detector = mock.Mock()
        detector.detect_for_video.return_value = result
        maker = mock.patch.object(track, "make_landmarkers", return_value={k: detector for k in ("hand", "pose", "face")}).start()
        clip = make_clip(self.tmp / "input.mp4", rate=4, extra=("-c:v", "mpeg4"))
        out = self.tmp / "landmarks.json"
        run_main(track, [clip, out, "--mode", "landmarks"])
        maker.assert_called_once_with(["hand", "pose", "face"])
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["frame_count"], 4)
        row = data["frames"][1]
        self.assertEqual(row["time_ms"], 250)
        self.assertNotIn("objects", row)
        self.assertEqual(row["hands"][0]["label"], "Left")
        self.assertEqual(row["hands"][0]["points"][0], {"x": 80.0, "y": 45.0, "z": 1.6})
        self.assertEqual(row["poses"][0]["points"][0]["visibility"], 0.9)
        self.assertEqual(len(row["faces"][0]["points"]), 468)
        self.assertEqual(detector.close.call_count, 3)


@unittest.skipUnless(NODE, "node not installed; JSX syntax check not run")
class JsxStatic(TempDirTest):
    """Node parses the ES3 used here; this does not exercise the Adobe host."""

    def test_jsx_files_parse(self):
        files = sorted((ROOT / "ae").glob("*.jsx")) + sorted((ROOT / "ae").glob("*.jsxinc"))
        self.assertEqual(len(files), 5)
        for path in files:
            with self.subTest(path.name), path.open("rb") as fh:
                res = subprocess.run([NODE, "--check", "-"], stdin=fh, capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, res.stderr)

    def parse_with_jsx_parser(self, text):
        script = ("const fs=require('fs');eval(fs.readFileSync(process.argv[1],'utf8'));"
                  "try{process.stdout.write(JSON.stringify(parseToolkitJSON(fs.readFileSync(process.argv[2],'utf8'))));}"
                  "catch(e){process.stdout.write('ERR:'+e.message);}")
        src = self.tmp / "in.json"
        src.write_text(text, encoding="utf-8")
        return subprocess.run([NODE, "-e", script, str(ROOT / "ae" / "json_parser.jsxinc"), str(src)],
                              check=True, capture_output=True, text=True).stdout

    def test_jsx_json_parser_reads_tracker_output_and_rejects_code(self):
        payload = {"source": "C:\\clips\\caf\u00e9 \"take\".mp4", "width": 160, "height": 90, "fps": 12.0, "frame_count": 1,
                   "seed": None, "frames": [{"frame": 0, "time_ms": 0, "objects": [{"id": 1, "box": [1, 2, 3, 4],
                   "centroid": [2.5, 4.0], "area": 12}], "poses": [{"id": 0, "points": [{"x": -0.0, "y": 1e-05, "z": -3.25, "visibility": 1.0}]}]}]}
        text = json.dumps(payload, separators=(",", ":"))
        self.assertEqual(json.loads(self.parse_with_jsx_parser(text)), payload)
        self.assertEqual(self.parse_with_jsx_parser('{"a":(function(){return 1})()}'), "ERR:Invalid tracking JSON")


if __name__ == "__main__":
    unittest.main()
