"""Application shell and lifecycle. No task producer is modified by the UI."""

import hashlib
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .audio import Audio
from .config import Settings, location
from .logging_utils import record
from .models import LABELS, SHORT, Task, aggregate, openable_path
from .skin import Skin
from .sources import collect
from .theme import PALETTES, stylesheet
from .widgets import CharacterStage, Companion, Spectrum, TaskTitle, status_color

ICON = Path(__file__).parent / "assets/grimoire.svg"


def label(text, name="", wrap=False):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setWordWrap(wrap)
    if name:
        item.setObjectName(name)
    return item


def button(text, callback, primary=False):
    item = QPushButton(text)
    item.clicked.connect(callback)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        item.setObjectName("primary")
    return item


class Collector(QThread):
    collected = Signal(object, object, str)

    def __init__(self, task_root, parent=None):
        super().__init__(parent)
        self.task_root = task_root

    def run(self):
        tasks, errors = collect(self.task_root, location("state") / "events")
        self.collected.emit(tasks, errors, self.task_root)


class TaskRow(QFrame):
    def __init__(self, task, palette, open_path, parent=None):
        super().__init__(parent)
        self.setObjectName("taskrow")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 11, 14, 11)
        outer.setSpacing(5)
        head = QHBoxLayout()
        status = label(SHORT[task.state])
        status.setStyleSheet(f"color: {status_color(palette, task.state)}; font-size: 11px;")
        head.addWidget(status)
        head.addStretch()
        head.addWidget(label(task.agent, "muted"))
        outer.addLayout(head)
        title = TaskTitle(task.title)
        outer.addWidget(title)
        meta = QHBoxLayout()
        age = max(0, time.time() - task.updated)
        when = (
            "방금"
            if age < 60
            else (
                f"{int(age / 60)}분 전"
                if age < 3600
                else (f"{int(age / 3600)}시간 전" if age < 86400 else f"{int(age / 86400)}일 전")
            )
        )
        meta.addWidget(label(when, "muted"))
        meta.addStretch()
        if task.handoff:
            b = button("이어가기", lambda: open_path(task.handoff))
            b.setAccessibleName(f"{task.title} 이어가기 기록 열기")
            b.setToolTip(task.detail)
            meta.addWidget(b)
        if task.artifacts:
            b = button("결과 열기", lambda: open_path(task.artifacts[0]))
            b.setAccessibleName(f"{task.title} 결과 열기")
            meta.addWidget(b)
        outer.addLayout(meta)


