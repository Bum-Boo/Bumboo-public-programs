"""Render a Bayer-dithered clip with the installed FFmpeg."""
import argparse
import json
import subprocess
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--colors", type=int, default=12)
    ap.add_argument("--bayer-scale", type=int, default=2)
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    graph = "[0:v]scale=iw/2:ih/2:flags=area,split[a][b];[a]palettegen=max_colors=%d:stats_mode=full[p];[b][p]paletteuse=dither=bayer:bayer_scale=%d,scale=iw*2:ih*2:flags=neighbor" % (a.colors, a.bayer_scale)
    start = time.perf_counter()
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(a.clip), "-filter_complex", graph, "-an", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", str(a.out)], check=True)
    print(json.dumps({"output": str(a.out), "elapsed_seconds": round(time.perf_counter() - start, 2)}))


if __name__ == "__main__":
    main()
