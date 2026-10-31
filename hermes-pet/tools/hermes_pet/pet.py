from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import webbrowser

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.hermes_pet.snippet import classify_status, extract_snippet
from tools.hermes_pet.sprite import FRAME_HEIGHT, FRAME_WIDTH, SPRITESHEET_HEIGHT, SPRITESHEET_WIDTH, sprite_row_for_status
from tools.hermes_pet.state_source import HermesStateSource, PetMessage


@dataclass(frozen=True)
class PetAsset:
    asset_id: str = "generic"
    display_name: str = "Hermes Pet"
    description: str = ""
    spritesheet: Path | None = None
    trust_alpha: bool = False


def default_asset_dir() -> Path:
    return Path(__file__).resolve().parent / "assets" / "generic"


def load_pet_asset(asset_dir: Path | str | None) -> PetAsset:
    if asset_dir is None:
        asset_dir = default_asset_dir()
    root = Path(asset_dir).expanduser()
    config_path = root / "pet.json"
    if not config_path.exists():
        return PetAsset()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PetAsset()
    display_name = str(config.get("displayName") or "Hermes Pet")
    asset_id = str(config.get("id") or root.name or "generic")
    description = str(config.get("description") or "")
    trust_alpha = bool(config.get("trustAlpha") or config.get("codexCompatible"))
    sheet_name = str(config.get("spritesheetPath") or "spritesheet.webp")
    sheet_path = root / sheet_name
    # The spritesheet is served over HTTP, so it must stay inside the asset dir
    # (no absolute paths or ".." escapes from a third-party pet.json).
    try:
        sheet_path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return PetAsset(asset_id=asset_id, display_name=display_name, description=description, trust_alpha=trust_alpha)
    if not sheet_path.exists() or not sheet_path.is_file():
        return PetAsset(asset_id=asset_id, display_name=display_name, description=description, trust_alpha=trust_alpha)
    return PetAsset(
        asset_id=asset_id,
        display_name=display_name,
        description=description,
        spritesheet=sheet_path,
        trust_alpha=trust_alpha,
    )

_STATUS_EMOJI = {
    "idle": "🌸",
    "working": "✨",
    "completed": "✅",
    "needs_approval": "🛡️",
    "error": "⚠️",
}

_STATUS_LABEL = {
    "idle": "기다리는 중",
    "working": "보고 있어",
    "completed": "끝났어",
    "needs_approval": "확인이 필요해",
    "error": "문제가 생겼어",
}


def default_state_db(profile: str) -> Path:
    home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()
    profile_path = home / "profiles" / profile / "state.db"
    if profile_path.exists():
        return profile_path
    return home / "state.db"


def message_payload(message: PetMessage | None, max_chars: int = 120) -> dict[str, object]:
    if message is None:
        return {
            "ok": True,
            "message_id": None,
            "status": "idle",
            "emoji": _STATUS_EMOJI["idle"],
            "label": _STATUS_LABEL["idle"],
            "sprite_row": sprite_row_for_status("idle"),
            "snippet": "아직 새 결과가 없습니다.",
            "source": None,
            "session_id": None,
            "timestamp": None,
        }
    status = classify_status(message.content)
    return {
        "ok": True,
        "message_id": message.id,
        "status": status,
        "emoji": _STATUS_EMOJI.get(status, "🌸"),
        "label": _STATUS_LABEL.get(status, "보고 있어"),
        "sprite_row": sprite_row_for_status(status),
        "snippet": extract_snippet(message.content, max_chars=max_chars),
        "source": message.source,
        "session_id": message.session_id,
        "timestamp": message.timestamp,
    }


def render_console(payload: dict[str, object]) -> str:
    return f"{payload['emoji']} {payload['label']} — {payload['snippet']}"


