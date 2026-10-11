# 활용하는 오픈소스

프로젝트 자체 코드는 MIT 라이선스입니다. 아래 프로젝트의 소스를 복사하거나 번들하지 않고, 배포판 패키지와 공개 API를 사용합니다. 각 의존성은 원래 라이선스를 따릅니다.

| 프로젝트 | 사용 목적 | 업스트림 / 라이선스 |
|---|---|---|
| power-profiles-daemon | 전력 프로필과 Intel EPP 설정, KDE 전력 관리 연동 | [업스트림](https://gitlab.freedesktop.org/upower/power-profiles-daemon) · GPL-3.0 |
| GTK 3 | 가벼운 네이티브 데스크톱 UI | [문서](https://docs.gtk.org/gtk3/) · LGPL-2.1-or-later |
| PyGObject | GTK·GLib·Gio / D-Bus Python 바인딩 | [업스트림](https://gitlab.gnome.org/GNOME/pygobject) · LGPL-2.1-or-later |
| psutil | 전체 CPU 및 프로세스의 구간별 사용률 | [업스트림](https://github.com/giampaolo/psutil) · BSD-3-Clause |
| systemd | 서비스 수명주기·권한 제한·사용자 작업 CPUQuota | [문서](https://www.freedesktop.org/software/systemd/man/latest/) · LGPL-2.1-or-later 등 |
| Linux intel_pstate | CPU P-state 상한과 터보 제어 | [문서](https://cdn.kernel.org/doc/html/latest/admin-guide/pm/intel_pstate.html) · GPL-2.0 |
| KWin | 선택적으로 흐림·대비·투명 효과를 이번 세션에서 제어 | [업스트림](https://invent.kde.org/plasma/kwin) · GPL-2.0-or-later |

외부 에셋·AI 모델·Electron·웹 서버는 필요하지 않습니다. 의존성은 Arch의 서명된 패키지로 설치합니다.
