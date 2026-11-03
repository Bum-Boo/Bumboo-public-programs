# Freiren Quiet

MSI **GL62 6QE / Intel i5-6300HQ / Intel HD 530 + GTX 950M / Arch Linux / KDE**에 맞춘 한국어 전력·소음 관리 앱입니다. `power-profiles-daemon`, GTK 3, psutil, systemd를 활용합니다.

CPU가 내는 열을 줄여 노트북의 자동 팬 제어가 조용해질 여지를 만듭니다. 팬 RPM이나 EC 레지스터를 직접 쓰지 않습니다. 목표 온도와 소음 감소는 작업 부하·실내 온도·냉각 상태에 따라 달라지며 보장값이 아닙니다.

## 사용

앱 메뉴에서 **Freiren Quiet · 소음 관리**를 실행하거나:

```bash
freiren-quiet
freiren-quiet mode auto
freiren-quiet mode quiet
freiren-quiet target 64
freiren-quiet status --json
freiren-quiet restore
```

| 모드 | CPU 상한 | 터보 | PPD 전력 프로필 |
|---|---:|---|---|
| 자동 (기본값) | 60%로 시작, 40~75% 자동 조절 | 꺼짐 | power-saver |
| 조용함 | 60% | 꺼짐 | power-saver |
| 균형 | 75% | 꺼짐 | balanced |
| 성능 | 100% | 허용 | performance, 미지원 시 balanced |
| 관리 해제 | 설치 전 값 복원 | 설치 전 값 복원 | 설치 전 프로필, 없었다면 balanced |

상한은 **최고 터보 P-state에 대한 비율**입니다. CPU 사용률이나 처리 속도와 일대일로 대응하지 않습니다. i5-6300HQ에서 60%는 대략 1.9GHz 상한에 해당하며 실제 동작 클럭은 더 낮을 수 있습니다.

화면에는 CPU 온도, 전체 CPU 사용률, 상한, 프로세스 상위 6개, NVIDIA 절전 상태를 표시합니다. 프로세스 사용률은 4코어 합계를 100%로 환산합니다. 실행 이후 평균 대신 psutil의 구간 측정을 사용합니다.

앱을 닫아도 서비스는 작동합니다. 서비스는 부팅 시 시작하며 마지막 모드·목표 온도를 보존합니다. 관리 해제 후에는 재시작해도 해제 상태를 유지합니다. UI는 자동으로 뜨지 않습니다.

## 자동 조절 규칙

- 5초 간격, 기본 목표 64°C. 목표는 58~75°C로 변경 가능.
- 목표+3°C 이상이 두 번 연속이면 상한을 5%p 낮춥니다.
- 목표−4°C 이하가 여섯 번 연속이면 상한을 5%p 높입니다.
- 자동 모드에서 78°C 이상이면 즉시 40%로 제한합니다.
- 관리 중인 모든 모드에서 85°C 이상이면 25%·터보 꺼짐으로 제한합니다. 75°C 이하에서 여섯 번 연속 측정돼야 완화합니다.
- CPU 센서를 읽지 못하면 40%·터보 꺼짐을 적용하고 경고를 표시합니다. 85°C 보호 중이면 25%를 유지합니다.
- 85°C 보호는 모드를 바꿔도 해제되지 않습니다.
- 커널과 펌웨어의 열 보호 기능은 계속 동작합니다.

KDE 설정이나 `powerprofilesctl`로 전력 프로필이 변경되면, 이 앱은 CPU 제한을 복원하고 관리 해제합니다. 다른 설정 도구와 같은 값을 반복해서 덮어쓰지 않습니다. 단, 같은 전력 프로필을 다시 선택하는 행위는 값이 바뀌지 않아 감지되지 않습니다.

## 선택 기능

현재 KDE 세션에서 흐림·대비·투명 효과만 줄이고, 이전에 켜져 있던 효과만 복원합니다. 자동으로 적용하지 않습니다.

```bash
freiren-quiet effects save
freiren-quiet effects restore
```

백그라운드 작업은 systemd 사용자 scope의 CPUQuota로 실행할 수 있습니다. 기존 프로세스를 임의로 중단하거나 제한하지 않습니다.

```bash
# 100% = 한 코어 분량, 이 컴퓨터 전체는 400%
freiren-quiet run --cpu 100 -- make -j2

# 상태와 앱 부하를 60초간 JSON Lines로 출력 (자동 전송 없음)
freiren-quiet monitor --seconds 60
```

