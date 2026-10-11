"""Lightweight GTK 3 interface to the local controller API."""

from __future__ import annotations

import json
import threading
from functools import partial
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .appearance_gui import AppearancePage  # noqa: E402
from .client import call as api_call  # noqa: E402
from .core import ControllerError  # noqa: E402
from .desktop_gui import EXTRA_NAV, DesktopPages  # noqa: E402
from .jobs import job_protected  # noqa: E402
from .jobs_gui import JobPages  # noqa: E402
from .monitor_gui import MonitorPage  # noqa: E402
from .themes import THEMES, theme_css  # noqa: E402

call = partial(api_call, _source="gui")

CSS_TEMPLATE = b"""
* { font-family: "Noto Sans CJK KR", sans-serif; }
label { color: @text; }
window, stack, scrolledwindow, dialog { background: @background; color: @text; }
menu, menuitem, cellview, list, row, treeview.view, .view { color: @text; }
menu, .menu { background: @surface; color: @text; border-color: @border; }
menuitem:hover { background: @selected; color: @text; }
menuitem:hover label, menuitem:hover cellview { color: @text; }
placessidebar, placessidebar list, filechooser .sidebar { background: @sidebar; color: @text; }
placessidebar row { background: transparent; color: @text; }
row:selected, treeview.view:selected, .view:selected { background: @selected; color: @text; }
row:selected label, row:selected .muted, row:selected .faint { color: @text; }
entry selection, textview text selection { background: @selected; color: @text; }
tooltip { background: @surface; color: @text; border-color: @border; }
tooltip label { color: @text; }
notebook > header { background: @sidebar; border-bottom: 1px solid @border; }
notebook > header > tabs > tab { background: @surface; padding: 8px 18px;
    border: 1px solid @border; border-radius: 8px 8px 0 0; }
notebook > header > tabs > tab:checked { background: @selected; border-bottom-color: @primary; }
notebook > header > tabs > tab label { color: @text; }
notebook > header > tabs > tab:checked label { color: @primary; font-weight: 700; }
headerbar { background: @sidebar; border-bottom: 1px solid @border; min-height: 48px; }
headerbar label, headerbar image { color: @text; }
headerbar button { border-radius: 8px; }
.sidebar { background: @sidebar; border-right: 1px solid @border; }
.brand { color: @accent; font-size: 11px; font-weight: 800; letter-spacing: 2px; }
.brand-name { color: @primary; font-family: "Noto Serif CJK KR", serif; font-size: 18px; font-weight: 700; }
.nav-list { background: transparent; }
.nav-list row { margin: 3px 12px; border-radius: 9px; min-height: 45px; border-left: 3px solid transparent;
    background: transparent;
    transition: background-color 140ms ease-out, border-color 140ms ease-out; }
.nav-list row:hover { background: @surface; }
.nav-list row:selected { background: @selected; border-left: 3px solid @primary; }
.nav-list row label, .nav-list row image { color: @muted; }
.nav-list row:selected label, .nav-list row:selected image { color: @primary; font-weight: 700; }
.page-title { color: @primary; font-size: 24px; font-weight: 800; }
.section-title { color: @text; font-size: 16px; font-weight: 700; }
.muted { color: @muted; font-size: 12px; }
.card { background: @surface; border: 1px solid @border; border-radius: 12px; padding: 20px; }
.card image { color: @cyan; }
.card.healthy image { color: @healthy; }
.card-title { color: @muted; font-size: 12px; font-weight: 700; }
.card-value { color: @text; font-size: 20px; font-weight: 700; }
.metric-value { color: @primary; font-size: 25px; font-weight: 800; }
.metric-card { background: @surface; border: 1px solid @border; border-radius: 12px; padding: 17px; }
.detail-title { color: @text; font-size: 17px; font-weight: 700; }
.detail-panel { background: @surface; border: 1px solid @border; border-radius: 12px; padding: 18px; }
.detail-panel label, .quiet-panel label { color: @text; }
.detail-panel .muted, .quiet-panel .muted { color: @muted; }
.quiet-panel .card-title { color: @muted; }
.quiet-panel .metric-value { color: @primary; }
.statusbar { background: @sidebar; border-top: 1px solid @border; }
.error, .card-value.error { color: @error; }
button.suggested-action { background: @accent; border-color: @accent; color: @background; }
button.suggested-action label { color: @background; }
button.suggested-action:disabled { background: @border; border-color: @border; }
button.suggested-action:disabled label { color: @muted; }
.hero { background: @surface; border: 1px solid @border; border-radius: 14px; }
.hero-resize:hover, .hero-resize:focus { background: @selected; border-radius: 6px; }
button { background: @surface; color: @text; border: 1px solid @border; box-shadow: none;
    transition: background-color 140ms ease-out, border-color 140ms ease-out; }
button:hover { background: @selected; }
button:disabled { color: @faint; }
button:active, button:checked { background: @selected; color: @text; transition-duration: 90ms; }
button:active label, button:checked label { color: @text; }
.saved-icon { color: @healthy; }
@keyframes card-arrive { from { opacity: 0; } to { opacity: 1; } }
.card-enter { animation: card-arrive 220ms ease-out both; }
.card-row-1 { animation-delay: 40ms; }
.card-row-2 { animation-delay: 80ms; }
.card-row-3 { animation-delay: 120ms; }
.nav-list row image { color: @cyan; }
.card-icon { background: transparent; border: none; box-shadow: none; padding: 0; }
.theme-choice { padding: 5px 8px; border-radius: 8px; }
.theme-choice:checked { background: @selected; }
popover { background: @surface; color: @text; border-color: @border; }
treeview.view, textview.view, textview text, entry, spinbutton { background: @background; color: @text; }
treeview.view:selected { background: @selected; color: @text; }
button, combobox button { color: @text; }
headerbar button.titlebutton { background: transparent; border-color: transparent; }
headerbar button.window-control { background: transparent; border-color: transparent; padding: 5px;
    min-width: 18px; min-height: 18px; }
headerbar button.window-control:hover { background: @selected; }
button.suggested-action:hover { background: shade(@accent, 0.92); }
button.suggested-action, button.suggested-action label { color: @background; }
button.suggested-action:active, button.suggested-action:checked { background: @accent; }
button:disabled, button.suggested-action:disabled { background: @surface; color: @muted; }
button:disabled label, button.suggested-action:disabled label { color: @muted; }
button.preset { padding: 14px; border-radius: 10px; }
button.preset.selected { background: @selected; border-color: @accent; }
button.preset.selected .muted { color: @text; }
button.preset image { color: @cyan; }
scale trough { background: @border; }
scale highlight { background: @accent; }
scale value { color: @text; }
switch:checked { background: @accent; }
"""


CSS = theme_css("night", CSS_TEMPLATE)


def label(text: str, style: str | None = None) -> Gtk.Label:
    widget = Gtk.Label(label=text, xalign=0)
    widget.set_line_wrap(True)
    if style:
        widget.get_style_context().add_class(style)
    return widget


