"""CAVA binary frames carried asynchronously through Qt's process API."""

import shutil
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .logging_utils import record


class FrameDecoder:
    def __init__(self, bars=32):
        self.bars = bars
        self.pending = bytearray()

    def feed(self, data: bytes):
        self.pending.extend(data)
        complete = len(self.pending) // self.bars
        if not complete:
            return None
        end = complete * self.bars
        newest = self.pending[end - self.bars : end]
        del self.pending[:end]
        return [value / 255 for value in newest]


class Audio(QObject):
    frame = Signal(list)
    status = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self._stderr)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.decoder = FrameDecoder()
        self.temp = None
        self.stopping = False
        self.message = ""
        self.state = "off"
        self.frames = 0
        self.last_energy = 0.0
        self.last_frame_at = 0.0
        self.watchdog = QTimer(self)
        self.watchdog.setInterval(1000)
        self.watchdog.timeout.connect(self._watch)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self._no_frames)

    def set_status(self, state, message):
        if (self.state, self.message) == (state, message):
            return
        self.state, self.message = state, message
        self.status.emit(state, message)

    def start(self, executable="", source="auto"):
        self.stop()
        binary = executable or shutil.which("cava")
        if not binary:
            local = Path.home() / ".local/bin/cava"
            binary = str(local) if local.is_file() else ""
        if not binary:
            self.set_status("missing", "CAVA를 설치하면 음악이 여기에 보여요.")
            record("audio_unavailable", reason="cava_missing")
            return
        if source != "auto" and not (
            source.endswith(".monitor") and all(c.isalnum() or c in "._-" for c in source)
        ):
            self.set_status("error", "재생 출력의 모니터만 선택할 수 있어요.")
            return
        self.temp = tempfile.TemporaryDirectory(prefix="grimoire-cava-")
        config = Path(self.temp.name) / "config"
        config.write_text(f"""[general]
framerate = 24
bars = 32
autosens = 1
lower_cutoff_freq = 40
higher_cutoff_freq = 12000
[input]
method = pulse
source = {source}
[output]
method = raw
raw_target = /dev/stdout
data_format = binary
bit_format = 8
channels = mono
[smoothing]
noise_reduction = 70
""")
        self.decoder = FrameDecoder()
        self.frames = 0
        self.stopping = False
        self.process.start(binary, ["-p", str(config)])
        self.last_frame_at = time.monotonic()
        self.watchdog.start()
        self.set_status("starting", "재생 소리에 귀 기울이는 중이에요.")
        self.deadline.start(8000)
        record("audio_start", backend="pulse_monitor", bars=32)

    def _read(self):
        values = self.decoder.feed(bytes(self.process.readAllStandardOutput()))
        if values is not None:
            self.deadline.stop()
            self.frames += 1
            self.last_frame_at = time.monotonic()
            self.last_energy = max(values)
            self.set_status("listening", "지금 재생되는 소리에 반응해요.")
            self.frame.emit(values)

    def _stderr(self):
        # Drain, but do not copy arbitrary server/device strings into logs.
        self.process.readAllStandardError()

    def _watch(self):
        if self.frames and time.monotonic() - self.last_frame_at > 5:
            self.set_status("error", "오디오 신호가 멈췄어요. 설정에서 다시 연결해 주세요.")
            self.frame.emit([0.0] * 32)

    def _no_frames(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.set_status("error", "오디오 신호를 받지 못했어요. 설정에서 다시 연결해 주세요.")
            record("audio_no_frames")

    def _finished(self, code, _status):
        self.deadline.stop()
        if not self.stopping:
            self.set_status("error", "음악 연결이 끊겼어요. 설정에서 다시 연결해 주세요.")
            record("audio_exit", exit_code=code)
            self.frame.emit([0.0] * 32)

    def _error(self, error):
        if not self.stopping:
            self.set_status("error", "CAVA를 시작하지 못했어요. 실행 파일을 확인해 주세요.")
            record("audio_process_error", code=error.value)

    def stop(self):
        self.stopping = True
        self.watchdog.stop()
        self.deadline.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(700):
                self.process.kill()
                self.process.waitForFinished(300)
            record("audio_stop")
        if self.temp:
            self.temp.cleanup()
            self.temp = None
        self.set_status("off", "음악 시각화를 쉬고 있어요.")
        self.frame.emit([0.0] * 32)
