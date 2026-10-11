"""Small, fixed session-bus facade for the Plasma widget; no subprocess polling."""

from __future__ import annotations

import json
import threading

from .core import ControllerError

SERVICE = "io.github.BumBoo.FrierenController"
PATH = "/io/github/BumBoo/FrierenController"
INTERFACE = SERVICE + "1"
XML = f"""<node><interface name="{INTERFACE}">
<method name="Status"><arg type="s" direction="out"/></method>
<method name="SetBrightness"><arg type="i" direction="in"/><arg type="s" direction="out"/></method>
<method name="ApplyMode"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
<method name="EndMode"><arg type="s" direction="out"/></method>
</interface></node>"""


class WidgetBus:
    def __init__(self, controller):
        self.controller = controller
        self.loop = None
        self.thread = None
        self.ready = threading.Event()

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready.wait(3)

    def _run(self):
        from gi.repository import Gio, GLib

        context = GLib.MainContext.new()
        context.push_thread_default()
        try:
            self.loop = GLib.MainLoop.new(context, False)
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            owner = Gio.bus_own_name_on_connection(bus, SERVICE, Gio.BusNameOwnerFlags.NONE, None, None)
            node = Gio.DBusNodeInfo.new_for_xml(XML)

            def dispatch(_bus, _sender, _path, _interface, method, parameters, invocation):
                self.controller.request_context.source = "widget"
                try:
                    args = parameters.unpack()
                    if method == "Status":
                        result = self.controller.widget_status()
                    elif method == "SetBrightness":
                        result = self.controller.widget_brightness(args[0])
                    elif method == "ApplyMode":
                        result = self.controller.work_mode_apply(args[0])
                    elif method == "EndMode":
                        result = self.controller.work_mode_end()
                    else:
                        raise ControllerError("지원하지 않는 위젯 동작이에요.")
                    invocation.return_value(GLib.Variant("(s)", (json.dumps(result, ensure_ascii=False),)))
                except (ControllerError, ValueError, TypeError) as exc:
                    invocation.return_dbus_error(INTERFACE + ".Error", str(exc))
                except Exception:
                    invocation.return_dbus_error(
                        INTERFACE + ".Error", "연결 상태를 확인한 뒤 다시 시도해 주세요."
                    )
                finally:
                    self.controller.request_context.source = "local"

            registration = bus.register_object(PATH, node.interfaces[0], dispatch, None, None)
            self.ready.set()
            self.loop.run()
            bus.unregister_object(registration)
            Gio.bus_unown_name(owner)
        except GLib.Error:
            self.ready.set()
        finally:
            context.pop_thread_default()

    def close(self):
        if self.loop:
            self.loop.quit()
        if self.thread:
            self.thread.join(timeout=3)
