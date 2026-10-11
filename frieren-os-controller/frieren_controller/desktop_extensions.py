"""Durable desktop transactions, reusable work modes and conflict-aware history."""

from __future__ import annotations

import copy
import json
import threading
import uuid
from datetime import datetime, timezone

from .appearance import atomic
from .core import ControllerError
from .desktop_common import choice, integer, wait_for

AREAS = {
    "panels": "패널과 위젯",
    "style": "OS 스타일",
    "windows": "창과 작업공간",
    "audio": "소리와 마이크",
    "input": "키보드와 마우스",
    "network": "연결과 원격",
    "session": "세션과 알림",
    "power": "전원",
    "display": "화면",
}
ACTORS = {"gui": "나 · GUI", "cli": "CLI", "mcp": "에이전트 · MCP", "widget": "나 · 위젯", "local": "로컬"}
BUILTIN_MODES = {
    "research": {
        "title": "연구",
        "settings": {
            "power": {"mode": "quiet"},
            "display": {"brightness": 75, "night_enabled": False, "auto_brightness": False},
            "session": {"notifications_muted": True},
            "audio": {"input_muted": True},
        },
    },
    "presentation": {
        "title": "발표",
        "settings": {
            "power": {"mode": "balanced"},
            "display": {"brightness": 100, "night_enabled": False, "auto_brightness": False},
            "session": {"notifications_muted": True, "keep_awake": 60},
            "audio": {"input_muted": True},
        },
    },
    "away": {
        "title": "외출",
        "settings": {
            "power": {"mode": "quiet"},
            "display": {"brightness": 45, "night_enabled": False, "auto_brightness": False},
            "session": {"notifications_muted": False, "screen_timeout": 180},
        },
    },
}


