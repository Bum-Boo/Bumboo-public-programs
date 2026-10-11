"""Connection profiles and distinct tailnet status, without reading network secrets."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from .core import ControllerError
from .desktop_common import choice, fields, run

UUID = re.compile(r"^[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}$")


def nm_fields(line):
    result, field, escaped = [], "", False
    for char in line:
        if escaped:
            field += char
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            result.append(field)
            field = ""
        else:
            field += char
    result.append(field)
    return result


class NetworkControls:
    def __init__(self):
        self.runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))

    def _tailnet(self, name):
        command = ["/usr/bin/tailscale"]
        if name == "lab":
            command += ["--socket=" + str(self.runtime / "tailscale-lab/tailscaled.sock")]
        try:
            result = subprocess.run(
                command + ["status", "--json"], text=True, capture_output=True, timeout=5, check=False
            )
            if result.returncode:
                return {"id": name, "state": "unavailable", "devices": []}
            value = json.loads(result.stdout)
            devices = [
                {
                    "name": row.get("HostName", ""),
                    "online": bool(row.get("Online")),
                    "addresses": row.get("TailscaleIPs", []),
                }
                for row in value.get("Peer", {}).values()
            ]
            return {"id": name, "state": value.get("BackendState", "unknown"), "devices": devices}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {"id": name, "state": "unavailable", "devices": []}

    def status(self):
        connections = []
        output = run(["/usr/bin/nmcli", "--terse", "--fields", "UUID,NAME,TYPE,DEVICE", "connection", "show"])
        for line in output.splitlines():
            row = nm_fields(line)
            if (
                len(row) == 4
                and row[2] in ("802-11-wireless", "802-3-ethernet", "vpn", "wireguard")
                and UUID.fullmatch(row[0])
            ):
                connections.append(
                    {"id": row[0], "name": row[1], "kind": row[2], "device": row[3], "active": bool(row[3])}
                )
        devices = []
        output = run(
            ["/usr/bin/nmcli", "--terse", "--fields", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"]
        )
        for line in output.splitlines():
            row = nm_fields(line)
            if len(row) == 4:
                devices.append(dict(zip(("id", "kind", "state", "connection"), row, strict=True)))
        tailnets = [self._tailnet("personal"), self._tailnet("lab")]
        himmel = [
            p
            for t in tailnets
            for p in t["devices"]
            if p["name"].casefold() in ("desktop-2f5dbdc", "himmel", "himmel-pc")
        ]
        return {
            "connections": connections,
            "devices": devices,
            "tailnets": tailnets,
            "himmel": {
                "online": any(p["online"] for p in himmel),
                "known": bool(himmel),
                "can_open": self._shortcut().is_file(),
            },
        }

    @staticmethod
    def _shortcut():
        return Path.home() / ".local/share/applications/himmel-desktop.desktop"

    def validate(self, settings):
        values = fields(settings, {"connection"}, ("connection",))
        if not isinstance(values["connection"], str) or not UUID.fullmatch(values["connection"]):
            raise ControllerError("저장된 연결을 다시 선택해 주세요.")
        choice(values["connection"], {r["id"] for r in self.status()["connections"]}, "저장된 연결")
        return values

    def capture(self, settings):
        state = self.status()
        target = next(r for r in state["connections"] if r["id"] == settings["connection"])
        previous = [r["id"] for r in state["connections"] if r["active"] and r["kind"] == target["kind"]]
        return {
            "target": target["id"],
            "kind": target["kind"],
            "previous": previous,
            "names": {
                r["id"]: r["name"] for r in state["connections"] if r["id"] in {*previous, target["id"]}
            },
        }

    def apply(self, settings):
        values = self.validate(settings)
        if not any(r["id"] == values["connection"] and r["active"] for r in self.status()["connections"]):
            run(
                ["/usr/bin/nmcli", "--wait", "15", "connection", "up", "uuid", values["connection"]],
                timeout=20,
            )
        if not any(r["id"] == values["connection"] and r["active"] for r in self.status()["connections"]):
            raise ControllerError("선택한 네트워크에 연결하지 못했어요.")

    def restore(self, snapshot):
        rows = self.status()["connections"]
        live = {r["id"] for r in rows}
        for identifier in snapshot["previous"]:
            choice(identifier, live, "이전에 쓰던 연결")
            self.apply({"connection": identifier})
        if snapshot["target"] not in snapshot["previous"] and any(
            r["id"] == snapshot["target"] and r["active"] for r in self.status()["connections"]
        ):
            run(
                ["/usr/bin/nmcli", "--wait", "10", "connection", "down", "uuid", snapshot["target"]],
                timeout=15,
            )

    def open_himmel(self):
        path = self._shortcut()
        if not path.is_file():
            raise ControllerError("힘멜 데스크탑 바로가기를 찾지 못했어요.")
        subprocess.Popen(
            ["/usr/bin/gio", "launch", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"opened": True}
