# Frieren OS Controller Quiet plugin

프리렌 OS 컨트롤러의 전원·온도 기능을 제공하는 백엔드 플러그인이에요. 독립 실행 화면과 앱 메뉴 항목은 제공하지 않아요. 화면과 MCP, API는 컨트롤러에서 사용해요.

지원 기기는 **MSI GL62 6QE / Intel i5-6300HQ / Arch Linux / KDE**예요. 다른 기기에서는 설치를 거절해요. CPU 상한과 터보, 절전 성향, CPU 패키지 전력 한도를 관리하며 팬이나 EC 레지스터는 직접 제어하지 않아요.

## 설치와 업데이트

소스를 검토한 뒤 실행하세요. 기존 Quiet 설치를 업데이트해도 복원 지점과 마지막 설정을 유지해요.

```bash
git clone https://github.com/Bum-Boo/Bumboo-public-programs.git
cd Bumboo-public-programs/quiet-controller-plugin
sudo /usr/bin/python -I scripts/install.py --user "$(id -un)"
```

Arch의 `power-profiles-daemon`, `python-psutil`, `python-gobject`를 사용해요. 설치기는 root 소유 코드를 `/usr/lib/freiren-quiet`에 설치해요. 정상 시작을 확인한 뒤 이전 Quiet 실행 아이콘과 GUI 소스를 제거해요.

## 컨트롤러 연결

기존 설치와 호환되도록 서비스 이름 `freiren-quiet.service`, 소켓 `/run/freiren-quiet/control.sock`, CLI `freiren-quiet`를 유지해요. 컨트롤러의 **전원과 온도** 화면이 이 소켓을 사용해요. 별도 네트워크 서버는 없어요.

소켓 요청은 `status`, `mode`, `target`, `configure`, `reset`만 허용하며 설치 때 지정한 UID를 검사해요. 모드는 `auto`, `quiet`, `balanced`, `performance`, `custom`, `restore`, 목표 온도는 정수 58~75°C예요. 모든 관리 모드에 85°C 냉각 보호를 적용해요. KDE에서 전원 프로필을 바꾸면 CPU 관리를 해제하고 그 선택을 존중해요.

```bash
freiren-quiet status --json
freiren-quiet mode balanced
freiren-quiet target 64
freiren-quiet custom --cap 70 --preference balance_power --power 24 --boost 32
freiren-quiet reset
```

화면 효과 조절과 작업별 CPU 제한은 일반 사용자 CLI로도 사용할 수 있어요.

```bash
freiren-quiet effects save
freiren-quiet effects restore
freiren-quiet run --cpu 100 -- make -j2
```

## 프리셋과 사용자 지정

| 프리셋 | CPU 상한 | 터보 | 지속 / 순간 전력 한도 |
|---|---:|---|---:|
| 조용함 | 60% | 끔 | 18 / 25W |
| 균형 | 75% | 끔 | 28 / 38W |
| 성능 | 100% | 켬 | 45 / 56.25W |

보수적인 시작값이며 성능·소음 벤치마크로 확정한 최적값은 아니에요. 전력 한도는 실제 소비 전력과 달라요. 처음 저장한 한도가 더 낮으면 그 값을 넘지 않아요. 자동 모드는 기존 온도 조절과 균형 전력 한도를 함께 사용해요.

사용자 지정은 CPU 상한 25~100%, 터보, 절전 성향 네 단계, 지속 10~45W / 순간 10~56.25W를 조절해요. 전력 한도는 0.25W 단위이고 순간 한도는 지속 한도 이상이어야 해요. 전력 한도를 지정하지 않으면 저장된 원래 한도로 돌아가요. RAPL이 없으면 CPU 설정만 사용할 수 있어요.

`reset`은 처음 저장한 CPU·전력 설정을 복원하고 관리를 해제해요. 사용자 지정 입력값과 목표 온도도 초기화해요. 화면 테마·화면 효과는 유지해요. `restore`는 기존 명령과의 호환을 위해 저장된 사용자 지정 값을 지우지 않아요.

기존 `baseline.json`은 덮어쓰지 않아요. 전력 복원값은 `power-baseline.json`에 별도로 한 번 저장해요. 구버전에서 업그레이드하면 기존 CPU 정책을 유지하고, 새 프리셋이나 사용자 지정을 적용할 때 전력 한도 관리를 시작해요. 설치 실패 시 `/var/lib/freiren-quiet/upgrade-*`의 관리자 전용 사본으로 코드와 설정을 복원해요.

## 제거

```bash
freiren-quiet effects restore
sudo /usr/bin/python -I scripts/uninstall.py
```

CPU·전력 한도를 복원하며 전원 관리 패키지와 `/var/lib/freiren-quiet`의 복원 지점은 남겨요.

## 검증

```bash
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
```

테스트는 가짜 하드웨어와 전력 프로필을 사용해요. 실제 기기의 설치·업데이트에는 관리자 인증이 필요해요. 실기 검증 결과는 릴리스 노트에 따로 기록해요.

GitHub Actions 설정 예제는 `ci/github-checks.yml`에 있어요. 자동 실행은 등록하지 않았어요. 릴리스 검증은 위 명령으로 로컬에서 수행했어요.

원래 Freiren Quiet의 MIT 코드를 분리한 배포판이에요. 개인 배경 이미지와 런타임 데이터는 포함하지 않아요. [권한 구조](ARCHITECTURE.md), [의존성](THIRD_PARTY.md)을 참고하세요.

## Public source edition

This fresh public history contains user-owned program code and dependency notices, without private runtime state or machine data. The supported hardware remains MSI GL62 6QE; installation changes CPU/power settings and requires the original documented hardware checks. Tests use mocks; this packaging pass did not run installation or hardware control. The upstream private development repository remains separate.