class DesktopExtensions:
    def __init__(self, controller, backends=None):
        self.controller = controller
        self.path = controller.state_dir / "desktop-extensions.json"
        self.lock = threading.RLock()
        self.backends = dict(backends or {})
        self.state = {
            "schema": 1,
            "modes": {},
            "presets": {},
            "history": [],
            "pending": None,
            "active_mode": None,
            "preferences": {},
        }
        if self.path.exists():
            try:
                value = json.loads(self.path.read_text())
                if not isinstance(value, dict) or value.get("schema") != 1 or set(value) != set(self.state):
                    raise ValueError("schema")
                self.state = value
            except (OSError, ValueError) as exc:
                raise ControllerError("추가 설정 기록을 읽지 못했어요. 원본 파일을 확인해 주세요.") from exc
        self.recovery_error = ""
        self._started = False

    def _save(self):
        atomic(self.path, json.dumps(self.state, ensure_ascii=False, indent=2) + "\n")

    def backend(self, area):
        choice(area, AREAS, "설정 화면")
        if area not in self.backends:
            from .audio_controls import AudioControls
            from .network_controls import NetworkControls
            from .panel_controls import PanelControls
            from .session_controls import DisplayControls, PowerControls, SessionControls
            from .style_controls import StyleControls
            from .x11_controls import InputControls, WindowControls

            factories = {
                "audio": AudioControls,
                "network": NetworkControls,
                "panels": PanelControls,
                "windows": WindowControls,
                "input": InputControls,
                "style": lambda: StyleControls(self.controller._appearance()),
                "session": lambda: SessionControls(self.controller),
                "power": lambda: PowerControls(self.controller),
                "display": lambda: DisplayControls(self.controller),
            }
            self.backends[area] = factories[area]()
        return self.backends[area]

    def start(self):
        with self.lock:
            if self._started:
                return
            self._started = True
            self.recover()
            if self.state["pending"]:
                return
            active = self.state["active_mode"]
            preferences = self.state["preferences"]
            session = active["settings"].get("session") if active else preferences.get("session")
            if session and "notifications_muted" in session:
                self.backend("session").apply({"notifications_muted": session["notifications_muted"]})
            for saved in preferences.get("pointers", {}).values():
                live = [
                    p for p in self.backend("input")._pointers() if p["fingerprint"] == saved["fingerprint"]
                ]
                if len(live) == 1:
                    self.backend("input").apply({"pointer": {**saved, "id": live[0]["id"]}})

    def status(self, area):
        with self.lock:
            return self.backend(area).status()

    @staticmethod
    def _name(name):
        if (
            not isinstance(name, str)
            or not 1 <= len(name.strip()) <= 50
            or any(c in name for c in "\x00\r\n")
        ):
            raise ControllerError("이름은 1~50자로 입력해 주세요.")
        return name.strip()

    def _record(self, entry):
        self.state["history"].append(copy.deepcopy(entry))
        # Restore snapshots remain private; bound the local file rather than growing without limit.
        recent = self.state["history"][-300:]
        active = self.state["active_mode"]
        if active and not any(row["id"] == active["entry"]["id"] for row in recent):
            recent.insert(0, copy.deepcopy(active["entry"]))
        self.state["history"] = recent

    def _persist(self, area, settings):
        preferences = self.state["preferences"]
        if area == "session" and "notifications_muted" in settings:
            preferences["session"] = {"notifications_muted": settings["notifications_muted"]}
        if area == "input" and "pointer" in settings:
            row = settings["pointer"]
            preferences.setdefault("pointers", {})[row["fingerprint"]] = copy.deepcopy(row)

    def _restore_preferences(self, entry):
        previous = entry["preferences_before"]
        current = self.state["preferences"]
        for component in entry["components"]:
            area, settings = component["area"], component["settings"]
            if area == "session" and "notifications_muted" in settings:
                if "session" in previous:
                    current["session"] = copy.deepcopy(previous["session"])
                else:
                    current.pop("session", None)
            if area == "input" and "pointer" in settings:
                fingerprint = settings["pointer"]["fingerprint"]
                pointers = current.setdefault("pointers", {})
                old = previous.get("pointers", {}).get(fingerprint)
                if old is not None:
                    pointers[fingerprint] = copy.deepcopy(old)
                else:
                    pointers.pop(fingerprint, None)

    def _matches(self, component):
        backend = self.backend(component["area"])
        current = self._read(component, component["after"])
        comparable = getattr(backend, "comparable", lambda value: value)
        return comparable(current) == comparable(component["after"])

    def _read(self, component, snapshot):
        backend = self.backend(component["area"])
        if hasattr(backend, "read_snapshot"):
            return backend.read_snapshot(snapshot)
        return backend.capture(component["settings"])

    def _restore(self, component, snapshot):
        backend = self.backend(component["area"])
        backend.restore(snapshot)
        comparable = getattr(backend, "comparable", lambda value: value)
        wait_for(lambda: comparable(self._read(component, snapshot)), comparable(snapshot))

    def _rollback(self, entry):
        errors = []
        for component in reversed(entry["components"]):
            if component.get("started"):
                try:
                    self._restore(component, component["before"])
                    component["started"] = False
                except Exception:
                    errors.append(AREAS[component["area"]])
        if errors:
            self.recovery_error = "복원할 연결을 확인해 주세요: " + ", ".join(errors)
            self._save()
            raise ControllerError(self.recovery_error)
        self.state["preferences"] = entry["preferences_before"]
        self.state["pending"] = None
        self.recovery_error = ""

    def recover(self):
        with self.lock:
            pending = self.state["pending"]
            if pending:
                try:
                    self._rollback(pending)
                    pending["status"] = "recovered"
                    self._record(pending)
                    self._save()
                except ControllerError:
                    return {"recovered": False, "error": self.recovery_error}
            return {"recovered": True}

    def _transaction(self, settings, actor, title, active=None, restoring=None):
        choice(actor, ACTORS, "적용 주체")
        if self.state["pending"]:
            raise ControllerError(self.recovery_error or "이전 변경을 먼저 복원해 주세요.")
        components = []
        for area, values in settings.items():
            backend = self.backend(area)
            if restoring:
                original = next(c for c in restoring["components"] if c["area"] == area)
                before = self._read(original, original["before"])
            else:
                values = backend.validate(values)
                before = backend.capture(values)
            components.append(
                {
                    "area": area,
                    "settings": values,
                    "before": before,
                    "after": None,
                    "started": False,
                }
            )
        entry = {
            "id": uuid.uuid4().hex,
            "title": title,
            "actor": actor,
            "status": "pending",
            "at": datetime.now(timezone.utc).isoformat(),
            "components": components,
            "preferences_before": copy.deepcopy(self.state["preferences"]),
        }
        state_before = copy.deepcopy(self.state)
        self.state["pending"] = entry
        try:
            self._save()
            for component in components:
                backend = self.backend(component["area"])
                component["started"] = True
                self._save()
                if restoring:
                    original = next(c for c in restoring["components"] if c["area"] == component["area"])
                    self._restore(component, original["before"])
                else:
                    backend.apply(component["settings"])
                component["after"] = self._read(component, component["before"])
                self._save()
            entry["status"] = "restored" if restoring else "applied"
            if restoring:
                self._restore_preferences(restoring)
                restoring["status"] = "reverted"
            elif active is None:
                for area, values in settings.items():
                    self._persist(area, values)
            if active:
                self.state["active_mode"] = {
                    "name": active,
                    "settings": copy.deepcopy(settings),
                    "entry": copy.deepcopy(entry),
                }
            elif (
                restoring
                and self.state["active_mode"]
                and restoring["id"] == self.state["active_mode"]["entry"]["id"]
            ):
                self.state["active_mode"] = None
            self._record(entry)
            self.state["pending"] = None
            self._save()
            return entry
        except Exception as exc:
            self.state = state_before
            self.state["pending"] = entry
            try:
                self._rollback(entry)
                entry["status"] = "failed"
                self._record(entry)
                self._save()
            except ControllerError as recovery:
                raise recovery from exc
            if isinstance(exc, ControllerError):
                raise
            raise ControllerError("설정을 저장하지 못해 이전 값으로 돌아갔어요.") from exc

    def configure(self, area, settings, actor="local"):
        choice(area, AREAS, "설정 화면")
        with self.lock:
            if self.state["active_mode"] and area in self.state["active_mode"]["settings"]:
                raise ControllerError("작업 모드를 끝내거나 모드 설정을 바꾼 뒤 적용해 주세요.")
            entry = self._transaction({area: settings}, actor, AREAS[area])
            return {"change": entry["id"]}

    def history(self, limit=50):
        integer(limit, 1, 200, "기록 건수")
        with self.lock:
            return [
                {
                    **copy.deepcopy(row),
                    "actor_label": ACTORS[row["actor"]],
                    "areas": [AREAS[c["area"]] for c in row["components"]],
                    "reversible": row["status"] == "applied" and not row["title"].endswith(" 복원"),
                }
                for row in reversed(self.state["history"][-limit:])
            ]

    def revert(self, identifier, actor="local"):
        if not isinstance(identifier, str) or len(identifier) != 32:
            raise ControllerError("복원할 변경을 다시 선택해 주세요.")
        with self.lock:
            original = next((r for r in self.state["history"] if r["id"] == identifier), None)
            if not original or original["status"] != "applied" or original["title"].endswith(" 복원"):
                raise ControllerError("이미 복원했거나 복원할 수 없는 기록이에요.")
            active = self.state["active_mode"]
            if (
                active
                and original["id"] != active["entry"]["id"]
                and any(c["area"] in active["settings"] for c in original["components"])
            ):
                raise ControllerError("이 설정을 쓰는 작업 모드를 먼저 끝내 주세요.")
            if not all(self._matches(c) for c in original["components"]):
                raise ControllerError("다른 곳에서 설정을 바꿨어요. 현재 값을 확인한 뒤 직접 적용해 주세요.")
            settings = {c["area"]: c["settings"] for c in original["components"]}
            self._transaction(settings, actor, original["title"] + " 복원", restoring=original)
            return {"reverted": identifier}

    def modes(self):
        with self.lock:
            modes = {**copy.deepcopy(BUILTIN_MODES), **copy.deepcopy(self.state["modes"])}
            active = self.state["active_mode"]
            return {
                "modes": [{"id": name, **row} for name, row in modes.items()],
                "active": active["name"] if active else None,
                "recovery_error": self.recovery_error,
            }

    def save_mode(self, name, settings):
        name = self._name(name)
        if not isinstance(settings, dict) or not settings or set(settings) - (set(AREAS) - {"network"}):
            raise ControllerError("작업 모드에 넣을 설정을 확인해 주세요.")
        with self.lock:
            result = {}
            for area, values in settings.items():
                if area == "panels" and "widget" in values:
                    raise ControllerError("위젯 추가는 작업 모드에 넣지 않아요.")
                if area == "audio" and "stream" in values:
                    raise ControllerError("앱별 볼륨은 소리 화면에서 조절해 주세요.")
                result[area] = self.backend(area).validate(values)
            self.state["modes"][name] = {"title": name, "settings": result}
            self._save()
            return self.modes()

    def apply_mode(self, name, actor="local"):
        with self.lock:
            choices = {r["id"]: r for r in self.modes()["modes"]}
            choice(name, choices, "작업 모드")
            # Validate and capture dependencies before ending the currently active mode.
            for area, values in choices[name]["settings"].items():
                backend = self.backend(area)
                backend.capture(backend.validate(values))
            previous = copy.deepcopy(self.state["active_mode"])
            if previous:
                self.end_mode(actor)
            try:
                self._transaction(
                    choices[name]["settings"], actor, choices[name]["title"] + " 모드", active=name
                )
            except ControllerError:
                if previous and not self.state["pending"]:
                    self._transaction(
                        previous["settings"], actor, previous["entry"]["title"], active=previous["name"]
                    )
                raise
            return self.modes()

    def end_mode(self, actor="local"):
        with self.lock:
            active = self.state["active_mode"]
            if active:
                self.revert(active["entry"]["id"], actor)
            return self.modes()

    def presets(self, area):
        choice(area, AREAS)
        return copy.deepcopy(self.state["presets"].get(area, {}))

    def save_preset(self, area, name, settings):
        choice(area, AREAS)
        name = self._name(name)
        with self.lock:
            if area not in ("style", "windows", "audio", "input", "panels"):
                raise ControllerError("이 화면에서는 프리셋을 저장하지 않아요.")
            if area == "panels" and "widget" in settings or area == "audio" and "stream" in settings:
                raise ControllerError("위젯 추가나 개별 앱 연결은 프리셋에 넣지 않아요.")
            values = self.backend(area).validate(settings)
            self.state["presets"].setdefault(area, {})[name] = values
            self._save()
            return self.presets(area)

    def apply_preset(self, area, name, actor="local"):
        with self.lock:
            presets = self.presets(area)
            choice(name, presets, "저장한 프리셋")
            return self.configure(area, presets[name], actor)

    def close(self):
        for backend in self.backends.values():
            if hasattr(backend, "close"):
                backend.close()
