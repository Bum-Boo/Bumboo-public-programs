"""Depth Anything V2 Small ONNX to temporally smoothed 16-bit PNGs."""
import argparse
import json
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

MODEL_URL = "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx"
ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models" / "depth_anything_v2_small.onnx"


def ensure_model():
    MODEL.parent.mkdir(exist_ok=True)
    if not MODEL.exists():
        tmp = MODEL.with_suffix(".download")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(MODEL)
    return MODEL


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--size", type=int, default=518, help="Inference square size (multiple of 14)")
    ap.add_argument("--smooth", type=float, default=0.65, help="Weight of current frame after flow-warped history")
    args = ap.parse_args()
    if args.size % 14:
        ap.error("--size must be a multiple of 14")
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    sess = ort.InferenceSession(str(ensure_model()), providers=["CPUExecutionProvider"])
    input_name = sess.get_inputs()[0].name
    cap = cv2.VideoCapture(str(args.clip))
    if not cap.isOpened():
        raise RuntimeError("Cannot open clip: " + str(args.clip))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width, height = int(cap.get(3)), int(cap.get(4))
    previous_gray = previous_depth = None
    raw_files = []
    frame = 0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        # DA-V2's ImageNet normalization and 518-square inference input.
        small = cv2.resize(rgb, (args.size, args.size), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
        small = (small - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        tensor = np.transpose(small, (2, 0, 1))[None].astype(np.float32)
        depth = sess.run(None, {input_name: tensor})[0].squeeze()
        depth = cv2.resize(depth, (width, height), interpolation=cv2.INTER_CUBIC).astype(np.float32)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        if previous_gray is not None:
            # Backward flow maps this frame's pixels to their previous-frame positions.
            flow = cv2.calcOpticalFlowFarneback(gray, previous_gray, None, .5, 3, 21, 3, 5, 1.2, 0)
            grid = np.indices((height, width), dtype=np.float32).transpose(1, 2, 0)
            warped = cv2.remap(previous_depth, grid[:, :, 1] + flow[:, :, 0], grid[:, :, 0] + flow[:, :, 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            depth = args.smooth * depth + (1 - args.smooth) * warped
        previous_gray, previous_depth = gray, depth
        raw = args.out / ("raw_%05d.npy" % frame)
        np.save(raw, depth)
        raw_files.append(raw)
        frame += 1
    cap.release()
    if not raw_files:
        raise RuntimeError("Clip has no readable frames")
    # One scale for the whole clip prevents framewise contrast pumping.
    sample = np.concatenate([np.load(p)[::12, ::12].ravel() for p in raw_files])
    low, high = np.percentile(sample, [1, 99])
    if high <= low:
        high = low + 1
    for i, p in enumerate(raw_files):
        depth = np.load(p)
        image = (np.clip((depth - low) / (high - low), 0, 1) * 65535).astype(np.uint16)
        cv2.imwrite(str(args.out / ("depth_%05d.png" % i)), image)
        p.unlink()
    metadata = {"source": str(args.clip), "width": width, "height": height, "fps": fps, "frame_count": frame, "format": "16-bit PNG", "near": "white", "model": "Depth Anything V2 Small ONNX", "elapsed_seconds": round(time.perf_counter() - started, 2), "normalization_percentiles": [float(low), float(high)]}
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
