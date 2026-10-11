"""Validated operations shared by the GUI, CLI and MCP interface."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

UNIT_RE = re.compile(r"^[A-Za-z0-9_.:@\\-]+\.(?:service|timer)$")
MODULE_RE = re.compile(r"^[a-z][a-z0-9-]{0,47}$")
PROTECTED = {
    "system": {
        "NetworkManager.service",
        "dbus-broker.service",
        "dbus.service",
        "polkit.service",
        "freiren-quiet.service",
        "sddm.service",
        "sshd.service",
        "syncthing@.service",
        "systemd-logind.service",
        "tailscaled.service",
    },
    "user": {"frieren-os-controller.service", "plasma-polkit-agent.service"},
}
BUILTIN_MODULES = {
    "failed-services": {"label": "실패한 서비스", "kind": "failed"},
    "freiren-quiet": {"label": "전원과 온도", "kind": "quiet"},
    "disk-space": {"label": "저장 공간", "kind": "disk", "path": "/"},
    "journal-space": {"label": "시스템 로그", "kind": "journal"},
    "package-cache": {"label": "패키지 캐시", "kind": "package-cache"},
    "orphan-packages": {"label": "고아 패키지", "kind": "orphan-packages"},
    "pcie-errors": {"label": "PCIe 오류", "kind": "pcie-errors"},
    "graphics": {"label": "그래픽 장치", "kind": "graphics"},
}


class ControllerError(Exception):
    """A safe error suitable for local clients."""


def validate_scope(scope: str) -> str:
    if scope not in ("system", "user"):
        raise ControllerError("범위는 system 또는 user여야 해요.")
    return scope


def validate_unit(unit: str) -> str:
    if not isinstance(unit, str) or not UNIT_RE.fullmatch(unit) or len(unit) > 255:
        raise ControllerError("서비스 또는 타이머 이름이 올바르지 않아요.")
    return unit


def validate_module(name: str) -> str:
    if not isinstance(name, str) or not MODULE_RE.fullmatch(name):
        raise ControllerError("모듈 이름은 소문자·숫자·하이픈만 사용할 수 있어요.")
    return name


def protected(scope: str, unit: str) -> bool:
    return (
        unit in PROTECTED[scope]
        or unit.startswith("systemd-")
        or unit.startswith("user@")
        or unit.startswith("frieren-os-controller@")
    )


class Controller:
    def __init__(self, state_dir: Path | None = None, runner=None, quiet=None, monitor=None):
        self.state_dir = Path(state_dir or Path.home() / ".local/state/frieren-os-controller")
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_dir.chmod(0o700)
        self.modules_dir = self.state_dir / "modules"
        self.modules_dir.mkdir(mode=0o700, exist_ok=True)
        self.runner = runner or subprocess.run
        if quiet is None:
            from .quiet import QuietPlugin

            quiet = QuietPlugin()
        self.quiet = quiet
        self.quiet_monitor = None
        self.monitor = monitor
        self.external_monitor = None
        self.appearance = None
        self.extensions = None
        self.request_context = threading.local()
        self.lock = threading.RLock()
        self._unit_cache: dict[str, tuple[float, list[dict], dict[str, dict]]] = {}

    def _run(
        self, args: list[str], timeout: int = 15, allow_failure=False, env=None
    ) -> subprocess.CompletedProcess:
        try:
            options = {"env": env} if env is not None else {}
            result = self.runner(
                args, text=True, capture_output=True, timeout=timeout, check=False, **options
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ControllerError(f"명령을 실행하지 못했어요: {type(exc).__name__}") from exc
        if result.returncode and not allow_failure:
            message = (result.stderr or result.stdout or "명령이 실패했어요.").strip()
            raise ControllerError(message[:600])
        return result

    def _systemctl(self, scope: str, *args: str, timeout=15, allow_failure=False):
        validate_scope(scope)
        command = ["/usr/bin/systemctl"]
        if scope == "user":
            command.append("--user")
        command.extend(args)
        return self._run(command, timeout=timeout, allow_failure=allow_failure)

    def _json_command(self, scope: str, *args: str) -> list[dict]:
        output = self._systemctl(scope, *args, "--no-pager", "--output=json").stdout
        try:
            value = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ControllerError("systemd 목록을 읽지 못했어요.") from exc
        if not isinstance(value, list):
            raise ControllerError("systemd 목록 형식이 올바르지 않아요.")
        return value

    def job_unit_read(self, unit: str) -> dict:
        from .jobs import JobEditor

        return JobEditor(self).unit_read(unit)

    def job_unit_save(self, unit: str, content: str, revision: str) -> dict:
        from .jobs import JobEditor

        return JobEditor(self).unit_save(unit, content, revision)

    def job_cron_read(self) -> dict:
        from .jobs import JobEditor

        return JobEditor(self).cron_read()

    def job_cron_save(self, content: str, revision: str) -> dict:
        from .jobs import JobEditor

        return JobEditor(self).cron_save(content, revision)

    def list_units(self, scope: str = "system", kind: str = "all", search: str = "") -> list[dict]:
        validate_scope(scope)
        if kind not in ("all", "service", "timer"):
            raise ControllerError("종류는 all, service 또는 timer여야 해요.")
        if not isinstance(search, str) or len(search) > 120:
            raise ControllerError("검색어가 너무 길어요.")
        with self.lock:
            cached = self._unit_cache.get(scope)
            if cached and time.monotonic() - cached[0] < 10:
                _, files, active_by_name = cached
            else:
                files = self._json_command(scope, "list-unit-files", "--type=service", "--type=timer")
                active = self._json_command(scope, "list-units", "--all", "--type=service", "--type=timer")
                active_by_name = {row.get("unit"): row for row in active}
                self._unit_cache[scope] = (time.monotonic(), files, active_by_name)
        query = search.casefold()
        rows = []
        for row in files:
            name = row.get("unit_file")
            if not isinstance(name, str) or not UNIT_RE.fullmatch(name):
                continue
            if kind != "all" and not name.endswith("." + kind):
                continue
            live = active_by_name.get(name, {})
            description = live.get("description") or ""
            if query and query not in (name + " " + description).casefold():
                continue
            state = row.get("state") or "unknown"
            rows.append(
                {
                    "unit": name,
                    "scope": scope,
                    "kind": name.rsplit(".", 1)[1],
                    "description": description,
                    "file_state": state,
                    "enabled": state in ("enabled", "enabled-runtime"),
                    "active": live.get("active", "inactive"),
                    "sub": live.get("sub", "dead"),
                    "protected": protected(scope, name),
                }
            )
        return sorted(rows, key=lambda item: (item["kind"], item["unit"].casefold()))

    def describe_unit(self, scope: str, unit: str) -> dict:
        validate_scope(scope)
        validate_unit(unit)
        result = self._systemctl(
            scope,
            "show",
            "--property=Id,Description,LoadState,ActiveState,SubState,UnitFileState,FragmentPath",
            "--",
            unit,
            allow_failure=True,
        )
        if result.returncode:
            raise ControllerError("유닛을 찾지 못했어요.")
        info = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if info.get("LoadState") in (None, "not-found"):
            raise ControllerError("유닛을 찾지 못했어요.")
        return {
            "unit": unit,
            "scope": scope,
            "description": info.get("Description", ""),
            "load": info.get("LoadState", ""),
            "active": info.get("ActiveState", ""),
            "sub": info.get("SubState", ""),
            "file_state": info.get("UnitFileState", ""),
            "fragment": info.get("FragmentPath", ""),
            "protected": protected(scope, unit),
            "note": self.get_note(scope, unit),
        }

    def preview_toggle(self, scope: str, unit: str, enabled: bool) -> dict:
        if type(enabled) is not bool:
            raise ControllerError("enabled 값은 true 또는 false여야 해요.")
        info = self.describe_unit(scope, unit)
        if info["protected"]:
            raise ControllerError("연결이나 로그인에 중요한 서비스는 이 앱에서 변경하지 않아요.")
        if info["file_state"] not in ("enabled", "enabled-runtime", "disabled"):
            raise ControllerError("이 유닛은 켜고 끌 수 있는 설치 상태가 아니에요.")
        action = "enable --now" if enabled else "disable --now"
        return {
            "unit": unit,
            "scope": scope,
            "action": action,
            "before": info,
            "after_enabled": enabled,
        }

    def toggle_unit(self, scope: str, unit: str, enabled: bool) -> dict:
        with self.lock:
            preview = self.preview_toggle(scope, unit, enabled)
            before = preview["before"]
            was_enabled = before["file_state"] in ("enabled", "enabled-runtime")
            was_active = before["active"] == "active"
            operation = "enable" if enabled else "disable"
            try:
                self._systemctl(scope, operation, "--now", "--", unit, timeout=120)
            except ControllerError:
                # enable --now may enable the unit even when its start fails.
                if enabled and not was_enabled:
                    self._systemctl(scope, "disable", "--now", "--", unit, timeout=120, allow_failure=True)
                elif not enabled and was_active:
                    self._systemctl(scope, "start", "--", unit, timeout=120, allow_failure=True)
                raise
            after = self.describe_unit(scope, unit)
            if (after["file_state"] in ("enabled", "enabled-runtime")) != enabled:
                raise ControllerError("설정 변경 결과를 확인하지 못했어요. systemctl 상태를 확인해 주세요.")
            self._unit_cache.pop(scope, None)
            self._audit(
                "toggle_unit", scope=scope, unit=unit, before=before["file_state"], after=after["file_state"]
            )
            return {"before": before, "after": after}

    def _atomic_json(self, path: Path, value: object) -> None:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.chmod(0o600)
        os.replace(temporary, path)

    def _notes(self) -> dict:
        path = self.state_dir / "notes.json"
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except (OSError, json.JSONDecodeError):
            pass
        raise ControllerError("메모 저장 파일을 읽지 못했어요.")

    def get_note(self, scope: str, unit: str) -> str:
        validate_scope(scope)
        validate_unit(unit)
        return self._notes().get(f"{scope}:{unit}", "")

    def set_note(self, scope: str, unit: str, note: str) -> dict:
        validate_scope(scope)
        validate_unit(unit)
        if not isinstance(note, str) or len(note) > 4000 or "\x00" in note:
            raise ControllerError("메모는 4,000자 이하의 텍스트여야 해요.")
        with self.lock:
            notes = self._notes()
            key = f"{scope}:{unit}"
            if note:
                notes[key] = note
            else:
                notes.pop(key, None)
            self._atomic_json(self.state_dir / "notes.json", notes)
            self._audit("set_note", scope=scope, unit=unit, length=len(note))
        return {"scope": scope, "unit": unit, "note": note}

    def journal_tail(self, scope: str, unit: str, lines: int = 30) -> dict:
        validate_scope(scope)
        validate_unit(unit)
        if type(lines) is not int or not 1 <= lines <= 100:
            raise ControllerError("로그 줄 수는 1~100이어야 해요.")
        command = ["/usr/bin/journalctl"]
        if scope == "user":
            command.append("--user")
        command.extend(("--no-pager", "--output=short-iso", "--unit", unit, "-n", str(lines)))
        return {"scope": scope, "unit": unit, "text": self._run(command).stdout[-20000:]}

    def audit_log(self, limit: int = 50) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ControllerError("기록 건수는 1~200이어야 해요.")
        path = self.state_dir / "audit.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[-limit:]]

    def _audit(self, action: str, **details) -> None:
        event = {
            "at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "actor": getattr(self.request_context, "source", "local"),
            **details,
        }
        descriptor = os.open(self.state_dir / "audit.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _validated_definition(self, definition: dict) -> dict:
        if not isinstance(definition, dict):
            raise ControllerError("모듈 정의는 객체여야 해요.")
        kind = definition.get("kind")
        if kind == "unit" and set(definition) == {"label", "kind", "scope", "unit"}:
            validate_scope(definition["scope"])
            validate_unit(definition["unit"])
        elif kind == "disk" and set(definition) == {"label", "kind", "path"}:
            if definition["path"] not in ("/", "/home"):
                raise ControllerError("디스크 모듈은 / 또는 /home만 조회해요.")
        else:
            raise ControllerError("지원하는 모듈은 unit 또는 disk예요.")
        label = definition["label"]
        if not isinstance(label, str) or not 1 <= len(label) <= 60 or "\x00" in label:
            raise ControllerError("모듈 제목이 올바르지 않아요.")
        return definition

    def list_modules(self) -> list[dict]:
        result = []
        for name, definition in BUILTIN_MODULES.items():
            result.append({"name": name, "builtin": True, "definition": definition})
        for file in sorted(self.modules_dir.glob("*.json")):
            try:
                definition = self._validated_definition(json.loads(file.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, ControllerError):
                continue
            result.append({"name": file.stem, "builtin": False, "definition": definition})
        return result

    def read_module(self, name: str) -> dict:
        validate_module(name)
        for item in self.list_modules():
            if item["name"] == name:
                return item
        raise ControllerError("모듈을 찾지 못했어요.")

    def write_module(self, name: str, definition: dict) -> dict:
        validate_module(name)
        if name in BUILTIN_MODULES:
            raise ControllerError("기본 모듈 이름은 바꿀 수 없어요.")
        valid = self._validated_definition(definition)
        with self.lock:
            self._atomic_json(self.modules_dir / f"{name}.json", valid)
            self._audit("write_module", module=name, kind=valid["kind"])
        return self.read_module(name)

    def run_check(self, name: str) -> dict:
        module = self.read_module(name)
        definition = module["definition"]
        kind = definition["kind"]
        if kind == "quiet":
            info = self.quiet.status()
            temperature = info.get("cpu_c")
            temperature_text = (
                f"{temperature:.0f}°C" if isinstance(temperature, (int, float)) else "온도 없음"
            )
            value = f"{info.get('mode_label', info['mode'])} · CPU {temperature_text}"
            maximum = (info.get("limits") or {}).get("max_perf_pct")
            if isinstance(maximum, int):
                value += f" · 상한 {maximum}%"
        elif kind == "unit":
            info = self.describe_unit(definition["scope"], definition["unit"])
            active_label = "실행 중" if info["active"] == "active" else "중지"
            enabled_label = (
                "시작 켜짐" if info["file_state"] in ("enabled", "enabled-runtime") else "시작 꺼짐"
            )
            value = f"{active_label} · {enabled_label}"
        elif kind == "disk":
            total, used, free = shutil.disk_usage(definition["path"])
            info = {"total": total, "used": used, "free": free, "path": definition["path"]}
            value = f"여유 {free / (1024**3):.1f} GiB"
        elif kind == "failed":
            rows = self._json_command("system", "list-units", "--failed", "--type=service")
            info = {"units": [row.get("unit") for row in rows]}
            value = f"실패 {len(rows)}개"
        elif kind == "journal":
            result = self._run(["/usr/bin/journalctl", "--disk-usage"])
            info = {"text": result.stdout.strip()}
            size = re.search(r"\b[\d.]+[KMGTPE]?\b", result.stdout)
            value = f"로그 {size.group(0)}" if size else "용량 확인 완료"
        elif kind == "package-cache":
            path = Path("/var/cache/pacman/pkg")
            if not path.is_dir():
                raise ControllerError("패키지 캐시 폴더를 찾지 못했어요.")
            size = sum(item.stat().st_size for item in path.iterdir() if item.is_file())
            info = {"path": str(path), "bytes": size}
            value = f"캐시 {size / (1024**3):.1f} GiB"
        elif kind == "orphan-packages":
            result = self._run(["/usr/bin/pacman", "-Qdtq"], allow_failure=True)
            names = [line for line in result.stdout.splitlines() if line]
            info = {"packages": names}
            value = f"고아 {len(names)}개"
        elif kind == "pcie-errors":
            result = self._run(
                [
                    "/usr/bin/journalctl",
                    "--boot",
                    "--dmesg",
                    "--grep=PCIe Bus Error",
                    "--lines=1",
                    "--no-pager",
                    "--quiet",
                ],
                allow_failure=True,
            )
            last_error = result.stdout.strip()
            info = {"last_error": last_error[-1000:]}
            value = "이번 부팅 기록 있음" if last_error else "이번 부팅 기록 없음"
        elif kind == "graphics":
            result = self._run(["/usr/bin/lspci", "-nn"])
            rows = [
                line
                for line in result.stdout.splitlines()
                if any(
                    marker in line
                    for marker in ("VGA compatible controller", "3D controller", "Display controller")
                )
            ]
            info = {"devices": rows}
            names = [vendor for vendor in ("Intel", "NVIDIA", "AMD") if any(vendor in row for row in rows)]
            value = " + ".join(names) if names else f"장치 {len(rows)}개"
        else:
            raise ControllerError("지원하지 않는 모듈이에요.")
        return {"name": name, "label": definition["label"], "kind": kind, "value": value, "details": info}

    def quiet_status(self) -> dict:
        with self.lock:
            status = self.quiet.status()
            if self.quiet_monitor is None:
                from .quiet import QuietMonitor

                self.quiet_monitor = QuietMonitor()
            status["usage"] = self.quiet_monitor.sample()
            status["effects_saving"] = self.quiet.effects_enabled()
            return status

    def quiet_set_mode(self, mode: str) -> dict:
        with self.lock:
            self.quiet.set_mode(mode)
            self._audit("quiet_set_mode", mode=mode)
            return self.quiet_status()

    def quiet_set_target(self, temperature: int) -> dict:
        with self.lock:
            self.quiet.set_target(temperature)
            self._audit("quiet_set_target", temperature=temperature)
            return self.quiet_status()

    def quiet_set_effects(self, enabled: bool) -> dict:
        with self.lock:
            self.quiet.set_effects(enabled)
            self._audit("quiet_set_effects", enabled=enabled)
            return self.quiet_status()

    def quiet_configure(self, settings: dict) -> dict:
        with self.lock:
            self.quiet.configure(settings)
            self._audit("quiet_configure", settings=settings)
            return self.quiet_status()

    def quiet_reset(self) -> dict:
        with self.lock:
            self.quiet.reset()
            self._audit("quiet_reset")
            return self.quiet_status()

    def _monitor(self):
        with self.lock:
            if self.monitor is None:
                from .monitor import Monitor

                self.monitor = Monitor(self.state_dir)
                self.monitor.start()
            return self.monitor

    def _external_monitor(self):
        with self.lock:
            if self.external_monitor is None:
                from .external_monitor import ExternalControls

                self.external_monitor = ExternalControls(self.state_dir, self._monitor().backend.command)
            return self.external_monitor

    def monitor_external_status(self) -> dict:
        return self._external_monitor().status()

    def monitor_external_set(self, identifier: str, feature: str, value: int) -> dict:
        result = self._external_monitor().set(identifier, feature, value)
        self._audit("monitor_external_set", identifier=identifier, feature=feature, value=value)
        return result

    def monitor_external_reset(self, identifier: str) -> dict:
        result = self._external_monitor().reset(identifier)
        self._audit("monitor_external_reset", identifier=identifier)
        return result

    def monitor_status(self) -> dict:
        return self._monitor().status()

    def monitor_configure(self, settings: dict) -> dict:
        result = self._monitor().configure(settings)
        self._audit("monitor_configure", settings=settings)
        return result

    def monitor_preset(self, name: str) -> dict:
        result = self._monitor().preset(name)
        self._audit("monitor_preset", name=name)
        return result

    def monitor_reset(self) -> dict:
        result = self._monitor().reset()
        self._audit("monitor_reset")
        return result

    def monitor_keep_awake(self, minutes: int) -> dict:
        result = self._monitor().keep_awake(minutes)
        self._audit("monitor_keep_awake", minutes=minutes)
        return result

    def monitor_original_color(self, minutes: int) -> dict:
        return self._monitor().original_color(minutes)

    def monitor_preview_layout(self, layout: list[dict]) -> dict:
        result = self._monitor().preview_layout(layout)
        self._audit("monitor_preview_layout", layout=layout)
        return result

    def monitor_confirm_layout(self, token: str, keep: bool) -> dict:
        result = self._monitor().confirm_layout(token, keep)
        self._audit("monitor_confirm_layout", keep=keep)
        return result

    def _appearance(self):
        with self.lock:
            if self.appearance is None:
                from .appearance import Appearance

                self.appearance = Appearance(self.state_dir)
            return self.appearance

    def _appearance_call(self, operation, *args):
        try:
            return getattr(self._appearance(), operation)(*args)
        except OSError as exc:
            raise ControllerError(
                "배경 설정 파일을 읽거나 저장하지 못했어요. 저장 공간과 권한을 확인해 주세요."
            ) from exc

    def appearance_status(self) -> dict:
        return self._appearance_call("status")

    def wallpaper_set(self, image: str, desktop_id: int | None = None, fill: str = "crop") -> dict:
        result = self._appearance_call("wallpaper_set", image, desktop_id, fill)
        self._audit("wallpaper_set", desktop_id=desktop_id, fill=fill)
        return result

    def wallpaper_reset(self, desktop_id: int | None = None) -> dict:
        result = self._appearance_call("wallpaper_reset", desktop_id)
        self._audit("wallpaper_reset", desktop_id=desktop_id)
        return result

    def terminal_configure(self, settings: dict) -> dict:
        result = self._appearance_call("terminal_configure", settings)
        self._audit("terminal_configure")
        return result

    def terminal_open(self) -> dict:
        return self._appearance_call("terminal_open")

    def terminal_reset(self) -> dict:
        result = self._appearance_call("terminal_reset")
        self._audit("terminal_reset")
        return result

    def _extensions(self):
        with self.lock:
            if self.extensions is None:
                from .desktop_extensions import DesktopExtensions

                self.extensions = DesktopExtensions(self)
        self.extensions.start()
        return self.extensions

    def _source(self):
        return getattr(self.request_context, "source", "local")

    def workspace_status(self, area: str) -> dict:
        return self._extensions().status(area)

    def workspace_configure(self, area: str, settings: dict) -> dict:
        return self._extensions().configure(area, settings, self._source())

    def work_mode_status(self) -> dict:
        return self._extensions().modes()

    def work_mode_save(self, name: str, settings: dict) -> dict:
        return self._extensions().save_mode(name, settings)

    def work_mode_apply(self, name: str) -> dict:
        return self._extensions().apply_mode(name, self._source())

    def work_mode_end(self) -> dict:
        return self._extensions().end_mode(self._source())

    def workspace_presets(self, area: str) -> dict:
        return self._extensions().presets(area)

    def workspace_save_preset(self, area: str, name: str, settings: dict) -> dict:
        return self._extensions().save_preset(area, name, settings)

    def workspace_apply_preset(self, area: str, name: str) -> dict:
        return self._extensions().apply_preset(area, name, self._source())

    def settings_history(self, limit: int = 50) -> list[dict]:
        return self._extensions().history(limit)

    def settings_revert(self, identifier: str) -> dict:
        return self._extensions().revert(identifier, self._source())

    def settings_recover(self) -> dict:
        return self._extensions().recover()

    def himmel_open(self) -> dict:
        return self._extensions().backend("network").open_himmel()

    def widget_status(self) -> dict:
        quiet = self.quiet.status()
        monitor = self._monitor()
        return {
            "temperature": quiet.get("cpu_c"),
            "brightness": monitor.backend.brightness()["percent"],
            "power_mode": quiet["mode_label"],
            "active_mode": self.work_mode_status()["active"],
            "modes": [{"id": r["id"], "title": r["title"]} for r in self.work_mode_status()["modes"]],
        }

    def widget_brightness(self, value: int) -> dict:
        self.workspace_configure("display", {"brightness": value})
        return self.widget_status()

    def dashboard(self) -> list[dict]:
        cards = []
        for item in self.list_modules():
            try:
                cards.append(self.run_check(item["name"]))
            except ControllerError as exc:
                cards.append({"name": item["name"], "label": item["definition"]["label"], "error": str(exc)})
        return cards
