import argparse
import json
import subprocess
import sys
import time

from . import __version__, client
from .policy import MODE_LABELS


def main(argv=None):
    parser = argparse.ArgumentParser(description="MSI GL62 6QE 맞춤 전력·소음 관리")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("gui", help="한국어 제어 화면")
    status = commands.add_parser("status", help="현재 설정과 온도")
    status.add_argument("--json", action="store_true")
    mode = commands.add_parser("mode", help="전력 모드 전환")
    mode.add_argument("mode", choices=MODE_LABELS)
    target = commands.add_parser("target", help="자동 모드 목표 온도 (58~75°C)")
    target.add_argument("temperature", type=int)
    commands.add_parser("restore", help="설치 전 CPU 설정 복원 및 자동 조절 해제")
    commands.add_parser("daemon", help=argparse.SUPPRESS)
    effect = commands.add_parser("effects", help="이번 KDE 세션의 화면 효과")
    effect.add_argument("action", choices=("save", "restore", "status"))
    monitor = commands.add_parser("monitor", help="간격별 온도·부하 JSON 출력")
    monitor.add_argument("--seconds", type=int, default=60)
    limited = commands.add_parser("run", help="현재 사용자 권한으로 CPU 제한을 적용해 작업 실행")
    limited.add_argument("--cpu", type=int, default=100, help="100=한 코어, 400=이 노트북 전체")
    limited.add_argument("program", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.command in (None, "gui"):
            from .gui import run

            return run()
        if args.command == "daemon":
            from .service import serve

            serve()
            return 0
        if args.command == "effects":
            from . import effects

            if args.action != "status":
                effects.set_savings(args.action == "save")
            print("화면 효과 절약 중" if effects.state_path().exists() else "기본 화면 효과")
            return 0
        if args.command == "run":
            if not 1 <= args.cpu <= 400:
                parser.error("--cpu 값은 1~400이어야 합니다.")
            program = args.program[1:] if args.program[:1] == ["--"] else args.program
            if not program:
                parser.error("실행할 명령이 필요합니다. 예: run --cpu 100 -- make")
            return subprocess.run(
                [
                    "systemd-run",
                    "--user",
                    "--scope",
                    "--quiet",
                    "--collect",
                    f"--property=CPUQuota={args.cpu}%",
                    "--",
                    *program,
                ],
                check=False,
            ).returncode
        if args.command == "monitor":
            if not 5 <= args.seconds <= 3600:
                parser.error("측정 시간은 5~3600초여야 합니다.")
            from .monitor import Monitor

            sampler = Monitor()
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline:
                time.sleep(min(5, max(0, deadline - time.monotonic())))
                status = client.request()
                status.update(sampler.sample())
                print(json.dumps(status, ensure_ascii=False), flush=True)
            return 0
        if args.command == "mode":
            status = client.request("mode", mode=args.mode)
        elif args.command == "restore":
            status = client.request("mode", mode="restore")
        elif args.command == "target":
            status = client.request("target", target=args.temperature)
        else:
            status = client.request()
        if getattr(args, "json", False):
            print(json.dumps(status, ensure_ascii=False, indent=2))
        else:
            temperature = f"{status['cpu_c']:.0f}°C" if status["cpu_c"] is not None else "센서 없음"
            print(
                f"{status['mode_label']} · CPU {temperature} · 상한 {status['limits']['max_perf_pct']}%"
            )
            print(status["reason"])
            if status["error"]:
                print(status["error"], file=sys.stderr)
                return 1
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"Freiren Quiet: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
