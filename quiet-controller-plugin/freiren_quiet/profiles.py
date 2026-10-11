"""Bounded, declarative hardware profiles shared by the root service and CLI."""

import math

PREFERENCES = ("power", "balance_power", "balance_performance", "performance")
PRESETS = {
    "quiet": {"cap": 60, "turbo": False, "preference": "power", "power_w": 18, "boost_w": 25},
    "balanced": {
        "cap": 75,
        "turbo": False,
        "preference": "balance_performance",
        "power_w": 28,
        "boost_w": 38,
    },
    "performance": {
        "cap": 100,
        "turbo": True,
        "preference": "performance",
        "power_w": 45,
        "boost_w": 56.25,
    },
}


def validate_custom(value):
    if not isinstance(value, dict) or set(value) != {
        "cap",
        "turbo",
        "preference",
        "power_w",
        "boost_w",
    }:
        raise ValueError("사용자 지정 설정 항목이 올바르지 않습니다.")
    if type(value["cap"]) is not int or not 25 <= value["cap"] <= 100:
        raise ValueError("CPU 상한은 25~100% 정수여야 합니다.")
    if type(value["turbo"]) is not bool or value["preference"] not in PREFERENCES:
        raise ValueError("터보 또는 절전 성향 값이 올바르지 않습니다.")
    long, short = value["power_w"], value["boost_w"]
    if long is None and short is None:
        return dict(value)
    for number, upper in ((long, 45), (short, 56.25)):
        if (
            type(number) not in (int, float)
            or not math.isfinite(number)
            or not 10 <= number <= upper
        ):
            raise ValueError("전력 한도는 지속 10~45W, 순간 10~56.25W여야 합니다.")
        if number * 4 != round(number * 4):
            raise ValueError("전력 한도는 0.25W 단위여야 합니다.")
    if long > short:
        raise ValueError("순간 전력 한도는 지속 한도 이상이어야 합니다.")
    return dict(value)


def bounded_preset(mode, baseline):
    result = dict(PRESETS["balanced" if mode == "auto" else mode])
    if baseline is None:
        result.update(power_w=None, boost_w=None)
    else:
        result["power_w"] = min(result["power_w"], baseline["power_w"])
        result["boost_w"] = min(result["boost_w"], baseline["boost_w"])
    return result
