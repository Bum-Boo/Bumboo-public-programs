"""A root-owned service with a small, UID-checked Unix socket protocol."""

import copy
import json
import logging
import os
import signal
import socket
import struct
import time
from pathlib import Path

from .hardware import Hardware, atomic_json
from .policy import MODE_LABELS, ThermalPolicy
from .power import PowerProfiles

SOCKET = "/run/freiren-quiet/control.sock"
STATE = Path("/var/lib/freiren-quiet")
LOG = logging.getLogger("freiren-quiet")


class ProfileRestoreError(RuntimeError):
    """CPU rollback succeeded, but the external power profile could not be restored."""


class Controller:
    def __init__(self, hardware, power, state: Path = STATE):
        self.hardware, self.power, self.state = hardware, power, state
        hardware.validate()
        self.baseline = json.loads((state / "baseline.json").read_text())
        if self.baseline["identity"] != hardware.identity():
            raise RuntimeError("저장된 복원 지점이 현재 하드웨어와 일치하지 않습니다.")
        settings = {"mode": "auto", "target": 64}
        if (state / "settings.json").exists():
            settings.update(json.loads((state / "settings.json").read_text()))
        self.policy = ThermalPolicy(settings["mode"], settings["target"])
        self.effective_profile = None
        self.reason = "자동 관리 해제 상태" if self.policy.mode == "restore" else "시작 중"
        self.error = None
        self.sampled_at = None
        self.readings = {"cpu_c": None, "sensors": {}}
        self.tick()

    def persist(self):
        atomic_json(
            self.state / "settings.json",
            {
                "mode": self.policy.mode,
                "target": self.policy.target,
            },
        )

    def restore(self, keep_power_profile=False):
        # Always attempt CPU rollback even if the external D-Bus service is unavailable.
        error = None
        try:
            if not keep_power_profile:
                self.power.set(self.baseline.get("power_profile") or "balanced")
        except Exception as failure:
            error = failure
        if keep_power_profile:
            self.hardware._restore_limits(self.baseline["limits"])
        else:
            self.hardware.restore(self.baseline)
        if error:
            raise ProfileRestoreError(f"CPU 설정 복원 완료, 전력 프로필 복원 실패: {error}")

    def tick(self):
        self.readings = self.hardware.temperatures()
        self.sampled_at = time.time()
        if self.policy.mode == "restore":
            return
        try:
            active = self.power.current()
            # A manual KDE/CLI profile change takes priority. Do not fight PowerDevil.
            if (
                self.effective_profile is not None
                and active != self.effective_profile
                and not self.error
            ):
                self.restore(keep_power_profile=True)
                self.policy.set_mode("restore")
                self.reason = "KDE/외부 전력 모드 변경 감지 · 자동 관리 해제"
                self.effective_profile = active
                self.persist()
                return
            decision = self.policy.decide(self.readings["cpu_c"])
            self.effective_profile = self.power.set(decision.profile)
            self.hardware.apply(decision.cap, decision.no_turbo)
            self.reason = decision.reason
            if self.effective_profile != decision.profile:
                self.reason += f" · 전력 프로필 {self.effective_profile} 사용"
            self.error = None
        except Exception as failure:
            self.error = str(failure)
            LOG.error("Control failed: %s", failure)
            try:
                self.hardware.apply(40, 1)
                self.reason = "전력 제어 오류 · 임시 속도 상한 40%"
            except Exception as fallback_failure:
                self.error += f"; 임시 제한도 실패: {fallback_failure}"

    def change_mode(self, mode):
        if not isinstance(mode, str) or mode not in MODE_LABELS:
            raise ValueError("지원하지 않는 모드입니다.")
        if mode == "restore":
            # Handing control back must still work when PPD is unavailable.
            warning = None
            try:
                self.restore()
            except ProfileRestoreError as error:
                warning = str(error)
            self.policy.set_mode("restore")
            self.effective_profile = None
            self.reason = "설치 전 CPU 설정 복원 · 자동 관리 해제"
            self.error = warning
            self.persist()
            return
        previous_policy = copy.deepcopy(self.policy)
        previous_snapshot = self.hardware.snapshot()
        previous_profile = self.power.current()
        previous_effective = self.effective_profile
        try:
            self.policy.set_mode(mode)
            self.effective_profile = None
            self.error = None
            self.tick()
            if self.error:
                raise RuntimeError(self.error)
            self.persist()
        except Exception as failure:
            self.policy = previous_policy
            self.effective_profile = previous_effective
            # Do not let a PPD failure prevent restoring the CPU controls.
            try:
                self.power.set(previous_profile)
            finally:
                self.hardware.restore(previous_snapshot)
            self.error = str(failure)
            raise

    def status(self):
        snapshot = self.hardware.snapshot()
        profile_error = None
        try:
            power_profile = self.power.current()
        except Exception as failure:
            power_profile = None
            profile_error = str(failure)
        return {
            "mode": self.policy.mode,
            "mode_label": MODE_LABELS[self.policy.mode],
            "target_c": self.policy.target,
            "reason": self.reason,
            "error": self.error or profile_error,
            "cpu_c": self.readings["cpu_c"],
            "sensors": self.readings["sensors"],
            "sampled_at": self.sampled_at,
            "limits": snapshot["limits"],
            "epp": snapshot["epp"],
            "device": snapshot["identity"],
            "power_profile": power_profile,
            "nvidia": self.hardware.gpu_state(),
            "fan_control": False,
            "interval_seconds": 5,
        }

    def request(self, data):
        if not isinstance(data, dict):
            raise ValueError("JSON 객체가 필요합니다.")
        operation = data.get("op")
        expected_keys = {
            "status": {"op"},
            "mode": {"op", "mode"},
            "target": {"op", "target"},
        }
        if not isinstance(operation, str) or operation not in expected_keys:
            raise ValueError("지원하지 않는 요청입니다.")
        if set(data) != expected_keys[operation]:
            raise ValueError("잘못된 요청 항목입니다.")
        if operation == "mode":
            self.change_mode(data["mode"])
        elif operation == "target":
            previous = self.policy.target
            self.policy.set_target(data["target"])
            try:
                self.persist()
            except Exception:
                self.policy.set_target(previous)
                raise
        return self.status()