화면 효과 설정은 재로그인 시 KWin이 원래 설정을 읽습니다. 효과 절약 버튼을 다시 사용하려면 저장된 세션 목록을 `effects restore`로 정리한 후 켜면 됩니다.

## 설치 / 업데이트

현재 사용자가 소스를 검토한 뒤 실행합니다. 다른 컴퓨터 모델에서는 설치와 서비스 시작을 거부합니다.

```bash
git clone https://github.com/Bum-Boo/Bumboo-public-programs.git
cd Bumboo-public-programs/quiet-desktop
sudo /usr/bin/python -I scripts/install.py --user "$(id -un)"
```

Arch 패키지 `power-profiles-daemon`, `python-psutil`, `python-gobject`, `gtk3`를 사용합니다. 부분 업데이트를 피하기 위해 설치기는 패키지 DB를 따로 갱신하지 않습니다. 패키지 다운로드가 실패하면 시스템의 일반 업데이트 절차를 먼저 확인하세요.

설치 파일은 root 소유의 `/usr/lib/freiren-quiet`, `/usr/bin/freiren-quiet`, `/etc/systemd/system/freiren-quiet.service`와 데스크톱 메뉴 항목입니다. 첫 설치 전 CPU/EPP 설정을 `/var/lib/freiren-quiet/baseline.json`에 보존하며 업데이트 때 덮어쓰지 않습니다.

```bash
git pull --ff-only
sudo /usr/bin/python -I scripts/install.py --user "$(id -un)"
```

## 복원 / 제거

```bash
freiren-quiet effects restore
freiren-quiet restore
sudo /usr/bin/python -I scripts/uninstall.py
```

서비스 정상 종료 시에도 CPU 설정을 복원합니다. 강제 종료 때는 systemd가 재시작합니다. 부팅 때부터 작동시키지 않으려면 `sudo systemctl disable --now freiren-quiet`를 사용하세요. 제거기는 앱만 지우며 전력 관리 패키지와 복원 지점은 보존합니다.

## 개발 / 검증

```bash
python -m unittest discover -s tests -v
python -m compileall -q freiren_quiet scripts
desktop-file-validate packaging/io.github.BumBoo.FreirenQuiet.desktop
python -m freiren_quiet gui
```

테스트는 가상 sysfs와 가짜 PPD, 임시 Unix 소켓을 사용하며 실제 CPU 설정을 바꾸지 않습니다. 핵심 로직 테스트에는 GTK·D-Bus·psutil·root 권한이 필요하지 않습니다. `desktop-file-validate`는 `desktop-file-utils` 패키지에 있습니다. `gui` 실행과 `tests/test_smoke.py`의 GTK 시작 테스트에는 python-gobject(PyGObject)·GTK 3·psutil과 디스플레이가 필요합니다. 없으면 그 테스트는 건너뜁니다. Ubuntu에서는 `sudo apt-get install desktop-file-utils python3-gi gir1.2-gtk-3.0 python3-psutil xvfb` 후 시스템 Python으로 `xvfb-run -a /usr/bin/python3 -m unittest discover -s tests -v`처럼 실행할 수 있습니다(서비스가 없으면 창에 연결 오류만 표시합니다). ci/의 참고 템플릿은 Python 3.11, 3.14 검증을 정의합니다. 이 저장소에서는 루트 워크플로 `.github/workflows/public-programs-smoke.yml`이 같은 검사를 실행합니다.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .

# 아래 두 검증은 실제 모드/효과를 잠깐 바꾸고 기존 모드로 복원합니다.
python scripts/verify_live.py --confirm-live
python scripts/verify_gui.py --confirm-live --screenshot artifacts/window.png
```

문제가 생기면 `journalctl -u freiren-quiet -n 40`와 `freiren-quiet status --json`을 확인하세요. 앱 자체는 네트워크 연결, 텔레메트리 전송, 외부 API 키가 필요 없습니다. 프로세스 이름과 CPU 사용률만 읽고 명령줄·브라우저 내용은 읽지 않습니다.

설계·권한 구조는 [ARCHITECTURE.md](ARCHITECTURE.md), 오픈소스 출처는 [THIRD_PARTY.md](THIRD_PARTY.md)를 참고하세요.

## Public source edition

This fresh public history contains user-owned program code and dependency notices, without private runtime state or machine data. The supported hardware remains MSI GL62 6QE; installation changes CPU/power settings and requires the original documented hardware checks. Tests use mocks; this packaging pass did not run installation or hardware control. The upstream private development repository remains separate.

CI configuration under `ci/` is a reference template for a standalone checkout. In this repository the same checks run from the root workflow `.github/workflows/public-programs-smoke.yml`.
