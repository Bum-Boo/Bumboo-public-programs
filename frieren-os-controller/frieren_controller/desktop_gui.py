"""Native desktop settings pages backed by the shared, validated local API."""

from __future__ import annotations

import struct
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from functools import partial

from gi.repository import Gtk

from .client import call as api_call
from .desktop_extensions import AREAS
from .x11_controls import sequence_text

call = partial(api_call, _source="gui")
EXTRA_NAV = (
    ("작업 모드", "preferences-system-symbolic"),
    ("데스크톱", "preferences-desktop-theme-symbolic"),
    ("창과 작업공간", "view-grid-symbolic"),
    ("소리와 마이크", "audio-volume-high-symbolic"),
    ("키보드와 마우스", "input-keyboard-symbolic"),
    ("연결과 원격", "network-wireless-symbolic"),
    ("변경 기록", "document-open-recent-symbolic"),
)
EXTRA_AREAS = {
    6: ("modes",),
    7: ("panels", "style"),
    8: ("session", "windows"),
    9: ("audio",),
    10: ("input",),
    11: ("network",),
    12: ("history",),
}


def label(value, style=None):
    widget = Gtk.Label(label=value, xalign=0)
    widget.set_line_wrap(True)
    if style:
        widget.get_style_context().add_class(style)
    return widget


def combo(rows=()):
    widget = Gtk.ComboBoxText()
    for identifier, name in rows:
        widget.append(str(identifier), name)
    if rows:
        widget.set_active(0)
    return widget


def spin(low, high, value, step=1):
    widget = Gtk.SpinButton.new_with_range(low, high, step)
    widget.set_value(value)
    return widget


def row(box, title, control):
    line = Gtk.Box(spacing=16)
    title_widget = label(title)
    title_widget.set_size_request(145, -1)
    line.pack_start(title_widget, False, False, 0)
    control.set_hexpand(True)
    line.pack_start(control, True, True, 0)
    box.pack_start(line, False, False, 0)
    return line


def button(box, title, action, suggested=False):
    widget = Gtk.Button(label=title)
    if suggested:
        widget.get_style_context().add_class("suggested-action")
    widget.connect("clicked", lambda *_: action())
    box.pack_start(widget, False, False, 0)
    return widget


