"""Wallpaper selection and a Konsole preview using the shared controller API."""

from __future__ import annotations

import re
from functools import partial
from pathlib import Path
from urllib.parse import unquote, urlparse

from gi.repository import Gdk, GdkPixbuf, Gtk

from .appearance import DEFAULT_TERMINAL, FILL_MODES, MANAGED
from .client import call as api_call
from .themes import THEMES

call = partial(api_call, _source="gui")


def text(value, style=None):
    widget = Gtk.Label(label=value, xalign=0)
    widget.set_line_wrap(True)
    if style:
        widget.get_style_context().add_class(style)
    return widget


def local_path(value):
    if value.startswith("file://"):
        return unquote(urlparse(value).path)
    return value


def image_title(value):
    name = Path(local_path(value)).name
    return "저장한 배경 이미지" if re.fullmatch(r"[0-9a-f]{64}\.(?:png|jpe?g|webp)", name) else name


class AppearancePage:
    def _make_appearance_page(self):
        self.appearance_data = None
        self.appearance_loading = False
        self.appearance_token = 0
        self.wallpaper_image_path = ""
        self.terminal_image_path = ""
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for edge in ("top", "bottom", "start", "end"):
            getattr(root, "set_margin_" + edge)(28)
        root.pack_start(text("배경과 터미널", "page-title"), False, False, 0)
        self.appearance_error = text("", "error")
        self.appearance_error.set_no_show_all(True)
        root.pack_start(self.appearance_error, False, False, 0)
        notebook = Gtk.Notebook()
        self.appearance_notebook = notebook
        root.pack_start(notebook, True, True, 0)
        self.appearance_panels = []
        for title, maker in (
            ("바탕화면", self._make_wallpaper_panel),
            ("Konsole", self._make_terminal_panel),
        ):
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            panel.get_style_context().add_class("quiet-panel")
            panel.set_border_width(20)
            scroll.add(panel)
            maker(panel)
            self.appearance_panels.append(panel)
            notebook.append_page(scroll, Gtk.Label(label=title))
        self._appearance_sensitive(False)
        return root

    def _make_wallpaper_panel(self, panel):
        row = Gtk.Box(spacing=12)
        row.pack_start(text("적용할 화면"), False, False, 0)
        self.wallpaper_desktop = Gtk.ComboBoxText()
        self.wallpaper_desktop.append("all", "연결된 모든 화면")
        self.wallpaper_desktop.set_active_id("all")
        self.wallpaper_desktop.connect("changed", self._wallpaper_target_changed)
        row.pack_start(self.wallpaper_desktop, False, False, 0)
        panel.pack_start(row, False, False, 0)
        self.wallpaper_current = text("현재 배경을 불러오는 중…", "muted")
        panel.pack_start(self.wallpaper_current, False, False, 0)
        self.wallpaper_preview = Gtk.Image()
        self.wallpaper_preview.set_size_request(-1, 230)
        panel.pack_start(self.wallpaper_preview, False, False, 0)
        self.wallpaper_filename = text("이미지를 선택해 주세요.", "muted")
        self.wallpaper_filename.set_selectable(True)
        panel.pack_start(self.wallpaper_filename, False, False, 0)
        choices = Gtk.Box(spacing=10)
        choices.pack_start(self._image_button("이미지 선택하기", "wallpaper"), False, False, 0)
        for theme in THEMES.values():
            path = Path.home() / "Pictures/frieren-wallpapers" / theme["wallpaper"]
            if path.is_file():
                button = Gtk.Button(label=theme["name"])
                button.connect("clicked", lambda _, path=path: self._appearance_image("wallpaper", str(path)))
                choices.pack_start(button, False, False, 0)
        panel.pack_start(choices, False, False, 0)
        fill_row = Gtk.Box(spacing=12)
        fill_row.pack_start(text("이미지 배치"), False, False, 0)
        self.wallpaper_fill = Gtk.ComboBoxText()
        for key, title in (
            ("crop", "화면 채우기"),
            ("fit", "이미지 전체 보기"),
            ("stretch", "화면 크기에 맞추기"),
            ("center", "가운데 놓기"),
            ("tile", "반복하기"),
        ):
            self.wallpaper_fill.append(key, title)
        self.wallpaper_fill.set_active_id("crop")
        fill_row.pack_start(self.wallpaper_fill, False, False, 0)
        panel.pack_start(fill_row, False, False, 0)
        actions = Gtk.Box(spacing=12)
        self.wallpaper_apply = Gtk.Button(label="배경 적용하기")
        self.wallpaper_apply.get_style_context().add_class("suggested-action")
        self.wallpaper_apply.connect(
            "clicked",
            lambda *_: self._appearance_change(
                "wallpaper_set",
                "wallpaper",
                image=self.wallpaper_image_path,
                desktop_id=self._wallpaper_target(),
                fill=self.wallpaper_fill.get_active_id(),
            ),
        )
        self.wallpaper_reset_button = Gtk.Button(label="원래 배경으로")
        self.wallpaper_reset_button.connect(
            "clicked",
            lambda *_: self._appearance_change(
                "wallpaper_reset",
                "wallpaper",
                desktop_id=self._wallpaper_target(),
            ),
        )
        actions.pack_start(self.wallpaper_apply, False, False, 0)
        actions.pack_start(self.wallpaper_reset_button, False, False, 0)
        panel.pack_start(actions, False, False, 0)
        panel.pack_start(
            text("선택한 이미지는 적용하기를 누를 때 바꿔요. 원래 배경은 따로 저장해요.", "muted"),
            False,
            False,
            0,
        )

    def _make_terminal_panel(self, panel):
        self.terminal_current = text("터미널 설정을 불러오는 중…", "muted")
        panel.pack_start(self.terminal_current, False, False, 0)
        self.terminal_preview = Gtk.Overlay()
        self.terminal_preview.set_size_request(-1, 170)
        self.terminal_preview_box = Gtk.EventBox()
        self.terminal_preview_box.set_name("terminal-preview")
        self.terminal_preview.add(self.terminal_preview_box)
        self.terminal_preview_image = Gtk.EventBox()
        self.terminal_preview_image.set_name("terminal-image")
        self.terminal_preview.add_overlay(self.terminal_preview_image)
        sample = Gtk.Label(xalign=0, yalign=0)
        sample.set_name("terminal-sample")
        sample.set_text("bumboo@frieren ~\n❯ ls\nDocuments  Pictures  Projects\n❯ █")
        sample.set_margin_top(20)
        sample.set_margin_start(24)
        self.terminal_preview.add_overlay(sample)
        self.terminal_preview_css = Gtk.CssProvider()
        self.terminal_preview_box.get_style_context().add_provider(
            self.terminal_preview_css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 5
        )
        self.terminal_preview_image.get_style_context().add_provider(
            self.terminal_preview_css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 5
        )
        sample.get_style_context().add_provider(
            self.terminal_preview_css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 5
        )
        panel.pack_start(self.terminal_preview, False, False, 0)
        panel.pack_start(
            text("색과 배경 이미지 미리보기예요. 창 투명도는 실제 Konsole에서 확인해 주세요.", "muted"),
            False,
            False,
            0,
        )
        grid = Gtk.Grid(column_spacing=22, row_spacing=16)
        self.terminal_background = Gtk.ColorButton()
        self.terminal_foreground = Gtk.ColorButton()
        self.terminal_opacity = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.terminal_image_opacity = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        for widget in (self.terminal_opacity, self.terminal_image_opacity):
            widget.set_digits(0)
            widget.set_hexpand(True)
            widget.connect("format-value", lambda _, value: f"{value:.0f}%")
            widget.connect("value-changed", lambda *_: self._terminal_preview_update())
        for widget in (self.terminal_background, self.terminal_foreground):
            widget.connect("color-set", lambda *_: self._terminal_preview_update())
        for index, (title, widget) in enumerate(
            (
                ("배경색", self.terminal_background),
                ("글자색", self.terminal_foreground),
                ("창 불투명도", self.terminal_opacity),
                ("배경 이미지 농도", self.terminal_image_opacity),
            )
        ):
            grid.attach(text(title), 0, index, 1, 1)
            grid.attach(widget, 1, index, 1, 1)
        panel.pack_start(grid, False, False, 0)
        panel.pack_start(text("창 불투명도 100%는 불투명, 0%는 투명이에요.", "muted"), False, False, 0)
        row = Gtk.Box(spacing=12)
        row.pack_start(self._image_button("배경 이미지 선택하기", "terminal"), False, False, 0)
        clear = Gtk.Button(label="이미지 빼기")
        clear.connect("clicked", lambda *_: self._appearance_image("terminal", ""))
        row.pack_start(clear, False, False, 0)
        panel.pack_start(row, False, False, 0)
        self.terminal_filename = text("배경 이미지 없음", "muted")
        self.terminal_filename.set_selectable(True)
        panel.pack_start(self.terminal_filename, False, False, 0)
        panel.pack_start(
            text("저장한 배경은 새 Konsole 창에 적용해요. 아래 버튼으로 새 창을 여세요.", "muted"),
            False,
            False,
            0,
        )
        actions = Gtk.Box(spacing=12)
        self.terminal_apply = Gtk.Button(label="저장하고 적용하기")
        self.terminal_apply.get_style_context().add_class("suggested-action")
        self.terminal_apply.connect(
            "clicked",
            lambda *_: self._appearance_change(
                "terminal_configure", "terminal", settings=self._terminal_values()
            ),
        )
        self.terminal_reset_button = Gtk.Button(label="원래 설정으로")
        self.terminal_reset_button.connect(
            "clicked", lambda *_: self._appearance_change("terminal_reset", "terminal")
        )
        actions.pack_start(self.terminal_apply, False, False, 0)
        actions.pack_start(self.terminal_reset_button, False, False, 0)
        self.terminal_open_button = Gtk.Button(label="Konsole 열기")
        self.terminal_open_button.connect(
            "clicked", lambda *_: self._appearance_change("terminal_open", "opened")
        )
        actions.pack_start(self.terminal_open_button, False, False, 0)
        panel.pack_start(actions, False, False, 0)
        self.terminal_feedback = text("기존 프로필을 보존하고 새 배경을 별도 프로필로 저장해요.", "muted")
        panel.pack_start(self.terminal_feedback, False, False, 0)
        self._terminal_fill(DEFAULT_TERMINAL)

    def _image_button(self, title, kind):
        button = Gtk.Button(label=title)
        button.connect("clicked", lambda *_: self._appearance_choose_image(kind))
        return button

    def _appearance_choose_image(self, kind):
        dialog = Gtk.FileChooserDialog(
            title="배경 이미지 선택", transient_for=self, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons("닫기", Gtk.ResponseType.CANCEL, "선택하기", Gtk.ResponseType.OK)
        filter_ = Gtk.FileFilter()
        filter_.set_name("PNG, JPG, WebP 이미지")
        for mime in ("image/png", "image/jpeg", "image/webp"):
            filter_.add_mime_type(mime)
        dialog.add_filter(filter_)
        folder = Path.home() / "Pictures"
        if folder.is_dir():
            dialog.set_current_folder(str(folder))
        if dialog.run() == Gtk.ResponseType.OK:
            self._appearance_image(kind, dialog.get_filename())
        dialog.destroy()

    def _appearance_image(self, kind, path):
        setattr(self, kind + "_image_path", path)
        getattr(self, kind + "_filename").set_text(image_title(path) if path else "배경 이미지 없음")
        if kind == "wallpaper":
            try:
                if not path:
                    self.wallpaper_preview.clear()
                else:
                    preview = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 600, 230, True)
                    self.wallpaper_preview.set_from_pixbuf(preview)
            except Exception:
                self.wallpaper_preview.clear()
                self.appearance_error.set_text("이미지를 열지 못했어요. 다른 파일을 선택해 주세요.")
                self.appearance_error.show()
        else:
            self._terminal_preview_update()

    def _wallpaper_target(self):
        value = self.wallpaper_desktop.get_active_id()
        return int(value) if value and value != "all" else None

    def _wallpaper_target_changed(self, *_):
        if not self.appearance_data:
            return
        target = self._wallpaper_target()
        rows = [r for r in self.appearance_data["desktops"] if target is None or r["id"] == target]
        self.wallpaper_current.set_text(
            "\n".join(
                f"화면 {r['screen'] + 1}: " + (image_title(r["image"].get("Image", "")) or "이미지 배경 없음")
                for r in rows
            )
        )
        self._appearance_sensitive(not self.busy and not self.appearance_loading)

    def _terminal_color(self, widget):
        rgba = widget.get_rgba()
        return "#" + "".join(f"{round(v * 255):02x}" for v in (rgba.red, rgba.green, rgba.blue))

    def _terminal_values(self):
        return {
            "background": self._terminal_color(self.terminal_background),
            "foreground": self._terminal_color(self.terminal_foreground),
            "opacity": round(self.terminal_opacity.get_value()),
            "image_opacity": round(self.terminal_image_opacity.get_value()),
            "image": self.terminal_image_path,
        }

    def _terminal_fill(self, settings):
        for key in ("background", "foreground"):
            color = Gdk.RGBA()
            color.parse(settings[key])
            getattr(self, "terminal_" + key).set_rgba(color)
        self.terminal_opacity.set_value(settings["opacity"])
        self.terminal_image_opacity.set_value(settings["image_opacity"])
        self._appearance_image("terminal", settings["image"])

    def _terminal_preview_update(self):
        if not hasattr(self, "terminal_image_opacity"):
            return
        values = self._terminal_values()
        image = (
            'url("' + Path(values["image"]).as_uri() + '")'
            if values["image"] and Path(values["image"]).is_absolute()
            else "none"
        )
        # GTK composites the background over a matching solid color so text remains opaque.
        css = f"""#terminal-preview {{ background-color: {values["background"]}; border-radius: 10px; }}
            #terminal-image {{ background-color: transparent; background-image: {image};
            background-size: cover; background-position: center; border-radius: 10px; }}
            #terminal-sample {{ font-family: "Noto Sans Mono", monospace; font-size: 16px;
            color: {values["foreground"]}; background: transparent; }}"""
        self.terminal_preview_css.load_from_data(css.encode())
        self.terminal_preview_image.set_opacity(values["image_opacity"] / 100 if image != "none" else 0)

    def _appearance_sensitive(self, enabled):
        data = self.appearance_data or {}
        for panel in self.appearance_panels:
            panel.set_sensitive(enabled)
        self.appearance_panels[0].set_sensitive(enabled and bool(data.get("desktops")))
        self.appearance_panels[1].set_sensitive(enabled and not data.get("terminal", {}).get("error"))
        target = self.wallpaper_desktop.get_active_id()
        baseline = data.get("wallpaper_baselines", [])
        self.wallpaper_reset_button.set_sensitive(bool(baseline) if target == "all" else target in baseline)
        self.terminal_reset_button.set_sensitive(bool(data.get("terminal", {}).get("has_baseline")))

    def _load_appearance(self):
        if self.busy or self.appearance_loading:
            return
        self.appearance_loading = True
        self.appearance_token += 1
        token = self.appearance_token
        self._work(
            "",
            lambda: call("appearance_status"),
            lambda data: self._appearance_result(token, data),
            lambda error: self._appearance_failure(token, error),
        )

    def _appearance_change(self, operation, refill, **args):
        if self.busy or self.appearance_loading:
            return
        self.busy = True
        self.appearance_token += 1
        token = self.appearance_token
        self._appearance_sensitive(False)
        self._work(
            "",
            lambda: call(operation, **args),
            lambda data: self._appearance_result(token, data, refill),
            lambda error: self._appearance_failure(token, error),
        )

    def _appearance_result(self, token, data, refill=None):
        if token != self.appearance_token:
            return False
        initial = self.appearance_data is None
        self.appearance_data = data
        self.appearance_loading = False
        if refill:
            self.busy = False
            self._saved()
        self.appearance_error.hide()
        errors = [v for v in (data.get("desktop_error"), data["terminal"].get("error")) if v]
        if errors:
            self.appearance_error.set_text("\n".join(errors))
            self.appearance_error.show()
        target = self.wallpaper_desktop.get_active_id()
        self.wallpaper_desktop.remove_all()
        self.wallpaper_desktop.append("all", "연결된 모든 화면")
        for row in data["desktops"]:
            self.wallpaper_desktop.append(str(row["id"]), f"화면 {row['screen'] + 1}")
        ids = {str(row["id"]) for row in data["desktops"]}
        self.wallpaper_desktop.set_active_id(target if target == "all" or target in ids else "all")
        self._wallpaper_target_changed()
        if initial or refill == "wallpaper":
            rows = [
                r
                for r in data["desktops"]
                if self._wallpaper_target() is None or r["id"] == self._wallpaper_target()
            ]
            if rows:
                self._appearance_image("wallpaper", local_path(rows[0]["image"].get("Image", "")))
                fill = rows[0]["image"].get("FillMode", 2)
                self.wallpaper_fill.set_active_id(
                    next((k for k, v in FILL_MODES.items() if v == fill), "crop")
                )
        terminal = data["terminal"]
        profile = terminal["default_profile"] or "Konsole 기본값"
        title = "저장한 배경" if profile.startswith(MANAGED) else Path(profile).stem
        self.terminal_current.set_text(f"현재 기본 프로필: {title}")
        if initial or refill == "terminal":
            self._terminal_fill(terminal["settings"])
        if refill == "terminal":
            self.terminal_feedback.set_text("저장했어요. Konsole 열기를 누르면 이 설정으로 새 창을 열어요.")
        self._appearance_sensitive(True)
        return False

    def _appearance_failure(self, token, error):
        if token != self.appearance_token:
            return False
        self.busy = False
        self.appearance_loading = False
        self.appearance_error.set_text(error)
        self.appearance_error.show()
        self._appearance_sensitive(True)
        return False
