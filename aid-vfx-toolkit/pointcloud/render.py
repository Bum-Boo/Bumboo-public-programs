"""Project an RGB/depth clip to a drifting, luminous point cloud on black."""
import argparse
import json
import math
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("depth_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--stride", type=int, default=4)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--drift", type=float, default=9, help="Peak yaw in degrees")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    cap = cv2.VideoCapture(str(args.clip))
    if not cap.isOpened():
        raise RuntimeError("Cannot open clip")
    width, height, fps = int(cap.get(3)), int(cap.get(4)), cap.get(cv2.CAP_PROP_FPS)
    paths = sorted(args.depth_dir.glob("depth_*.png"))
    if not paths:
        raise RuntimeError("No depth PNGs in " + str(args.depth_dir))
    proc = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "%dx%d" % (width, height), "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", str(args.out)], stdin=subprocess.PIPE)
    ys, xs = np.mgrid[0:height:args.stride, 0:width:args.stride]
    x = ((xs.ravel().astype(np.float32) - width / 2) / width) * 2
    y = ((ys.ravel().astype(np.float32) - height / 2) / height) * 2
    index = 0
    try:
        while index < len(paths):
            ok, bgr = cap.read()
            if not ok:
                break
            depth = cv2.imread(str(paths[index]), cv2.IMREAD_UNCHANGED)
            if depth is None or depth.shape != (height, width):
                raise RuntimeError("Depth/frame mismatch at " + str(index))
            d = depth[::args.stride, ::args.stride].ravel().astype(np.float32) / 65535
            color = bgr[::args.stride, ::args.stride].reshape(-1, 3).astype(np.float32)
            z = (1 - d) * .9
            phase = index / max(1, len(paths) - 1)
            yaw = math.radians(args.drift) * math.sin(phase * math.pi)
            xr = x * math.cos(yaw) + z * math.sin(yaw)
            zr = z * math.cos(yaw) - x * math.sin(yaw)
            perspective = 1 / (1 + .36 * zr)
            px = np.rint((xr * perspective * .83 + 1) * width / 2).astype(np.int32)
            py = np.rint((y * perspective * .9 + 1) * height / 2).astype(np.int32)
            valid = (px >= 0) & (px < width) & (py >= 0) & (py < height)
            frame = np.zeros((height, width, 3), np.uint8)
            lum = np.clip((color.mean(axis=1) / 255) ** .4, .58, 1)
            cyan = np.stack([255 * lum, 240 * lum, 90 * lum], axis=1)
            if args.scan:
                scan_y = (phase * 1.4 - .2) * height
                boost = np.exp(-((py - scan_y) / 24) ** 2)
                cyan += boost[:, None] * np.array([45, 60, 130])
            frame[py[valid], px[valid]] = np.clip(cyan[valid], 0, 255).astype(np.uint8)
            frame = cv2.dilate(frame, np.ones((2, 2), np.uint8))
            glow = cv2.GaussianBlur(frame, (0, 0), 3)
            frame = cv2.addWeighted(frame, 1, glow, .45, 0)
            if args.scan:
                scan_y = int((phase * 1.4 - .2) * height)
                if 0 <= scan_y < height:
                    cv2.line(frame, (0, scan_y), (width - 1, scan_y), (155, 125, 55), 1, cv2.LINE_AA)
            proc.stdin.write(frame.tobytes())
            index += 1
    finally:
        cap.release()
        proc.stdin.close()
        code = proc.wait()
    if code:
        raise RuntimeError("ffmpeg failed with code " + str(code))
    print(json.dumps({"output": str(args.out), "frames": index, "fps": fps, "size": [width, height], "elapsed_seconds": round(time.perf_counter() - started, 2)}))


if __name__ == "__main__":
    main()
