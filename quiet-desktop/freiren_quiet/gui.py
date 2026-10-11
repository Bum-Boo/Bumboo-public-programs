"""Native GTK UI; the privileged controller keeps working when this window closes."""

from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import __version__  # noqa: E402
from . import client, effects  # noqa: E402
from .monitor import Monitor  # noqa: E402

STYLE = b"""
window { background: #111a24; color: #e4edf5; }
headerbar { background: #172330; border: 0; color: #e4edf5; }
label { color: #e4edf5; }
.muted { color: #9cafbf; font-size: 12px; }
.eyebrow { color: #80d7bc; font-size: 11px; letter-spacing: 1px; }
.heading { font-size: 26px; font-weight: bold; }
.metric { font-size: 32px; font-weight: bold; }
.card { background: #1a2937; border-radius: 12px; padding: 18px; }
.message { background: #203b38; color: #bdeadc; border-radius: 8px; padding: 12px; }
.error { background: #512c32; color: #ffd8d8; }
button:not(.titlebutton) { background: #233547; color: #e4edf5; border: 1px solid #385063;
         border-radius: 8px; padding: 10px 14px; box-shadow: none; text-shadow: none; }
button:not(.titlebutton):hover { background: #30495d; }
button.selected { background: #81d9bc; color: #102c24; border-color: #81d9bc; }
button.selected label { color: #102c24; }
button:disabled { opacity: 0.5; }
spinbutton { background: #233547; color: #e4edf5; border-radius: 6px; }
spinbutton entry { background: #233547; color: #e4edf5; }
separator { background: #304352; min-height: 1px; }
"""


def label(text, css=None, xalign=0):
    widget = Gtk.Label(label=text, xalign=xalign)
    if css:
        widget.get_style_context().add_class(css)
    return widget


class QuietWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Freiren Quiet")
        self.set_default_size(760, 650)
        self.set_border_width(0)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quiet-ui")
        self.monitor = Monitor()
        self.busy = False
        self.closed = False
        self.last_status = None
        self.timer = None
        self.connect("destroy", self.close_worker)

        header = Gtk.HeaderBar(title="Freiren Quiet", subtitle="MSI GL62 6QE · i5-6300HQ")
        header.set_show_close_button(True)
        self.set_titlebar(header)
        restore = Gtk.Button(label="관리 해제")
        restore.set_tooltip_text("설치 전 CPU 설정을 복원하고 자동 조절을 멈춥니다.")
        restore.connect("clicked", lambda _: self.submit("mode", mode="restore"))
        header.pack_end(restore)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin=24)
        self.add(outer)
        title_row = Gtk.Box(spacing=16)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        titles.pack_start(label("FREIREN · 조용한 작업 환경", "eyebrow"), False, False, 0)
        titles.pack_start(label("필요한 성능만, 더 조용하게", "heading"), False, False, 0)
        title_row.pack_start(titles, True, True, 0)
        outer.pack_start(title_row, False, False, 0)

        metrics = Gtk.Box(spacing=12, homogeneous=True)
        self.values = {}
        for key, title in (("temp", "CPU 온도"), ("cpu", "전체 CPU 사용"), ("cap", "속도 상한")):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.get_style_context().add_class("card")
            card.pack_start(label(title, "muted"), False, False, 0)
            self.values[key] = label("—", "metric")
            card.pack_start(self.values[key], False, False, 0)
            metrics.pack_start(card, True, True, 0)
        outer.pack_start(metrics, False, False, 0)

        modes = Gtk.Box(spacing=8, homogeneous=True)
        self.buttons = {}
        for name, title in (
            ("auto", "자동"),
            ("quiet", "조용함"),
            ("balanced", "균형"),
            ("performance", "성능"),
        ):
            button = Gtk.Button(label=title)
            button.connect("clicked", lambda _, selected=name: self.submit("mode", mode=selected))
            modes.pack_start(button, True, True, 0)
            self.buttons[name] = button
        outer.pack_start(modes, False, False, 0)

        target_row = Gtk.Box(spacing=10)
        target_row.pack_start(label("자동 모드 목표 온도", "muted"), False, False, 0)
        self.target = Gtk.SpinButton.new_with_range(58, 75, 1)
        self.target.set_value(64)
        target_row.pack_start(self.target, False, False, 0)
        target_row.pack_start(label("°C", "muted"), False, False, 0)
        apply_button = Gtk.Button(label="적용")
        apply_button.connect(
            "clicked", lambda _: self.submit("target", target=self.target.get_value_as_int())
        )
        target_row.pack_start(apply_button, False, False, 0)
        self.target_help = label("온도를 보며 속도 상한을 40~75%로 조절", "muted")
        target_row.pack_end(self.target_help, False, False, 0)
        outer.pack_start(target_row, False, False, 0)

        self.message = label("전력 제어 서비스에 연결 중…")
        self.message.set_line_wrap(True)
        self.message.get_style_context().add_class("message")
        outer.pack_start(self.message, False, False, 0)

        process_title = Gtk.Box(spacing=8)
        process_title.pack_start(label("지금 CPU를 쓰는 앱"), True, True, 0)
        process_title.pack_end(
            label("전체 4코어 합계 = 100% · 5초마다 갱신", "muted"), False, False, 0
        )
        outer.pack_start(process_title, False, False, 0)
        self.rows = Gtk.Grid(column_spacing=24, row_spacing=7)
        self.process_labels = []
        for index in range(6):
            name, percent = label("—", "muted"), label("", "muted", xalign=1)
            name.set_hexpand(True)
            self.rows.attach(name, 0, index, 1, 1)
            self.rows.attach(percent, 1, index, 1, 1)
            self.process_labels.append((name, percent))
        outer.pack_start(self.rows, True, True, 0)
        outer.pack_start(Gtk.Separator(), False, False, 0)

        footer = Gtk.Box(spacing=10)
        self.effects_button = Gtk.Button()
        self.update_effect_button()
        self.effects_button.set_tooltip_text("KWin의 흐림·대비·투명 효과를 이번 세션에서 줄입니다.")
        self.effects_button.connect("clicked", self.toggle_effects)
        footer.pack_start(self.effects_button, False, False, 0)
        self.details = label("", "muted", xalign=1)
        footer.pack_end(self.details, True, True, 0)
        outer.pack_start(footer, False, False, 0)
        outer.pack_start(
            label("창을 닫아도 자동 조절은 계속됩니다. 팬 속도는 노트북이 관리합니다.", "muted"),
            False,
            False,
            0,
        )

        self.show_all()
        self.submit()
        self.timer = GLib.timeout_add_seconds(5, self.refresh)

    def update_effect_button(self):
        self.effects_button.set_label(
            "화면 효과 복원" if effects.state_path().exists() else "화면 효과 절약"
        )

    def close_worker(self, *_):
        self.closed = True
        if self.timer:
            GLib.source_remove(self.timer)
        self.executor.shutdown(wait=False, cancel_futures=True)

    def refresh(self):
        if not self.closed:
            window = self.get_window()
            if window and not window.get_state() & Gdk.WindowState.ICONIFIED:
                self.submit()
        return not self.closed

    def submit(self, operation="status", **parameters):
        if self.busy or self.closed:
            return
        self.busy = True

        def work():
            try:
                status = client.request(operation, **parameters)
                sample = self.monitor.sample()
                GLib.idle_add(self.render, status, sample, operation != "status")
            except Exception as error:
                GLib.idle_add(self.show_error, str(error))

        self.executor.submit(work)

    def toggle_effects(self, _):
        if self.busy or self.closed:
            return
        self.busy = True

        def work():
            try:
                effects.set_savings(not effects.state_path().exists())
                GLib.idle_add(self.effects_done)
            except Exception as error:
                GLib.idle_add(self.show_error, str(error))

        self.executor.submit(work)

    def effects_done(self):
        if self.closed:
            return False
        self.busy = False
        self.update_effect_button()
        self.submit()
        return False

    def show_error(self, error):
        if self.closed:
            return False
        self.busy = False
        self.message.set_text(error)
        self.message.get_style_context().add_class("error")
        return False

    def render(self, status, sample, changed=False):
        if self.closed:
            return False
        self.busy = False
        initial = self.last_status is None
        self.last_status = status
        self.values["temp"].set_text(
            f"{status['cpu_c']:.0f}°C" if status["cpu_c"] is not None else "—"
        )
        self.values["cpu"].set_text(f"{sample['cpu_percent']:.0f}%")
        self.values["cap"].set_text(f"{status['limits']['max_perf_pct']}%")
        if initial or changed:
            self.target.set_value(status["target_c"])
        self.message.set_text(status["error"] or status["reason"])
        context = self.message.get_style_context()
        (context.add_class if status["error"] else context.remove_class)("error")
        for mode, button in self.buttons.items():
            context = button.get_style_context()
            (context.add_class if mode == status["mode"] else context.remove_class)("selected")
        processes = sample["top_processes"]
        for index, (name, percent) in enumerate(self.process_labels):
            if index < len(processes):
                process = processes[index]
                name.set_text(f"{process['name']}  ·  {process['pid']}")
                percent.set_text(f"{process['cpu_percent']:.1f}%")
            else:
                name.set_text("측정 중…" if index == 0 else "")
                percent.set_text("")
        gpu = "NVIDIA 절전 중" if status["nvidia"] == "suspended" else f"NVIDIA {status['nvidia']}"
        turbo = "터보 꺼짐" if status["limits"]["no_turbo"] else "터보 허용"
        self.details.set_text(f"{turbo} · {gpu}\nv{__version__}")
        return False


class QuietApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.BumBoo.FreirenQuiet", flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self.window = None

    def do_activate(self):
        if self.window is None:
            Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
            provider = Gtk.CssProvider()
            provider.load_from_data(STYLE)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            self.window = QuietWindow(self)
        self.window.present()


def run():
    GLib.set_prgname("freiren-quiet")
    return QuietApp().run(None)
