# AID VFX Toolkit

Python command-line depth, tracking, point-cloud and dither tools, with optional After Effects JSX composition builders. This is experimental source: Python syntax and JSX parsing are checked separately from rendering and Adobe host behavior. No footage, model weights, generated outputs or dependency binaries are bundled.

## Setup

Python 3.11 is recommended. Install ffmpeg separately.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python dither/render.py input.mp4 output/dither.mp4
.venv/bin/python depth/depth.py input.mp4 output/depth
.venv/bin/python track/track.py input.mp4 output/tracking.json
.venv/bin/python pointcloud/render.py input.mp4 output/depth output/pointcloud.mp4 --scan
```

Input footage must be provided by the user. Tracking seed uses x y width height via `--seed`. Depth/landmark commands download external model files on first use; review `models/MODELS.md` before invoking them. Models are not covered by the toolkit MIT license. No cloud API is needed.

For After Effects, review the constants in `ae/*.jsx`, set input/output paths and run from File → Scripts in an empty project you control. Scripts create compositions and report files; host effect selectors vary by Adobe version. Parsing success does not establish Adobe runtime or visual correctness.

A synthetic smoke clip can be created with separately installed ffmpeg: `ffmpeg -f lavfi -i testsrc2=size=160x90:rate=12 -t 1 -c:v mpeg4 input.mp4`. No customer footage is distributed. GPU acceleration, depth accuracy and Adobe rendering remain unverified in this public packaging pass. Dependencies retain their respective licenses; ffmpeg is invoked externally and not redistributed.
