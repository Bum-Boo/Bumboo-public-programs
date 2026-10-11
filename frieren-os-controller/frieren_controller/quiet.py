"""Fixed-protocol adapter for the installed Freiren Quiet service."""

from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import time
from pathlib import Path

import psutil

from .core import ControllerError

QUIET_SOCKET = Path("/run/freiren-quiet/control.sock")
MODES = ("auto", "quiet", "balanced", "performance", "restore", "custom")


class QuietPlugin:
    def __init__(self, path: Path = QUIET_SOCKET, runner=None, effects_path: Path | None = None):
        self.path = path
        self.runner = runner or subprocess.run
        self.effects_path = effects_path or (
            Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
            / "freiren-quiet/effects.json"
        )

    def _request(self, request: dict) -> dict:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(8)
                connection.connect(str(self.path))
                connection.sendall((json.dumps(request) + "\n").encode())
                with connection.makefile("rb") as incoming:
                    line = incoming.readline(65537)
        except (OSError, TimeoutError) as exc:
            raise ControllerError("Freiren Quiet 서비스에 연결하지 못했어요.") from exc
        if not line or len(line) > 65536 or not line.endswith(b"\n"):
            raise ControllerError("Freiren Quiet 응답이 올바르지 않아요.")
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ControllerError("Freiren Quiet 응답을 읽지 못했어요.") from exc
        if not isinstance(response, dict):
            raise ControllerError("Freiren Quiet 응답이 올바르지 않아요.")
        if response.get("ok") is not True:
            error = response.get("error")
            raise ControllerError(str(error)[:600] if error else "Freiren Quiet 요청이 실패했어요.")
        status = response.get("status")
        if not isinstance(status, dict) or status.get("mode") not in MODES:
            raise ControllerError("Freiren Quiet 상태를 읽지 못했어요.")
        return status

    def status(self) -> dict:
        return self._request({"op": "status"})

    def set_mode(self, mode: str) -> dict:
        if not isinstance(mode, str) or mode not in MODES:
            raise ControllerError("지원하지 않는 전원 모드예요.")
        return self._request({"op": "mode", "mode": mode})

    def set_target(self, temperature: int) -> dict:
        if type(temperature) is not int or not 58 <= temperature <= 75:
            raise ControllerError("목표 온도는 58~75°C의 정수여야 해요.")
        return self._request({"op": "target", "target": temperature})

    def configure(self, settings: dict) -> dict:
        if not isinstance(settings, dict) or set(settings) != {
            "cap",
            "turbo",
            "preference",
            "power_w",
            "boost_w",
        }:
            raise ControllerError("사용자 지정 설정 항목이 올바르지 않아요.")
        if type(settings["cap"]) is not int or not 25 <= settings["cap"] <= 100:
            raise ControllerError("CPU 상한은 25~100%여야 해요.")
        if type(settings["turbo"]) is not bool or settings["preference"] not in (
            "power",
            "balance_power",
            "balance_performance",
            "performance",
        ):
            raise ControllerError("터보 또는 절전 성향 값이 올바르지 않아요.")
        long, short = settings["power_w"], settings["boost_w"]
        if long is not None or short is not None:
            for value, maximum in ((long, 45), (short, 56.25)):
                if type(value) not in (int, float) or not math.isfinite(value) or not 10 <= value <= maximum:
                    raise ControllerError("전력 한도가 허용 범위를 벗어났어요.")
                if value * 4 != round(value * 4):
                    raise ControllerError("전력 한도는 0.25W 단위여야 해요.")
            if long > short:
                raise ControllerError("순간 전력 한도는 지속 한도 이상이어야 해요.")
        return self._request({"op": "configure", "settings": settings})

    def reset(self) -> dict:
        if self.status().get("protocol_version", 1) < 2:
            return self.set_mode("restore")
        return self._request({"op": "reset"})

    def effects_enabled(self) -> bool:
        return self.effects_path.exists()

    def set_effects(self, enabled: bool) -> bool:
        if type(enabled) is not bool:
            raise ControllerError("화면 효과 설정은 true 또는 false여야 해요.")
        if self.effects_enabled() == enabled:
            return enabled
        operation = "save" if enabled else "restore"
        try:
            result = self.runner(
                ["/usr/bin/freiren-quiet", "effects", operation],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ControllerError("화면 효과를 변경하지 못했어요.") from exc
        if result.returncode:
            raise ControllerError((result.stderr or result.stdout or "화면 효과 변경 실패").strip()[:600])
        if self.effects_enabled() != enabled:
            raise ControllerError("화면 효과 변경 결과를 확인하지 못했어요.")
        return enabled


class QuietMonitor:
    """Read interval CPU load without exposing process command lines."""

    def __init__(self):
        self.cpu_times = psutil.cpu_times()
        self.sampled_at = time.monotonic()
        self.latest = {"cpu_percent": None, "logical_cpus": psutil.cpu_count() or 1, "top_processes": []}
        self.known: set[tuple[int, float]] = set()
        self._processes()

    def _processes(self) -> list[dict]:
        cores = psutil.cpu_count() or 1
        current: set[tuple[int, float]] = set()
        processes = []
        for process in psutil.process_iter(["name", "create_time"]):
            try:
                identity = (process.pid, process.info["create_time"])
                current.add(identity)
                percent = process.cpu_percent(interval=None) / cores
                if identity in self.known and percent >= 0.1:
                    processes.append(
                        {"pid": process.pid, "name": process.info["name"], "cpu_percent": round(percent, 1)}
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        self.known = current
        processes.sort(key=lambda item: item["cpu_percent"], reverse=True)
        return processes[:6]

    def sample(self) -> dict:
        now = time.monotonic()
        if now - self.sampled_at < 1:
            return self.latest
        current = psutil.cpu_times()
        delta = {
            key: max(0, value - getattr(self.cpu_times, key)) for key, value in current._asdict().items()
        }
        total = sum(value for key, value in delta.items() if key not in ("guest", "guest_nice"))
        idle = delta.get("idle", 0) + delta.get("iowait", 0)
        usage = min(100, max(0, 100 * (total - idle) / total)) if total else 0
        self.cpu_times = current
        self.sampled_at = now
        self.latest = {
            "cpu_percent": round(usage, 1),
            "logical_cpus": psutil.cpu_count() or 1,
            "top_processes": self._processes(),
        }
        return self.latest
