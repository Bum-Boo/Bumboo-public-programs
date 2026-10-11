"""Use power-profiles-daemon's public D-Bus API instead of duplicating EPP policy."""

SERVICE = "org.freedesktop.UPower.PowerProfiles"
PATH = "/org/freedesktop/UPower/PowerProfiles"
PROPERTIES = "org.freedesktop.DBus.Properties"


class PowerProfiles:
    def __init__(self):
        from gi.repository import Gio, GLib

        self.Gio, self.GLib = Gio, GLib
        self.connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

    def get(self, name: str):
        return self.connection.call_sync(
            SERVICE,
            PATH,
            PROPERTIES,
            "Get",
            self.GLib.Variant("(ss)", (SERVICE, name)),
            self.GLib.VariantType.new("(v)"),
            self.Gio.DBusCallFlags.NONE,
            1500,
            None,
        ).unpack()[0]

    def current(self) -> str:
        return self.get("ActiveProfile")

    def supported(self) -> list[str]:
        return [item["Profile"] for item in self.get("Profiles")]

    def set(self, requested: str) -> str:
        supported = self.supported()
        effective = requested if requested in supported else "balanced"
        if effective not in supported:
            raise RuntimeError("사용 가능한 전력 프로필이 없습니다.")
        if self.current() != effective:
            self.connection.call_sync(
                SERVICE,
                PATH,
                PROPERTIES,
                "Set",
                self.GLib.Variant(
                    "(ssv)", (SERVICE, "ActiveProfile", self.GLib.Variant("s", effective))
                ),
                None,
                self.Gio.DBusCallFlags.NONE,
                1500,
                None,
            )
        if self.current() != effective:
            raise RuntimeError("다른 전력 프로필 요청이 현재 모드와 충돌합니다.")
        return effective