def peer_allowed(connection, allowed_uid):
    credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    _, uid, _ = struct.unpack("3i", credentials)
    return uid in (0, allowed_uid)


def serve(config: Path = Path("/etc/freiren-quiet/config.json")):
    if os.geteuid() != 0:
        raise RuntimeError("서비스는 systemd에서 실행해야 합니다.")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = json.loads(config.read_text())
    controller = Controller(Hardware(), PowerProfiles())
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    endpoint = Path(SOCKET)
    endpoint.unlink(missing_ok=True)
    server.bind(SOCKET)
    os.chown(SOCKET, 0, settings["allowed_gid"])
    os.chmod(SOCKET, 0o660)
    server.listen(8)
    server.settimeout(0.5)
    deadline = time.monotonic() + 5
    LOG.info("Controller ready for UID %s", settings["allowed_uid"])
    try:
        while running:
            if time.monotonic() >= deadline:
                controller.tick()
                deadline = time.monotonic() + 5
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            with connection:
                connection.settimeout(1)
                try:
                    if not peer_allowed(connection, settings["allowed_uid"]):
                        raise PermissionError("이 사용자는 장치 제어 권한이 없습니다.")
                    payload = bytearray()
                    while b"\n" not in payload and len(payload) <= 4096:
                        chunk = connection.recv(4097 - len(payload))
                        if not chunk:
                            break
                        payload.extend(chunk)
                    if len(payload) > 4096 or not payload.endswith(b"\n"):
                        raise ValueError("요청 크기 또는 형식 오류")
                    response = {"ok": True, "status": controller.request(json.loads(payload))}
                except Exception as error:
                    response = {"ok": False, "error": str(error)}
                try:
                    connection.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode())
                except (OSError, TimeoutError):
                    pass
    finally:
        server.close()
        endpoint.unlink(missing_ok=True)
        if controller.policy.mode != "restore":
            controller.restore()
            LOG.info("Original CPU settings restored on service stop")
