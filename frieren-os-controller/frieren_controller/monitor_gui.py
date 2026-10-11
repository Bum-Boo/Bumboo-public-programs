"""Display page for the shared local controller API."""

from __future__ import annotations

import math
import time
from functools import partial

from gi.repository import Gtk

from .client import call as api_call
from .monitor import DEFAULTS, PRESETS, capture_layout

call = partial(api_call, _source="gui")


def text(value, style=None):
    widget = Gtk.Label(label=value, xalign=0)
    widget.set_line_wrap(True)
    if style:
        widget.get_style_context().add_class(style)
    return widget


class MonitorPage:
    def _make_monitor_page(self):
        self.monitor_status_data = None
        self.monitor_loading = False
        self.monitor_token = 0
        self.monitor_pending = None
        self.monitor_layout_signature = None
        self.monitor_rows = []
        self.monitor_deadline = 0
        self.monitor_last_read = 0
        self.monitor_external_loading = False
        self.monitor_external_mutating = False
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        body.get_style_context().add_class("quiet-panel")
        for edge in ("top", "bottom", "start", "end"):
            getattr(body, "set_margin_" + edge)(28)
        scroll.add(body)
        heading = Gtk.Box(spacing=12)
        heading.pack_start(text("화면", "page-title"), True, True, 0)
        self.monitor_reset_button = Gtk.Button(label="기본값으로")
        self.monitor_reset_button.set_tooltip_text("처음 저장한 밝기·색온도·화면 구성으로 되돌려요.")
        self.monitor_reset_button.connect(
            "clicked", lambda *_: self._monitor_change("monitor_reset", refill=True)
        )
        heading.pack_end(self.monitor_reset_button, False, False, 0)
        body.pack_start(heading, False, False, 0)
        self.monitor_summary = text("화면을 불러오는 중…", "card-value")
        body.pack_start(self.monitor_summary, False, False, 0)
        self.monitor_error = text("", "error")
        self.monitor_error.set_no_show_all(True)
        body.pack_start(self.monitor_error, False, False, 0)

        self.monitor_confirm_bar = Gtk.Box(spacing=12)
        self.monitor_confirm_bar.get_style_context().add_class("card")
        self.monitor_confirm_bar.set_no_show_all(True)
        self.monitor_countdown = text("", "section-title")
        self.monitor_confirm_bar.pack_start(self.monitor_countdown, True, True, 0)
        for keep, title in ((False, "되돌리기"), (True, "유지하기")):
            button = Gtk.Button(label=title)
            if keep:
                button.get_style_context().add_class("suggested-action")
            button.connect("clicked", lambda _, keep=keep: self._monitor_confirm(keep))
            self.monitor_confirm_bar.pack_end(button, False, False, 0)
        body.pack_start(self.monitor_confirm_bar, False, False, 0)

        settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        settings.get_style_context().add_class("card")
        self.monitor_settings_box = settings
        settings.pack_start(text("프리셋", "section-title"), False, False, 0)
        presets = Gtk.Box(spacing=10, homogeneous=True)
        self.monitor_preset_buttons = {}
        for key, title in (
            ("work", "작업"),
            ("night", "야간"),
            ("presentation", "발표"),
            ("battery", "배터리"),
        ):
            button = Gtk.Button(label=title)
            button.get_style_context().add_class("preset")
            button.connect("clicked", lambda _, key=key: self._monitor_select(key))
            self.monitor_preset_buttons[key] = button
            presets.pack_start(button, True, True, 0)
        settings.pack_start(presets, False, False, 0)
        preset_row = Gtk.Box(spacing=12)
        self.monitor_preset_combo = Gtk.ComboBoxText()
        for key, title in (
            ("work", "작업"),
            ("night", "야간"),
            ("presentation", "발표"),
            ("battery", "배터리"),
            ("custom", "저장한 사용자 지정"),
        ):
            self.monitor_preset_combo.append(key, title)
        self.monitor_preset_combo.set_active_id("work")
        self.monitor_preset_combo.connect("changed", self._monitor_preset_selected)
        preset_row.pack_start(self.monitor_preset_combo, False, False, 0)
        apply_preset = Gtk.Button(label="프리셋 적용하기")
        apply_preset.connect(
            "clicked",
            lambda *_: self._monitor_change(
                "monitor_preset", refill=True, name=self.monitor_preset_combo.get_active_id()
            ),
        )
        preset_row.pack_start(apply_preset, False, False, 0)
        settings.pack_start(preset_row, False, False, 0)
        settings.pack_start(
            text("발표는 밝기 100%로 바꾸고 60분 동안 화면을 켜둬요.", "muted"), False, False, 0
        )
        settings.pack_start(Gtk.Separator(), False, False, 0)
        settings.pack_start(text("사용자 지정", "section-title"), False, False, 0)
        grid = Gtk.Grid(column_spacing=20, row_spacing=16)
        self.monitor_brightness = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 100, 1)
        self.monitor_brightness.set_digits(0)
        self.monitor_brightness.set_hexpand(True)
        self.monitor_brightness.connect("format-value", lambda _, value: f"{value:.0f}%")
        self.monitor_night_enabled = Gtk.CheckButton(label="야간 모드 켜기")
        self.monitor_temperature = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 2500, 6500, 100)
        self.monitor_temperature.set_digits(0)
        self.monitor_temperature.connect("format-value", lambda _, value: f"{value:.0f} K")
        self.monitor_scheduled = Gtk.CheckButton(label="정한 시간에만 켜기")
        times = Gtk.Box(spacing=10)
        self.monitor_start = Gtk.Entry()
        self.monitor_end = Gtk.Entry()
        for entry, title in ((self.monitor_start, "시작"), (self.monitor_end, "종료")):
            entry.set_width_chars(7)
            entry.set_max_length(5)
            times.pack_start(text(title), False, False, 0)
            times.pack_start(entry, False, False, 0)
        self.monitor_auto_brightness = Gtk.CheckButton(label="전원 연결이 바뀌면 밝기 자동 조절")
        self.monitor_ac = Gtk.SpinButton.new_with_range(5, 100, 1)
        self.monitor_battery = Gtk.SpinButton.new_with_range(5, 100, 1)
        for index, (title, widget) in enumerate(
            (
                ("밝기", self.monitor_brightness),
                ("색온도", self.monitor_temperature),
                ("야간 모드", self.monitor_night_enabled),
                ("시간 예약", self.monitor_scheduled),
                ("예약 시각", times),
                ("자동 밝기", self.monitor_auto_brightness),
                ("충전 중 밝기 · %", self.monitor_ac),
                ("배터리 밝기 · %", self.monitor_battery),
            )
        ):
            grid.attach(text(title), 0, index, 1, 1)
            grid.attach(widget, 1, index, 1, 1)
        settings.pack_start(grid, False, False, 0)
        self.monitor_apply = Gtk.Button(label="저장하고 적용하기")
        self.monitor_apply.get_style_context().add_class("suggested-action")
        self.monitor_apply.set_halign(Gtk.Align.START)
        self.monitor_apply.connect(
            "clicked",
            lambda *_: self._monitor_change(
                "monitor_configure", refill=True, settings=self._monitor_settings()
            ),
        )
        settings.pack_start(self.monitor_apply, False, False, 0)
        body.pack_start(settings, False, False, 0)

        temporary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        temporary.get_style_context().add_class("card")
        temporary.pack_start(text("잠시 바꾸기", "section-title"), False, False, 0)
        self.monitor_temporary_box = temporary
        self.monitor_temporary_status = text("", "muted")
        temporary.pack_start(self.monitor_temporary_status, False, False, 0)
        for kind, title, default, ceiling in (
            ("awake", "화면 켜두기", 60, 240),
            ("color", "원래 색 보기", 10, 120),
        ):
            row = Gtk.Box(spacing=12)
            row.pack_start(text(title), True, True, 0)
            spin = Gtk.SpinButton.new_with_range(1, ceiling, 1)
            spin.set_value(default)
            setattr(self, "monitor_" + kind + "_minutes", spin)
            row.pack_start(spin, False, False, 0)
            row.pack_start(text("분"), False, False, 0)
            op = "monitor_keep_awake" if kind == "awake" else "monitor_original_color"
            start = Gtk.Button(label="시작하기")
            start.connect(
                "clicked",
                lambda _, op=op, spin=spin: self._monitor_change(op, minutes=spin.get_value_as_int()),
            )
            end = Gtk.Button(label="해제하기")
            end.connect("clicked", lambda _, op=op: self._monitor_change(op, minutes=0))
            row.pack_start(start, False, False, 0)
            row.pack_start(end, False, False, 0)
            temporary.pack_start(row, False, False, 0)
        temporary.pack_start(
            text("화면 잠금과 컴퓨터 절전 설정은 그대로 적용돼요.", "muted"), False, False, 0
        )
        body.pack_start(temporary, False, False, 0)

        layout_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        layout_panel.get_style_context().add_class("card")
        layout_panel.pack_start(text("화면 구성", "section-title"), False, False, 0)
        layout_panel.pack_start(
            text("변경 후 15초 안에 유지하기를 누르세요. 시간이 끝나면 되돌려요.", "muted"), False, False, 0
        )
        self.monitor_layout_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        layout_panel.pack_start(self.monitor_layout_box, False, False, 0)
        layout_actions = Gtk.Box(spacing=10)
        for arrangement, title in (("extend", "오른쪽으로 확장"), ("clone", "같은 화면으로 배치")):
            button = Gtk.Button(label=title)
            button.connect("clicked", lambda _, key=arrangement: self._monitor_arrange(key))
            layout_actions.pack_start(button, False, False, 0)
        self.monitor_layout_apply = Gtk.Button(label="화면 구성 적용하기")
        self.monitor_layout_apply.connect(
            "clicked",
            lambda *_: self._monitor_change("monitor_preview_layout", layout=self._monitor_layout()),
        )
        layout_actions.pack_end(self.monitor_layout_apply, False, False, 0)
        layout_panel.pack_start(layout_actions, False, False, 0)
        self.monitor_layout_actions = layout_actions
        body.pack_start(layout_panel, False, False, 0)
        external = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        external.get_style_context().add_class("card")
        external_heading = Gtk.Box(spacing=12)
        external_heading.pack_start(text("외장 모니터", "section-title"), True, True, 0)
        scan = Gtk.Button(label="연결 확인하기")
        scan.connect("clicked", lambda *_: self._monitor_external_scan())
        external_heading.pack_end(scan, False, False, 0)
        external.pack_start(external_heading, False, False, 0)
        self.monitor_external_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.monitor_external_box.pack_start(
            text("외장 모니터를 연결한 뒤 확인해 주세요.", "muted"), False, False, 0
        )
        external.pack_start(self.monitor_external_box, False, False, 0)
        body.pack_start(external, False, False, 0)
        self._monitor_fill_settings(DEFAULTS)
        self._monitor_sensitive(False)
        return scroll

    def _monitor_select(self, name):
        self.monitor_preset_combo.set_active_id(name)
        self._monitor_preset_selected()

    def _monitor_preset_selected(self, *_):
        name = self.monitor_preset_combo.get_active_id()
        for key, button in self.monitor_preset_buttons.items():
            context = button.get_style_context()
            (context.add_class if key == name else context.remove_class)("selected")
        settings = (self.monitor_status_data or {}).get("custom") if name == "custom" else PRESETS.get(name)
        if settings:
            self._monitor_fill_settings(settings)

    def _monitor_settings(self):
        return {
            "brightness": round(self.monitor_brightness.get_value()),
            "night_enabled": self.monitor_night_enabled.get_active(),
            "temperature": round(self.monitor_temperature.get_value()),
            "scheduled": self.monitor_scheduled.get_active(),
            "start": self.monitor_start.get_text(),
            "end": self.monitor_end.get_text(),
            "auto_brightness": self.monitor_auto_brightness.get_active(),
            "ac_brightness": self.monitor_ac.get_value_as_int(),
            "battery_brightness": self.monitor_battery.get_value_as_int(),
        }

    def _monitor_fill_settings(self, settings):
        for key, widget in (
            ("brightness", self.monitor_brightness),
            ("temperature", self.monitor_temperature),
            ("ac_brightness", self.monitor_ac),
            ("battery_brightness", self.monitor_battery),
        ):
            widget.set_value(settings[key])
        for key, widget in (
            ("night_enabled", self.monitor_night_enabled),
            ("scheduled", self.monitor_scheduled),
            ("auto_brightness", self.monitor_auto_brightness),
        ):
            widget.set_active(settings[key])
        self.monitor_start.set_text(settings["start"])
        self.monitor_end.set_text(settings["end"])

    def _monitor_sensitive(self, enabled):
        self.monitor_settings_box.set_sensitive(enabled and not self.monitor_pending)
        self.monitor_temporary_box.set_sensitive(enabled)
        self.monitor_layout_box.set_sensitive(enabled and not self.monitor_pending)
        self.monitor_layout_actions.set_sensitive(enabled and not self.monitor_pending)
        self.monitor_reset_button.set_sensitive(
            enabled and bool((self.monitor_status_data or {}).get("has_baseline"))
        )
        self.monitor_confirm_bar.set_sensitive(enabled)

    def _load_monitor(self):
        if self.busy or self.monitor_loading:
            return
        self.monitor_loading = True
        self.monitor_token += 1
        token = self.monitor_token
        self._work(
            "",
            lambda: call("monitor_status"),
            lambda status: self._monitor_result(token, status, False, False),
            lambda error: self._monitor_failure(token, error),
        )

    def _monitor_tick(self):
        if self.monitor_pending:
            remaining = max(0, math.ceil(self.monitor_deadline - time.monotonic()))
            self.monitor_countdown.set_text(f"이 화면을 유지할까요? {remaining}초")
        if self._page_index() == 4 and time.monotonic() - self.monitor_last_read >= (
            1 if self.monitor_pending else 5
        ):
            self._load_monitor()
        return True

    def _monitor_change(self, operation, refill=False, **args):
        if self.busy:
            return
        self.busy = True
        self.monitor_token += 1
        token = self.monitor_token
        self._monitor_sensitive(False)
        self._work(
            "",
            lambda: call(operation, **args),
            lambda status: self._monitor_result(
                token,
                status,
                True,
                refill,
                operation in ("monitor_reset", "monitor_preview_layout", "monitor_confirm_layout"),
            ),
            lambda error: self._monitor_failure(token, error, True),
        )

    def _monitor_result(self, token, status, changed, refill, relayout=False):
        if token != self.monitor_token:
            return False
        self.monitor_loading = False
        self.monitor_last_read = time.monotonic()
        if changed:
            self.busy = False
        initial = self.monitor_status_data is None
        self.monitor_status_data = status
        names = {
            "work": "작업",
            "night": "야간",
            "presentation": "발표",
            "battery": "배터리",
            "custom": "사용자 지정",
            "original": "기본값",
        }
        brightness = status.get("brightness")
        night = status.get("night") or {}
        screen_names = ", ".join(row["name"] for row in status["outputs"])
        self.monitor_summary.set_text(
            f"{names.get(status['preset'], '화면')}  ·  "
            + (f"밝기 {brightness['percent']}%" if brightness else "밝기 확인 필요")
            + f"  ·  {night.get('currentTemperature', '—')} K\n{screen_names}"
        )
        if initial or refill:
            self.monitor_preset_combo.set_active_id(
                status["preset"] if status["preset"] != "original" else "work"
            )
            settings = dict(status["settings"])
            if status["preset"] == "original":
                settings.update(
                    brightness=max(5, brightness["percent"]) if brightness else 80,
                    night_enabled=night.get("enabled", False),
                )
            self._monitor_fill_settings(settings)
        signature = tuple((row["name"], tuple(m["id"] for m in row["modes"])) for row in status["outputs"])
        topology_changed = signature != self.monitor_layout_signature
        if initial or topology_changed:
            self._monitor_external_scan()
        pending_finished = self.monitor_pending is not None and status.get("pending") is None
        if topology_changed or relayout or pending_finished:
            self._monitor_fill_layout(status["outputs"])
            self.monitor_layout_signature = signature
        self.monitor_pending = status.get("pending")
        if self.monitor_pending:
            self.monitor_deadline = time.monotonic() + self.monitor_pending["remaining"]
            self.monitor_countdown.set_text(f"이 화면을 유지할까요? {self.monitor_pending['remaining']}초")
            for child in self.monitor_confirm_bar.get_children():
                child.show_all()
            self.monitor_confirm_bar.show()
        else:
            self.monitor_confirm_bar.hide()
        temporary = []
        for key, title in (("hold_remaining", "화면 켜두기"), ("color_remaining", "원래 색 보기")):
            if status[key]:
                temporary.append(f"{title} {math.ceil(status[key] / 60)}분 남음")
        self.monitor_temporary_status.set_text(
            " · ".join(temporary) or "정한 시간이 끝나면 자동으로 해제해요."
        )
        self.monitor_error.set_text(status.get("error", ""))
        self.monitor_error.set_visible(bool(status.get("error")))
        self._monitor_sensitive(True)
        if not status.get("error"):
            self._ready("")
        if changed:
            self._saved()
        return False

    def _monitor_failure(self, token, error, changed=False):
        if token != self.monitor_token:
            return False
        self.monitor_loading = False
        if changed:
            self.busy = False
        self.monitor_error.set_text(error)
        self.monitor_error.show()
        self._monitor_sensitive(self.monitor_status_data is not None)
        self.monitor_last_read = time.monotonic()
        return False

    def _monitor_fill_layout(self, outputs):
        for child in self.monitor_layout_box.get_children():
            self.monitor_layout_box.remove(child)
        self.monitor_rows = []
        first_primary = None
        for state in capture_layout(outputs):
            output = next(row for row in outputs if row["name"] == state["name"])
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            row = Gtk.Box(spacing=12)
            enabled = Gtk.CheckButton(label=state["name"])
            enabled.set_active(state["enabled"])
            row.pack_start(enabled, False, False, 0)
            primary = Gtk.RadioButton.new_with_label_from_widget(first_primary, "주 화면")
            first_primary = first_primary or primary
            row.pack_end(primary, False, False, 0)
            section.pack_start(row, False, False, 0)
            controls = Gtk.Box(spacing=10)
            mode = Gtk.ComboBoxText()
            for item in sorted(
                output["modes"], key=lambda m: (-m["size"]["width"], -m["size"]["height"], -m["refreshRate"])
            ):
                mode.append(
                    item["id"],
                    f"{item['size']['width']}×{item['size']['height']}  ·  {item['refreshRate']:.2f} Hz",
                )
            mode.set_active_id(state["mode"] or (output["preferredModes"] or [output["modes"][0]["id"]])[0])
            controls.pack_start(mode, True, True, 0)
            rotation = Gtk.ComboBoxText()
            for key, title in (
                ("none", "정방향"),
                ("left", "왼쪽 90°"),
                ("right", "오른쪽 90°"),
                ("inverted", "180°"),
            ):
                rotation.append(key, title)
            rotation.set_active_id(state["rotation"])
            controls.pack_start(rotation, False, False, 0)
            section.pack_start(controls, False, False, 0)
            position = Gtk.Box(spacing=10)
            x = Gtk.SpinButton.new_with_range(0, 16000, 1)
            y = Gtk.SpinButton.new_with_range(0, 16000, 1)
            x.set_value(state["x"])
            y.set_value(state["y"])
            for title, spin in (("가로 위치", x), ("세로 위치", y)):
                position.pack_start(text(title, "muted"), False, False, 0)
                position.pack_start(spin, False, False, 0)
            section.pack_start(position, False, False, 0)
            self.monitor_layout_box.pack_start(section, False, False, 0)
            self.monitor_rows.append(
                {
                    "name": state["name"],
                    "enabled": enabled,
                    "primary": primary,
                    "mode": mode,
                    "rotation": rotation,
                    "x": x,
                    "y": y,
                    "output": output,
                }
            )
        for state, widgets in zip(capture_layout(outputs), self.monitor_rows, strict=True):
            if state["primary"]:
                widgets["primary"].set_active(True)
        self.monitor_layout_box.show_all()

    def _monitor_layout(self):
        return [
            {
                "name": row["name"],
                "enabled": row["enabled"].get_active(),
                "primary": row["primary"].get_active(),
                "mode": row["mode"].get_active_id(),
                "rotation": row["rotation"].get_active_id(),
                "x": row["x"].get_value_as_int(),
                "y": row["y"].get_value_as_int(),
            }
            for row in self.monitor_rows
        ]

    def _monitor_arrange(self, arrangement):
        enabled = [row for row in self.monitor_rows if row["enabled"].get_active()]
        common = None
        if arrangement == "clone":
            for row in enabled:
                sizes = {(mode["size"]["width"], mode["size"]["height"]) for mode in row["output"]["modes"]}
                common = sizes if common is None else common & sizes
            if not common:
                self.monitor_error.set_text("같이 쓸 해상도가 없어요. 화면별 해상도를 직접 골라 주세요.")
                self.monitor_error.show()
                return
            size = max(common, key=lambda pair: pair[0] * pair[1])
            for row in enabled:
                mode = max(
                    (m for m in row["output"]["modes"] if (m["size"]["width"], m["size"]["height"]) == size),
                    key=lambda m: m["refreshRate"],
                )
                row["mode"].set_active_id(mode["id"])
                row["rotation"].set_active_id("none")
        offset = 0
        for row in enabled:
            row["x"].set_value(offset if arrangement == "extend" else 0)
            row["y"].set_value(0)
            mode = next(m for m in row["output"]["modes"] if m["id"] == row["mode"].get_active_id())
            offset += mode["size"][
                "height" if row["rotation"].get_active_id() in ("left", "right") else "width"
            ]

    def _monitor_confirm(self, keep):
        if self.monitor_pending:
            self._monitor_change("monitor_confirm_layout", token=self.monitor_pending["token"], keep=keep)

    def _monitor_external_scan(self):
        if self.monitor_external_loading:
            return
        self.monitor_external_loading = True
        self._work(
            "",
            lambda: call("monitor_external_status"),
            self._monitor_external_render,
            self._monitor_external_failure,
        )

    def _monitor_external_failure(self, error):
        self.monitor_external_loading = False
        if self.monitor_external_mutating:
            self.busy = False
            self.monitor_external_mutating = False
        self.monitor_external_box.set_sensitive(True)
        self.monitor_error.set_text(error)
        self.monitor_error.show()
        return False

    def _monitor_external_render(self, status):
        self.monitor_external_loading = False
        if self.monitor_external_mutating:
            self.busy = False
            self.monitor_external_mutating = False
        self.monitor_external_box.set_sensitive(True)
        for child in self.monitor_external_box.get_children():
            self.monitor_external_box.remove(child)
        if not status["displays"]:
            self.monitor_external_box.pack_start(text(status["message"], "muted"), False, False, 0)
        for device in status["displays"]:
            self.monitor_external_box.pack_start(text(device["name"], "section-title"), False, False, 0)
            for feature, title in (("brightness", "밝기"), ("contrast", "명암"), ("input", "입력")):
                row = Gtk.Box(spacing=12)
                row.pack_start(text(title), True, True, 0)
                current = device["features"][feature]
                if current is None or (feature == "input" and not device["inputs"]):
                    row.pack_start(text("이 항목을 조절할 수 없어요.", "muted"), False, False, 0)
                else:
                    if feature == "input":
                        widget = Gtk.ComboBoxText()
                        for item in device["inputs"]:
                            widget.append(str(item["value"]), item["name"])
                        widget.set_active_id(str(current["value"]))
                    else:
                        widget = Gtk.SpinButton.new_with_range(5 if feature == "brightness" else 0, 100, 1)
                        widget.set_value(current["value"])
                    row.pack_start(widget, False, False, 0)
                    apply = Gtk.Button(label="전환하기" if feature == "input" else "적용하기")
                    apply.connect(
                        "clicked",
                        lambda _, feature=feature, identifier=device["id"], widget=widget: (
                            self._monitor_external_apply(identifier, feature, widget)
                        ),
                    )
                    row.pack_start(apply, False, False, 0)
                self.monitor_external_box.pack_start(row, False, False, 0)
            reset = Gtk.Button(label="이 모니터 기본값으로")
            reset.set_sensitive(device["has_baseline"])
            reset.set_halign(Gtk.Align.START)
            reset.connect(
                "clicked",
                lambda _, identifier=device["id"]: self._monitor_external_change(
                    "monitor_external_reset", identifier=identifier
                ),
            )
            self.monitor_external_box.pack_start(reset, False, False, 0)
        self.monitor_external_box.show_all()
        return False

    def _monitor_external_apply(self, identifier, feature, widget):
        if feature == "input":
            choice = widget.get_active_id()
            if choice is None:
                return
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.NONE,
                text="모니터 입력을 바꿀까요?",
            )
            dialog.format_secondary_text("화면이 안 보이면 모니터 버튼으로 원래 입력을 골라 주세요.")
            dialog.add_button("닫기", Gtk.ResponseType.CANCEL)
            dialog.add_button("전환하기", Gtk.ResponseType.OK)
            response = dialog.run()
            dialog.destroy()
            if response != Gtk.ResponseType.OK:
                return
            value = int(choice)
        else:
            value = widget.get_value_as_int()
        self._monitor_external_change(
            "monitor_external_set", identifier=identifier, feature=feature, value=value
        )

    def _monitor_external_change(self, operation, **args):
        if self.busy or self.monitor_external_loading:
            return
        self.busy = True
        self.monitor_external_loading = True
        self.monitor_external_mutating = True
        self.monitor_external_box.set_sensitive(False)

        def run():
            call(operation, **args)
            return call("monitor_external_status")

        self._work("", run, self._monitor_external_render, self._monitor_external_failure)
