# AID VFX Toolkit

Python command-line depth, tracking, point-cloud and dither tools, with optional After Effects JSX composition builders. This is experimental source: Python syntax and JSX parsing are checked separately from rendering and Adobe host behavior. No footage, model weights, generated outputs or dependency binaries are bundled.

## Setup

Python 3.11 is recommended. Install ffmpeg (with the libx264 encoder) separately. On headless Linux the MediaPipe landmark path also needs the GLES/EGL runtime libraries, otherwise it fails with `OSError: libGLESv2.so.2`; on Debian/Ubuntu:

```sh
sudo apt-get install -y --no-install-recommends ffmpeg libgles2 libegl1
```

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python dither/render.py input.mp4 output/dither.mp4
.venv/bin/python depth/depth.py input.mp4 output/depth
.venv/bin/python track/track.py input.mp4 output/tracking.json
.venv/bin/python pointcloud/render.py input.mp4 output/depth output/pointcloud.mp4 --scan
```

Run `depth/depth.py` before `pointcloud/render.py`: the point cloud reads the 16-bit `depth_*.png` frames it writes, which must match the clip size (odd frame sizes are padded to even for H.264). Input footage must be provided by the user. Tracking seed uses x y width height via `--seed`. `track/track.py` defaults to `--mode all`, which needs the MediaPipe landmark models; `--mode blobs` (MOG2 motion blobs, or CSRT with `--seed`) runs without any model file. Depth/landmark commands download external model files on first use; review `models/MODELS.md` before invoking them. Models are not covered by the toolkit MIT license. No cloud API is needed.

For After Effects, review the constants in `ae/*.jsx`, set input/output paths (the empty-path defaults point at `demo/xr/tracking.json` and `demo/xr/depth/`, which are not bundled, so set `TRACKING_JSON`, `LANDMARK_JSON`, `CLIP_PATH`, `DEPTH_FIRST_PNG` and `HALFTONE_CLIP_PATH` to absolute paths of your outputs) and run from File → Scripts in an empty project you control. Scripts create compositions and report files; host effect selectors vary by Adobe version. Parsing success does not establish Adobe runtime or visual correctness.

A synthetic smoke clip can be created with separately installed ffmpeg: `ffmpeg -f lavfi -i testsrc2=size=160x90:rate=12 -t 1 -c:v mpeg4 input.mp4`. No customer footage is distributed. GPU acceleration, depth accuracy and Adobe rendering remain unverified in this public packaging pass. Dependencies retain their respective licenses; ffmpeg is invoked externally and not redistributed.

## Tests

Smoke tests use synthetic ffmpeg clips and never download models (the depth ONNX session and MediaPipe landmarkers are faked). JSX is only syntax-checked with Node (if installed) and the shared JSON parser is run under Node; Adobe host behavior is not tested.

```sh
.venv/bin/python -m unittest discover -s tests -v
```
