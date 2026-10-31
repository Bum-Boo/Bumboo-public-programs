"""Fixed desktop commands and targeted KConfig access; never execute client code."""

from __future__ import annotations

import json
import subprocess
import time

from .core import ControllerError


def run(args, timeout=12):
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ControllerError("설정 도구에 연결하지 못했어요. 다시 확인해 주세요.") from exc
    if result.returncode:
        raise ControllerError("설정을 적용하지 못했어요. 연결 상태와 권한을 확인해 주세요.")
    return result.stdout.strip()


def fields(settings, allowed, required=()):
    if not isinstance(settings, dict) or not settings or set(settings) - set(allowed):
        raise ControllerError("설정 항목을 확인해 주세요.")
    if not set(required) <= set(settings):
        raise ControllerError("필요한 설정값을 입력해 주세요.")
    return dict(settings)


def integer(value, low, high, title):
    if type(value) is not int or not low <= value <= high:
        raise ControllerError(f"{title}은 {low}~{high} 사이 정수로 입력해 주세요.")
    return value


def boolean(value):
    if type(value) is not bool:
        raise ControllerError("켜기·끄기 값을 확인해 주세요.")
    return value


def choice(value, options, title="선택한 항목"):
    if not isinstance(value, str) or value not in options:
        raise ControllerError(f"{title}을 다시 선택해 주세요.")
    return value


def wait_for(read, expected, seconds=3):
    deadline = time.monotonic() + seconds
    while True:
        actual = read()
        if actual == expected:
            return actual
        if time.monotonic() >= deadline:
            raise ControllerError("변경한 설정을 확인하지 못했어요. 이전 설정으로 돌아가요.")
        time.sleep(0.08)


class SessionBus:
    def __init__(self):
        try:
            from gi.repository import Gio, GLib
        except ImportError as exc:
            raise ControllerError("PyGObject를 불러오지 못해 데스크톱 기능을 쓸 수 없어요.") from exc

        self.Gio, self.GLib = Gio, GLib
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as exc:
            # Without a session bus only desktop features are unavailable; callers handle this.
            raise ControllerError("데스크톱 세션 D-Bus에 연결하지 못했어요.") from exc

    def call(self, service, path, interface, method, signature=None, args=()):
        try:
            reply = self.bus.call_sync(
                service,
                path,
                interface,
                method,
                self.GLib.Variant(signature, args) if signature else None,
                None,
                self.Gio.DBusCallFlags.NONE,
                5000,
                None,
            ).unpack()
            return reply[0] if len(reply) == 1 else reply
        except self.GLib.Error as exc:
            raise ControllerError("데스크톱 기능에 연결하지 못했어요. 로그인 상태를 확인해 주세요.") from exc

    def properties(self, service, path, interface):
        return self.call(service, path, "org.freedesktop.DBus.Properties", "GetAll", "(s)", (interface,))

    def notify_config(self, file, changes):
        payload = {group: [list(key.encode()) for key in keys] for group, keys in changes.items()}
        self.bus.emit_signal(
            None,
            "/" + file,
            "org.kde.kconfig.notify",
            "ConfigChanged",
            self.GLib.Variant("(a{saay})", (payload,)),
        )
        self.bus.flush_sync(None)


class Config:
    def __init__(self, bus=None):
        self.bus = bus or SessionBus()

    def read(self, file, group, key):
        args = ["/usr/bin/kreadconfig6", "--file", file]
        for part in group:
            args += ["--group", part]
        value = run(args + ["--key", key, "--default", "__frieren_absent__"])
        return None if value == "__frieren_absent__" else value

    def write(self, file, group, key, value):
        args = ["/usr/bin/kwriteconfig6", "--file", file]
        for part in group:
            args += ["--group", part]
        args += ["--key", key]
        run(args + (["--delete"] if value is None else [str(value)]))

    def capture(self, mapping, keys):
        return {key: self.read(*mapping[key]) for key in keys}

    def restore(self, mapping, values):
        notifications = {}
        for key, value in values.items():
            file, group, entry = mapping[key]
            self.write(file, group, entry, value)
            notifications.setdefault(file, {}).setdefault("\x1d".join(group), []).append(entry)
        for file, groups in notifications.items():
            self.bus.notify_config(file, groups)


def json_command(args):
    try:
        return json.loads(run(args))
    except ValueError as exc:
        raise ControllerError("설정 목록을 읽지 못했어요.") from exc
