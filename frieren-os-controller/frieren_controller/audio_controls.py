"""PipeWire audio devices and app streams through pactl's JSON interface."""

from __future__ import annotations

from .core import ControllerError
from .desktop_common import boolean, choice, fields, integer, json_command, run, wait_for


class AudioControls:
    def _list(self, kind):
        return json_command(["/usr/bin/pactl", "--format=json", "list", kind])

    @staticmethod
    def _volume(row):
        return [channel["value"] for channel in row.get("volume", {}).values()]

    def status(self):
        info = json_command(["/usr/bin/pactl", "--format=json", "info"])
        result = {"output": info["default_sink_name"], "input": info["default_source_name"]}
        for key, kind in (("outputs", "sinks"), ("inputs", "sources"), ("streams", "sink-inputs")):
            result[key] = []
            for row in self._list(kind):
                props = row.get("properties", {})
                if kind == "sources" and props.get("device.class") == "monitor":
                    continue
                values = self._volume(row)
                result[key].append(
                    {
                        "id": row.get("name", str(row["index"])),
                        "index": row["index"],
                        "name": row.get("description") or props.get("application.name", "앱 소리"),
                        "serial": str(props.get("object.serial", "")),
                        "volume": round(max(values, default=0) / 65536 * 100),
                        "channels": values,
                        "muted": bool(row.get("mute", False)),
                        "sink": row.get("sink"),
                        "port": row.get("active_port", ""),
                        "ports": [
                            {
                                "id": p["name"],
                                "name": p["description"],
                                "available": p.get("availability") != "not available",
                            }
                            for p in row.get("ports", [])
                        ],
                    }
                )
        return result

    def validate(self, settings):
        values = fields(
            settings,
            {
                "output",
                "input",
                "output_volume",
                "input_volume",
                "output_muted",
                "input_muted",
                "output_port",
                "input_port",
                "move_streams",
                "stream",
            },
        )
        state = self.status()
        for direction in ("output", "input"):
            if not any(k == direction or k.startswith(direction + "_") for k in values):
                continue
            devices = {r["id"]: r for r in state[direction + "s"]}
            target = values.get(direction, state[direction])
            choice(target, devices, "오디오 장치")
            if direction in values and target.startswith("-"):
                raise ControllerError("오디오 장치를 다시 선택해 주세요.")
            for field in (direction + "_volume",):
                if field in values:
                    integer(values[field], 0, 100, "볼륨")
            if direction + "_muted" in values:
                boolean(values[direction + "_muted"])
            if direction + "_port" in values:
                ports = [p["id"] for p in devices[target]["ports"] if p["available"]]
                choice(values[direction + "_port"], ports, "오디오 연결")
        if "move_streams" in values:
            boolean(values["move_streams"])
        if "stream" in values:
            stream = fields(values["stream"], {"id", "serial", "volume", "muted", "output"}, ("id", "serial"))
            integer(stream["id"], 0, 2**32 - 1, "앱 식별자")
            live = next((r for r in state["streams"] if r["index"] == stream["id"]), None)
            if not live or not stream["serial"] or live["serial"] != stream["serial"]:
                raise ControllerError("앱의 소리 연결이 바뀌었어요. 다시 선택해 주세요.")
            if "volume" in stream:
                integer(stream["volume"], 0, 100, "앱 볼륨")
            if "muted" in stream:
                boolean(stream["muted"])
            if "output" in stream:
                choice(stream["output"], {r["id"] for r in state["outputs"]}, "출력 장치")
        return values

    def capture(self, settings):
        state = self.status()
        snapshot = {"defaults": {}, "devices": [], "streams": []}
        for direction, kind in (("output", "sink"), ("input", "source")):
            if direction in settings:
                snapshot["defaults"][direction] = state[direction]
            if any(k == direction or k.startswith(direction + "_") for k in settings):
                device = next(
                    r for r in state[direction + "s"] if r["id"] == settings.get(direction, state[direction])
                )
                snapshot["devices"].append(
                    {
                        "kind": kind,
                        "id": device["id"],
                        "channels": device["channels"],
                        "muted": device["muted"],
                        "port": device["port"],
                    }
                )
        if "stream" in settings or settings.get("move_streams"):
            ids = None if settings.get("move_streams") else {settings["stream"]["id"]}
            outputs = {r["index"]: r["id"] for r in state["outputs"]}
            snapshot["streams"] = [
                {
                    "id": r["index"],
                    "serial": r["serial"],
                    "channels": r["channels"],
                    "muted": r["muted"],
                    "output": outputs.get(r["sink"]),
                }
                for r in state["streams"]
                if ids is None or r["index"] in ids
            ]
        return snapshot

    def apply(self, settings):
        values = self.validate(settings)
        state = self.status()
        for direction, kind in (("output", "sink"), ("input", "source")):
            target = values.get(direction, state[direction])
            if direction in values:
                run(["/usr/bin/pactl", "set-default-" + kind, target])
            if direction + "_port" in values:
                run(["/usr/bin/pactl", "set-" + kind + "-port", target, values[direction + "_port"]])
            for suffix, command in (("_volume", "volume"), ("_muted", "mute")):
                if direction + suffix in values:
                    value = values[direction + suffix]
                    run(
                        [
                            "/usr/bin/pactl",
                            f"set-{kind}-{command}",
                            target,
                            str(int(value)) if suffix == "_muted" else str(value) + "%",
                        ]
                    )
        if values.get("move_streams"):
            for stream in state["streams"]:
                run(
                    [
                        "/usr/bin/pactl",
                        "move-sink-input",
                        str(stream["index"]),
                        values.get("output", state["output"]),
                    ]
                )
        if "stream" in values:
            stream = values["stream"]
            for key, command in (
                ("volume", "set-sink-input-volume"),
                ("muted", "set-sink-input-mute"),
                ("output", "move-sink-input"),
            ):
                if key in stream:
                    value = stream[key]
                    argument = (
                        str(value) + "%"
                        if key == "volume"
                        else (str(int(value)) if key == "muted" else value)
                    )
                    run(["/usr/bin/pactl", command, str(stream["id"]), argument])
        self._verify(values)

    def _verify(self, settings):
        def actual():
            state = self.status()
            outputs = {r["index"]: r["id"] for r in state["outputs"]}
            result = {}
            for direction in ("output", "input"):
                if direction in settings:
                    result[direction] = state[direction]
                device = next(
                    (
                        r
                        for r in state[direction + "s"]
                        if r["id"] == settings.get(direction, state[direction])
                    ),
                    None,
                )
                for suffix, field in (("_volume", "volume"), ("_muted", "muted"), ("_port", "port")):
                    if direction + suffix in settings:
                        result[direction + suffix] = device[field] if device else None
            if "stream" in settings:
                wanted = settings["stream"]
                stream = next(
                    (
                        r
                        for r in state["streams"]
                        if r["index"] == wanted["id"] and r["serial"] == wanted["serial"]
                    ),
                    None,
                )
                result["stream"] = {
                    k: (outputs.get(stream["sink"]) if k == "output" else stream[k]) if stream else None
                    for k in wanted
                    if k in ("volume", "muted", "output")
                }
            if settings.get("move_streams"):
                result["move_streams"] = all(
                    outputs.get(row["sink"]) == settings.get("output", state["output"])
                    for row in state["streams"]
                )
            return result

        expected = {k: v for k, v in settings.items() if k != "move_streams" or v}
        if "stream" in expected:
            expected["stream"] = {
                k: v for k, v in expected["stream"].items() if k in ("volume", "muted", "output")
            }
        wait_for(actual, expected)

    def comparable(self, snapshot):
        live = {(r["index"], r["serial"]) for r in self.status()["streams"]}
        return {**snapshot, "streams": [r for r in snapshot["streams"] if (r["id"], r["serial"]) in live]}

    def read_snapshot(self, snapshot):
        state = self.status()
        result = {"defaults": {key: state[key] for key in snapshot["defaults"]}, "devices": [], "streams": []}
        for saved in snapshot["devices"]:
            direction = "output" if saved["kind"] == "sink" else "input"
            row = next((r for r in state[direction + "s"] if r["id"] == saved["id"]), None)
            if not row:
                raise ControllerError("복원할 오디오 장치를 다시 연결해 주세요.")
            result["devices"].append(
                {"kind": saved["kind"], **{k: row[k] for k in ("id", "channels", "muted", "port")}}
            )
        outputs = {r["index"]: r["id"] for r in state["outputs"]}
        for saved in snapshot["streams"]:
            row = next(
                (r for r in state["streams"] if r["index"] == saved["id"] and r["serial"] == saved["serial"]),
                None,
            )
            if row:
                result["streams"].append(
                    {
                        "id": row["index"],
                        "serial": row["serial"],
                        "channels": row["channels"],
                        "muted": row["muted"],
                        "output": outputs.get(row["sink"]),
                    }
                )
        return result

    def restore(self, snapshot):
        state = self.status()
        for row in snapshot["devices"]:
            direction = "output" if row["kind"] == "sink" else "input"
            if row["id"] not in {r["id"] for r in state[direction + "s"]}:
                raise ControllerError("복원할 오디오 장치가 분리됐어요. 다시 연결해 주세요.")
        for direction, target in snapshot["defaults"].items():
            choice(target, {r["id"] for r in state[direction + "s"]}, "복원할 장치")
        snapshot = self.comparable(snapshot)
        for row in snapshot["devices"]:
            kind = row["kind"]
            if row["port"]:
                run(["/usr/bin/pactl", f"set-{kind}-port", row["id"], row["port"]])
            run(["/usr/bin/pactl", f"set-{kind}-volume", row["id"], *map(str, row["channels"])])
            run(["/usr/bin/pactl", f"set-{kind}-mute", row["id"], str(int(row["muted"]))])
        for direction, target in snapshot["defaults"].items():
            run(["/usr/bin/pactl", "set-default-" + ("sink" if direction == "output" else "source"), target])
        for row in snapshot["streams"]:
            if row["output"]:
                run(["/usr/bin/pactl", "move-sink-input", str(row["id"]), row["output"]])
            run(["/usr/bin/pactl", "set-sink-input-volume", str(row["id"]), *map(str, row["channels"])])
            run(["/usr/bin/pactl", "set-sink-input-mute", str(row["id"]), str(int(row["muted"]))])
