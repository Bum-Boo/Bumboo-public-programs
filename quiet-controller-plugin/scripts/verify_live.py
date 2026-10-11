"""Explicit hardware round trips; preserve the active profile, custom settings and target."""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from freiren_quiet import client  # noqa: E402
from freiren_quiet.hardware import Hardware  # noqa: E402


def check_readback(status):
    assert status["error"] is None, status["error"]
    hardware = Hardware().snapshot()
    for key in ("limits", "epp", "power_limits"):
        assert status[key] == hardware[key], (key, status[key], hardware[key])
    return hardware


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live", action="store_true", required=True)
    parser.parse_args()
    original = client.request()
    if original.get("protocol_version", 1) < 2 or not original.get("advanced"):
        parser.error("먼저 새 프리셋을 직접 선택하세요. 구버전 설정을 자동 전환하지 않습니다.")
    try:
        baseline = check_readback(client.request("reset"))
        for mode, desired in original["presets"].items():
            status = client.request("mode", mode=mode)
            check_readback(status)
            assert status["mode"] == mode, status
            guarded = "85°C" in status["reason"] or "센서" in status["reason"]
            if not guarded:
                assert status["limits"]["max_perf_pct"] == desired["cap"], status
                assert status["limits"]["no_turbo"] == int(not desired["turbo"]), status
            if desired["power_w"] is not None:
                for key in ("power_w", "boost_w"):
                    assert abs(status["power_limits"][key] - desired[key]) <= 0.125, status
            print(f"PASS: {mode} actual CPU/EPP/RAPL readback")
        custom = {**original["presets"]["quiet"], "cap": 65, "preference": "balance_power"}
        check_readback(client.request("configure", settings=custom))
        time.sleep(6)
        status = client.request()
        check_readback(status)
        assert status["mode"] == "custom" and status["custom"] == custom, status
        print("PASS: custom survives periodic control")
        restored = check_readback(client.request("reset"))
        for key in ("limits", "epp", "power_limits"):
            assert restored[key] == baseline[key], key
        print("PASS: reset restores CPU, EPP and power limits")
        try:
            client.request("configure", settings={**custom, "power_w": 500})
        except RuntimeError:
            pass
        else:
            raise AssertionError("Invalid power accepted")
        assert Hardware().snapshot() == restored
        print("PASS: invalid input leaves hardware unchanged")
    finally:
        client.request("configure", settings=original["custom"])
        client.request("mode", mode=original["mode"])
        client.request("target", target=original["target_c"])
        print("Previous profile, saved custom settings and target restored.")


if __name__ == "__main__":
    main()