def _html() -> bytes:
    page = """
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes Pet</title>
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0;
    min-height: 100vh;
    display: grid;
    place-items: center;
    background: radial-gradient(circle at top, #3b1d0f, #111827 55%, #030712);
    font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: #fff7ed;
  }
  .pet {
    width: min(440px, calc(100vw - 32px));
    border: 1px solid rgba(251, 146, 60, .45);
    border-radius: 28px;
    padding: 24px;
    background: rgba(17, 24, 39, .78);
    box-shadow: 0 24px 80px rgba(0,0,0,.45), 0 0 80px rgba(249,115,22,.18);
    backdrop-filter: blur(18px);
  }
  .face {
    --frame-w: 192px;
    --frame-h: 208px;
    --sheet-w: 1536px;
    --sheet-h: 1872px;
    --sprite-row: 0;
    width: var(--frame-w);
    height: var(--frame-h);
    margin: 0 auto 18px;
    display: grid;
    place-items: center;
    position: relative;
    overflow: hidden;
    color: #431407;
    font-size: 56px;
    animation: float 2.8s ease-in-out infinite;
  }
  .aura {
    position: absolute;
    inset: 28px;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(253,230,138,.38), rgba(249,115,22,.10), transparent 68%);
    filter: blur(2px);
  }
  .sprite {
    position: absolute;
    inset: 0;
    background-image: url('/assets/spritesheet.webp');
    background-repeat: no-repeat;
    background-size: var(--sheet-w) var(--sheet-h);
    background-position: 0 calc(var(--sprite-row) * -208px);
    image-rendering: pixelated;
    transform: scale(1.08);
    transform-origin: center bottom;
    animation: sprite-step 1.1s steps(8) infinite;
  }
  .fallback {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
  }
  @keyframes float { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-8px) } }
  @keyframes sprite-step { from { background-position-x: 0; } to { background-position-x: -1536px; } }
  .label { text-align: center; color: #fed7aa; font-weight: 800; letter-spacing: .02em; }
  .bubble {
    margin-top: 14px;
    padding: 16px 18px;
    border-radius: 20px;
    background: rgba(255, 247, 237, .10);
    line-height: 1.55;
    word-break: keep-all;
  }
  .meta { margin-top: 12px; text-align: center; color: #fdba74; font-size: 12px; opacity: .8; }
  .hint { margin-top: 14px; text-align: center; color: #9ca3af; font-size: 12px; }
</style>
</head>
<body>
  <main class="pet" title="Read-only result pet">
    <div id="face" class="face"><div class="aura"></div><div class="fallback">🌸</div><div id="sprite" class="sprite" aria-label="pet sprite"></div></div>
    <div id="label" class="label">기다리는 중</div>
    <div id="bubble" class="bubble">아직 새 결과가 없습니다.</div>
    <div id="meta" class="meta">zero-token display</div>
    <div class="hint">이미 생성된 Hermes 결과만 읽어서 보여줘.</div>
  </main>
<script>
async function refresh() {
  try {
    const res = await fetch('/api/state', {cache: 'no-store'});
    const data = await res.json();
    document.getElementById('face').style.setProperty('--sprite-row', data.sprite_row ?? 0);
    document.querySelector('.fallback').textContent = data.emoji || '🌸';
    document.getElementById('label').textContent = data.label || '기다리는 중';
    document.getElementById('bubble').textContent = data.snippet || '아직 새 결과가 없습니다.';
    document.getElementById('meta').textContent = data.source ? `${data.source} · message ${data.message_id}` : 'zero-token display';
  } catch (e) {
    document.querySelector('.fallback').textContent = '⚠️';
    document.getElementById('label').textContent = '연결 확인 중';
  }
}
refresh();
setInterval(refresh, 2500);
</script>
</body>
</html>
"""
    return page.encode("utf-8")


class PetHandler(BaseHTTPRequestHandler):
    source: HermesStateSource
    asset: PetAsset = PetAsset()
    max_chars: int = 120

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            self._send_json(message_payload(self.source.latest_assistant_message(), self.max_chars))
            return
        if path == "/assets/spritesheet.webp" and self.asset.spritesheet is not None:
            try:
                body = self.asset.spritesheet.read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/webp")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in {"/", "/index.html"}:
            body = _html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)


def serve(source: HermesStateSource, host: str, port: int, max_chars: int, open_browser: bool, asset: PetAsset) -> None:
    PetHandler.source = source
    PetHandler.max_chars = max_chars
    PetHandler.asset = asset
    server = ThreadingHTTPServer((host, port), PetHandler)
    url = f"http://{host}:{port}/"
    print(f"Hermes Pet listening on {url}")
    print("읽기 전용 표시 모드야. 새 모델 호출은 하지 않아.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nHermes Pet stopped.")
    finally:
        server.server_close()


def watch_console(source: HermesStateSource, interval: float, max_chars: int) -> None:
    last_id: int | None = None
    print("Hermes Pet console watch started. Ctrl+C to stop.")
    try:
        while True:
            msg = source.latest_assistant_message(after_id=last_id)
            if msg is not None:
                last_id = msg.id
                print(render_console(message_payload(msg, max_chars=max_chars)), flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nHermes Pet stopped.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Zero-token Hermes result pet")
    parser.add_argument("--profile", default="default", help="Hermes profile whose state.db should be read")
    parser.add_argument("--db", type=Path, default=None, help="Explicit Hermes state.db path")
    parser.add_argument("--source", action="append", default=None, help="Allowed session source; repeatable (default: telegram)")
    parser.add_argument("--max-chars", type=int, default=120, help="Maximum snippet length")
    parser.add_argument("--asset-dir", type=Path, default=default_asset_dir(), help="Directory containing pet.json and spritesheet.webp")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Print the latest pet bubble once")
    mode.add_argument("--watch", action="store_true", help="Print new result bubbles in the terminal")
    mode.add_argument("--serve", action="store_true", help="Serve a local browser pet")
    parser.add_argument("--host", default="127.0.0.1", help="Local bind host for --serve")
    parser.add_argument("--port", type=int, default=8765, help="Local port for --serve")
    parser.add_argument("--open", action="store_true", help="Open browser for --serve")
    parser.add_argument("--interval", type=float, default=2.5, help="Polling interval for --watch")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    db_path = args.db or default_state_db(args.profile)
    source = HermesStateSource(db_path, allowed_sources=set(args.source or ["telegram"]))
    asset = load_pet_asset(args.asset_dir)

    if args.watch:
        watch_console(source, args.interval, args.max_chars)
        return 0
    if args.serve:
        serve(source, args.host, args.port, args.max_chars, args.open, asset)
        return 0

    payload = message_payload(source.latest_assistant_message(), max_chars=args.max_chars)
    print(render_console(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