class Window(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.setWindowTitle("Grimoire · 작은 마법서")
        self.setWindowIcon(QIcon(str(ICON)))
        self.resize(1050, 740)
        self.setMinimumSize(830, 610)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(30, 22, 30, 20)
        layout.setSpacing(12)
        header = QHBoxLayout()
        wordmark = label("Grimoire", "brand")
        header.addWidget(wordmark)
        header.addWidget(label("  작은 마법서", "muted"))
        header.addStretch()
        self.companion_button = button("동반자 숨기기", controller.toggle_companion)
        header.addWidget(self.companion_button)
        layout.addLayout(header)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        layout.addWidget(self.tabs, 1)
        self.home = self.make_home()
        self.tabs.addTab(self.home, "여정")
        self.history_page = self.make_history()
        self.tabs.addTab(self.history_page, "작업 기록")
        self.settings_page = self.make_settings()
        self.tabs.addTab(self.settings_page, "설정")
        self.footer = label("기록을 연결하고 있어요.", "muted")
        layout.addWidget(self.footer)
        QShortcut(QKeySequence("Ctrl+,"), self, lambda: self.tabs.setCurrentIndex(2))
        QShortcut(QKeySequence("Escape"), self, self.close)
        QShortcut(QKeySequence("Ctrl+Q"), self, controller.quit)

    def make_home(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(28)
        left = QVBoxLayout()
        left.setSpacing(7)
        self.eyebrow = label("YOUR QUIET COMPANION", "eyebrow")
        left.addWidget(self.eyebrow)
        self.heading = label("여정은 계속되고 있어요.", "title")
        left.addWidget(self.heading)
        self.subheading = label("음악을 곁에 두고, 새로운 결과를 기다려요.", "subtitle", True)
        left.addWidget(self.subheading)
        self.stage = CharacterStage()
        left.addWidget(self.stage, 1)
        audio_panel = QFrame()
        audio_panel.setObjectName("panel")
        audio_layout = QVBoxLayout(audio_panel)
        audio_layout.setContentsMargins(18, 12, 18, 12)
        row = QHBoxLayout()
        row.addWidget(label("소리의 결", "section"))
        row.addStretch()
        self.audio_button = button("잠시 끄기", self.c.toggle_audio)
        row.addWidget(self.audio_button)
        audio_layout.addLayout(row)
        self.spectrum = Spectrum()
        audio_layout.addWidget(self.spectrum)
        self.audio_label = label("재생 소리에 연결하고 있어요.", "muted", True)
        audio_layout.addWidget(self.audio_label)
        left.addWidget(audio_panel)
        layout.addLayout(left, 3)
        right = QVBoxLayout()
        right.setSpacing(12)
        title = QHBoxLayout()
        title.addWidget(label("작은 소식", "section"))
        title.addStretch()
        self.count_label = label("0개의 기록", "muted")
        title.addWidget(self.count_label)
        right.addLayout(title)
        self.recent = QVBoxLayout()
        self.recent.setSpacing(10)
        right.addLayout(self.recent)
        right.addStretch()
        self.source_note = label("진행 표시는 에이전트가 남긴 기록을 기준으로 해요.", "muted", True)
        right.addWidget(self.source_note)
        right.addWidget(button("모든 기록 보기  →", lambda: self.tabs.setCurrentIndex(1)))
        layout.addLayout(right, 2)
        return page

    def make_history(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 0, 0)
        heading = QHBoxLayout()
        heading.addWidget(label("작업이 남긴 발자취", "title"))
        heading.addStretch()
        self.filter = QComboBox()
        self.filter.addItems(["모든 기록", "진행 기록", "완료 기록", "확인 필요"])
        self.filter.currentIndexChanged.connect(lambda: self.render_history())
        heading.addWidget(self.filter)
        layout.addLayout(heading)
        layout.addWidget(
            label("최근 14일의 기록이에요. 결과와 이어가기 파일은 클릭할 때만 열어요.", "muted")
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.history = QVBoxLayout(content)
        self.history.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.history.setSpacing(10)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page

    def make_settings(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 18, 18, 12)
        layout.setSpacing(12)
        layout.addWidget(label("곁에 두는 방식", "title"))
        layout.addWidget(label("모양과 움직임", "section"))
        self.theme = QComboBox()
        self.theme.addItems(["달빛의 서재", "새벽의 서재"])
        self.theme.setCurrentIndex(0 if self.c.settings["theme"] == "night" else 1)
        self.theme.currentIndexChanged.connect(lambda i: self.c.change(theme=["night", "dawn"][i]))
        layout.addWidget(self.theme)
        self.checks = {}
        for key, text in [
            ("companion_visible", "바탕화면에 동반자 표시"),
            ("always_on_top", "다른 창 위에 표시"),
            ("reduced_motion", "캐릭터 움직임 줄이기"),
            ("quiet", "조용히 지내기 · 완료 알림 끄기"),
            ("resting", "동반자 잠시 쉬기 · 기록은 계속 확인해요"),
            ("audio_enabled", "음악 시각화 켜기"),
        ]:
            check = QCheckBox(text)
            check.setChecked(self.c.settings[key])
            check.toggled.connect(lambda checked, k=key: self.c.change(**{k: checked}))
            self.checks[key] = check
            layout.addWidget(check)
        size_row = QHBoxLayout()
        size_row.addWidget(label("동반자 크기"))
        self.size_label = label("100%", "muted")
        size_row.addWidget(self.size_label)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(65, 160)
        self.size_slider.setValue(round(self.c.settings["scale"] * 100))
        self.size_slider.setAccessibleName("동반자 크기")
        self.size_slider.valueChanged.connect(lambda v: self.size_label.setText(f"{v}%"))
        self.size_debounce = QTimer(self)
        self.size_debounce.setSingleShot(True)
        self.size_debounce.timeout.connect(
            lambda: self.c.change(scale=self.size_slider.value() / 100)
        )
        self.size_slider.valueChanged.connect(lambda _v: self.size_debounce.start(250))
        size_row.addWidget(self.size_slider, 1)
        size_row.addWidget(button("위치 되돌리기", self.c.reset_position))
        layout.addLayout(size_row)
        layout.addWidget(label("캐릭터", "section"))
        self.skin_label = label("", "muted", True)
        layout.addWidget(self.skin_label)
        skin_row = QHBoxLayout()
        skin_row.addWidget(button("캐릭터 파일 선택", self.choose_skin))
        skin_row.addWidget(button("기본 마법서", lambda: self.c.change(skin="")))
        skin_row.addStretch()
        layout.addLayout(skin_row)
        layout.addWidget(label("음악", "section"))
        self.audio_settings_label = label("", "muted", True)
        layout.addWidget(self.audio_settings_label)
        gain_row = QHBoxLayout()
        gain_row.addWidget(label("파형 높이"))
        self.gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.gain_slider.setRange(25, 300)
        self.gain_slider.setValue(round(self.c.settings["gain"] * 100))
        self.gain_slider.setAccessibleName("파형 높이")
        self.gain_debounce = QTimer(self)
        self.gain_debounce.setSingleShot(True)
        self.gain_debounce.timeout.connect(
            lambda: self.c.change(gain=self.gain_slider.value() / 100)
        )
        self.gain_slider.valueChanged.connect(lambda _v: self.gain_debounce.start(250))
        gain_row.addWidget(self.gain_slider)
        gain_row.addWidget(button("소리 다시 연결", self.c.restart_audio))
        layout.addLayout(gain_row)
        layout.addWidget(label("작업 기록 연결", "section"))
        layout.addWidget(
            label("agent-task의 프로젝트 폴더들이 들어 있는 폴더를 선택해 주세요.", "muted", True)
        )
        folder_row = QHBoxLayout()
        self.task_root = QLineEdit(self.c.settings["task_root"])
        self.task_root.setReadOnly(True)
        self.task_root.setPlaceholderText("아직 폴더를 연결하지 않았어요")
        self.task_root.setAccessibleName("작업 기록 폴더")
        folder_row.addWidget(self.task_root, 1)
        folder_row.addWidget(button("폴더 선택", self.choose_source))
        folder_row.addWidget(button("연결 해제", lambda: self.c.change(task_root="")))
        layout.addLayout(folder_row)
        layout.addWidget(
            label(
                "그 밖의 에이전트는 grimoire event 명령으로 소식을 보낼 수 있어요.", "muted", True
            )
        )
        log_row = QHBoxLayout()
        log_row.addWidget(
            button(
                "앱 로그 열기", lambda: self.c.open_path(str(location("state") / "events.jsonl"))
            )
        )
        log_row.addWidget(button("사용법 열기", self.c.open_help))
        log_row.addStretch()
        log_row.addWidget(label(f"Grimoire {__version__}", "muted"))
        layout.addLayout(log_row)
        layout.addStretch()
        page.setWidget(content)
        return page

    def choose_skin(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "캐릭터 파일 선택", str(location("data")), "캐릭터 설명 (skin.json *.json)"
        )
        if path:
            skin = Skin(path)
            if skin.error:
                QMessageBox.information(self, "캐릭터", skin.error)
            else:
                self.c.change(skin=path)

    def choose_source(self):
        path = QFileDialog.getExistingDirectory(
            self, "작업 기록 폴더", self.c.settings["task_root"] or str(Path.home())
        )
        if path:
            self.c.change(task_root=path)

    @staticmethod
    def clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def render_tasks(self):
        self.clear(self.recent)
        tasks = self.c.tasks
        # Recent active work is visible ahead of old stale entries.
        chosen = sorted(tasks, key=lambda t: (t.state != "working", -t.updated))[:3]
        if not chosen:
            self.recent.addWidget(
                label(
                    "아직 도착한 소식이 없어요.\n설정에서 작업 기록을 연결해 주세요.", "muted", True
                )
            )
        for task in chosen:
            self.recent.addWidget(TaskRow(task, self.c.palette, self.c.open_path))
        self.count_label.setText(f"{len(tasks)}개의 기록")
        self.render_history()

    def render_history(self):
        if not hasattr(self, "history"):
            return
        self.clear(self.history)
        wanted = [None, {"working"}, {"done"}, {"attention", "error"}][self.filter.currentIndex()]
        tasks = [t for t in self.c.tasks if wanted is None or t.state in wanted]
        for task in tasks[:100]:
            self.history.addWidget(TaskRow(task, self.c.palette, self.c.open_path))
        if not tasks:
            self.history.addWidget(label("여기에 해당하는 기록이 없어요.", "muted"))
        elif len(tasks) > 100:
            self.history.addWidget(label("최근 100개를 표시했어요.", "muted"))

    def sync(self):
        s = self.c.settings
        self.companion_button.setText("동반자 숨기기" if s["companion_visible"] else "동반자 표시")
        self.audio_button.setText("잠시 끄기" if s["audio_enabled"] else "음악 켜기")
        for key, check in self.checks.items():
            check.blockSignals(True)
            check.setChecked(s[key])
            check.blockSignals(False)
        self.theme.blockSignals(True)
        self.theme.setCurrentIndex(0 if s["theme"] == "night" else 1)
        self.theme.blockSignals(False)
        self.size_label.setText(f"{round(s['scale'] * 100)}%")
        self.task_root.setText(s["task_root"])
        self.skin_label.setText(self.c.skin.error or f"지금 곁에 있는 동반자: {self.c.skin.name}")
        self.stage.configure(s, self.c.skin)
        self.spectrum.palette_values = self.c.palette
        self.spectrum.gain = s["gain"]
        self.spectrum.update()

    def closeEvent(self, event):
        if self.c.tray and self.c.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self.c.quit()
            event.accept()


class Controller(QObject):
    def __init__(self, app: QApplication, settings: Settings, demo=False):
        super().__init__(app)
        self.app, self.settings, self.demo = app, settings, demo
        self.tasks = []
        self.seen = None
        self.task_signature = None
        self.errors_signature = None
        self.worker = None
        self.document_windows = []
        self.shutting_down = False
        self.started_at = time.time()
        self.palette = PALETTES[settings["theme"]]
        self.skin = Skin(settings["skin"])
        self.audio = Audio(app)
        self.companion = Companion()
        self.tray = None
        self.window = Window(self)
        self.app.setStyleSheet(stylesheet(self.palette))
        self.companion.configure(settings, self.skin)
        self.companion.place(settings["position"])
        self.companion.activated.connect(self.show_window)
        self.companion.moved.connect(lambda pos: self.change(position=pos))
        self.companion.hideRequested.connect(lambda: self.change(companion_visible=False))
        self.companion.quietRequested.connect(lambda: self.change(quiet=not self.settings["quiet"]))
        self.companion.restRequested.connect(
            lambda: self.change(resting=not self.settings["resting"])
        )
        self.audio.frame.connect(self.window.spectrum.set_frame)
        self.audio.frame.connect(self.window.stage.set_frame)
        self.audio.frame.connect(self.companion.set_frame)
        self.audio.status.connect(self.audio_status)
        self.audio.stop()
        self.celebration = QTimer(app)
        self.celebration.setSingleShot(True)
        self.celebration.timeout.connect(self.refresh_state)
        self.poll = QTimer(app)
        self.poll.timeout.connect(self.refresh)
        self.make_tray()
        self.window.sync()
        if settings["companion_visible"]:
            self.companion.show()
        self.app.aboutToQuit.connect(self.shutdown)
        if demo:
            self.set_demo()
        else:
            self.poll.start(3000)
            self.refresh()
            if settings["audio_enabled"]:
                QTimer.singleShot(150, self.restart_audio)
        for screen in app.screens():
            screen.availableGeometryChanged.connect(lambda _r: self.companion.clamp_position())
        app.screenRemoved.connect(lambda _s: self.companion.clamp_position())
        if settings.error:
            self.window.footer.setText(settings.error)
        record(
            "startup",
            version=__version__,
            demo=demo,
            platform=app.platformName(),
            skin="custom" if settings["skin"] else "default",
        )

    def make_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(QIcon(str(ICON)), self.app)
        self.tray.setToolTip("Grimoire · 작은 마법서")
        menu = QMenu()
        menu.addAction("여정 열기", self.show_window)
        menu.addAction("동반자 표시 / 숨기기", self.toggle_companion)
        menu.addAction("음악 켜기 / 끄기", self.toggle_audio)
        menu.addAction("조용히 / 알림 받기", lambda: self.change(quiet=not self.settings["quiet"]))
        menu.addAction("쉬기 / 돌아오기", lambda: self.change(resting=not self.settings["resting"]))
        menu.addSeparator()
        menu.addAction("종료", self.quit)
        self.tray.setContextMenu(menu)
        self.tray_menu = menu
        self.tray.activated.connect(
            lambda reason: (
                self.show_window()
                if reason
                in (
                    QSystemTrayIcon.ActivationReason.Trigger,
                    QSystemTrayIcon.ActivationReason.DoubleClick,
                )
                else None
            )
        )
        self.tray.show()

    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def change(self, **changes):
        try:
            self.settings.update(**changes)
        except OSError:
            QMessageBox.warning(
                self.window, "설정", "설정을 저장하지 못했어요. 폴더 권한을 확인해 주세요."
            )
            record("settings_write_failed")
            return
        record("settings_changed", keys=sorted(changes))
        if "skin" in changes:
            self.skin = Skin(self.settings["skin"])
        self.palette = PALETTES[self.settings["theme"]]
        if "theme" in changes:
            self.app.setStyleSheet(stylesheet(self.palette))
        self.companion.configure(self.settings, self.skin)
        self.companion.setVisible(self.settings["companion_visible"])
        self.window.sync()
        if "theme" in changes:
            self.window.render_tasks()
        if "audio_enabled" in changes:
            self.restart_audio() if self.settings["audio_enabled"] else self.audio.stop()
        if "task_root" in changes:
            self.seen = None  # Switching source is a baseline, not a burst of completions.
            self.refresh()
        if "resting" in changes:
            self.refresh_state()

    def toggle_companion(self):
        self.change(companion_visible=not self.settings["companion_visible"])

    def toggle_audio(self):
        self.change(audio_enabled=not self.settings["audio_enabled"])

    def reset_position(self):
        self.companion.place()
        self.change(position=[self.companion.x(), self.companion.y()])

    def restart_audio(self):
        if not self.demo and self.settings["audio_enabled"]:
            self.audio.start(self.settings["cava_path"], self.settings["audio_source"])

    def audio_status(self, state, message):
        self.window.audio_label.setText(message)
        self.window.audio_settings_label.setText(
            message + " 재생 출력만 읽고 마이크는 사용하지 않아요."
        )

    def refresh(self):
        if self.demo or self.shutting_down or (self.worker and self.worker.isRunning()):
            return
        if self.worker:
            self.worker.deleteLater()
        self.worker = Collector(self.settings["task_root"], self.app)
        self.worker.collected.connect(self.source_received)
        self.worker.start()

    @Slot(object, object, str)
    def source_received(self, tasks, errors, root):
        if root == self.settings["task_root"]:
            self.received(tasks, errors)

    def received(self, tasks, errors):
        if self.shutting_down:
            return
        self.tasks = tasks
        state_map = {task.id: (task.state, task.revision) for task in tasks}
        fresh_done = []
        if self.seen is not None:
            for task in tasks:
                if (
                    task.state == "done"
                    and self.seen.get(task.id, (None, ""))[0] != "done"
                    and task.updated >= self.started_at - 5
                ):
                    fresh_done.append(task)
                if self.seen.get(task.id) != state_map[task.id]:
                    record(
                        "task_transition",
                        id=hashlib.sha256(task.id.encode()).hexdigest()[:12],
                        state=task.state,
                        source=task.source,
                    )
        self.seen = state_map
        if fresh_done:
            self.set_state("done")
            self.celebration.start(9000)
            if self.tray and not self.settings["quiet"]:
                self.tray.showMessage(
                    "Grimoire",
                    f"{len(fresh_done)}개의 새 결과가 도착했어요.",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
        elif not self.celebration.isActive():
            self.refresh_state()
        signature = tuple((t.id, t.state, t.revision) for t in tasks)
        if self.task_signature != signature:
            self.task_signature = signature
            self.window.render_tasks()
        if tuple(errors) != self.errors_signature:
            self.errors_signature = tuple(errors)
            if errors:
                record("source_diagnostics", issues=errors[:16], count=len(errors))
        if not self.celebration.isActive():
            self.refresh_state()
        active = sum(t.state == "working" for t in tasks)
        stale = sum(t.state in ("attention", "error") for t in tasks)
        text = f"진행 기록 {active} · 확인 필요 {stale} · 최근 확인 {time.strftime('%H:%M')}"
        if errors:
            text += f" · 읽지 못한 항목 {len(errors)}"
        self.window.footer.setText(text)

    def refresh_state(self):
        state = aggregate(self.tasks)
        if self.errors_signature and state == "idle":
            state = "attention"
        self.set_state("sleep" if self.settings["resting"] else state)

    def set_state(self, state):
        self.companion.set_state(state)
        self.window.stage.set_state(state)
        self.window.heading.setText(
            {
                "working": "맡겨 둔 일이 있어요.",
                "done": "새로운 결과가 도착했어요.",
                "attention": "다음 걸음을 살펴봐요.",
                "error": "살펴볼 일이 생겼어요.",
                "idle": "새로운 여정을 기다려요.",
                "sleep": "잠시 책을 덮어 둘게요.",
            }[state]
        )
        if self.tray:
            self.tray.setToolTip(f"Grimoire · {LABELS[state]}")

    def open_path(self, path):
        target = openable_path(path)
        if target is None:
            QMessageBox.information(
                self.window, "파일 열기", "파일이 없거나 직접 열 수 없는 형식이에요."
            )
            record("artifact_open_rejected")
            return False
        if target.is_file() and target.suffix.lower() in {
            ".md",
            ".txt",
            ".json",
            ".jsonl",
            ".log",
            ".csv",
        }:
            try:
                with target.open("rb") as stream:
                    raw = stream.read(2_000_001)
                truncated = len(raw) > 2_000_000
                content = raw[:2_000_000].decode("utf-8", errors="replace")
            except OSError:
                QMessageBox.information(self.window, "파일 열기", "파일을 읽지 못했어요.")
                record("artifact_read_failed")
                return False
            viewer = QDialog(self.window)
            viewer.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            viewer.setWindowTitle(target.name + " · Grimoire")
            viewer.resize(800, 590)
            layout = QVBoxLayout(viewer)
            layout.addWidget(label(target.name, "section"))
            editor = QPlainTextEdit()
            editor.setReadOnly(True)
            editor.setPlainText(content)
            editor.setAccessibleName("파일 내용")
            layout.addWidget(editor, 1)
            if truncated:
                layout.addWidget(
                    label(
                        "큰 파일이라 처음 2MB만 보여요. 전체 내용은 기본 앱에서 열어 주세요.",
                        "muted",
                        True,
                    )
                )
            controls = QHBoxLayout()
            controls.addWidget(
                button("경로 복사", lambda: self.app.clipboard().setText(str(target)))
            )
            controls.addWidget(
                button(
                    "기본 앱에서 열기",
                    lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))),
                )
            )
            controls.addStretch()
            controls.addWidget(button("닫기", viewer.close))
            layout.addLayout(controls)
            self.document_windows.append(viewer)
            viewer.destroyed.connect(
                lambda: (
                    self.document_windows.remove(viewer)
                    if viewer in self.document_windows
                    else None
                )
            )
            viewer.show()
            record(
                "artifact_open",
                success=True,
                kind=target.suffix,
                reader="native",
                truncated=truncated,
            )
            return True
        result = QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        record(
            "artifact_open", success=result, kind="directory" if target.is_dir() else target.suffix
        )
        if not result:
            QMessageBox.information(self.window, "파일 열기", "연결된 앱에서 파일을 열지 못했어요.")
        return result

    def open_help(self):
        help_path = location("data") / "README.md"
        if help_path.exists():
            self.open_path(str(help_path))
        else:
            QMessageBox.information(
                self.window,
                "사용법",
                "캐릭터를 드래그해 옮기고 클릭해 여정을 열어요.\n오른쪽 버튼으로 숨길 수 있어요.\n트레이 아이콘이나 앱 메뉴에서 다시 열어요.\nCtrl+, 설정 · Ctrl+Q 종료",
            )

    def set_demo(self):
        self.tasks = [
            Task(
                "example:1",
                "별빛 도서관을 정리하고 있어요",
                "Codex",
                "working",
                time.time() - 120,
                "example",
                revision="1",
            ),
            Task(
                "example:2",
                "새로운 지도가 도착했어요",
                "Claude",
                "done",
                time.time() - 900,
                "example",
                revision="1",
            ),
            Task(
                "example:3",
                "다음 여행지를 골라 주세요",
                "Hermes",
                "attention",
                time.time() - 3600,
                "example",
                revision="1",
            ),
        ]
        self.window.eyebrow.setText("DESIGN PREVIEW · 예시 데이터")
        self.window.footer.setText("디자인 미리보기예요. 실제 작업이나 소리를 나타내지 않아요.")
        self.window.audio_label.setText("예시 파형 · 실시간 오디오가 아니에요.")
        self.window.spectrum.set_frame(
            [
                0.1,
                0.2,
                0.3,
                0.15,
                0.2,
                0.4,
                0.55,
                0.7,
                0.45,
                0.3,
                0.4,
                0.8,
                0.9,
                0.6,
                0.4,
                0.3,
                0.25,
                0.5,
                0.6,
                0.35,
                0.2,
                0.1,
                0.2,
                0.3,
                0.2,
                0.5,
                0.3,
                0.2,
                0.12,
                0.1,
                0.05,
                0.02,
            ]
        )
        self.set_state("working")
        self.window.render_tasks()

    def quit(self):
        self.shutdown()
        self.app.quit()

    def shutdown(self):
        if self.shutting_down:
            return
        self.shutting_down = True
        self.poll.stop()
        self.celebration.stop()
        self.audio.stop()
        if self.worker and self.worker.isRunning():
            self.worker.wait(5000)
        self.companion.close()
        if self.tray:
            self.tray.hide()
        record("shutdown")