class DesktopPages:
    def _make_extra_pages(self):
        self.extra_data = {}
        self.extra_presets = {}
        self.extra_loading = set()
        self.extra_tokens = defaultdict(int)
        self.extra_dirty = set()
        self.extra_guard = False
        self.extra_errors = {}
        self.extra_roots = {}
        self.extra_preset_boxes = {}
        for number, make in (
            (6, self._make_modes),
            (7, self._make_desktop),
            (8, self._make_windows),
            (9, self._make_audio),
            (10, self._make_input),
            (11, self._make_network),
            (12, self._make_history),
        ):
            self.stack.add_named(make(), str(number))

    def _extra_page(self, title, area, description=""):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.set_border_width(26)
        scroll.add(body)
        body.pack_start(label(title, "page-title"), False, False, 0)
        if description:
            body.pack_start(label(description, "muted"), False, False, 0)
        self._extra_panel(body, area)
        return scroll, body

    def _extra_panel(self, body, area):
        error = label("", "error")
        error.set_no_show_all(True)
        body.pack_start(error, False, False, 0)
        self.extra_errors[area] = error
        self.extra_roots[area] = body

    def _extra_watch(self, area, *widgets):
        for widget in widgets:
            signal = (
                "toggled"
                if isinstance(widget, Gtk.ToggleButton)
                else ("value-changed" if isinstance(widget, (Gtk.SpinButton, Gtk.Scale)) else "changed")
            )
            widget.connect(
                signal, lambda *_, area=area: self.extra_dirty.add(area) if not self.extra_guard else None
            )

    def _extra_combo(self, widget, rows, selected=None):
        previous = widget.get_active_id()
        widget.remove_all()
        ids = set()
        for identifier, name in rows:
            identifier = str(identifier)
            widget.append(identifier, str(name))
            ids.add(identifier)
        wanted = str(selected) if selected is not None else previous
        if wanted in ids:
            widget.set_active_id(wanted)
        elif ids:
            widget.set_active(0)

    def _extra_load_current(self, force=False):
        for area in EXTRA_AREAS.get(self._page_index(), ()):
            self._extra_load(area, force)

    def _extra_load(self, area, force=False):
        if self.busy or area in self.extra_loading:
            return
        self.extra_loading.add(area)
        self.extra_tokens[area] += 1
        token = self.extra_tokens[area]

        def load():
            if area == "modes":
                return {
                    "data": call("work_mode_status"),
                    "presets": {kind: call("workspace_presets", area=kind) for kind in ("windows", "style")},
                }
            if area == "history":
                return {"data": call("settings_history")}
            return {
                "data": call("workspace_status", area=area),
                "presets": call("workspace_presets", area=area),
            }

        self._work(
            "",
            load,
            lambda data: self._extra_result(area, token, data, force),
            lambda error: self._extra_failure(area, token, error),
        )

    def _extra_result(self, area, token, payload, force):
        if token != self.extra_tokens[area]:
            return False
        self.extra_loading.discard(area)
        first = area not in self.extra_data
        self.extra_data[area] = payload["data"]
        self.extra_presets[area] = payload.get("presets", {})
        self.extra_errors[area].hide()
        if first or force or area not in self.extra_dirty:
            self.extra_guard = True
            try:
                getattr(self, "_fill_" + area)(payload["data"])
                self.extra_dirty.discard(area)
                if area in self.extra_preset_boxes:
                    self._extra_combo(
                        self.extra_preset_boxes[area]["choice"],
                        [(name, name) for name in payload.get("presets", {})],
                    )
            finally:
                self.extra_guard = False
        self.extra_roots[area].show_all()
        return False

    def _extra_failure(self, area, token, error):
        if token == self.extra_tokens[area]:
            self.extra_loading.discard(area)
            self.extra_errors[area].set_text(error)
            self.extra_errors[area].show()
        return False

    def _extra_action(self, page_area, operation, **args):
        area = page_area
        if self.busy or area in self.extra_loading:
            return
        self.busy = True
        for body in self.extra_roots.values():
            body.set_sensitive(False)

        def finished(_result):
            self.busy = False
            for body in self.extra_roots.values():
                body.set_sensitive(True)
            self._saved()
            self.extra_dirty.discard(area)
            self._extra_load(area, True)
            return False

        def failed(message):
            self.busy = False
            for body in self.extra_roots.values():
                body.set_sensitive(True)
            self.extra_errors[area].set_text(message)
            self.extra_errors[area].show()
            return False

        self._work("", lambda: call(operation, **args), finished, failed)

    def _extra_apply(self, area, getter):
        try:
            settings = getter()
        except (TypeError, ValueError, KeyError, StopIteration):
            self.extra_errors[area].set_text("적용할 항목을 먼저 선택해 주세요.")
            self.extra_errors[area].show()
            return
        self._extra_action(area, "workspace_configure", area=area, settings=settings)

    def _extra_preset_bar(self, body, area, getter):
        body.pack_start(Gtk.Separator(), False, False, 6)
        line = Gtk.Box(spacing=10)
        name = Gtk.Entry(placeholder_text="프리셋 이름")
        line.pack_start(name, True, True, 0)

        def save():
            try:
                settings = getter()
            except (TypeError, ValueError, KeyError, StopIteration):
                self.extra_errors[area].set_text("저장할 항목을 먼저 선택해 주세요.")
                self.extra_errors[area].show()
                return
            self._extra_action(
                area, "workspace_save_preset", area=area, name=name.get_text(), settings=settings
            )

        button(line, "프리셋 저장하기", save)
        body.pack_start(line, False, False, 0)
        line = Gtk.Box(spacing=10)
        selected = combo()
        line.pack_start(selected, True, True, 0)
        button(
            line,
            "저장한 설정 적용하기",
            lambda: self._extra_action(
                area, "workspace_apply_preset", area=area, name=selected.get_active_id()
            ),
        )
        body.pack_start(line, False, False, 0)
        self.extra_preset_boxes[area] = {"name": name, "choice": selected}

    def _make_modes(self):
        scroll, body = self._extra_page("작업 모드", "modes", "모드를 끝내면 시작 전 설정으로 돌아가요.")
        self.mode_current = label("현재 모드를 불러오는 중…", "muted")
        body.pack_start(self.mode_current, False, False, 0)
        self.mode_choice = combo()
        row(body, "작업 모드", self.mode_choice)
        self.mode_choice.connect("changed", lambda *_: self._mode_choose())
        actions = Gtk.Box(spacing=10)
        button(
            actions,
            "모드 시작하기",
            lambda: self._extra_action("modes", "work_mode_apply", name=self.mode_choice.get_active_id()),
            True,
        )
        self.mode_end_button = button(
            actions, "모드 끝내기", lambda: self._extra_action("modes", "work_mode_end")
        )
        body.pack_start(actions, False, False, 0)
        self.mode_editor = Gtk.Expander(label="모드 편집")
        editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        editor.set_margin_top(16)
        self.mode_editor.add(editor)
        body.pack_start(self.mode_editor, False, False, 0)
        body = editor
        self.mode_name = Gtk.Entry(placeholder_text="모드 이름")
        row(body, "이름", self.mode_name)
        self.mode_power_include = Gtk.CheckButton(label="전원 설정 함께 바꾸기")
        self.mode_power_include.set_active(True)
        body.pack_start(self.mode_power_include, False, False, 0)
        self.mode_power = combo(
            (
                ("quiet", "조용함"),
                ("balanced", "균형"),
                ("performance", "성능"),
                ("auto", "자동"),
                ("custom", "저장한 전원 설정"),
                ("restore", "원래 전원 설정"),
            )
        )
        row(body, "전원", self.mode_power)
        self.mode_display_include = Gtk.CheckButton(label="화면 설정 함께 바꾸기")
        self.mode_display_include.set_active(True)
        body.pack_start(self.mode_display_include, False, False, 0)
        self.mode_brightness = spin(5, 100, 75)
        row(body, "밝기 (%)", self.mode_brightness)
        self.mode_night = Gtk.CheckButton(label="야간 색으로 보기")
        body.pack_start(self.mode_night, False, False, 0)
        self.mode_temperature = spin(2500, 6500, 4500, 100)
        row(body, "색온도 (K)", self.mode_temperature)
        self.mode_notifications_include = Gtk.CheckButton(label="알림 설정 함께 바꾸기")
        self.mode_notifications_include.set_active(True)
        self.mode_notifications = Gtk.CheckButton(label="알림 숨기기")
        self.mode_notifications.set_active(True)
        body.pack_start(self.mode_notifications_include, False, False, 0)
        body.pack_start(self.mode_notifications, False, False, 0)
        self.mode_awake_include = Gtk.CheckButton(label="정해진 시간 동안 화면 켜두기")
        body.pack_start(self.mode_awake_include, False, False, 0)
        self.mode_awake = spin(1, 240, 60)
        row(body, "화면 유지 (분)", self.mode_awake)
        self.mode_timeout_include = Gtk.CheckButton(label="자동 화면 꺼짐 시간 바꾸기")
        body.pack_start(self.mode_timeout_include, False, False, 0)
        self.mode_timeout = spin(60, 3600, 180, 30)
        row(body, "화면 꺼짐 (초)", self.mode_timeout)
        self.mode_audio_include = Gtk.CheckButton(label="소리 설정 함께 바꾸기")
        body.pack_start(self.mode_audio_include, False, False, 0)
        self.mode_mic_muted = Gtk.CheckButton(label="마이크 음소거")
        self.mode_mic_muted.set_active(True)
        body.pack_start(self.mode_mic_muted, False, False, 0)
        self.mode_volume_include = Gtk.CheckButton(label="스피커 볼륨 바꾸기")
        body.pack_start(self.mode_volume_include, False, False, 0)
        self.mode_volume = spin(0, 100, 40)
        row(body, "스피커 볼륨 (%)", self.mode_volume)
        self.mode_window_preset = combo((("", "함께 바꾸지 않기"),))
        self.mode_style_preset = combo((("", "함께 바꾸지 않기"),))
        row(body, "창 배치", self.mode_window_preset)
        row(body, "OS 스타일", self.mode_style_preset)
        actions = Gtk.Box(spacing=10)
        button(
            actions,
            "내 모드 저장하기",
            lambda: self._extra_action(
                "modes", "work_mode_save", name=self.mode_name.get_text(), settings=self._mode_settings()
            ),
            True,
        )
        body.pack_start(actions, False, False, 0)
        body.pack_start(
            label("화면 유지는 자동 잠금과 시스템 절전 설정을 따로 바꾸지 않아요.", "muted"), False, False, 0
        )
        return scroll

    def _mode_settings(self):
        saved = getattr(self, "mode_original", {})
        result = {k: deepcopy(v) for k, v in saved.items() if k in ("input", "panels")}
        if self.mode_power_include.get_active():
            result["power"] = {**saved.get("power", {}), "mode": self.mode_power.get_active_id()}
        if self.mode_display_include.get_active():
            result["display"] = {
                **saved.get("display", {}),
                "brightness": self.mode_brightness.get_value_as_int(),
                "night_enabled": self.mode_night.get_active(),
                "temperature": self.mode_temperature.get_value_as_int(),
                "auto_brightness": False,
            }
        session = {}
        if self.mode_notifications_include.get_active():
            session["notifications_muted"] = self.mode_notifications.get_active()
        if self.mode_awake_include.get_active():
            session["keep_awake"] = self.mode_awake.get_value_as_int()
        if self.mode_timeout_include.get_active():
            session["screen_timeout"] = self.mode_timeout.get_value_as_int()
        if session:
            result["session"] = session
        if self.mode_audio_include.get_active():
            result["audio"] = {**saved.get("audio", {}), "input_muted": self.mode_mic_muted.get_active()}
            if self.mode_volume_include.get_active():
                result["audio"]["output_volume"] = self.mode_volume.get_value_as_int()
            else:
                result["audio"].pop("output_volume", None)
        for area, control in (("windows", self.mode_window_preset), ("style", self.mode_style_preset)):
            selected = control.get_active_id()
            if selected == "__saved__":
                result[area] = deepcopy(saved[area])
            elif selected:
                result[area] = self.extra_presets["modes"][area][selected]
        return result

    def _fill_modes(self, data):
        active = data["active"]
        titles = {r["id"]: r["title"] for r in data["modes"]}
        self.mode_current.set_text(
            "현재 모드: " + titles.get(active, active) if active else "실행 중인 모드 없음"
        )
        self.mode_end_button.set_sensitive(bool(active))
        self._extra_combo(self.mode_choice, [(r["id"], r["title"]) for r in data["modes"]])
        for area, control in (("windows", self.mode_window_preset), ("style", self.mode_style_preset)):
            self._extra_combo(
                control,
                [
                    ("", "함께 바꾸지 않기"),
                    *((name, name) for name in self.extra_presets["modes"].get(area, {})),
                ],
            )
        self._mode_choose()
        if data.get("recovery_error"):
            self.extra_errors["modes"].set_text(data["recovery_error"])
            self.extra_errors["modes"].show()

    def _mode_choose(self):
        data = self.extra_data.get("modes")
        if not data:
            return
        selected = next((r for r in data["modes"] if r["id"] == self.mode_choice.get_active_id()), None)
        if not selected:
            return
        values = selected["settings"]
        self.mode_original = deepcopy(values)
        for area, control in (("windows", self.mode_window_preset), ("style", self.mode_style_preset)):
            presets = self.extra_presets.get("modes", {}).get(area, {})
            options = [("", "함께 바꾸지 않기"), *((name, name) for name in presets)]
            selected_id = ""
            if area in values:
                selected_id = next(
                    (name for name, data in presets.items() if data == values[area]), "__saved__"
                )
                if selected_id == "__saved__":
                    options.append(("__saved__", "이 모드에 저장한 설정"))
            self._extra_combo(control, options)
            control.set_active_id(selected_id)
        self.mode_name.set_text(selected["title"])
        self.mode_power_include.set_active("power" in values)
        self.mode_power.set_active_id(values.get("power", {}).get("mode", "quiet"))
        display = values.get("display", {})
        self.mode_display_include.set_active(bool(display))
        self.mode_brightness.set_value(display.get("brightness", 75))
        self.mode_night.set_active(display.get("night_enabled", False))
        self.mode_temperature.set_value(display.get("temperature", 4500))
        session = values.get("session", {})
        self.mode_notifications_include.set_active("notifications_muted" in session)
        self.mode_notifications.set_active(session.get("notifications_muted", False))
        self.mode_awake_include.set_active("keep_awake" in session)
        self.mode_awake.set_value(session.get("keep_awake", 60))
        self.mode_timeout_include.set_active("screen_timeout" in session)
        self.mode_timeout.set_value(session.get("screen_timeout", 180))
        audio = values.get("audio", {})
        self.mode_audio_include.set_active(bool(audio))
        self.mode_mic_muted.set_active(audio.get("input_muted", False))
        self.mode_volume_include.set_active("output_volume" in audio)
        self.mode_volume.set_value(audio.get("output_volume", 40))

    def _make_desktop(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        root.set_border_width(24)
        root.pack_start(label("데스크톱", "page-title"), False, False, 0)
        notebook = Gtk.Notebook()
        self.desktop_notebook = notebook
        root.pack_start(notebook, True, True, 0)
        for area, title, maker in (
            ("panels", "패널과 위젯", self._make_panels),
            ("style", "OS 스타일", self._make_style),
        ):
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            body.set_border_width(20)
            body.get_style_context().add_class("quiet-panel")
            scroll.add(body)
            self._extra_panel(body, area)
            maker(body)
            notebook.append_page(scroll, Gtk.Label(label=title))
        return root

    def _make_panels(self, body):
        self.panel_choice = combo()
        row(body, "패널", self.panel_choice)
        self.panel_choice.connect("changed", lambda *_: self._panel_choose())
        self.panel_location = combo(
            (("top", "위"), ("bottom", "아래"), ("left", "왼쪽"), ("right", "오른쪽"))
        )
        self.panel_height = spin(24, 128, 40)
        self.panel_hiding = combo(
            (
                ("none", "항상 표시"),
                ("autohide", "자동 숨김"),
                ("dodgewindows", "창이 닿으면 숨김"),
                ("windowsgobelow", "창 위에 표시"),
            )
        )
        self.panel_length = combo(
            (("fit", "위젯에 맞추기"), ("fill", "화면 너비 채우기"), ("custom", "현재 길이 유지"))
        )
        row(body, "위치", self.panel_location)
        row(body, "크기 (px)", self.panel_height)
        row(body, "표시", self.panel_hiding)
        row(body, "길이", self.panel_length)
        self.panel_widgets = label("", "muted")
        body.pack_start(self.panel_widgets, False, False, 0)
        actions = Gtk.Box(spacing=10)
        button(actions, "패널 적용하기", lambda: self._extra_apply("panels", self._panel_settings), True)
        body.pack_start(actions, False, False, 0)
        self._extra_watch(
            "panels", self.panel_location, self.panel_height, self.panel_hiding, self.panel_length
        )
        body.pack_start(Gtk.Separator(), False, False, 6)
        self.widget_target = combo()
        self.widget_kind = combo()
        row(body, "위젯을 놓을 곳", self.widget_target)
        row(body, "추가할 위젯", self.widget_kind)
        actions = Gtk.Box(spacing=10)
        button(actions, "위젯 추가하기", lambda: self._extra_apply("panels", self._widget_settings))
        body.pack_start(actions, False, False, 0)
        self._extra_preset_bar(body, "panels", self._panel_settings)

    def _panel_settings(self):
        return {
            "panel": {
                "id": int(self.panel_choice.get_active_id()),
                "location": self.panel_location.get_active_id(),
                "height": self.panel_height.get_value_as_int(),
                "hiding": self.panel_hiding.get_active_id(),
                "length_mode": self.panel_length.get_active_id(),
            }
        }

    def _widget_settings(self):
        target, identifier = self.widget_target.get_active_id().split(":")
        return {"widget": {"target": target, "id": int(identifier), "kind": self.widget_kind.get_active_id()}}

    def _fill_panels(self, data):
        locations = {"top": "위", "bottom": "아래", "left": "왼쪽", "right": "오른쪽", "floating": "떠 있는"}
        self._extra_combo(
            self.panel_choice,
            [
                (p["id"], f"{locations.get(p['location'], '')} 패널 {i + 1} · 화면 {p['screen'] + 1}")
                for i, p in enumerate(data["panels"])
            ],
        )
        self._extra_combo(
            self.widget_target,
            [(f"panel:{p['id']}", f"패널 {i + 1}") for i, p in enumerate(data["panels"])]
            + [(f"desktop:{d['id']}", f"화면 {d['screen'] + 1} 바탕화면") for d in data["desktops"]],
        )
        self._extra_combo(self.widget_kind, [(r["id"], r["name"]) for r in data["kinds"] if r["available"]])
        self._panel_choose()

    def _panel_choose(self):
        data = self.extra_data.get("panels")
        if not data:
            return
        panel = next((p for p in data["panels"] if str(p["id"]) == self.panel_choice.get_active_id()), None)
        if not panel:
            return
        self.panel_location.set_active_id(panel["location"])
        self.panel_height.set_value(panel["height"])
        self.panel_hiding.set_active_id(panel["hiding"])
        self.panel_length.set_active_id(panel["length_mode"])
        names = {
            "org.kde.plasma.kickoff": "앱 메뉴",
            "org.kde.plasma.pager": "작업공간 전환",
            "org.kde.plasma.digitalclock": "시계",
            "org.kde.plasma.systemtray": "시스템 트레이",
            "org.kde.plasma.icontasks": "앱 아이콘",
            "org.kde.plasma.showdesktop": "바탕화면 보기",
            "io.github.BumBoo.FrierenController": "프리렌 컨트롤러",
        }
        self.panel_widgets.set_text(
            "현재 위젯: " + ", ".join(names.get(w["type"], "추가 위젯") for w in panel["widgets"])
        )

    def _make_style(self, body):
        self.style_choices = {}
        for key, title in (
            ("color_scheme", "시스템 색"),
            ("plasma_style", "패널 스타일"),
            ("icons", "아이콘"),
            ("cursor", "커서"),
            ("decoration", "창 장식"),
        ):
            self.style_choices[key] = combo()
            row(body, title, self.style_choices[key])
        self.style_cursor_size = spin(16, 64, 24)
        row(body, "커서 크기 (px)", self.style_cursor_size)
        self.style_font = combo()
        self.style_font_size = spin(6, 32, 10)
        self.style_fixed = combo()
        self.style_fixed_size = spin(6, 32, 10)
        row(body, "화면 글꼴", self.style_font)
        row(body, "글꼴 크기", self.style_font_size)
        row(body, "고정폭 글꼴", self.style_fixed)
        row(body, "고정폭 크기", self.style_fixed_size)
        self.style_lock_path = ""
        self.style_lock_title = label("잠금 화면 배경 유지", "muted")
        body.pack_start(self.style_lock_title, False, False, 0)
        actions = Gtk.Box(spacing=10)
        button(actions, "잠금 화면 이미지 선택하기", self._choose_lock_image)
        button(actions, "스타일 적용하기", lambda: self._extra_apply("style", self._style_settings), True)
        body.pack_start(actions, False, False, 0)
        body.pack_start(
            label("패널 위치와 위젯 배치는 유지해요. 일부 앱은 새 창에서 글꼴과 아이콘을 반영해요.", "muted"),
            False,
            False,
            0,
        )
        self._extra_watch(
            "style",
            *self.style_choices.values(),
            self.style_cursor_size,
            self.style_font,
            self.style_font_size,
            self.style_fixed,
            self.style_fixed_size,
        )
        self._extra_preset_bar(body, "style", self._style_settings)

    def _choose_lock_image(self):
        dialog = Gtk.FileChooserDialog(
            title="잠금 화면 이미지 선택", transient_for=self, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons("닫기", Gtk.ResponseType.CANCEL, "선택하기", Gtk.ResponseType.OK)
        file_filter = Gtk.FileFilter()
        file_filter.set_name("이미지 (PNG, JPG, WebP)")
        for mime in ("image/png", "image/jpeg", "image/webp"):
            file_filter.add_mime_type(mime)
        dialog.add_filter(file_filter)
        if dialog.run() == Gtk.ResponseType.OK:
            self.style_lock_path = dialog.get_filename()
            self.style_lock_title.set_text("선택한 잠금 화면: " + dialog.get_filename().rsplit("/", 1)[-1])
            self.extra_dirty.add("style")
        dialog.destroy()

    def _style_settings(self):
        result = {
            key: control.get_active_id()
            for key, control in self.style_choices.items()
            if control.get_active_id()
        }
        result.update(
            cursor_size=self.style_cursor_size.get_value_as_int(),
            font_family=self.style_font.get_active_id(),
            font_size=self.style_font_size.get_value_as_int(),
            fixed_family=self.style_fixed.get_active_id(),
            fixed_size=self.style_fixed_size.get_value_as_int(),
        )
        if self.style_lock_path:
            result["lock_image"] = self.style_lock_path
        return result

    def _fill_style(self, data):
        current, choices = data["current"], data["choices"]
        for key, control in self.style_choices.items():
            rows = choices[key]
            names = [
                (name, value["name"] if isinstance(value, dict) else value) for name, value in rows.items()
            ]
            if current.get(key) is None and key == "decoration":
                names.insert(0, ("", "현재 창 장식 유지"))
            self._extra_combo(control, names, current.get(key, ""))
        self.style_cursor_size.set_value(int(current["cursor_size"] or 24))
        for key, control, size in (
            ("font", self.style_font, self.style_font_size),
            ("fixed_font", self.style_fixed, self.style_fixed_size),
        ):
            values = (current[key] or "Noto Sans,10").split(",")
            self._extra_combo(control, [(name, name) for name in choices["fonts"]], values[0])
            size.set_value(float(values[1]))
        self.style_lock_path = ""
        self.style_lock_title.set_text("잠금 화면 배경 유지")

    def _make_windows(self):
        scroll, body = self._extra_page(
            "창과 작업공간", "windows", "열려 있는 창을 배치하고 앱별 배치를 저장해요."
        )
        session = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        session.get_style_context().add_class("quiet-panel")
        session.set_border_width(16)
        session.pack_start(label("로그인할 때", "section-title"), False, False, 0)
        self._extra_panel(session, "session")
        self.session_restore_switch = Gtk.Switch()
        self.session_restore_switch.set_halign(Gtk.Align.END)
        self.session_restore_switch.set_sensitive(False)
        self.session_restore_switch.connect("notify::active", self._session_restore_changed)
        row(session, "세션 복원", self.session_restore_switch)
        session.pack_start(
            label("켜면 종료 전에 열었던 앱을 다시 열어요. 자동 시작 앱은 이 설정과 별개예요.", "muted"),
            False,
            False,
            0,
        )
        self.session_restore_hint = label("현재 설정을 불러오는 중…", "muted")
        self.session_restore_hint.set_no_show_all(True)
        self.session_restore_hint.show()
        session.pack_start(self.session_restore_hint, False, False, 0)
        body.pack_start(session, False, False, 0)
        self.window_choice = combo()
        row(body, "배치할 창", self.window_choice)
        self.window_choice.connect("changed", lambda *_: self._window_choose())
        self.window_desktop = combo()
        row(body, "작업공간", self.window_desktop)
        actions = Gtk.Box(spacing=8)
        for placement, title in (
            ("left", "왼쪽"),
            ("right", "오른쪽"),
            ("top", "위쪽"),
            ("bottom", "아래쪽"),
            ("maximize", "최대화"),
        ):
            button(
                actions,
                title,
                lambda placement=placement: self._extra_apply(
                    "windows", lambda: self._window_settings(placement)
                ),
            )
        body.pack_start(actions, False, False, 0)
        self.window_geometry_editor = Gtk.Expander(label="정확한 위치와 크기")
        geometry = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        geometry.set_margin_top(16)
        self.window_geometry_editor.add(geometry)
        body.pack_start(self.window_geometry_editor, False, False, 0)
        self.window_rect = {}
        for key, title, low, high, default in (
            ("x", "가로 위치", -16000, 16000, 0),
            ("y", "세로 위치", -16000, 16000, 0),
            ("width", "창 너비", 200, 16000, 800),
            ("height", "창 높이", 150, 16000, 600),
        ):
            self.window_rect[key] = spin(low, high, default)
            row(geometry, title + " (px)", self.window_rect[key])
        actions = Gtk.Box(spacing=10)
        button(
            actions, "직접 배치 적용하기", lambda: self._extra_apply("windows", self._window_settings), True
        )
        geometry.pack_start(actions, False, False, 0)
        self._extra_watch("windows", self.window_desktop, *self.window_rect.values())
        self.window_current_desktop = combo()
        row(body, "현재 작업공간", self.window_current_desktop)
        actions = Gtk.Box(spacing=10)
        button(
            actions,
            "작업공간으로 이동하기",
            lambda: self._extra_apply(
                "windows", lambda: {"current_desktop": int(self.window_current_desktop.get_active_id())}
            ),
        )
        body.pack_start(actions, False, False, 0)
        self.window_names_editor = Gtk.Expander(label="작업공간 이름 바꾸기")
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        names.set_margin_top(16)
        self.window_names_editor.add(names)
        body.pack_start(self.window_names_editor, False, False, 0)
        self.window_desktop_names = Gtk.Entry(placeholder_text="작업공간 이름을 쉼표로 구분해 주세요.")
        row(names, "작업공간 이름", self.window_desktop_names)
        actions = Gtk.Box(spacing=10)
        button(
            actions,
            "이름 저장하기",
            lambda: self._extra_apply(
                "windows",
                lambda: {
                    "desktop_names": [n.strip() for n in self.window_desktop_names.get_text().split(",")]
                },
            ),
        )
        names.pack_start(actions, False, False, 0)
        self._extra_preset_bar(body, "windows", self._window_layout_settings)
        body.pack_start(
            label("현재 열린 앱들의 배치를 저장해요. 다시 적용할 때 해당 앱을 먼저 열어 주세요.", "muted"),
            False,
            False,
            0,
        )
        return scroll

    def _fill_session(self, data):
        self.session_restore_switch.set_active(data["session_restore"])
        self.session_restore_switch.set_sensitive(True)
        mode = data["session_restore_mode"]
        self.session_restore_hint.set_text("수동으로 저장한 세션을 복원해요.")
        self.session_restore_hint.set_visible(mode == "restoreSavedSession")

    def _session_restore_changed(self, switch, _property):
        if self.extra_guard or "session" not in self.extra_data:
            return
        requested = switch.get_active()
        current = self.extra_data["session"]["session_restore"]
        self.extra_guard = True
        try:
            switch.set_active(current)
        finally:
            self.extra_guard = False
        if requested != current:
            self._extra_action(
                "session", "workspace_configure", area="session", settings={"session_restore": requested}
            )

    def _selected_window(self):
        return next(
            w
            for w in self.extra_data["windows"]["windows"]
            if str(w["id"]) == self.window_choice.get_active_id()
        )

    def _window_settings(self, placement=None):
        window = self._selected_window()
        settings = {
            "id": window["id"],
            "fingerprint": window["fingerprint"],
            "desktop": int(self.window_desktop.get_active_id()),
        }
        if placement:
            settings["placement"] = placement
        else:
            settings["rect"] = {k: v.get_value_as_int() for k, v in self.window_rect.items()}
        return {"windows": [settings]}

    def _window_layout_settings(self):
        rules = []
        ordinals = defaultdict(int)
        for window in self.extra_data["windows"]["windows"]:
            if not window["app"]:
                continue
            key = (window["app"], window["instance"])
            rule = {
                "app": window["app"],
                "instance": window["instance"],
                "ordinal": ordinals[key],
                "rect": window["rect"],
            }
            ordinals[key] += 1
            if window["desktop"] != 2**32 - 1:
                rule["desktop"] = window["desktop"]
            if len(window["maximized"]) == 2:
                rule.pop("rect")
                rule["placement"] = "maximize"
            rules.append(rule)
        return {"rules": rules}

    def _fill_windows(self, data):
        self._extra_combo(
            self.window_choice, [(w["id"], (w["name"] or w["app"])[:90]) for w in data["windows"]]
        )
        desktops = [(d["id"], d["name"]) for d in data["desktops"]]
        self._extra_combo(self.window_desktop, [(2**32 - 1, "모든 작업공간"), *desktops])
        self._extra_combo(self.window_current_desktop, desktops, data["current_desktop"])
        self.window_desktop_names.set_text(", ".join(d["name"] for d in data["desktops"]))
        self._window_choose()

    def _window_choose(self):
        if "windows" not in self.extra_data or not self.window_choice.get_active_id():
            return
        window = self._selected_window()
        self.window_desktop.set_active_id(str(window["desktop"]))
        for key, control in self.window_rect.items():
            control.set_value(window["rect"][key])

    def _make_audio(self):
        scroll, body = self._extra_page("소리와 마이크", "audio")
        self.audio_controls = {}
        for direction, title in (("output", "스피커와 헤드셋"), ("input", "마이크")):
            body.pack_start(label(title, "section-title"), False, False, 0)
            controls = {
                "device": combo(),
                "port": combo(),
                "volume": spin(0, 100, 50),
                "muted": Gtk.CheckButton(label="음소거"),
            }
            self.audio_controls[direction] = controls
            row(body, "장치", controls["device"])
            row(body, "연결", controls["port"])
            row(body, "볼륨 (%)", controls["volume"])
            body.pack_start(controls["muted"], False, False, 0)
            controls["device"].connect(
                "changed", lambda *_, direction=direction: self._audio_choose(direction)
            )
            self._extra_watch("audio", *controls.values())
        self.audio_move = Gtk.CheckButton(label="지금 재생 중인 앱도 선택한 출력으로 옮기기")
        self.audio_move.set_active(True)
        body.pack_start(self.audio_move, False, False, 0)
        actions = Gtk.Box(spacing=10)
        button(actions, "소리 설정 적용하기", lambda: self._extra_apply("audio", self._audio_settings), True)
        button(
            actions,
            "회의용으로 바꾸기",
            lambda: self._extra_apply("audio", lambda: {"input_muted": False, "output_volume": 50}),
        )
        body.pack_start(actions, False, False, 0)
        body.pack_start(label("앱별 소리", "section-title"), False, False, 0)
        self.audio_streams = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.pack_start(self.audio_streams, False, False, 0)
        self._extra_preset_bar(body, "audio", self._audio_settings)
        return scroll

    def _audio_settings(self):
        result = {"move_streams": self.audio_move.get_active()}
        for direction, controls in self.audio_controls.items():
            if controls["device"].get_active_id():
                result.update(
                    {
                        direction: controls["device"].get_active_id(),
                        direction + "_volume": controls["volume"].get_value_as_int(),
                        direction + "_muted": controls["muted"].get_active(),
                    }
                )
                if controls["port"].get_active_id():
                    result[direction + "_port"] = controls["port"].get_active_id()
        return result

    def _audio_choose(self, direction):
        data = self.extra_data.get("audio")
        if not data:
            return
        controls = self.audio_controls[direction]
        device = next(
            (r for r in data[direction + "s"] if r["id"] == controls["device"].get_active_id()), None
        )
        if device:
            self._extra_combo(
                controls["port"],
                [(p["id"], p["name"]) for p in device["ports"] if p["available"]],
                device["port"],
            )
            controls["volume"].set_value(device["volume"])
            controls["muted"].set_active(device["muted"])

    def _fill_audio(self, data):
        for direction, controls in self.audio_controls.items():
            self._extra_combo(
                controls["device"], [(r["id"], r["name"]) for r in data[direction + "s"]], data[direction]
            )
            self._audio_choose(direction)
            for control in controls.values():
                control.set_sensitive(bool(data[direction + "s"]))
        for child in self.audio_streams.get_children():
            self.audio_streams.remove(child)
        if not data["streams"]:
            self.audio_streams.pack_start(label("소리를 재생하는 앱이 없어요.", "muted"), False, False, 0)
        for stream in data["streams"]:
            line = Gtk.Box(spacing=10)
            name = label(stream["name"])
            name.set_size_request(160, -1)
            line.pack_start(name, True, True, 0)
            volume = spin(0, 100, min(stream["volume"], 100))
            muted = Gtk.CheckButton(label="음소거")
            muted.set_active(stream["muted"])
            line.pack_start(volume, False, False, 0)
            line.pack_start(muted, False, False, 0)
            button(
                line,
                "적용하기",
                lambda stream=stream, volume=volume, muted=muted: self._extra_apply(
                    "audio",
                    lambda: {
                        "stream": {
                            "id": stream["index"],
                            "serial": stream["serial"],
                            "volume": volume.get_value_as_int(),
                            "muted": muted.get_active(),
                        }
                    },
                ),
            )
            self.audio_streams.pack_start(line, False, False, 0)

    def _make_input(self):
        scroll, body = self._extra_page("키보드와 마우스", "input")
        self.pointer_choice = combo()
        row(body, "입력 장치", self.pointer_choice)
        self.pointer_choice.connect("changed", lambda *_: self._pointer_choose())
        self.pointer_speed = spin(-100, 100, 0)
        self.pointer_acceleration = combo()
        row(body, "포인터 속도", self.pointer_speed)
        row(body, "가속 방식", self.pointer_acceleration)
        self.pointer_flags = {
            key: Gtk.CheckButton(label=title)
            for key, title in (
                ("natural_scroll", "스크롤 방향 반대로"),
                ("tap", "탭으로 클릭하기"),
                ("disable_while_typing", "타이핑 중 터치패드 쉬기"),
            )
        }
        for control in self.pointer_flags.values():
            body.pack_start(control, False, False, 0)
        actions = Gtk.Box(spacing=10)
        button(
            actions, "입력 설정 적용하기", lambda: self._extra_apply("input", self._pointer_settings), True
        )
        body.pack_start(actions, False, False, 0)
        body.pack_start(
            label("지원되는 항목만 켜져요. 저장한 설정은 다음 로그인에도 적용해요.", "muted"), False, False, 0
        )
        self._extra_watch(
            "input", self.pointer_speed, self.pointer_acceleration, *self.pointer_flags.values()
        )
        self._extra_preset_bar(body, "input", self._pointer_settings)
        body.pack_start(Gtk.Separator(), False, False, 6)
        body.pack_start(label("단축키", "section-title"), False, False, 0)
        self.shortcut_search = Gtk.SearchEntry(placeholder_text="동작 검색")
        body.pack_start(self.shortcut_search, False, False, 0)
        self.shortcut_search.connect("search-changed", lambda *_: self._shortcuts_filter())
        self.shortcut_choice = combo()
        row(body, "동작", self.shortcut_choice)
        self.shortcut_choice.connect("changed", lambda *_: self._shortcut_choose())
        self.shortcut_sequence = Gtk.Entry(placeholder_text="Meta+Shift+R")
        row(body, "단축키", self.shortcut_sequence)
        actions = Gtk.Box(spacing=10)
        button(actions, "단축키 저장하기", lambda: self._extra_apply("input", self._shortcut_settings), True)
        body.pack_start(actions, False, False, 0)
        body.pack_start(
            label("Meta는 Windows 키예요. 빈칸으로 저장하면 해당 단축키를 해제해요.", "muted"),
            False,
            False,
            0,
        )
        return scroll

    def _pointer_settings(self):
        pointer = next(
            p
            for p in self.extra_data["input"]["pointers"]
            if str(p["id"]) == self.pointer_choice.get_active_id()
        )
        result = {"id": pointer["id"], "fingerprint": pointer["fingerprint"]}
        if "speed" in pointer["values"]:
            result["speed"] = self.pointer_speed.get_value_as_int()
        if "acceleration" in pointer["values"] and self.pointer_acceleration.get_active_id():
            result["acceleration"] = self.pointer_acceleration.get_active_id()
        result.update(
            {
                key: control.get_active()
                for key, control in self.pointer_flags.items()
                if key in pointer["values"]
            }
        )
        return {"pointer": result}

    def _fill_input(self, data):
        self._extra_combo(self.pointer_choice, [(p["id"], p["name"]) for p in data["pointers"]])
        self._pointer_choose()
        self._shortcuts_filter()

    def _pointer_choose(self):
        if "input" not in self.extra_data:
            return
        pointer = next(
            (
                p
                for p in self.extra_data["input"]["pointers"]
                if str(p["id"]) == self.pointer_choice.get_active_id()
            ),
            None,
        )
        values = pointer["values"] if pointer else {}
        self.pointer_speed.set_sensitive("speed" in values)
        self.pointer_speed.set_value(values.get("speed", 0))
        self._extra_combo(
            self.pointer_acceleration,
            [
                (v, "일정하게" if v == "flat" else "움직임에 따라")
                for v in (pointer["acceleration_choices"] if pointer else [])
            ],
            values.get("acceleration"),
        )
        self.pointer_acceleration.set_sensitive(bool(pointer and pointer["acceleration_choices"]))
        for key, control in self.pointer_flags.items():
            control.set_sensitive(key in values)
            control.set_active(values.get(key, False))

    def _shortcuts_filter(self):
        if "input" not in self.extra_data:
            return
        query = self.shortcut_search.get_text().casefold()
        self._extra_combo(
            self.shortcut_choice,
            [
                (i, row["name"])
                for i, row in enumerate(self.extra_data["input"]["shortcuts"])
                if query in (row["name"] + " " + row["action"]).casefold()
            ],
        )
        self._shortcut_choose()

    def _shortcut_choose(self):
        selected = self.shortcut_choice.get_active_id()
        if "input" in self.extra_data and selected is not None:
            self.shortcut_sequence.set_text(
                self.extra_data["input"]["shortcuts"][int(selected)]["sequence"].split(",")[0]
            )

    def _shortcut_settings(self):
        selected = self.extra_data["input"]["shortcuts"][int(self.shortcut_choice.get_active_id())]
        return {
            "shortcut": {
                "component": selected["component"],
                "action": selected["action"],
                "sequence": self.shortcut_sequence.get_text(),
            }
        }

    def _make_network(self):
        scroll, body = self._extra_page("연결과 원격", "network")
        self.network_devices = label("연결을 확인하는 중…", "muted")
        body.pack_start(self.network_devices, False, False, 0)
        self.network_connection = combo()
        row(body, "저장된 연결", self.network_connection)
        actions = Gtk.Box(spacing=10)
        button(
            actions,
            "이 네트워크에 연결하기",
            lambda: self._extra_apply(
                "network", lambda: {"connection": self.network_connection.get_active_id()}
            ),
            True,
        )
        body.pack_start(actions, False, False, 0)
        self.network_tailnets = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.pack_start(self.network_tailnets, False, False, 0)
        self.himmel_status = label("", "muted")
        body.pack_start(self.himmel_status, False, False, 0)
        actions = Gtk.Box(spacing=10)
        self.himmel_open_button = button(
            actions, "힘멜 데스크탑 열기", lambda: self._extra_action("network", "himmel_open")
        )
        body.pack_start(actions, False, False, 0)
        return scroll

    def _fill_network(self, data):
        names = [
            r["connection"]
            for r in data["devices"]
            if r["kind"] in ("wifi", "ethernet") and r["connection"] != "--"
        ]
        self.network_devices.set_text(
            "연결 중: " + ", ".join(names) if names else "연결된 Wi-Fi나 유선 네트워크가 없어요."
        )
        self._extra_combo(
            self.network_connection,
            [(r["id"], r["name"] + (" · 연결 중" if r["active"] else "")) for r in data["connections"]],
            next((r["id"] for r in data["connections"] if r["active"]), None),
        )
        for child in self.network_tailnets.get_children():
            self.network_tailnets.remove(child)
        for tailnet in data["tailnets"]:
            title = "개인 Tailscale" if tailnet["id"] == "personal" else "랩 Tailscale"
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.get_style_context().add_class("quiet-panel")
            box.set_border_width(16)
            state = "연결됨" if tailnet["state"] == "Running" else "연결 확인 필요"
            box.pack_start(label(title + " · " + state, "section-title"), False, False, 0)
            devices = [
                r["name"] + (" · 온라인" if r["online"] else " · 오프라인") for r in tailnet["devices"]
            ]
            box.pack_start(label("\n".join(devices) or "확인한 기기가 없어요.", "muted"), False, False, 0)
            self.network_tailnets.pack_start(box, False, False, 0)
        self.himmel_status.set_text(
            "힘멜 · Tailscale 온라인" if data["himmel"]["online"] else "힘멜 · 연결 상태 확인 필요"
        )
        self.himmel_open_button.set_sensitive(data["himmel"]["can_open"])

    def _make_history(self):
        scroll, body = self._extra_page(
            "변경 기록", "history", "누가 무엇을 바꿨는지 확인하고 변경 직전 값으로 돌아가요."
        )
        self.history_rows = Gtk.ListBox()
        self.history_rows.set_selection_mode(Gtk.SelectionMode.SINGLE)
        body.pack_start(self.history_rows, False, False, 0)
        self.history_selected = None
        self.history_rows.connect("row-selected", self._history_selected)
        self.history_details = label("변경을 선택해 주세요.", "muted")
        body.pack_start(self.history_details, False, False, 0)
        actions = Gtk.Box(spacing=10)
        self.history_revert_button = button(
            actions,
            "변경 직전으로 돌아가기",
            lambda: self._extra_action("history", "settings_revert", identifier=self.history_selected),
            True,
        )
        self.history_revert_button.set_sensitive(False)
        button(actions, "중단된 변경 복원하기", lambda: self._extra_action("history", "settings_recover"))
        body.pack_start(actions, False, False, 0)
        return scroll

    def _fill_history(self, data):
        for child in self.history_rows.get_children():
            self.history_rows.remove(child)
        self.history_selected = None
        self.history_revert_button.set_sensitive(False)
        if not data:
            self.history_rows.add(label("아직 변경 기록이 없어요.", "muted"))
        statuses = {
            "applied": "적용",
            "reverted": "복원함",
            "restored": "복원 실행",
            "failed": "실패 후 복원",
            "recovered": "중단 후 복원",
        }
        for record in data:
            item = Gtk.ListBoxRow()
            item.record = record
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.set_border_width(12)
            box.pack_start(label(record["title"]), False, False, 0)
            box.pack_start(
                label(
                    record["actor_label"]
                    + " · "
                    + datetime.fromisoformat(record["at"]).astimezone().strftime("%m월 %d일 %H:%M:%S")
                    + " · "
                    + statuses.get(record["status"], "확인 필요"),
                    "muted",
                ),
                False,
                False,
                0,
            )
            item.add(box)
            self.history_rows.add(item)

    def _history_selected(self, _list, selected):
        record = getattr(selected, "record", None)
        self.history_selected = record["id"] if record else None
        self.history_revert_button.set_sensitive(bool(record and record["reversible"]))
        if record:
            self.history_details.set_text("\n".join(history_summary(c) for c in record["components"]))


def history_summary(component):
    area, before, after = component["area"], component["before"], component.get("after") or {}
    if area == "power":
        names = {
            "quiet": "조용함",
            "balanced": "균형",
            "performance": "성능",
            "auto": "자동",
            "custom": "사용자 지정",
            "restore": "원래 설정",
        }
        if "mode" in before:
            return (
                "전원: "
                + names.get(before["mode"], before["mode"])
                + " → "
                + names.get(after.get("mode"), "이전 설정")
            )
    if area == "display":
        maximum = before.get("maximum", 187)
        old = round(before["brightness"] / maximum * 100)
        new = round(after.get("brightness", before["brightness"]) / maximum * 100)
        return f"화면 밝기: {old}% → {new}%"
    if area == "panels" and "panel" in before:
        names = {"top": "위", "bottom": "아래", "left": "왼쪽", "right": "오른쪽"}
        previous, changed = before["panel"], after.get("panel", before["panel"])
        titles = {
            "location": "위치",
            "height": "크기",
            "hiding": "숨김",
            "length_mode": "길이",
            "alignment": "정렬",
        }
        names.update(
            none="항상 표시",
            autohide="자동 숨김",
            dodgewindows="창과 겹칠 때",
            windowsgobelow="창 위",
            left="왼쪽",
            right="오른쪽",
            center="가운데",
            fit="내용에 맞춤",
            fill="화면에 맞춤",
            custom="사용자 지정",
        )
        return "패널: " + ", ".join(
            f"{titles[k]} {names.get(str(v), v)} → {names.get(str(changed.get(k)), changed.get(k))}"
            for k, v in previous.items()
            if k in titles
        )
    if area == "panels":
        return (
            "위젯: "
            + str(len(before["widgets"]))
            + "개 → "
            + str(len(after.get("widgets", before["widgets"])))
            + "개"
        )
    if area == "style":
        keys = {
            "color_scheme": "시스템 색",
            "plasma_style": "패널 스타일",
            "icons": "아이콘",
            "cursor": "커서",
            "cursor_size": "커서 크기",
            "font": "글꼴",
            "fixed_font": "고정폭 글꼴",
            "lock_image": "잠금 화면 배경",
            "decoration_library": "창 장식",
        }

        def display_style(key, value):
            if not value:
                return "기본값"
            if key in ("font", "fixed_font"):
                parts = value.split(",")
                return parts[0] + (" · " + parts[1] + "pt" if len(parts) > 1 else "")
            if key == "lock_image":
                return "선택한 이미지"
            if key == "decoration_library":
                return "Breeze" if value == "org.kde.breeze" else "설치된 창 장식"
            return value

        return "OS 스타일:\n" + "\n".join(
            f"{keys[k]}: {display_style(k, v)} → {display_style(k, after.get('values', {}).get(k))}"
            for k, v in before["values"].items()
            if k in keys
        )
    if area == "audio":
        values = []
        for old, new in zip(before.get("devices", []), after.get("devices", []), strict=False):
            title = "스피커" if old["kind"] == "sink" else "마이크"
            old_volume = round(max(old["channels"], default=0) / 65536 * 100)
            new_volume = round(max(new["channels"], default=0) / 65536 * 100)
            values.append(f"{title}: {old_volume}% → {new_volume}%" + (" · 음소거" if new["muted"] else ""))
        return "\n".join(values) or "앱 소리 설정"
    if area == "windows":
        lines = []
        for index, old in enumerate(before.get("windows", []), 1):
            new = next((w for w in after.get("windows", []) if w["fingerprint"] == old["fingerprint"]), old)

            def position(window):
                rect = window["rect"]
                return f"{rect['width']}×{rect['height']} ({rect['x']}, {rect['y']})"

            lines.append(f"창 {index}: {position(old)} → {position(new)}")
        if "desktop_names" in before:
            lines.append(
                "작업공간 이름: "
                + ", ".join(before["desktop_names"])
                + " → "
                + ", ".join(after.get("desktop_names", []))
            )
        if "current_desktop" in before:
            destination = after.get("current_desktop", before["current_desktop"]) + 1
            lines.append(f"작업공간: {before['current_desktop'] + 1} → {destination}")
        return "\n".join(lines)
    if area == "input":
        if "shortcut" in before:
            return (
                "단축키: "
                + (sequence_text(before["shortcut"]["keys"]) or "없음")
                + " → "
                + (sequence_text(after.get("shortcut", before["shortcut"])["keys"]) or "없음")
            )
        titles = {
            "speed": "속도",
            "acceleration": "가속",
            "natural_scroll": "자연스러운 스크롤",
            "tap": "탭 클릭",
            "disable_while_typing": "입력 중 끄기",
        }

        def value(key, row):
            raw = row["values"]
            if key == "speed":
                return str(round(struct.unpack("=f", struct.pack("=I", raw[0]))[0] * 100))
            if key == "acceleration":
                return "움직임에 따라" if raw[0] else "일정하게"
            return "켜짐" if raw[0] else "꺼짐"

        old = before["pointer"]["properties"]
        new = after.get("pointer", before["pointer"])["properties"]
        return "\n".join(f"{titles[k]}: {value(k, v)} → {value(k, new.get(k, v))}" for k, v in old.items())
    if area == "network":

        def connections(snapshot):
            return (
                ", ".join(
                    snapshot.get("names", {}).get(identifier, "저장된 연결")
                    for identifier in snapshot.get("previous", [])
                )
                or "연결 없음"
            )

        return "네트워크: " + connections(before) + " → " + connections(after)
    if area == "session" and "session_restore" in before:
        names = {
            None: "종료 전 앱 복원 (기본값)",
            "restorePreviousLogout": "종료 전 앱 복원",
            "restoreSavedSession": "수동 저장한 세션 복원",
            "emptySession": "꺼짐",
        }
        old = before["session_restore"]["mode"]
        new = after.get("session_restore", before["session_restore"])["mode"]
        return "세션 복원: " + names.get(old, str(old)) + " → " + names.get(new, str(new))
    if area == "session" and "notifications_muted" in before:
        return (
            "알림: "
            + ("숨김" if before["notifications_muted"] else "표시")
            + " → "
            + ("숨김" if after.get("notifications_muted") else "표시")
        )
    return AREAS[area]
