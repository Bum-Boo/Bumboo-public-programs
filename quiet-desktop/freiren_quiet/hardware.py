"""Only the documented Intel P-state controls are written. Fan/EC registers are untouched."""

import json
import math
import os
from pathlib import Path


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class Hardware:
    def __init__(self, sys_root: Path = Path("/sys")):
        self.root = sys_root
        self.pstate = sys_root / "devices/system/cpu/intel_pstate"
        self.policies = sys_root / "devices/system/cpu/cpufreq"

    def identity(self) -> dict:
        dmi = self.root / "devices/virtual/dmi/id"
        return {
            "vendor": (dmi / "sys_vendor").read_text().strip(),
            "model": (dmi / "product_name").read_text().strip(),
            "driver": (self.policies / "policy0/scaling_driver").read_text().strip(),
        }

    def validate(self) -> dict:
        identity = self.identity()
        if (
            identity["model"] != "GL62 6QE"
            or "Micro-Star" not in identity["vendor"]
            or identity["driver"] != "intel_pstate"
        ):
            raise RuntimeError("이 설정은 MSI GL62 6QE / intel_pstate 전용입니다.")
        for name in ("no_turbo", "min_perf_pct", "max_perf_pct"):
            if not (self.pstate / name).is_file():
                raise RuntimeError(f"필수 CPU 제어 항목이 없습니다: {name}")
        return identity

    def snapshot(self) -> dict:
        return {
            "identity": self.identity(),
            "limits": {
                name: int((self.pstate / name).read_text())
                for name in ("no_turbo", "min_perf_pct", "max_perf_pct")
            },
            "epp": {
                policy.name: (policy / "energy_performance_preference").read_text().strip()
                for policy in sorted(self.policies.glob("policy[0-9]*"))
                if (policy / "energy_performance_preference").is_file()
            },
        }

    def _write(self, name: str, value: int) -> None:
        path = self.pstate / name
        if int(path.read_text()) == value:
            return
        path.write_text(str(value), encoding="ascii")
        if int(path.read_text()) != value:
            raise RuntimeError(f"CPU 설정 검증 실패: {name}={value}")

    def _restore_limits(self, limits: dict) -> None:
        # Widen first so a former high minimum cannot clamp the restored maximum.
        self._write("min_perf_pct", min(limits["min_perf_pct"], 25))
        self._write("no_turbo", limits["no_turbo"])
        self._write("max_perf_pct", limits["max_perf_pct"])
        self._write("min_perf_pct", limits["min_perf_pct"])

    def apply(self, cap: int, no_turbo: int) -> None:
        if type(cap) is not int or not 25 <= cap <= 100 or type(no_turbo) is not int:
            raise ValueError("CPU 제어 값 범위 오류")
        if no_turbo not in (0, 1):
            raise ValueError("터보 제어 값 오류")
        previous = self.snapshot()["limits"]
        try:
            self._write("min_perf_pct", min(previous["min_perf_pct"], cap))
            self._write("no_turbo", no_turbo)
            self._write("max_perf_pct", cap)
        except (OSError, RuntimeError) as error:
            try:
                self._restore_limits(previous)
            except (OSError, RuntimeError) as rollback_error:
                raise RuntimeError(f"{error}; 되돌리기도 실패: {rollback_error}") from error
            raise

    def restore(self, snapshot: dict) -> None:
        if snapshot["identity"] != self.identity():
            raise RuntimeError("복원 파일의 하드웨어가 현재 컴퓨터와 다릅니다.")
        self._restore_limits(snapshot["limits"])
        for policy, value in snapshot["epp"].items():
            if not policy.startswith("policy") or not policy[6:].isdigit():
                raise ValueError("잘못된 CPU 정책 이름")
            path = self.policies / policy / "energy_performance_preference"
            if path.exists() and path.read_text().strip() != value:
                path.write_text(value, encoding="ascii")
                if path.read_text().strip() != value:
                    raise RuntimeError(f"절전 성향 복원 검증 실패: {policy}")

    def temperatures(self) -> dict:
        readings = {}
        # coretemp is authoritative; ACPI is displayed separately and not substituted
        # for an unavailable CPU package sensor.
        for hwmon in (self.root / "class/hwmon").glob("hwmon*"):
            try:
                name = (hwmon / "name").read_text().strip()
            except OSError:
                continue
            if name not in ("coretemp", "acpitz"):
                continue
            for sensor in hwmon.glob("temp*_input"):
                try:
                    value = float(sensor.read_text()) / 1000
                    label_path = sensor.with_name(sensor.name.replace("_input", "_label"))
                    label = label_path.read_text().strip() if label_path.exists() else sensor.stem
                    if math.isfinite(value) and 0 < value < 125:
                        readings[f"{name}:{label}"] = value
                except (OSError, ValueError):
                    continue
        core = [value for key, value in readings.items() if key.startswith("coretemp:")]
        return {"cpu_c": max(core) if core else None, "sensors": readings}

    def gpu_state(self) -> str:
        # Reading runtime_status does not wake the NVIDIA device.
        path = self.root / "bus/pci/devices/0000:01:00.0/power/runtime_status"
        try:
            return path.read_text().strip()
        except OSError:
            return "unknown"
