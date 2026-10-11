"""Install this checkout as a current-user daemon and desktop application."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
EXEC = PROJECT / ".venv/bin/frieren-controller"


def install() -> None:
    if not EXEC.exists():
        raise SystemExit("먼저 .venv에 이 프로젝트를 설치해 주세요: .venv/bin/pip install -e .")
    systemd = Path.home() / ".config/systemd/user"
    desktop = Path.home() / ".local/share/applications"
    systemd.mkdir(parents=True, exist_ok=True)
    desktop.mkdir(parents=True, exist_ok=True)
    icons = Path.home() / ".local/share/icons/hicolor/scalable/apps"
    icons.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        PROJECT / "assets/frieren-controller.svg",
        icons / "io.github.BumBoo.FrierenOSController.svg",
    )
    widgets = Path.home() / ".local/share/plasma/plasmoids/io.github.BumBoo.FrierenController"
    shutil.copytree(PROJECT / "assets/plasmoid", widgets, dirs_exist_ok=True)
    for source, destination in (
        (PROJECT / "packaging/frieren-os-controller.service.in", systemd / "frieren-os-controller.service"),
        (
            PROJECT / "packaging/io.github.BumBoo.FrierenOSController.desktop.in",
            desktop / "io.github.BumBoo.FrierenOSController.desktop",
        ),
    ):
        contents = (
            source.read_text(encoding="utf-8").replace("@EXEC@", str(EXEC)).replace("@PROJECT@", str(PROJECT))
        )
        destination.write_text(contents, encoding="utf-8")
        print(destination)
    subprocess.run(["/usr/bin/systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(
        ["/usr/bin/systemctl", "--user", "enable", "--now", "frieren-os-controller.service"], check=True
    )
    print("프리렌 OS 컨트롤러를 앱 메뉴와 사용자 서비스에 설치했어요.")


if __name__ == "__main__":
    install()
