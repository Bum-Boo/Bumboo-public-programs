"""Motion blobs and MediaPipe hand, pose, face landmarks as pixel-space JSON."""
import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp

ROOT = Path(__file__).resolve().parents[1]
MODEL_URLS = {
    "hand": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    "pose": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    "face": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
}


def model_path(kind):
    path = ROOT / "models" / (kind + "_landmarker.task")
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        tmp = path.with_suffix(".%d.download" % os.getpid())
        urllib.request.urlretrieve(MODEL_URLS[kind], tmp)
        tmp.replace(path)
    return str(path)


def points(items, width, height):
    return [{"x": round(p.x * width, 2), "y": round(p.y * height, 2), "z": round(p.z * width, 2), **({"visibility": round(p.visibility, 3)} if hasattr(p, "visibility") else {})} for p in items]


def make_landmarkers(kinds):
    vision = mp.tasks.vision
    base = mp.tasks.BaseOptions
    mode = vision.RunningMode.VIDEO
    result = {}
    if "hand" in kinds:
        result["hand"] = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(base_options=base(model_asset_path=model_path("hand")), running_mode=mode, num_hands=2))
    if "pose" in kinds:
        result["pose"] = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(base_options=base(model_asset_path=model_path("pose")), running_mode=mode, num_poses=2))
    if "face" in kinds:
        result["face"] = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(base_options=base(model_asset_path=model_path("face")), running_mode=mode, num_faces=2))
    return result


def detect_blobs(bgr, subtractor, tracks, next_id, min_area):
    h, w = bgr.shape[:2]
    mask = subtractor.apply(bgr)
    mask = cv2.medianBlur(mask, 5)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw * bh < min_area or bw > w * .95 or bh > h * .95:
            continue
        cx, cy = x + bw / 2, y + bh / 2
        boxes.append({"box": [x, y, bw, bh], "centroid": [round(cx, 2), round(cy, 2)], "area": int(cv2.contourArea(c))})
    used = set()
    updated = {}
    for box in boxes:
        cx, cy = box["centroid"]
        nearest = None
        best = max(w, h) * .12
        for ident, (px, py, age) in tracks.items():
            if ident in used or age > 4:
                continue
            dist = ((cx - px) ** 2 + (cy - py) ** 2) ** .5
            if dist < best:
                best, nearest = dist, ident
        if nearest is None:
            nearest, next_id = next_id, next_id + 1
        used.add(nearest)
        updated[nearest] = (cx, cy, 0)
        box["id"] = nearest
    for ident, (x, y, age) in tracks.items():
        if ident not in updated and age < 4:
            updated[ident] = (x, y, age + 1)
    return boxes, updated, next_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--mode", choices=["all", "blobs", "landmarks"], default="all")
    ap.add_argument("--min-area", type=int, default=700)
    ap.add_argument("--seed", type=int, nargs=4, metavar=("X", "Y", "W", "H"), help="Optional first-frame ROI for stable CSRT object tracking")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    cap = cv2.VideoCapture(str(args.clip))
    if not cap.isOpened():
        raise RuntimeError("Cannot open clip: " + str(args.clip))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width, height = int(cap.get(3)), int(cap.get(4))
    kinds = [] if args.mode == "blobs" else ["hand", "pose", "face"]
    detectors = make_landmarkers(kinds)
    subtractor = cv2.createBackgroundSubtractorMOG2(history=120, varThreshold=24, detectShadows=False)
    tracks, next_id, frames = {}, 1, []
    roi_tracker = cv2.TrackerCSRT_create() if args.seed else None
    index = 0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        timestamp = round(index * 1000 / fps)
        row = {"frame": index, "time_ms": timestamp}
        if args.mode != "landmarks":
            if roi_tracker:
                if index == 0:
                    roi_tracker.init(bgr, tuple(args.seed))
                    good, box = True, args.seed
                else:
                    good, box = roi_tracker.update(bgr)
                if good:
                    x, y, bw, bh = [int(round(v)) for v in box]
                    row["objects"] = [{"id": 1, "box": [x, y, bw, bh], "centroid": [round(x + bw / 2, 2), round(y + bh / 2, 2)], "area": bw * bh}]
                else:
                    row["objects"] = []
            else:
                row["objects"], tracks, next_id = detect_blobs(bgr, subtractor, tracks, next_id, args.min_area)
        if detectors:
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            if "hand" in detectors:
                r = detectors["hand"].detect_for_video(image, timestamp)
                row["hands"] = [{"id": i, "label": r.handedness[i][0].category_name, "points": points(v, width, height)} for i, v in enumerate(r.hand_landmarks)]
            if "pose" in detectors:
                r = detectors["pose"].detect_for_video(image, timestamp)
                row["poses"] = [{"id": i, "points": points(v, width, height)} for i, v in enumerate(r.pose_landmarks)]
            if "face" in detectors:
                r = detectors["face"].detect_for_video(image, timestamp)
                row["faces"] = [{"id": i, "points": points(v, width, height)} for i, v in enumerate(r.face_landmarks)]
        frames.append(row)
        index += 1
    cap.release()
    for detector in detectors.values():
        detector.close()
    payload = {"source": str(args.clip), "width": width, "height": height, "fps": fps, "frame_count": index, "coordinates": "pixel, top-left origin", "tracking_method": "CSRT seeded ROI" if args.seed else "MOG2 motion blobs", "seed": args.seed, "elapsed_seconds": round(time.perf_counter() - started, 2), "frames": frames}
    args.out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "frames"}, indent=2))


if __name__ == "__main__":
    main()