class ControllerWindow(JobPages, DesktopPages, AppearancePage, MonitorPage, Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, *, preferences_path: Path | None = None):
        super().__init__(application=app, title="프리렌 OS 컨트롤러")
        self.set_icon_name("io.github.BumBoo.FrierenOSController")
        self.set_default_size(1220, 780)
        self.set_size_request(960, 600)
        self.busy = False
        self.switch_guard = False
        self.selected: dict | None = None
        self.pages: dict[str, dict] = {}
        self.search_source = 0
        self.quiet_last_status = None
        self.quiet_effects = False
        self.quiet_loading = False
        self.quiet_token = 0
        self.dashboard_loaded = False
        self.feedback_source = 0
        self.preferences_path = preferences_path or Path.home() / ".local/state/frieren-os-controller/ui.json"
        try:
            preferences = json.loads(self.preferences_path.read_text())
        except (OSError, ValueError):
            preferences = {}
        self.preferences = preferences if isinstance(preferences, dict) else {}
        hero_height = self.preferences.get("hero_height")
        self.hero_height = max(96, min(600, hero_height)) if type(hero_height) is int else 200
        self.hero_drag_start = None
        self.reduce_motion = self.preferences.get("reduce_motion") is True
        theme_name = self.preferences.get("theme")
        self.theme_name = theme_name if isinstance(theme_name, str) and theme_name in THEMES else "night"
        self.theme_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.theme_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
        )
        self.motion_css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.motion_css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 2
        )

        header = Gtk.HeaderBar()
        header.set_show_close_button(False)
        header.props.title = "프리렌 OS 컨트롤러"
        for icon, title, action in (
            ("window-close-symbolic", "닫기", lambda *_: self.close()),
            ("window-maximize-symbolic", "최대화", lambda *_: self._maximize()),
            ("window-minimize-symbolic", "최소화", lambda *_: self.iconify()),
        ):
            button = Gtk.Button()
            picture = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU)
            picture.set_pixel_size(16)
            button.set_image(picture)
            button.set_tooltip_text(title)
            button.get_style_context().add_class("window-control")
            button.connect("clicked", action)
            header.pack_end(button)
        motion_menu = Gtk.MenuButton()
        motion_menu.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        motion_menu.set_tooltip_text("화면 설정")
        popover = Gtk.Popover.new(motion_menu)
        self.settings_popover = popover
        settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        settings_box.set_border_width(14)
        settings_box.pack_start(label("테마", "section-title"), False, False, 4)
        first_choice = None
        self.theme_choices = {}
        for key, theme in THEMES.items():
            choice = Gtk.RadioButton.new_from_widget(first_choice)
            first_choice = first_choice or choice
            choice.get_style_context().add_class("theme-choice")
            row = Gtk.Box(spacing=12)
            swatch = Gtk.EventBox()
            swatch.set_size_request(24, 24)
            swatch.set_valign(Gtk.Align.CENTER)
            swatch_css = Gtk.CssProvider()
            swatch_css.load_from_data(
                ("* { background: " + theme["colors"]["accent"] + "; border-radius: 12px; }").encode()
            )
            swatch.get_style_context().add_provider(swatch_css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 3)
            row.pack_start(swatch, False, False, 0)
            row.pack_start(label(theme["name"]), True, True, 0)
            choice.add(row)
            choice.set_active(key == self.theme_name)
            self.theme_choices[key] = choice
            settings_box.pack_start(choice, False, False, 0)
        for key, choice in self.theme_choices.items():
            choice.connect("toggled", self._theme_toggled, key)
        settings_box.pack_start(Gtk.Separator(), False, False, 9)
        motion_toggle = Gtk.CheckButton(label="움직임 줄이기")
        motion_toggle.set_active(self.reduce_motion)
        motion_toggle.connect("toggled", self._motion_toggled)
        settings_box.pack_start(motion_toggle, False, False, 3)
        popover.add(settings_box)
        settings_box.show_all()
        motion_menu.set_popover(popover)
        header.pack_end(motion_menu)
        self.saved_feedback = Gtk.Revealer()
        self.saved_feedback.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.saved_feedback.set_transition_duration(160)
        saved_icon = Gtk.Image.new_from_icon_name("object-select-symbolic", Gtk.IconSize.BUTTON)
        saved_icon.get_style_context().add_class("saved-icon")
        saved_icon.set_tooltip_text("저장했어요")
        self.saved_feedback.add(saved_icon)
        header.pack_end(self.saved_feedback)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("현재 화면 새로고침")
        refresh.connect("clicked", lambda *_: self.refresh())
        header.pack_end(refresh)
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        outer.pack_start(content, True, True, 0)
        content.pack_start(self._make_sidebar(), False, False, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(180)
        content.pack_start(self.stack, True, True, 0)

        self.dashboard_scroll = Gtk.ScrolledWindow()
        self.dashboard_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        dashboard_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        dashboard_body.set_margin_top(24)
        dashboard_body.set_margin_bottom(24)
        dashboard_body.set_margin_start(28)
        dashboard_body.set_margin_end(28)
        dashboard_body.pack_start(self._make_hero(), False, False, 0)
        dashboard_body.pack_start(label("시스템 상태", "section-title"), False, False, 0)
        self.card_grid = Gtk.FlowBox()
        self.card_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.card_grid.set_homogeneous(True)
        self.card_grid.set_max_children_per_line(2)
        self.card_grid.set_min_children_per_line(2)
        self.card_grid.set_row_spacing(16)
        self.card_grid.set_column_spacing(16)
        dashboard_body.pack_start(self.card_grid, False, False, 0)
        self.dashboard_scroll.add(dashboard_body)
        self.stack.add_named(self.dashboard_scroll, "0")

        for kind in ("service", "timer"):
            page = self._make_unit_page(kind)
            self.pages[kind] = page
            self.stack.add_named(page["root"], "1" if kind == "service" else "2")
        self.stack.add_named(self._make_quiet_page(), "3")
        self.stack.add_named(self._make_monitor_page(), "4")
        self.stack.add_named(self._make_appearance_page(), "5")
        self._make_extra_pages()

        statusbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.statusbar = statusbar
        statusbar.get_style_context().add_class("statusbar")
        self.message = label("", "muted")
        self.message.set_margin_start(18)
        self.message.set_margin_top(7)
        self.message.set_margin_bottom(7)
        statusbar.pack_start(self.message, True, True, 0)
        self.error_revealer = Gtk.Revealer()
        self.error_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.error_revealer.set_transition_duration(160)
        self.error_revealer.add(statusbar)
        outer.pack_end(self.error_revealer, False, False, 0)
        self.stack.connect("notify::visible-child-name", self._on_page_changed)
        self.nav.connect("row-selected", self._on_nav_selected)
        self.nav.select_row(self.nav.get_row_at_index(0))
        self.quiet_refresh_source = GLib.timeout_add_seconds(5, self._quiet_tick)
        self.monitor_refresh_source = GLib.timeout_add_seconds(1, self._monitor_tick)
        self.connect("destroy", self._on_destroy)
        self.motion_setting_handler = Gtk.Settings.get_default().connect(
            "notify::gtk-enable-animations", self._sync_motion
        )
        self._sync_motion()
        self._apply_theme()
        self.show_all()
        self.refresh()

    def _on_destroy(self, *_args):
        GLib.source_remove(self.quiet_refresh_source)
        GLib.source_remove(self.monitor_refresh_source)
        if self.feedback_source:
            GLib.source_remove(self.feedback_source)
        Gtk.Settings.get_default().disconnect(self.motion_setting_handler)
        Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(), self.motion_css)
        Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(), self.theme_provider)

    def _maximize(self):
        if self.is_maximized():
            self.unmaximize()
        else:
            self.maximize()

    def _motion_toggled(self, toggle):
        self.reduce_motion = toggle.get_active()
        self._sync_motion()
        self._save_preferences()

    def _theme_toggled(self, choice, name):
        if choice.get_active():
            self.theme_name = name
            self._apply_theme()
            self._save_preferences()

    def _apply_theme(self):
        theme = THEMES[self.theme_name]
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-theme-name", "Breeze-Dark" if theme["dark"] else "Breeze")
        settings.set_property("gtk-application-prefer-dark-theme", theme["dark"])
        settings.set_property("gtk-icon-theme-name", "Papirus-Dark" if theme["dark"] else "Papirus")
        self.theme_provider.load_from_data(theme_css(self.theme_name, CSS_TEMPLATE))
        path = Path.home() / "Pictures/frieren-wallpapers" / theme["wallpaper"]
        has_wallpaper = path.is_file()
        image = 'url("' + path.as_uri() + '")' if has_wallpaper else "none"
        self.hero_frame.set_visible(has_wallpaper)
        self.hero_provider.load_from_data(
            (
                ".hero { background-image: "
                + image
                + "; background-size: cover; background-position: "
                + theme["position"]
                + "; }"
            ).encode()
        )

    def _save_preferences(self):
        self.preferences.update(
            {"theme": self.theme_name, "reduce_motion": self.reduce_motion, "hero_height": self.hero_height}
        )
        try:
            self.preferences_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = self.preferences_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.preferences) + "\n")
            temporary.chmod(0o600)
            temporary.replace(self.preferences_path)
        except OSError:
            self._failure("화면 설정 저장 실패")

    def _sync_motion(self, *_args):
        enabled = not self.reduce_motion and Gtk.Settings.get_default().get_property("gtk-enable-animations")
        self.stack.set_transition_duration(180 if enabled else 0)
        self.saved_feedback.set_transition_duration(160 if enabled else 0)
        self.error_revealer.set_transition_duration(160 if enabled else 0)
        self.motion_css.load_from_data(b"" if enabled else b"* { transition-duration: 0s; animation: none; }")

    def _saved(self):
        if self.feedback_source:
            GLib.source_remove(self.feedback_source)
        self.saved_feedback.set_reveal_child(True)
        self.feedback_source = GLib.timeout_add(1200, self._hide_saved)

    def _hide_saved(self):
        self.feedback_source = 0
        self.saved_feedback.set_reveal_child(False)
        return False

    def _page_index(self):
        return int(self.stack.get_visible_child_name() or "0")

    def _make_sidebar(self) -> Gtk.Widget:
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.get_style_context().add_class("sidebar")
        sidebar.set_size_request(216, -1)
        brand = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        brand.set_margin_start(24)
        brand.set_margin_top(30)
        brand.set_margin_bottom(37)
        brand.pack_start(label("FRIEREN", "brand"), False, False, 0)
        brand.pack_start(label("OS 컨트롤러", "brand-name"), False, False, 0)
        sidebar.pack_start(brand, False, False, 0)
        self.nav = Gtk.ListBox()
        self.nav.get_style_context().add_class("nav-list")
        self.nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for title, icon in (
            ("대시보드", "view-grid-symbolic"),
            ("서비스", "applications-system-symbolic"),
            ("타이머", "alarm-symbolic"),
            ("전원과 온도", "battery-symbolic"),
            ("화면", "video-display-symbolic"),
            ("배경과 터미널", "preferences-desktop-wallpaper-symbolic"),
            *EXTRA_NAV,
        ):
            row = Gtk.ListBoxRow()
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=13)
            line.set_margin_start(14)
            line.set_margin_end(14)
            picture = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU)
            picture.set_pixel_size(28)
            line.pack_start(picture, False, False, 0)
            line.pack_start(label(title), True, True, 0)
            row.add(line)
            self.nav.add(row)
        nav_scroll = Gtk.ScrolledWindow()
        nav_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        nav_scroll.add(self.nav)
        sidebar.pack_start(nav_scroll, True, True, 0)
        return sidebar

    def _on_nav_selected(self, _nav, row):
        if row is not None:
            self.stack.set_visible_child_name(str(row.get_index()))

    def _make_hero(self) -> Gtk.Widget:
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.hero_frame = frame
        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.hero = hero
        hero.set_size_request(-1, self.hero_height)
        hero.get_style_context().add_class("hero")
        self.hero_provider = Gtk.CssProvider()
        hero.get_style_context().add_provider(self.hero_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)
        frame.pack_start(hero, False, False, 0)
        handle = Gtk.EventBox()
        self.hero_resize_handle = handle
        handle.set_can_focus(True)
        handle.set_tooltip_text("위아래로 드래그해 이미지 크기를 조절해요. 방향키로도 조절할 수 있어요.")
        handle.get_accessible().set_name("이미지 높이 조절")
        handle.get_style_context().add_class("hero-resize")
        handle.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        grip = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        grip.set_size_request(48, 2)
        grip.set_halign(Gtk.Align.CENTER)
        grip.set_margin_top(7)
        grip.set_margin_bottom(7)
        handle.add(grip)
        handle.connect(
            "realize",
            lambda widget: widget.get_window().set_cursor(
                Gdk.Cursor.new_from_name(widget.get_display(), "ns-resize")
            ),
        )
        handle.connect("button-press-event", self._hero_resize_begin)
        handle.connect("motion-notify-event", self._hero_resize_motion)
        handle.connect("button-release-event", self._hero_resize_end)
        handle.connect("grab-broken-event", self._hero_resize_end)
        handle.connect("key-press-event", self._hero_resize_key)
        frame.pack_start(handle, False, False, 0)
        frame.show_all()
        frame.set_no_show_all(True)
        return frame

    def _set_hero_height(self, height):
        self.hero_height = max(96, min(600, round(height)))
        self.hero.set_size_request(-1, self.hero_height)

    def _hero_resize_begin(self, handle, event):
        if event.button != 1:
            return False
        handle.grab_focus()
        self.hero_drag_start = (event.y_root, self.hero_height)
        return True

    def _hero_resize_motion(self, _handle, event):
        if self.hero_drag_start is None:
            return False
        origin, height = self.hero_drag_start
        self._set_hero_height(height + event.y_root - origin)
        return True

    def _hero_resize_end(self, _handle, event):
        if event.type == Gdk.EventType.BUTTON_RELEASE and event.button != 1:
            return False
        if self.hero_drag_start is None:
            return False
        _, initial_height = self.hero_drag_start
        self.hero_drag_start = None
        if initial_height != self.hero_height:
            self._save_preferences()
        return True

    def _hero_resize_key(self, _handle, event):
        if event.keyval not in (Gdk.KEY_Up, Gdk.KEY_Down):
            return False
        self._set_hero_height(self.hero_height + (16 if event.keyval == Gdk.KEY_Down else -16))
        self._save_preferences()
        return True

    def _make_unit_page(self, kind: str) -> dict:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        root.set_margin_start(18)
        root.set_margin_end(18)
        root.pack_start(label("서비스" if kind == "service" else "타이머", "page-title"), False, False, 0)
        toolbar = Gtk.Box(spacing=12)
        toolbar.pack_start(label("범위", "muted"), False, False, 0)
        scope = Gtk.ComboBoxText()
        scope.append("system", "컴퓨터")
        scope.append("user", "내 계정")
        scope.set_active_id("system")
        scope.connect("changed", lambda *_: self._load_list(kind))
        toolbar.pack_start(scope, False, False, 0)
        search = Gtk.SearchEntry()
        search.set_placeholder_text(f"{kind == 'service' and '서비스' or '타이머'} 이름 검색")
        search.connect("search-changed", lambda *_: self._queue_search(kind))
        toolbar.pack_start(search, True, True, 0)
        add = Gtk.Button(label="서비스 추가하기" if kind == "service" else "타이머 추가하기")
        add.connect("clicked", lambda *_: self._edit_job_unit(kind, new=True))
        toolbar.pack_start(add, False, False, 0)
        if kind == "timer":
            cron = Gtk.Button(label="cron 편집하기")
            cron.connect("clicked", lambda *_: self._edit_cron())
            toolbar.pack_start(cron, False, False, 0)
        root.pack_start(toolbar, False, False, 0)

        pane = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        pane.set_position(575)
        root.pack_start(pane, True, True, 0)

        model = Gtk.ListStore(str, str, str, str, bool, bool, str, str)
        view = Gtk.TreeView(model=model)
        view.set_headers_visible(True)
        view.set_enable_search(False)
        for index, title, width in (
            (0, "이름", 220),
            (1, "설명", 175),
            (2, "현재", 76),
            (3, "시작 설정", 78),
        ):
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", 3)
            column = Gtk.TreeViewColumn(title, renderer, text=index)
            column.set_resizable(True)
            column.set_min_width(width)
            view.append_column(column)
        view.get_selection().connect("changed", lambda selection: self._select_unit(kind, selection))
        scroll = Gtk.ScrolledWindow()
        scroll.set_hexpand(True)
        scroll.add(view)
        pane.pack1(scroll, resize=True, shrink=False)

        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        details.get_style_context().add_class("detail-panel")
        details.set_margin_start(24)
        details.set_margin_end(14)
        details.set_margin_top(12)
        title = label("왼쪽에서 항목을 고르세요.", "detail-title")
        details.pack_start(title, False, False, 0)
        description = label("", "muted")
        details.pack_start(description, False, False, 0)
        status = label("")
        details.pack_start(status, False, False, 0)
        switch_row = Gtk.Box(spacing=12)
        switch_row.pack_start(label("부팅/로그인 때 시작"), False, False, 0)
        toggle = Gtk.Switch()
        toggle.set_sensitive(False)
        toggle.connect("notify::active", lambda widget, *_: self._toggle(kind, widget))
        switch_row.pack_end(toggle, False, False, 0)
        details.pack_start(switch_row, False, False, 0)
        details.pack_start(label("이 기능 메모", "card-title"), False, False, 0)
        note_view = Gtk.TextView()
        note_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        note_view.set_left_margin(9)
        note_view.set_right_margin(9)
        note_scroll = Gtk.ScrolledWindow()
        note_scroll.set_min_content_height(140)
        note_scroll.add(note_view)
        details.pack_start(note_scroll, False, False, 0)
        actions = Gtk.Box(spacing=8)
        save = Gtk.Button(label="메모 저장")
        save.set_sensitive(False)
        save.connect("clicked", lambda *_: self._save_note(kind))
        actions.pack_start(save, False, False, 0)
        logs = Gtk.Button(label="최근 로그")
        logs.set_sensitive(False)
        logs.connect("clicked", lambda *_: self._show_logs(kind))
        actions.pack_start(logs, False, False, 0)
        edit = Gtk.Button(label="내용 편집하기")
        edit.set_sensitive(False)
        edit.connect("clicked", lambda *_: self._edit_job_unit(kind))
        actions.pack_start(edit, False, False, 0)
        details.pack_start(actions, False, False, 0)
        pane.pack2(details, resize=False, shrink=False)
        return {
            "root": root,
            "kind": kind,
            "scope": scope,
            "search": search,
            "model": model,
            "view": view,
            "title": title,
            "description": description,
            "status": status,
            "toggle": toggle,
            "note": note_view,
            "save": save,
            "logs": logs,
            "edit": edit,
        }

    def _make_quiet_page(self) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow()
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        body.get_style_context().add_class("quiet-panel")
        body.set_margin_top(28)
        body.set_margin_bottom(28)
        body.set_margin_start(28)
        body.set_margin_end(28)
        scroll.add(body)
        heading = Gtk.Box(spacing=12)
        heading.pack_start(label("전원과 온도", "page-title"), True, True, 0)
        self.quiet_reset_button = Gtk.Button(label="기본값으로")
        self.quiet_reset_button.set_tooltip_text("처음 저장한 CPU·전력 설정으로 되돌려요.")
        self.quiet_reset_button.connect("clicked", self._reset_quiet)
        self.quiet_reset_button.set_sensitive(False)
        heading.pack_end(self.quiet_reset_button, False, False, 0)
        body.pack_start(heading, False, False, 0)

        status = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        status.get_style_context().add_class("card")
        status.set_size_request(430, -1)
        self.quiet_summary = label("불러오는 중…", "card-value")
        self.quiet_details = label("", "muted")
        status.pack_start(self.quiet_summary, False, False, 0)
        status.pack_start(self.quiet_details, False, False, 0)
        body.pack_start(status, False, False, 0)

        metrics = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.quiet_metrics = {}
        for key, title in (
            ("temperature", "CPU 온도"),
            ("usage", "전체 CPU 사용"),
            ("limit", "속도 상한"),
            ("power", "지속 전력 한도"),
        ):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.get_style_context().add_class("metric-card")
            card.pack_start(label(title, "card-title"), False, False, 0)
            value = label("—", "metric-value")
            card.pack_start(value, False, False, 0)
            metrics.pack_start(card, True, True, 0)
            self.quiet_metrics[key] = value
        body.pack_start(metrics, False, False, 0)

        settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        settings.get_style_context().add_class("card")
        settings.pack_start(label("프리셋", "section-title"), False, False, 0)

        presets = Gtk.Box(spacing=10, homogeneous=True)
        self.quiet_preset_buttons = {}
        for mode, name, description, icon in (
            ("quiet", "조용함", "소음과 발열을 줄여요", "weather-clear-night-symbolic"),
            ("balanced", "균형", "평소 작업에 맞춰요", "emblem-default-symbolic"),
            ("performance", "성능", "무거운 작업에 힘을 써요", "power-profile-performance-symbolic"),
        ):
            button = Gtk.Button()
            button.get_style_context().add_class("preset")
            row = Gtk.Box(spacing=12)
            picture = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.DIALOG)
            picture.set_pixel_size(32)
            row.pack_start(picture, False, False, 0)
            copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            copy.pack_start(label(name, "section-title"), False, False, 0)
            copy.pack_start(label(description, "muted"), False, False, 0)
            row.pack_start(copy, True, True, 0)
            button.add(row)
            button.connect("clicked", lambda _button, key=mode: self.quiet_mode.set_active_id(key))
            presets.pack_start(button, True, True, 0)
            self.quiet_preset_buttons[mode] = button
        settings.pack_start(presets, False, False, 0)

        mode_row = Gtk.Box(spacing=12)
        self.quiet_mode = Gtk.ComboBoxText()
        for value, name in (
            ("auto", "자동"),
            ("quiet", "조용함"),
            ("balanced", "균형"),
            ("performance", "성능"),
            ("custom", "사용자 지정"),
            ("restore", "기본값"),
        ):
            self.quiet_mode.append(value, name)
        self.quiet_mode.set_sensitive(False)
        mode_row.pack_start(self.quiet_mode, False, False, 0)
        self.quiet_mode_button = Gtk.Button(label="적용하기")
        self.quiet_mode_button.get_style_context().add_class("suggested-action")
        self.quiet_mode_button.set_sensitive(False)
        self.quiet_mode_button.connect("clicked", self._apply_quiet_mode)
        mode_row.pack_start(self.quiet_mode_button, False, False, 0)
        settings.pack_start(mode_row, False, False, 0)

        self.quiet_custom_expander = Gtk.Expander(label="사용자 지정")
        custom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        custom_box.set_margin_top(14)
        self.quiet_custom_expander.add(custom_box)
        grid = Gtk.Grid(column_spacing=16, row_spacing=14)
        self.quiet_cap = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 25, 100, 1)
        self.quiet_cap.set_digits(0)
        self.quiet_cap.set_hexpand(True)
        self.quiet_cap.set_size_request(200, -1)
        self.quiet_cap.set_value(75)
        self.quiet_cap.connect("format-value", lambda _scale, value: f"{value:.0f}%")
        self.quiet_turbo = Gtk.Switch()
        self.quiet_turbo.set_halign(Gtk.Align.START)
        self.quiet_preference = Gtk.ComboBoxText()
        for value, name in (
            ("power", "절전 우선"),
            ("balance_power", "절전 쪽으로"),
            ("balance_performance", "반응성 쪽으로"),
            ("performance", "성능 우선"),
        ):
            self.quiet_preference.append(value, name)
        self.quiet_preference.set_active_id("balance_performance")
        self.quiet_power_enabled = Gtk.CheckButton(label="전력 한도 직접 정하기")
        self.quiet_power_enabled.set_tooltip_text("끄면 처음 저장한 전력 한도로 돌아가요.")
        self.quiet_power_enabled.connect("toggled", lambda *_: self._quiet_sensitive(not self.busy))
        self.quiet_power = Gtk.SpinButton.new_with_range(10, 45, 0.25)
        self.quiet_boost = Gtk.SpinButton.new_with_range(10, 56.25, 0.25)
        for spin, value in ((self.quiet_power, 28), (self.quiet_boost, 38)):
            spin.set_digits(2)
            spin.set_value(value)
        for index, (name, widget) in enumerate(
            (
                ("CPU 속도 상한", self.quiet_cap),
                ("터보 부스트", self.quiet_turbo),
                ("전력 사용 성향", self.quiet_preference),
                ("지속 전력 한도 · W", self.quiet_power),
                ("순간 전력 한도 · W", self.quiet_boost),
            )
        ):
            grid.attach(label(name), 0, index, 1, 1)
            grid.attach(widget, 1, index, 1, 1)
        custom_box.pack_start(self.quiet_power_enabled, False, False, 0)
        custom_box.pack_start(grid, False, False, 0)
        self.quiet_custom_hint = label("온도가 높아지면 성능을 잠시 낮춰요.", "muted")
        custom_box.pack_start(self.quiet_custom_hint, False, False, 0)
        self.quiet_custom_error = label("", "error")
        self.quiet_custom_error.set_no_show_all(True)
        custom_box.pack_start(self.quiet_custom_error, False, False, 0)
        self.quiet_custom_button = Gtk.Button(label="사용자 설정 적용")
        self.quiet_custom_button.set_halign(Gtk.Align.START)
        self.quiet_custom_button.get_style_context().add_class("suggested-action")
        self.quiet_custom_button.connect("clicked", self._apply_quiet_custom)
        custom_box.pack_start(self.quiet_custom_button, False, False, 0)
        settings.pack_start(self.quiet_custom_expander, False, False, 0)
        self.quiet_mode.connect("changed", self._quiet_mode_selected)

        target_row = Gtk.Box(spacing=12)
        target_row.pack_start(label("자동 모드 목표 온도"), False, False, 0)
        self.quiet_target = Gtk.SpinButton.new_with_range(58, 75, 1)
        self.quiet_target.set_sensitive(False)
        target_row.pack_start(self.quiet_target, False, False, 0)
        target_row.pack_start(label("°C", "muted"), False, False, 0)
        self.quiet_target_button = Gtk.Button(label="저장하기")
        self.quiet_target_button.set_sensitive(False)
        self.quiet_target_button.connect("clicked", self._apply_quiet_target)
        target_row.pack_start(self.quiet_target_button, False, False, 0)
        settings.pack_start(target_row, False, False, 0)
        body.pack_start(settings, False, False, 0)

        effects = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        effects.get_style_context().add_class("card")
        effects_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        effects_text.pack_start(label("화면 효과", "section-title"), False, False, 0)
        effects.pack_start(effects_text, True, True, 0)
        self.quiet_effects_button = Gtk.Button(label="줄이기")
        self.quiet_effects_button.set_sensitive(False)
        self.quiet_effects_button.connect("clicked", self._apply_quiet_effects)
        effects.pack_end(self.quiet_effects_button, False, False, 0)
        body.pack_start(effects, False, False, 0)

        processes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=13)
        processes.get_style_context().add_class("card")
        processes.pack_start(label("지금 CPU를 쓰는 앱", "section-title"), False, False, 0)
        self.quiet_process_labels = []
        for _index in range(6):
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name = label("측정 중…", "muted")
            amount = label("", "muted")
            line.pack_start(name, True, True, 0)
            line.pack_end(amount, False, False, 0)
            processes.pack_start(line, False, False, 0)
            self.quiet_process_labels.append((name, amount))
        body.pack_start(processes, False, False, 0)
        return scroll

    def _quiet_sensitive(self, enabled: bool):
        for widget in (
            self.quiet_mode,
            self.quiet_mode_button,
            self.quiet_target,
            self.quiet_target_button,
            self.quiet_effects_button,
            self.quiet_reset_button,
            *self.quiet_preset_buttons.values(),
        ):
            widget.set_sensitive(enabled)
        status = self.quiet_last_status or {}
        custom = enabled and status.get("capabilities", {}).get("custom", False)
        power = custom and status.get("capabilities", {}).get("power_limits", False)
        for widget in (self.quiet_cap, self.quiet_turbo, self.quiet_preference, self.quiet_custom_button):
            widget.set_sensitive(custom)
        self.quiet_power_enabled.set_sensitive(power)
        self.quiet_power.set_sensitive(power and self.quiet_power_enabled.get_active())
        self.quiet_boost.set_sensitive(power and self.quiet_power_enabled.get_active())
        if self.quiet_mode.get_active_id() == "custom":
            self.quiet_mode_button.set_sensitive(custom)

    def _quiet_mode_selected(self, *_):
        mode = self.quiet_mode.get_active_id()
        for key, button in self.quiet_preset_buttons.items():
            context = button.get_style_context()
            (context.add_class if key == mode else context.remove_class)("selected")
        if mode == "custom":
            self.quiet_custom_expander.set_expanded(True)
        self._quiet_sensitive(not self.busy and self.quiet_last_status is not None)

    def _fill_quiet_custom(self, status):
        settings = status.get("custom") or {}
        if status["mode"] in status.get("presets", {}):
            settings = status["presets"][status["mode"]]
        self.quiet_cap.set_value(settings.get("cap", 75))
        self.quiet_turbo.set_active(settings.get("turbo", False))
        self.quiet_preference.set_active_id(settings.get("preference", "balance_performance"))
        defaults = status.get("power_defaults") or {}
        for spin, key, ceiling in ((self.quiet_power, "power_w", 45), (self.quiet_boost, "boost_w", 56.25)):
            spin.set_range(10, max(10, min(ceiling, defaults.get(key, ceiling))))
            spin.set_value(settings.get(key) or defaults.get(key, 10))
        self.quiet_power_enabled.set_active(settings.get("power_w") is not None)
        self.quiet_custom_error.hide()

    def _load_quiet(self):
        if self.busy or self.quiet_loading:
            return
        self.quiet_loading = True
        self.quiet_token += 1
        token = self.quiet_token
        self._work(
            "전원 상태를 읽는 중…",
            lambda: call("quiet_status"),
            lambda status: self._quiet_result(token, status, False),
            lambda message: self._quiet_failure(token, message, False),
        )

    def _quiet_tick(self):
        if self._page_index() == 3:
            self._load_quiet()
        return True

    def _quiet_result(self, token: int, status: dict, changed: bool):
        if token != self.quiet_token:
            return False
        self.quiet_loading = False
        if changed:
            self.busy = False
        return self._show_quiet(status, changed)

    def _quiet_failure(self, token: int, message: str, changed: bool):
        if token != self.quiet_token:
            return False
        self.quiet_loading = False
        if changed:
            self.busy = False
            self._quiet_sensitive(True)
        else:
            self._quiet_sensitive(False)
            self.quiet_summary.set_text("전원 상태를 확인하지 못했어요")
            self.quiet_details.set_text("새로고침으로 다시 확인해 주세요.")
            self.quiet_details.show()
        return self._failure(message)

    def _show_quiet(self, status: dict, changed: bool):
        temperature = status.get("cpu_c")
        temperature_text = f"{temperature:.0f}°C" if isinstance(temperature, (int, float)) else "온도 없음"
        modes = {
            "auto": "자동",
            "quiet": "조용함",
            "balanced": "균형",
            "performance": "성능",
            "custom": "사용자 지정",
            "restore": "기본값",
        }
        self.quiet_summary.set_text(modes.get(status["mode"], "전원 모드"))
        limits = status.get("limits") or {}
        maximum = limits.get("max_perf_pct")
        reason = status.get("reason") or ""
        if "85°C" in reason:
            detail = "온도가 높아 성능을 잠시 낮췄어요."
        elif "센서" in reason:
            detail = "온도를 확인하지 못했어요."
        else:
            detail = ""
        self.quiet_details.set_text(detail)
        self.quiet_details.set_visible(bool(detail))
        self.quiet_metrics["temperature"].set_text(temperature_text)
        usage = status.get("usage") or {}
        cpu_percent = usage.get("cpu_percent")
        self.quiet_metrics["usage"].set_text(
            f"{cpu_percent:.0f}%" if isinstance(cpu_percent, (int, float)) else "—"
        )
        self.quiet_metrics["limit"].set_text(f"{maximum}%" if maximum is not None else "—")
        power_w = (status.get("power_limits") or {}).get("power_w")
        self.quiet_metrics["power"].set_text(f"{power_w:g} W" if power_w is not None else "—")
        for index, (name, amount) in enumerate(self.quiet_process_labels):
            rows = usage.get("top_processes") or []
            if index < len(rows):
                name.set_text(rows[index]["name"] or "이름 없음")
                amount.set_text(f"{rows[index]['cpu_percent']:.1f}%")
            else:
                name.set_text("측정 중…" if index == 0 else "")
                amount.set_text("")
        if self.quiet_last_status is None or changed:
            self.quiet_mode.set_active_id(status["mode"])
            self.quiet_target.set_value(status.get("target_c", 64))
            self._fill_quiet_custom(status)
        self.quiet_last_status = status
        self.quiet_custom_hint.set_text(
            "온도가 높아지면 성능을 잠시 낮춰요."
            if status.get("capabilities", {}).get("custom")
            else "추가 설정을 쓰려면 전원 기능을 업데이트해 주세요."
        )
        self.quiet_effects = bool(status.get("effects_saving"))
        self.quiet_effects_button.set_label("원래대로" if self.quiet_effects else "줄이기")
        self._quiet_sensitive(True)
        if status.get("error"):
            self._failure(status["error"])
        else:
            self._ready("전원 상태를 확인했어요.")
            if changed:
                self._saved()
        return False

    def _apply_quiet_mode(self, _button):
        mode = self.quiet_mode.get_active_id()
        if not mode or self.busy:
            return
        if mode == "custom":
            return self._apply_quiet_custom(_button)
        if mode == "restore":
            return self._reset_quiet(_button)
        self.busy = True
        self.quiet_token += 1
        token = self.quiet_token
        self._quiet_sensitive(False)
        self._work(
            "전원 모드를 바꾸는 중…",
            lambda: call("quiet_set_mode", mode=mode),
            lambda status: self._quiet_result(token, status, True),
            lambda message: self._quiet_failure(token, message, True),
        )

    def _apply_quiet_custom(self, _button):
        if self.busy or not self.quiet_custom_button.get_sensitive():
            return
        limited = self.quiet_power_enabled.get_active() and self.quiet_power_enabled.get_sensitive()
        settings = {
            "cap": round(self.quiet_cap.get_value()),
            "turbo": self.quiet_turbo.get_active(),
            "preference": self.quiet_preference.get_active_id(),
            "power_w": self.quiet_power.get_value() if limited else None,
            "boost_w": self.quiet_boost.get_value() if limited else None,
        }
        if limited and settings["power_w"] > settings["boost_w"]:
            self.quiet_custom_error.set_text("순간 전력 한도를 지속 전력 한도 이상으로 맞춰 주세요.")
            self.quiet_custom_error.show()
            return
        self._change_quiet("quiet_configure", settings=settings)

    def _reset_quiet(self, _button):
        if not self.busy:
            self._change_quiet("quiet_reset")

    def _change_quiet(self, operation, **arguments):
        self.busy = True
        self.quiet_token += 1
        token = self.quiet_token
        self._quiet_sensitive(False)
        self._work(
            "전원 설정을 바꾸는 중…",
            lambda: call(operation, **arguments),
            lambda status: self._quiet_result(token, status, True),
            lambda message: self._quiet_failure(token, message, True),
        )

    def _apply_quiet_target(self, _button):
        if self.busy:
            return
        temperature = self.quiet_target.get_value_as_int()
        self.busy = True
        self.quiet_token += 1
        token = self.quiet_token
        self._quiet_sensitive(False)
        self._work(
            "목표 온도를 저장하는 중…",
            lambda: call("quiet_set_target", temperature=temperature),
            lambda status: self._quiet_result(token, status, True),
            lambda message: self._quiet_failure(token, message, True),
        )

    def _apply_quiet_effects(self, _button):
        if self.busy:
            return
        enabled = not self.quiet_effects
        self.busy = True
        self.quiet_token += 1
        token = self.quiet_token
        self._quiet_sensitive(False)
        self._work(
            "화면 효과를 바꾸는 중…",
            lambda: call("quiet_set_effects", enabled=enabled),
            lambda status: self._quiet_result(token, status, True),
            lambda message: self._quiet_failure(token, message, True),
        )

    def _work(self, message: str, operation, success, failure=None):

        def run():
            try:
                value = operation()
            except Exception as exc:  # surface transport and systemd errors in the UI
                GLib.idle_add(failure or self._failure, str(exc))
            else:
                GLib.idle_add(success, value)

        threading.Thread(target=run, daemon=True).start()

    def _failure(self, message: str):
        self.last_error = message
        if "연결하지 못" in message:
            message = "연결이 끊겼어요. 다시 시도해 주세요."
        elif "권한" in message or "authentication" in message.lower():
            message = "권한 확인을 완료해 주세요."
        else:
            message = "작업을 완료하지 못했어요. 다시 시도해 주세요."
        self.message.set_text(message)
        self.message.get_style_context().add_class("error")
        self.error_revealer.set_reveal_child(True)
        return False

    def _ready(self, message: str):
        self.message.get_style_context().remove_class("error")
        self.message.set_text("")
        self.error_revealer.set_reveal_child(False)

    def refresh(self):
        index = self._page_index()
        if index == 0:
            self._load_dashboard()
        elif index == 3:
            self._load_quiet()
        elif index == 4:
            self._load_monitor()
        elif index == 5:
            self._load_appearance()
        elif index >= 6:
            self._extra_load_current(force=True)
        else:
            self._load_list("service" if index == 1 else "timer")

    def _on_page_changed(self, *_args):
        index = self._page_index()
        row = self.nav.get_row_at_index(index)
        if row is not None and self.nav.get_selected_row() != row:
            self.nav.select_row(row)
        if index == 0:
            self._load_dashboard()
        elif index == 1:
            self._load_list("service")
        elif index == 2:
            self._load_list("timer")
        elif index == 3:
            self._load_quiet()
        elif index == 4:
            self._load_monitor()
        elif index == 5:
            self._load_appearance()
        elif index >= 6:
            self._extra_load_current()

    def _load_dashboard(self):
        if not self.card_grid.get_children():
            self._render_cards([{"label": "상태 확인 중", "value": "카드를 불러오고 있어요."}])
        self._work("상태를 읽는 중…", lambda: call("dashboard"), self._show_cards)

    def _show_cards(self, cards):
        self._render_cards(cards)
        if self._page_index() == 0:
            self._ready(f"상태 카드 {len(cards)}개를 확인했어요.")
        return False

    def _render_cards(self, cards):
        for child in self.card_grid.get_children():
            self.card_grid.remove(child)
        icons = {
            "failed-services": "dialog-warning-symbolic",
            "freiren-quiet": "battery-symbolic",
            "disk-space": "drive-harddisk-symbolic",
            "journal-space": "document-open-recent-symbolic",
            "package-cache": "package-x-generic-symbolic",
            "orphan-packages": "package-x-generic-symbolic",
            "pcie-errors": "computer-symbolic",
            "graphics": "video-display-symbolic",
        }
        first_data = not self.dashboard_loaded and any(item.get("name") for item in cards)
        for index, item in enumerate(cards):
            titles = {
                "failed-services": "서비스",
                "package-cache": "설치 파일",
                "orphan-packages": "사용하지 않는 패키지",
                "pcie-errors": "장치 통신",
                "graphics": "그래픽",
            }
            title = titles.get(item.get("name"), item["label"])
            text = "확인하지 못했어요" if item.get("error") else item.get("value") or "—"
            if item.get("name") == "failed-services" and not item.get("error"):
                count = len(item.get("details", {}).get("units", []))
                text = "오류 없음" if count == 0 else f"오류 {count}개"
            elif item.get("name") == "orphan-packages" and not item.get("error"):
                text = f"{len(item.get('details', {}).get('packages', []))}개"
            elif item.get("name") == "pcie-errors" and not item.get("error"):
                text = "확인할 기록 있음" if item.get("details", {}).get("last_error") else "오류 기록 없음"
            frame = Gtk.EventBox()
            frame.get_style_context().add_class("card")
            if first_data:
                frame.get_style_context().add_class("card-enter")
                frame.get_style_context().add_class(f"card-row-{min(index // 2, 3)}")
            frame.set_size_request(320, 122)
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
            box.set_margin_top(16)
            box.set_margin_bottom(16)
            box.set_margin_start(20)
            box.set_margin_end(20)
            icon = icons.get(item.get("name"), "view-grid-symbolic")
            if item.get("name") == "failed-services" and text == "오류 없음":
                icon = "object-select-symbolic"
                frame.get_style_context().add_class("healthy")
            picture = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.DIALOG)
            picture.set_pixel_size(44)
            picture.set_valign(Gtk.Align.CENTER)
            picture.get_style_context().add_class("card-icon")
            box.pack_start(picture, False, False, 0)
            copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            copy.set_valign(Gtk.Align.CENTER)
            copy.pack_start(label(title, "card-title"), False, False, 0)
            value = label(text, "card-value")
            if item.get("error"):
                value.get_style_context().add_class("error")
            copy.pack_start(value, False, False, 0)
            box.pack_start(copy, True, True, 0)
            frame.add(box)
            self.card_grid.add(frame)
        self.card_grid.show_all()
        if first_data:
            self.dashboard_loaded = True

    def _queue_search(self, kind: str):
        if self.search_source:
            GLib.source_remove(self.search_source)
        self.search_source = GLib.timeout_add(250, self._search_now, kind)

    def _search_now(self, kind: str):
        self.search_source = 0
        self._load_list(kind)
        return False

    def _load_list(self, kind: str):
        page = self.pages[kind]
        scope = page["scope"].get_active_id()
        if scope is None:
            return
        query = page["search"].get_text()
        self._work(
            f"{kind == 'service' and '서비스' or '타이머'} 목록을 읽는 중…",
            lambda: call("list_units", scope=scope, kind=kind, search=query),
            lambda rows: self._show_list(kind, scope, query, rows),
        )

    def _show_list(self, kind: str, scope: str, query: str, rows):
        page = self.pages[kind]
        if page["scope"].get_active_id() != scope or page["search"].get_text() != query:
            return False
        page["model"].clear()
        selected_iter = None
        selected_unit = self.selected["unit"] if self.selected and self.selected["kind"] == kind else None
        for row in rows:
            active = {"active": "실행 중", "inactive": "중지", "failed": "실패"}.get(row["active"], "확인 중")
            file_state = {
                "enabled": "켜짐",
                "enabled-runtime": "켜짐",
                "disabled": "꺼짐",
                "static": "고정",
                "alias": "별칭",
                "masked": "차단",
            }.get(row["file_state"], "확인 필요")
            iterator = page["model"].append(
                (
                    row["unit"],
                    row["description"],
                    active,
                    file_state,
                    row["enabled"],
                    row["protected"],
                    row["active"],
                    row["file_state"],
                )
            )
            if row["unit"] == selected_unit:
                selected_iter = iterator
        if selected_iter is not None:
            page["view"].get_selection().select_iter(selected_iter)
        self._ready(f"{len(rows)}개 항목을 읽었어요.")
        return False

    def _select_unit(self, kind: str, selection):
        model, index = selection.get_selected()
        if index is None:
            return
        page = self.pages[kind]
        unit = model[index][0]
        scope = page["scope"].get_active_id()
        self.selected = {"scope": scope, "unit": unit, "kind": kind}
        page["title"].set_text(unit)
        page["description"].set_text(model[index][1] or "설명이 없어요.")
        page["status"].set_text(f"현재 {model[index][2]}  ·  시작 설정 {model[index][3]}")
        self.switch_guard = True
        page["toggle"].set_active(model[index][4])
        self.switch_guard = False
        editable = not model[index][5] and model[index][7] in ("enabled", "enabled-runtime", "disabled")
        page["toggle"].set_sensitive(editable)
        page["toggle"].set_tooltip_text(
            "연결이나 로그인에 중요한 항목은 보호돼요." if model[index][5] else None
        )
        page["save"].set_sensitive(True)
        page["logs"].set_sensitive(True)
        page["edit"].set_sensitive(scope == "user" and not job_protected(unit))
        page["edit"].set_tooltip_text("내 계정의 서비스와 타이머를 편집해요.")
        page["note"].get_buffer().set_text("")
        self._work(
            "메모를 읽는 중…",
            lambda: call("get_note", scope=scope, unit=unit),
            lambda text: self._show_note(kind, scope, unit, text),
        )

    def _show_note(self, kind: str, scope: str, unit: str, text: str):
        if self.selected != {"scope": scope, "unit": unit, "kind": kind}:
            return False
        self.pages[kind]["note"].get_buffer().set_text(text)
        self._ready("메모를 읽었어요.")
        return False

    def _selection(self, kind: str) -> dict | None:
        if self.selected and self.selected["kind"] == kind:
            return dict(self.selected)
        return None

    def _toggle(self, kind: str, switch: Gtk.Switch):
        if self.switch_guard:
            return
        selected = self._selection(kind)
        if not selected or self.busy:
            return
        enabled = switch.get_active()
        try:
            call("preview_toggle", scope=selected["scope"], unit=selected["unit"], enabled=enabled)
        except ControllerError as exc:
            self._reset_switch(switch, not enabled)
            self._failure(str(exc))
            return
        action = "켜고 시작" if enabled else "끄고 중지"
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"{selected['unit']}을(를) {action}할까요?",
        )
        dialog.format_secondary_text(
            "지금 시작하고 컴퓨터를 다시 켜도 자동으로 시작해요."
            if enabled
            else "지금 중지하고 자동으로 시작하지 않아요."
        )
        dialog.add_button("닫기", Gtk.ResponseType.CANCEL)
        dialog.add_button("적용하기", Gtk.ResponseType.OK)
        decision = dialog.run()
        dialog.destroy()
        if decision != Gtk.ResponseType.OK:
            self._reset_switch(switch, not enabled)
            return
        self.busy = True
        switch.set_sensitive(False)
        self._work(
            f"{selected['unit']} 변경 중…",
            lambda: call("toggle_unit", scope=selected["scope"], unit=selected["unit"], enabled=enabled),
            lambda result: self._toggle_done(kind, selected, result),
            lambda message: self._toggle_failed(kind, selected, enabled, message),
        )

    def _toggle_failed(self, kind: str, selected: dict, enabled: bool, message: str):
        self.busy = False
        if self._selection(kind) == selected:
            switch = self.pages[kind]["toggle"]
            self._reset_switch(switch, not enabled)
            switch.set_sensitive(True)
        self._failure(message)
        return False

    def _reset_switch(self, switch: Gtk.Switch, enabled: bool):
        self.switch_guard = True
        switch.set_active(enabled)
        self.switch_guard = False

    def _toggle_done(self, kind: str, selected: dict, result: dict):
        self.busy = False
        if self._selection(kind) == selected:
            page = self.pages[kind]
            after = result["after"]
            self._reset_switch(page["toggle"], after["file_state"] in ("enabled", "enabled-runtime"))
            page["toggle"].set_sensitive(True)
            current = "실행 중" if after["active"] == "active" else "중지"
            startup = "켜짐" if after["file_state"] in ("enabled", "enabled-runtime") else "꺼짐"
            page["status"].set_text(f"{current} · 자동 시작 {startup}")
        self._ready("설정을 바꾸고 실제 상태를 확인했어요.")
        self._saved()
        self._load_list(kind)
        return False

    def _save_note(self, kind: str):
        selected = self._selection(kind)
        if not selected:
            return
        buffer = self.pages[kind]["note"].get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        self._work(
            "메모를 저장하는 중…",
            lambda: call("set_note", scope=selected["scope"], unit=selected["unit"], note=text),
            lambda _result: self._note_saved(),
        )

    def _note_saved(self):
        self._ready("메모를 저장했어요.")
        self._saved()
        return False

    def _show_logs(self, kind: str):
        selected = self._selection(kind)
        if not selected:
            return
        self._work(
            "최근 로그를 읽는 중…",
            lambda: call("journal_tail", scope=selected["scope"], unit=selected["unit"], lines=40),
            lambda result: self._logs_dialog(selected, result),
        )

    def _logs_dialog(self, selected: dict, result: dict):
        dialog = Gtk.Dialog(
            title=f"최근 로그 · {selected['unit']}", transient_for=self, flags=Gtk.DialogFlags.MODAL
        )
        dialog.set_default_size(850, 470)
        dialog.add_button("닫기", Gtk.ResponseType.CLOSE)
        scroll = Gtk.ScrolledWindow()
        scroll.set_margin_start(12)
        scroll.set_margin_end(12)
        scroll.set_margin_top(12)
        scroll.set_margin_bottom(12)
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_monospace(True)
        view.get_buffer().set_text(result["text"] or "최근 로그가 없어요.")
        scroll.add(view)
        dialog.get_content_area().pack_start(scroll, True, True, 0)
        dialog.show_all()
        dialog.run()
        dialog.destroy()
        self._ready("최근 로그를 확인했어요.")
        return False


class ControllerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.BumBoo.FrierenOSController")

    def do_activate(self):
        window = self.get_active_window()
        if window is None:
            window = ControllerWindow(self)
        window.present()


def main() -> int:
    return ControllerApp().run(None)
