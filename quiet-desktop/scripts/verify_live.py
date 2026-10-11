"""Explicit opt-in checks on the installed controller; restores the previous mode and effects."""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from freiren_quiet import client, effects  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live", action="store_true", required=True)
    parser.parse_args()
    original = client.request()
    initial_effects = effects.state_path().exists()
    changed_effects = False
    try:
        for mode, cap, turbo in (("quiet", 60, 1), ("balanced", 75, 1), ("performance", 100, 0)):
            status = client.request("mode", mode=mode)
            assert status["error"] is None, status
            assert status["mode"] == mode, status
            # The 85°C guard deliberately overrides fixed modes on a hot machine.
            if status["cpu_c"] is not None and status["cpu_c"] < 85:
                assert status["limits"]["max_perf_pct"] == cap, status
                assert status["limits"]["no_turbo"] == turbo, status
            print(f"PASS: {mode} readback")
        restored = client.request("mode", mode="restore")
        assert restored["mode"] == "restore", restored
        assert restored["error"] is None, restored
        print("PASS: restore")
        for payload in (("target", {"target": 500}), ("mode", {"mode": "invalid"})):
            try:
                client.request(payload[0], **payload[1])
            except RuntimeError:
                pass
            else:
                raise AssertionError("Invalid request accepted")
        print("PASS: invalid requests rejected")
        if not initial_effects:
            before = {name: effects.call("isEffectLoaded", name) for name in effects.EFFECTS}
            changed_effects = True
            effects.set_savings(True)
            assert all(effects.call("isEffectLoaded", name) == "false" for name in effects.EFFECTS)
            effects.set_savings(False)
            assert {
                name: effects.call("isEffectLoaded", name) for name in effects.EFFECTS
            } == before
            changed_effects = False
            print("PASS: KWin effects round trip")
        command = [
            "freiren-quiet",
            "run",
            "--cpu",
            "50",
            "--",
            sys.executable,
            "-c",
            "from pathlib import Path; "
            "group=next(line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')); "
            "quota,period=(Path('/sys/fs/cgroup') / group.lstrip('/') / 'cpu.max').read_text().split(); "
            "assert int(quota)/int(period)==0.5; print('PASS: user scope CPUQuota=50%')",
        ]
        subprocess.run(command, check=True)
    finally:
        if changed_effects:
            effects.set_savings(False)
        client.request("target", target=original["target_c"])
        client.request("mode", mode=original["mode"])
        print("Previous mode and target restored.")


if __name__ == "__main__":
    main()
