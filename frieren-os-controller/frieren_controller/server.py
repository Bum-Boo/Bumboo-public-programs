"""Local JSON-line API over an owner-only Unix socket."""

from __future__ import annotations

import json
import os
import socket
import socketserver
import struct
from pathlib import Path

from .core import Controller, ControllerError

ALLOWED = {
    "job_unit_read",
    "job_unit_save",
    "job_cron_read",
    "job_cron_save",
    "workspace_status",
    "workspace_configure",
    "workspace_presets",
    "workspace_save_preset",
    "workspace_apply_preset",
    "work_mode_status",
    "work_mode_save",
    "work_mode_apply",
    "work_mode_end",
    "settings_history",
    "settings_revert",
    "settings_recover",
    "himmel_open",
    "widget_status",
    "widget_brightness",
    "appearance_status",
    "wallpaper_set",
    "wallpaper_reset",
    "terminal_configure",
    "terminal_reset",
    "terminal_open",
    "list_units",
    "describe_unit",
    "preview_toggle",
    "toggle_unit",
    "get_note",
    "set_note",
    "journal_tail",
    "audit_log",
    "list_modules",
    "read_module",
    "write_module",
    "run_check",
    "dashboard",
    "quiet_status",
    "quiet_set_mode",
    "quiet_set_target",
    "quiet_set_effects",
    "quiet_configure",
    "quiet_reset",
    "monitor_status",
    "monitor_external_status",
    "monitor_external_set",
    "monitor_external_reset",
    "monitor_configure",
    "monitor_preset",
    "monitor_reset",
    "monitor_keep_awake",
    "monitor_original_color",
    "monitor_preview_layout",
    "monitor_confirm_layout",
}
MAX_REQUEST = 65536


def socket_path() -> Path:
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    return runtime / "frieren-os-controller.sock"


def dispatch(controller: Controller, request: object) -> dict:
    if not isinstance(request, dict) or set(request) not in ({"op", "args"}, {"op", "args", "source"}):
        return {"ok": False, "error": "요청 형식이 올바르지 않아요."}
    operation = request["op"]
    args = request["args"]
    source = request.get("source", "local")
    if source not in ("local", "gui", "cli", "mcp", "widget"):
        return {"ok": False, "error": "요청 출처가 올바르지 않아요."}
    if not isinstance(operation, str) or operation not in ALLOWED or not isinstance(args, dict):
        return {"ok": False, "error": "지원하지 않는 요청이에요."}
    try:
        controller.request_context.source = source
        result = getattr(controller, operation)(**args)
        return {"ok": True, "result": result}
    except (ControllerError, TypeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "기능에 연결하지 못했어요. 상태를 확인한 뒤 다시 시도해 주세요."}
    finally:
        controller.request_context.source = "local"


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        credentials = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _, uid, _ = struct.unpack("3i", credentials)
        if uid != os.getuid():
            return
        line = self.rfile.readline(MAX_REQUEST + 1)
        if not line or len(line) > MAX_REQUEST or not line.endswith(b"\n"):
            self._send({"ok": False, "error": "요청 크기나 형식이 올바르지 않아요."})
            return
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            self._send({"ok": False, "error": "JSON 요청이 올바르지 않아요."})
            return
        self._send(dispatch(self.server.controller, request))

    def _send(self, data):
        try:
            self.wfile.write((json.dumps(data, ensure_ascii=False) + "\n").encode())
            self.wfile.flush()
        except BrokenPipeError:
            pass


class ThreadedServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False


def serve(path: Path | None = None, controller: Controller | None = None):
    from .session_environment import load_desktop_environment

    load_desktop_environment()
    path = Path(path or socket_path())
    if path.exists():
        if not path.is_socket():
            raise ControllerError("소켓 경로에 다른 파일이 있어요.")
        try:
            with socket.socket(socket.AF_UNIX) as sock:
                sock.settimeout(0.25)
                sock.connect(str(path))
        except ConnectionRefusedError:
            path.unlink()
        else:
            raise ControllerError("컨트롤러가 이미 실행 중이에요.")
    previous_umask = os.umask(0o077)
    try:
        server = ThreadedServer(str(path), Handler)
    finally:
        os.umask(previous_umask)
    path.chmod(0o600)
    server.controller = controller or Controller()
    # Start recovery/automation even before the first GUI or MCP request.
    try:
        server.controller._monitor()
    except ControllerError:
        pass  # Other local controls remain available if the KDE session is unavailable.
    try:
        server.controller._extensions()
    except ControllerError:
        pass
    from .widget_bus import WidgetBus

    widget_bus = WidgetBus(server.controller)
    widget_bus.start()
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        widget_bus.close()
        if server.controller.extensions is not None:
            server.controller.extensions.close()
        if server.controller.monitor is not None:
            server.controller.monitor.close()
        server.server_close()
        path.unlink(missing_ok=True)
