"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from functools import partial

from .client import call as api_call
from .core import ControllerError

call = partial(api_call, _source="cli")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="frieren-controller", description="프리렌 OS 컨트롤러")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("daemon", help="사용자 소켓 데몬 실행")
    actions.add_parser("gui", help="GTK 관리 화면 실행")
    actions.add_parser("mcp", help="MCP stdio 서버 실행")
    actions.add_parser("dashboard", help="상태 카드 출력")
    jobs = actions.add_parser("jobs", help="내 계정 서비스·타이머·crontab 추가와 편집")
    jobs.add_argument("operation", choices=("read", "save", "cron-read", "cron-save"))
    jobs.add_argument("unit", nargs="?")
    jobs.add_argument("--revision")
    jobs.add_argument("--file", help="저장할 UTF-8 파일; -는 표준 입력")
    workspace = actions.add_parser("workspace", help="패널·스타일·창·소리·입력·연결 설정")
    workspace.add_argument(
        "operation", choices=("status", "apply", "presets", "save", "preset", "open-himmel")
    )
    workspace.add_argument("area", nargs="?")
    workspace.add_argument("value", nargs="?")
    workspace.add_argument("extra", nargs="?")
    mode = actions.add_parser("mode", help="통합 작업 모드 저장·적용·종료")
    mode.add_argument("operation", choices=("status", "save", "apply", "end"))
    mode.add_argument("name", nargs="?")
    mode.add_argument("settings", nargs="?")
    history = actions.add_parser("history", help="설정 변경 기록과 변경 직전 값 복원")
    history.add_argument("operation", choices=("list", "revert", "recover"), default="list", nargs="?")
    history.add_argument("identifier", nargs="?")
    quiet = actions.add_parser("quiet", help="Freiren Quiet 전원 모드")
    quiet.add_argument("operation", choices=("status", "mode", "target", "effects", "custom", "reset"))
    quiet.add_argument("value", nargs="?")
    quiet.add_argument("--cap", type=int)
    quiet.add_argument("--turbo", action="store_true")
    quiet.add_argument("--preference", default="balance_performance")
    quiet.add_argument("--power", type=float)
    quiet.add_argument("--boost", type=float)
    monitor = actions.add_parser("monitor", help="화면 밝기·야간 모드·구성")
    monitor.add_argument(
        "operation",
        choices=("status", "preset", "configure", "reset", "awake", "color", "layout", "confirm", "revert"),
    )
    monitor.add_argument("value", nargs="?")
    external = actions.add_parser("external", help="외장 모니터 직접 제어")
    external.add_argument("operation", choices=("status", "set", "reset"))
    external.add_argument("identifier", nargs="?")
    external.add_argument("feature", nargs="?", choices=("brightness", "contrast", "input"))
    external.add_argument("value", nargs="?", type=int)
    appearance = actions.add_parser("appearance", help="바탕화면과 Konsole 배경")
    appearance.add_argument(
        "operation",
        choices=("status", "wallpaper", "wallpaper-reset", "terminal", "terminal-reset", "terminal-open"),
    )
    appearance.add_argument("value", nargs="?")
    appearance.add_argument("--desktop", type=int)
    appearance.add_argument("--fill", choices=("crop", "fit", "stretch", "center", "tile"), default="crop")
    listing = actions.add_parser("list", help="서비스·타이머 목록")
    listing.add_argument("--scope", choices=("system", "user"), default="system")
    listing.add_argument("--kind", choices=("all", "service", "timer"), default="all")
    listing.add_argument("--search", default="")
    toggle = actions.add_parser("toggle", help="서비스·타이머 켜기/끄기")
    toggle.add_argument("scope", choices=("system", "user"))
    toggle.add_argument("unit")
    toggle.add_argument("state", choices=("on", "off"))
    toggle.add_argument("--preview", action="store_true")
    note = actions.add_parser("note", help="서비스·타이머 메모 확인/저장")
    note.add_argument("scope", choices=("system", "user"))
    note.add_argument("unit")
    note.add_argument("text", nargs="?")
    options = parser.parse_args(argv)
    try:
        if options.action == "daemon":
            from .server import serve

            serve()
            return 0
        if options.action == "gui":
            try:
                from .gui import main as gui_main
            except (ImportError, ValueError) as exc:
                # PyGObject or the GTK 3 typelib is missing (gi.require_version raises ValueError).
                raise ControllerError(
                    f"GTK 3 화면을 열 수 없어요. PyGObject와 GTK 3를 확인해 주세요: {exc}"
                ) from exc

            return gui_main()
        if options.action == "mcp":
            from .mcp_server import main as mcp_main

            return mcp_main()
        if options.action == "jobs":
            operation = options.operation
            if operation in ("read", "save") and not options.unit:
                parser.error("서비스 또는 타이머 이름을 입력해 주세요.")
            if operation.startswith("cron-") and options.unit:
                parser.error("cron 명령에는 서비스 이름이 필요 없어요.")
            args = {"unit": options.unit} if operation in ("read", "save") else {}
            if operation in ("save", "cron-save"):
                if options.file is None or options.revision is None:
                    parser.error("--file과 읽었을 때의 --revision을 입력해 주세요.")
                from pathlib import Path

                try:
                    content = sys.stdin.read(24001) if options.file == "-" else Path(options.file).read_text()
                except (OSError, UnicodeError) as exc:
                    raise ControllerError("입력 파일을 읽지 못했어요.") from exc
                args.update(content=content, revision=options.revision)
            result = call(
                {
                    "read": "job_unit_read",
                    "save": "job_unit_save",
                    "cron-read": "job_cron_read",
                    "cron-save": "job_cron_save",
                }[operation],
                **args,
            )
        elif options.action == "workspace":
            operation = options.operation
            if operation == "open-himmel":
                if options.area or options.value or options.extra:
                    parser.error("open-himmel에는 추가 값이 필요 없어요.")
                result = call("himmel_open")
            elif operation in ("status", "presets"):
                if not options.area or options.value or options.extra:
                    parser.error("설정 화면 이름만 입력해 주세요.")
                result = call(
                    "workspace_status" if operation == "status" else "workspace_presets", area=options.area
                )
            elif operation == "preset":
                if not options.area or not options.value or options.extra:
                    parser.error("설정 화면과 프리셋 이름을 입력해 주세요.")
                result = call("workspace_apply_preset", area=options.area, name=options.value)
            else:
                raw = options.extra if operation == "save" else options.value
                if (
                    not options.area
                    or raw is None
                    or (operation == "save" and not options.value)
                    or (operation == "apply" and options.extra is not None)
                ):
                    parser.error("설정 화면과 설정 JSON을 입력해 주세요. save에는 이름도 필요해요.")
                try:
                    values = json.loads(raw)
                except ValueError:
                    parser.error("설정값을 JSON으로 입력해 주세요.")
                result = (
                    call("workspace_save_preset", area=options.area, name=options.value, settings=values)
                    if (operation == "save")
                    else call("workspace_configure", area=options.area, settings=values)
                )
        elif options.action == "mode":
            if options.operation in ("status", "end"):
                if options.name or options.settings:
                    parser.error("이 명령에는 추가 값이 필요 없어요.")
                result = call("work_mode_status" if options.operation == "status" else "work_mode_end")
            elif options.operation == "apply":
                if not options.name or options.settings:
                    parser.error("적용할 모드 이름을 입력해 주세요.")
                result = call("work_mode_apply", name=options.name)
            else:
                if not options.name or options.settings is None:
                    parser.error("모드 이름과 설정 JSON을 입력해 주세요.")
                try:
                    values = json.loads(options.settings)
                except ValueError:
                    parser.error("설정값을 JSON으로 입력해 주세요.")
                result = call("work_mode_save", name=options.name, settings=values)
        elif options.action == "history":
            if options.operation == "revert":
                if not options.identifier:
                    parser.error("복원할 변경 식별자를 입력해 주세요.")
                result = call("settings_revert", identifier=options.identifier)
            else:
                if options.identifier:
                    parser.error("이 명령에는 식별자가 필요 없어요.")
                result = call("settings_history" if options.operation == "list" else "settings_recover")
        elif options.action == "dashboard":
            result = call("dashboard")
        elif options.action == "appearance":
            if options.operation in ("status", "wallpaper-reset", "terminal-reset", "terminal-open"):
                if options.value is not None:
                    parser.error("이 명령에는 값이 필요 없어요.")
                result = (
                    call("wallpaper_reset", desktop_id=options.desktop)
                    if options.operation == "wallpaper-reset"
                    else call(
                        "appearance_status"
                        if options.operation == "status"
                        else options.operation.replace("-", "_")
                    )
                )
            else:
                if options.value is None:
                    parser.error("이미지 경로나 터미널 설정 JSON을 입력해 주세요.")
                if options.operation == "wallpaper":
                    result = call(
                        "wallpaper_set", image=options.value, desktop_id=options.desktop, fill=options.fill
                    )
                else:
                    try:
                        settings = json.loads(options.value)
                    except ValueError:
                        parser.error("설정값을 JSON으로 입력해 주세요.")
                    result = call("terminal_configure", settings=settings)
        elif options.action == "external":
            if options.operation == "status":
                if options.identifier is not None:
                    parser.error("status에는 값이 필요 없어요.")
                result = call("monitor_external_status")
            elif options.operation == "reset":
                if options.identifier is None or options.feature is not None:
                    parser.error("복원할 모니터 식별자를 입력해 주세요.")
                result = call("monitor_external_reset", identifier=options.identifier)
            else:
                if options.identifier is None or options.feature is None or options.value is None:
                    parser.error("모니터 식별자와 항목·값을 입력해 주세요.")
                result = call(
                    "monitor_external_set",
                    identifier=options.identifier,
                    feature=options.feature,
                    value=options.value,
                )
        elif options.action == "monitor":
            operation = options.operation
            if operation in ("status", "reset"):
                if options.value is not None:
                    parser.error("이 명령에는 값이 필요 없어요.")
                result = call("monitor_" + operation)
            else:
                if options.value is None:
                    parser.error("설정값을 입력해 주세요.")
                if operation == "preset":
                    result = call("monitor_preset", name=options.value)
                elif operation in ("awake", "color"):
                    try:
                        minutes = int(options.value)
                    except ValueError:
                        parser.error("시간은 분 단위 정수로 입력해 주세요.")
                    result = call(
                        "monitor_keep_awake" if operation == "awake" else "monitor_original_color",
                        minutes=minutes,
                    )
                elif operation in ("configure", "layout"):
                    try:
                        settings = json.loads(options.value)
                    except ValueError:
                        parser.error("설정값을 JSON으로 입력해 주세요.")
                    result = (
                        call("monitor_configure", settings=settings)
                        if operation == "configure"
                        else call("monitor_preview_layout", layout=settings)
                    )
                else:
                    result = call("monitor_confirm_layout", token=options.value, keep=operation == "confirm")
        elif options.action == "quiet":
            if options.operation == "custom":
                if options.cap is None:
                    parser.error("--cap 값을 입력해 주세요.")
                result = call(
                    "quiet_configure",
                    settings={
                        "cap": options.cap,
                        "turbo": options.turbo,
                        "preference": options.preference,
                        "power_w": options.power,
                        "boost_w": options.boost,
                    },
                )
            elif options.operation == "reset":
                result = call("quiet_reset")
            elif options.operation == "status":
                if options.value is not None:
                    parser.error("status에는 값이 필요 없어요.")
                result = call("quiet_status")
            elif options.operation == "mode":
                if options.value is None:
                    parser.error("mode 값을 입력해 주세요.")
                result = call("quiet_set_mode", mode=options.value)
            elif options.operation == "target":
                if options.value is None:
                    parser.error("목표 온도를 입력해 주세요.")
                try:
                    temperature = int(options.value)
                except ValueError:
                    parser.error("목표 온도는 정수여야 해요.")
                result = call("quiet_set_target", temperature=temperature)
            elif options.value == "status":
                result = call("quiet_status")["effects_saving"]
            elif options.value in ("on", "off"):
                result = call("quiet_set_effects", enabled=options.value == "on")
            else:
                parser.error("effects 값은 on, off 또는 status여야 해요.")
        elif options.action == "list":
            result = call("list_units", scope=options.scope, kind=options.kind, search=options.search)
        elif options.action == "toggle":
            operation = "preview_toggle" if options.preview else "toggle_unit"
            result = call(operation, scope=options.scope, unit=options.unit, enabled=options.state == "on")
        elif options.action == "note":
            if options.text is None:
                result = call("get_note", scope=options.scope, unit=options.unit)
            else:
                result = call("set_note", scope=options.scope, unit=options.unit, note=options.text)
        else:
            parser.error("알 수 없는 명령이에요.")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ControllerError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
