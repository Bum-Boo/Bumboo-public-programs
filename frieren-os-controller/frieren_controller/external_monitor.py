"""Conditional DDC/CI support with fixed feature codes and per-device baselines."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
from pathlib import Path

from .core import ControllerError
from .monitor import integer

FEATURES = {"brightness": "10", "contrast": "12", "input": "60"}
INPUT_NAMES = {1: "VGA 1", 3: "DVI 1", 15: "DisplayPort 1", 16: "DisplayPort 2", 17: "HDMI 1", 18: "HDMI 2"}


def parse_detect(output):
    displays = []
    for block in re.split(r"(?m)^(?=Display \d+\s*$|Invalid display)", output):
        display = re.match(r"Display (\d+)\s*\n", block)
        bus = re.search(r"I2C bus:\s*/dev/i2c-(\d+)", block)
        identity = re.search(r"Monitor:\s*(.+)", block)
        connector = re.search(r"DRM connector:\s*(\S+)", block)
        if not display or not bus or not identity:
            continue
        connector = connector[1] if connector else ""
        if "eDP" in connector or "LVDS" in connector:
            continue
        identifier = hashlib.sha256((connector + ":" + identity[1].strip()).encode()).hexdigest()[:24]
        parts = identity[1].strip().split(":")
        displays.append(
            {
                "id": identifier,
                "bus": int(bus[1]),
                "connector": connector,
                "name": " ".join(parts[:2]) or "외장 모니터",
            }
        )
    return displays


def parse_vcp(output, code):
    continuous = re.search(rf"(?m)^VCP {code} C (\d+) (\d+)\s*$", output, re.I)
    if continuous:
        current, maximum = map(int, continuous.groups())
        if maximum > 0 and current <= maximum:
            return {"raw": current, "maximum": maximum, "value": round(current * 100 / maximum)}
    noncontinuous = re.search(rf"(?m)^VCP {code} SNC x([0-9a-f]+)\s*$", output, re.I)
    if noncontinuous:
        value = int(noncontinuous[1], 16)
        return {"raw": value, "value": value}
    raise ControllerError("이 모니터에서 해당 항목을 읽지 못했어요.")


class ExternalControls:
    def __init__(self, state_dir: Path, command):
        self.command = command
        self.path = state_dir / "external-monitor.json"
        self.lock = threading.RLock()
        try:
            self.baselines = json.loads(self.path.read_text()) if self.path.exists() else {}
        except ValueError as exc:
            raise ControllerError("외장 모니터 복원 파일을 확인해 주세요.") from exc
        if not isinstance(self.baselines, dict):
            raise ControllerError("외장 모니터 복원 파일을 확인해 주세요.")

    def _save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.baselines) + "\n")
        temporary.chmod(0o600)
        temporary.replace(self.path)

    def _run(self, *args):
        return self.command(["/usr/bin/ddcutil", "--noconfig", *args], timeout=8)

    def _detect(self):
        if not shutil.which("ddcutil"):
            return []
        return parse_detect(self._run("detect", "--terse"))

    def _read(self, device, feature):
        return parse_vcp(
            self._run("--bus", str(device["bus"]), "getvcp", FEATURES[feature], "--terse"), FEATURES[feature]
        )

    def _inputs(self, device):
        try:
            caps = self._run("--bus", str(device["bus"]), "capabilities", "--terse")
        except ControllerError:
            return []
        values = re.search(r"(?:^|[\s(])60\s*\(([^()]*)\)", caps, re.I)
        if not values:
            return []
        return sorted(
            {
                int(value, 16)
                for value in values[1].split()
                if re.fullmatch(r"[0-9a-fA-F]{2}", value) and int(value, 16) > 0
            }
        )

    def status(self):
        with self.lock:
            rows = self._detect()
            for row in rows:
                features = {}
                for feature in FEATURES:
                    try:
                        features[feature] = self._read(row, feature)
                    except ControllerError:
                        features[feature] = None
                inputs = self._inputs(row) if features["input"] else []
                row["features"] = features
                row["inputs"] = [
                    {"value": value, "name": INPUT_NAMES.get(value, f"입력 {value:02X}")} for value in inputs
                ]
                row["has_baseline"] = row["id"] in self.baselines
                row.pop("bus")
            return {
                "displays": rows,
                "available": shutil.which("ddcutil") is not None,
                "message": "외장 모니터를 연결한 뒤 다시 확인해 주세요." if not rows else "",
            }

    def _device(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{24}", identifier):
            raise ControllerError("외장 모니터를 다시 확인해 주세요.")
        device = next((row for row in self._detect() if row["id"] == identifier), None)
        if device is None:
            raise ControllerError("모니터 연결이 바뀌었어요. 다시 확인해 주세요.")
        return device

    def set(self, identifier, feature, value):
        if not isinstance(feature, str) or feature not in FEATURES:
            raise ControllerError("밝기·명암·입력만 조절할 수 있어요.")
        integer(value, 5 if feature == "brightness" else 0, 255 if feature == "input" else 100, "외장 설정")
        with self.lock:
            device = self._device(identifier)
            before = self._read(device, feature)
            if feature == "input":
                if value not in self._inputs(device):
                    raise ControllerError("모니터에서 지원하는 입력을 골라 주세요.")
                raw = value
            else:
                if "maximum" not in before:
                    raise ControllerError("이 모니터의 조절 범위를 확인하지 못했어요.")
                raw = round(value * before["maximum"] / 100)
            baseline = self.baselines.setdefault(identifier, {})
            baseline.setdefault(feature, before["raw"])
            self._save()
            try:
                self._write(device, feature, raw)
                after = self._read(device, feature)
                if after["raw"] != raw:
                    raise ControllerError("변경 값을 확인하지 못해 이전 값으로 되돌렸어요.")
            except ControllerError as exc:
                try:
                    self._write(device, feature, before["raw"])
                    if self._read(device, feature)["raw"] != before["raw"]:
                        raise ControllerError("복원 값을 확인하지 못했어요.")
                except ControllerError:
                    raise ControllerError(
                        "변경과 복원 값을 확인하지 못했어요. 모니터 연결이나 입력 버튼을 확인해 주세요."
                    ) from exc
                raise
            return {"id": identifier, "feature": feature, "applied": after}

    def _write(self, device, feature, raw):
        self._run("--bus", str(device["bus"]), "setvcp", FEATURES[feature], str(raw), "--verify")

    def reset(self, identifier):
        with self.lock:
            device = self._device(identifier)
            baseline = self.baselines.get(identifier)
            if not baseline:
                raise ControllerError("이 모니터의 원래 설정을 아직 저장하지 않았어요.")
            restored = []
            # Restore input last: switching inputs may disconnect the DDC transport.
            for feature in ("brightness", "contrast", "input"):
                if feature in baseline:
                    self._write(device, feature, baseline[feature])
                    if self._read(device, feature)["raw"] != baseline[feature]:
                        raise ControllerError("복원 값을 확인하지 못했어요. 모니터 연결을 확인해 주세요.")
                    restored.append(feature)
            return {"id": identifier, "restored": restored}
