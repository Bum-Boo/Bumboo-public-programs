"""Pure, testable thermal policy. Percentages are Intel P-state limits, not CPU usage."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    cap: int
    no_turbo: int
    profile: str
    reason: str


MODES = {
    "quiet": Decision(60, 1, "power-saver", "조용함 · 속도 상한 60%"),
    "balanced": Decision(75, 1, "balanced", "균형 · 속도 상한 75%"),
    "performance": Decision(100, 0, "performance", "성능 · 터보 허용"),
}
MODE_LABELS = {
    "auto": "자동",
    "quiet": "조용함",
    "balanced": "균형",
    "performance": "성능",
    "restore": "관리 해제",
}


class ThermalPolicy:
    """5-second samples; fast reduction, slow recovery, and an independent hot guard."""

    def __init__(self, mode: str = "auto", target: int = 64):
        self.set_mode(mode)
        self.set_target(target)

    def set_mode(self, mode: str) -> None:
        if mode not in MODE_LABELS:
            raise ValueError("지원하지 않는 모드입니다.")
        self.mode = mode
        self.cap = 60
        self.hot_samples = 0
        self.cool_samples = 0
        self.emergency = False

    def set_target(self, target: int) -> None:
        if type(target) is not int or not 58 <= target <= 75:
            raise ValueError("목표 온도는 58~75°C의 정수여야 합니다.")
        self.target = target
        self.hot_samples = 0
        self.cool_samples = 0

    def decide(self, temperature: float | None) -> Decision | None:
        if self.mode == "restore":
            return None
        if temperature is None or not math.isfinite(temperature) or not 0 < temperature < 125:
            self.cool_samples = 0
            self.hot_samples = 0
            self.cap = min(self.cap, 40)
            return Decision(40, 1, "power-saver", "온도 센서를 읽을 수 없어 보수적으로 제한 중")

        if temperature >= 85:
            self.emergency = True
            self.cool_samples = 0
        if self.emergency:
            self.cool_samples = self.cool_samples + 1 if temperature <= 75 else 0
            if self.cool_samples < 6:
                return Decision(25, 1, "power-saver", "85°C 이상 감지 · 냉각 후 제한 완화")
            self.emergency = False
            self.cool_samples = 0
            self.cap = 40

        if self.mode != "auto":
            return MODES[self.mode]

        if temperature >= 78:
            self.cap = 40
            self.hot_samples = 0
            self.cool_samples = 0
        elif temperature >= self.target + 3:
            self.hot_samples += 1
            self.cool_samples = 0
            if self.hot_samples >= 2:
                self.cap = max(40, self.cap - 5)
                self.hot_samples = 0
        elif temperature <= self.target - 4:
            self.cool_samples += 1
            self.hot_samples = 0
            if self.cool_samples >= 6:
                self.cap = min(75, self.cap + 5)
                self.cool_samples = 0
        else:
            self.hot_samples = 0
            self.cool_samples = 0
        return Decision(self.cap, 1, "power-saver", f"목표 {self.target}°C · 속도 상한 {self.cap}%")
