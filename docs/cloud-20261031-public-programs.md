# 공개 프로그램 10종 Linux 검증 보고서 (cloud, 2026-10-31)

브랜치 `claude/public-programs-docs-verify-q8dekf` (기준: `main` d7561b8). 각 도구의 README를 깨끗한 clone에서 Linux(Ubuntu 24.04 VM, Python 3.11/3.12/3.13, Node 22.23.4, npm 10.9.9)로 그대로 따라 하고, 스모크 테스트와 CI 워크플로를 추가하고, 재현된 결함만 고쳤습니다. 도구별로 병렬 하위 에이전트가 1차 작업을 했고, 변경은 모두 직접 diff 검토 후 도구별 커밋으로 나눴습니다. 의존성 버전·lockfile·라이선스·릴리스 메타데이터는 바꾸지 않았고, 모든 테스트 데이터는 합성입니다(외부 서비스·모델 다운로드 호출 없음).

분류: **검증된 결함**(재현 → 수정 → 회귀 테스트), **정적 위험**(재현 못 함/수정 보류), **이미 커버됨**, **문제 아님**.

## 요약

| 도구 | 이전 (문서 명령) | 이후 | 검증된 결함 |
| --- | --- | --- | --- |
| hermes-pet | unittest 13 OK | 23 OK (3.11–3.13) | 4 |
| procedural-soundscape | `npm run check` 테스트 3/3 | 13/13, build OK | 1 |
| typecast-shorts-toolkit | `npm test` 13/13 | 35 (34 pass, 1 skip), build OK | 5 |
| emergent-life-lab | `npm run check` 2/2, **`npm run dev` 빈 화면** | 17/17, dev/preview 200 | 3 |
| quiet-desktop | unittest 24 OK | 49 OK (skip 1; xvfb에서 skip 0) | 1 + 공유 2 |
| quiet-controller-plugin | unittest 35 OK | 57 OK (3.11–3.14) | 2 |
| aid-vfx-toolkit | 테스트 없음, headless에서 landmark 실패 | 11 OK | 1 + 설정 1 |
| grimoire-companion | pytest 11 passed, **offscreen 캡처 실패(libEGL)** | 24 passed, 1 skip | 4 |
| frieren-os-controller | unittest 82 중 **1 fail + 6 error** | 96 OK (xvfb, skip 1) | 4 |
| agent-workflow | (아래 절 참고) | | |

CI: `.github/workflows/public-programs-smoke.yml` — 도구별 job, Linux만. 파일 상단에 커버하지 않는 범위를 명시했습니다. 루트 README의 "CI는 `ci/` 참고 템플릿뿐" 문장은 이 워크플로 추가로 더 이상 정확하지 않으므로 함께 고쳤습니다.

## 도구별 결과

### hermes-pet
- 이전: `python3 -m unittest discover -s tests -v` 13 OK(3.13에서 ResourceWarning: unclosed database). `--once`/`--serve` 동작. 폴더 밖에서 `python3 -m tools.hermes_pet.pet` 실행 시 `ModuleNotFoundError` — README에 실행 위치 없음.
- 검증된 결함
  - `--source NAME`이 기본 `telegram`을 대체하지 않고 덧붙음 → `hermes-pet/tools/hermes_pet/pet.py:326`, `:343`. 테스트 `test_source_flag_replaces_default_telegram`.
  - DB 경로를 SQLite `file:` URI에 이스케이프 없이 넣어 `#`, `?`, `%`가 든 경로에서 조용히 idle 표시 → `state_source.py:55`. 테스트 `test_db_path_with_uri_special_characters`.
  - 연결을 닫지 않음(`with`는 commit만 함) → `state_source.py:57` `contextlib.closing`. 테스트 `test_state_source_closes_connection`.
  - (보안) `pet.json`의 `spritesheetPath`가 절대경로/`..`로 asset 폴더 밖 파일을 `/assets/spritesheet.webp`로 서빙 가능 → `pet.py:53-58`. 테스트 `test_asset_spritesheet_path_cannot_escape_asset_dir`. 부작용: 밖을 가리키는 심볼릭 링크 스프라이트도 거부.
- 정적 위험: Host 헤더 미검사(DNS rebinding으로 `/api/state` 읽기 가능성, 기본 loopback), `--host 0.0.0.0` 노출, `--once` 출력에 DB 문자열의 터미널 제어문자 그대로, NULL timestamp 시 예외(실제 스키마 미확인), 상태 키워드 부분 문자열 매칭.
- 이미 커버됨: 읽기 전용 열기(체크섬 불변), DB 없음 → idle·파일 미생성, XSS(`textContent`만 사용), 모델 호출 없음.
- 스모크: `tests/test_smoke.py` — 실제 `python -m ... --once` 서브프로세스, 포트 0 `serve()`에 HTTP 요청.
- 이후: 23 OK(3.11/3.12/3.13, `-X dev -W error::ResourceWarning`). 수정 전 코드 + 새 테스트 → 7개 subtest 실패.

### procedural-soundscape
- 이전: `npm ci` OK(취약점 0), `npm run check` OK(테스트 3/3), dev/preview HTTP 200. headless Chromium(swiftshader)에서 WebGL2 ready, 콘솔 오류 없음.
- 검증된 결함: Resume 시 시작 시각을 초기화해 움직임이 0초로 되돌아감(브라우저에서 3.68 s → 0.23 s 재현) → `src/playback-clock.ts` 신설, `src/main.ts:55`, `:71-72`. 테스트 `tests/playback-clock.test.ts` "regression: resume continues…"(수정 후 3.92 s → 4.49 s).
- 정적 위험: 프리셋 전환 중 WebGL 초기화 실패 시 상태 문구가 "WebGL2 ready"로 남음.
- 문제 아님: 숫자가 아닌 tempo 입력(range input이라 UI에서 불가).
- 스모크: `tests/smoke.test.ts` — index.html 컨트롤, 전 프리셋, tempo/strength 클램프, 장면별 전체 루프.
- 이후: `npm run check` 13/13, build OK.

### typecast-shorts-toolkit
- 이전: `npm ci` OK, `npm test` 13/13, `npm run build` OK. Premiere `src/*.ts`는 어떤 빌드에도 포함되지 않음(패널은 `main.js`를 로드).
- 검증된 결함
  - 문서에 있는 `start_ms`/`end_ms`/`duration_ms` 키를 읽지 않아 cue 0개 → `packages/typecast-sync-core/src/parseTypecastJson.ts:6-8`, `:183`, AE `aeCaptionGenerator.jsx:299-303`, Premiere `main.js:385-389`.
  - `formatSrt`가 쓰는 100시간 이상 타임스탬프를 파서가 못 읽어 cue 손실 → `timecode.ts:2`, `parseSrt.ts:6`, `parseVtt.ts:6`, AE/Premiere 패턴 동일 수정.
  - `splitLongCue(maxLines=1)`가 첫 줄 이후 텍스트를 버림 → `normalize.ts:28`.
  - AE 파서가 typecast.json cue를 시작 시각으로 정렬하지 않음(코어·Premiere와 불일치) → `aeCaptionGenerator.jsx:259-261`.
  - 패널 파서가 UTF-8 BOM이 있는 JSON에서 예외 → `aeCaptionGenerator.jsx:322`, `main.js:340`. (실제 ExtendScript/UXP 파일 읽기가 BOM을 제거하는지는 미확인)
  - 테스트: `tests/regressions.test.mjs`(패널 파서 사본을 Node에서 가짜 `File`/UXP 객체로 실행). 수정 전 8개 실패.
- 문서화만: 패널은 단어 단위 typecast.json을 무시하고 SRT/VTT로 대체, VTT 인라인 태그는 그대로 남음(`docs/limitations.md`).
- 정적 위험: `aeSmokeTest.jsx`는 저장소에 없는 `samples/smoke_runtime_srt/`가 필요하고 AE를 종료함. 사용되지 않는 Premiere `.ts`가 `main.js`와 어긋날 수 있음.
- 문제 아님: 10000 초과 값을 ms로 보는 규칙(의도, 문서화).
- 스모크: `tests/smoke.test.mjs`(샘플 폴더 탐색→검증→파싱→SRT 내보내기→재파싱 바이트 일치 등), `tests/panels.smoke.test.mjs`(AE/Premiere 로직, Adobe 호스트는 명시적 skip).
- 이후: `npm test` 35(34 pass, 1 skip), build OK.

### emergent-life-lab
- 이전: `npm run check` 통과(2/2), preview 정상. **`npm run dev`는 `/src/main.tsx`가 HTTP 500**(`Failed to resolve import "@/src/app/App"`)이라 빈 화면.
- 검증된 결함
  - `@/` 별칭이 tsconfig에만 있어 dev 서버가 해석 못 함 → `vite.config.ts:7`. 테스트 `tests/devserver.test.ts`.
  - 조작된 공유 해시(`generation` null/누락)로 metrics 패널이 `toLocaleString` of null로 앱 전체 크래시, `rule: "constructor"`가 `in` 검사를 통과해 `Object`가 규칙으로 로드됨 → `src/utils/encoding.ts:31-43`, `src/app/App.tsx:152`. 회귀 테스트 3개(`tests/smoke.test.ts`).
  - "HighLife replicator" 프리셋이 3세대 만에 소멸 → `src/ca/presets.ts:99-114`(표준 복제자 패턴). 테스트 "regression: HighLife replicator preset actually replicates".
- 정적 위험: 공유 상태 디코더가 잘못된 RLE 조각을 위치 이동 없이 건너뜀(이후 셀이 밀릴 수 있음).
- 문제 아님: 다른 프리셋 동작, 포커스 중 단축키 무시(의도).
- 이후: 17/17, dev·preview 모두 200, headless Chromium 콘솔 오류 없음(수동 확인).

### quiet-desktop
- 이전: unittest 24 OK, compileall OK, `desktop-file-validate`는 명령 없음 → `desktop-file-utils` 설치 후 OK, ruff OK. `python -m freiren_quiet gui`는 PyGObject 없는 인터프리터에서 ImportError traceback, 시스템 Python 3.12 + apt GTK3 + xvfb에서는 서비스 없음 오류를 창에 정상 표시.
- 검증된 결함
  - 85°C 보호가 우회됨: `set_mode()`가 `emergency`를 지워 86°C → `mode performance` → 80°C에서 100%·터보 허용, 보호 중 센서 실패는 25%가 아닌 40% → `freiren_quiet/policy.py:34`, `:60`. 테스트 `test_regression_*`(`tests/test_smoke.py`). 플러그인 쪽 사본은 이미 같은 형태로 고쳐져 있었음.
  - (플러그인과 공유) 아래 quiet-controller-plugin의 두 결함을 이식 → `freiren_quiet/hardware.py:35-39`, `freiren_quiet/client.py:14-24`. 테스트 `tests/test_regressions.py`(수정 전 3 error).
- 정적 위험: 보호 상태가 저장되지 않아 서비스 재시작 시 해제(두 사본 공통), `restore` 후에도 보호 유지(안전 방향).
- 경미/문제 아님: `status --json`은 오류여도 exit 0, `monitor`는 첫 요청까지 5초 대기.
- 이후: 49 OK(skip 1, 3.11/3.13), `xvfb-run -a /usr/bin/python3.12 -m unittest …`는 skip 0, compileall·desktop-file-validate·ruff OK.

### quiet-controller-plugin
- 이전: unittest 35 OK, ruff/format/compileall OK. README 검증 절에 ruff 설치 단계가 없음(Arch는 PEP 668로 시스템 pip 차단) → venv + `pip install -r requirements-dev.txt` 추가.
- 검증된 결함
  - DMI/cpufreq가 없는 기기(VM, 컨테이너)에서 문서화된 거절 대신 `FileNotFoundError` traceback → `freiren_quiet/hardware.py:38-42`. 테스트 `test_missing_dmi_or_cpufreq_is_a_clear_refusal`.
  - 권한 없는 사용자가 "권한 없음" 대신 `[Errno 32] Broken pipe`를 봄(서비스가 요청 읽기 전에 응답 후 종료), 빈 응답은 `JSONDecodeError` → `freiren_quiet/client.py:14-24`. 테스트 `ClientRejectedPeerTests` 2개.
- 정적 위험: 저장된 RAPL 기준값이 프리셋보다 낮고 0.25 W 배수가 아니면(예: 15.125 W) `bounded_preset()` 결과가 검증에 걸려 서비스 시작 실패(합성 값으로만 재현, 반올림 정책이 바뀌므로 수정 보류).
- 이후: 57 OK(3.11/3.12/3.13/3.14.6, 100회 반복 0 실패, 비 root 실행 OK), ruff OK.

### aid-vfx-toolkit
- 이전: Python 3.11 venv에서 `pip install -r requirements.txt` 성공(약 1분 40초, torch 없음). README ffmpeg 합성 클립, `dither`, `track --mode blobs`, 합성 16-bit depth로 `pointcloud` 동작. `depth`/기본 `track`은 모델 다운로드라 실행 안 함. 테스트 없음.
- 검증된 설정 결함: headless Linux에서 mediapipe가 `libGLESv2.so.2` 없음으로 실패(`track/track.py:126`) → README에 `ffmpeg libgles2 libegl1` 명시.
- 검증된 결함: 홀수 해상도(161x91) 입력에서 libx264 거부 → `BrokenPipeError` → `pointcloud/render.py:31`에 짝수 pad 필터. 테스트 `test_pointcloud_odd_frame_size`.
- 정적 위험: fps 0이면 `track.py:109` 0 나누기, 8-bit depth PNG를 거의 전부 먼 거리로 처리, `--stride 0` traceback, 모델 다운로드 체크섬 없음(`models/MODELS.md`에 기재).
- 문제 아님: dither의 홀수→짝수 크기 변환, JSX JSON 파서와 tracker 출력 형식 일치.
- 스모크: `tests/test_smoke.py` 11개 — 다운로드 함수는 예외로 막고 depth/landmark는 가짜 모델로 실제 `main()` 실행, JSX는 `node --check`로 구문만 확인.
- 이후: 11 OK(약 5초). 의존성 없는 Python에서는 8개가 사유와 함께 skip.

### grimoire-companion
- 이전: `pip install .`, `grimoire --help`, event 예제, `doctor` OK, pytest 11 passed, ruff OK, build OK, `tools/install.py`(임시 HOME) OK. **`QT_QPA_PLATFORM=offscreen grimoire --demo --capture`는 `libEGL.so.1` 없음으로 실패** → README에 headless apt 목록 추가. 긴 `XDG_STATE_HOME`에서 소켓 경로 108바이트 초과로 시작 실패(문서화).
- 검증된 결함(`src/grimoire/sources.py`, 테스트 `tests/test_regressions.py`)
  - 깊게 중첩된 JSON이 `RecursionError`로 수집 스레드를 죽임 → `:23-26`.
  - 깨진 `*.json` 심볼릭 링크 하나가 mtime 정렬을 깨 소스 전체가 사라짐 → `:107-111`, `:127`.
  - 레코드 이름의 FIFO가 `collect()`를 영원히 막음 → `:17`.
  - event handoff 경로의 연속 공백이 합쳐져 존재하지 않는 파일을 가리킴 → `:101`.
- 정적 위험: `MANIFEST.in`이 없는 `AGENTS.md`를 나열, `requirements-tested.txt`(PySide 6.11.2)와 실제 설치(6.12.0) 차이(둘 다 통과).
- 이후: pytest 24 passed, 1 skipped(네이티브 트레이/CAVA 명시적 skip), ruff OK, 3.11(`-c requirements-tested.txt`)·3.12에서도 동일.

### frieren-os-controller
- 이전: Python 3.13 venv `pip install -e .` OK, `--help` OK, 데몬 없을 때 `dashboard`/`list`/`quiet status`는 exit 1 깔끔한 메시지. unittest 82개 중 **1 fail + 6 error**(`gi` 없음 5, GdkPixbuf 1, `systemd-analyze` "Failed to initialize manager" 1). ruff는 venv에도 pyproject에도 없음.
- README 결함: GTK 4라고 적혀 있으나 코드는 `Gtk 3.0`·`GdkPixbuf 2.0` 사용, apt `gi`는 시스템 Python 전용이라 `--system-site-packages` venv 필요, 데몬 실행 단계·ruff 설치·실제 상태 경로 누락 → 모두 수정.
- 검증된 결함(테스트 `tests/test_smoke.py`)
  - MCP 도구 오류가 "Error executing tool"로만 전달됨(mcp 2.x는 `ToolError`만 메시지 유지) → `frieren_controller/mcp_server.py:13-18`.
  - 세션 D-Bus가 없으면 `daemon`이 `GLib.GError` traceback으로 종료 → `monitor.py:76-86`, `desktop_common.py:61-71`.
  - `XDG_RUNTIME_DIR`가 없으면 `FileNotFoundError` traceback → `server.py:150-151`.
  - GTK 바인딩 없이 `gui` 실행 시 traceback → `cli.py:90-96`.
  - 테스트 환경 수정: 실제 systemd 검증 테스트는 user manager에 실제로 연결될 때만 실행(`tests/test_jobs.py:17`).
- 정적 위험: `XDG_STATE_HOME` 무시(`core.py:78`, `gui.py:154`) — 기존 데이터 이동 문제로 문서화만.
- 문제 아님: "Freiren" 철자는 플러그인 소켓 경로와 일치.
- 이후: `/usr/bin/python3.12 -m venv --system-site-packages`에서 96 OK(skip 2), `xvfb-run -a`에서 96 OK(skip 1), ruff check/format OK.

### agent-workflow
(작성 중)

## 이 VM에서 검증하지 못한 것
- Windows·macOS 전부, Wayland, 실제 KDE Plasma 세션·KWin·PolicyKit·systemd user/system manager·cronie.
- Adobe After Effects / Premiere 실행(ExtendScript·UXP 런타임, 레이어/캡션 생성, 권한).
- MSI GL62 6QE 실기, power-profiles-daemon D-Bus, RAPL 실기 쓰기, 설치/제거/`verify_live`/`verify_gui` 스크립트.
- 실제 depth/MediaPipe 모델 추론, GPU 가속.
- GUI 상호작용(GTK 창은 시작만, Qt 트레이·창 배치·CAVA 오디오, 브라우저 canvas/WebGL은 headless 수동 확인만).
- 실제 Codex/Claude CLI, 원격 호스트, Hermes 실제 DB 스키마.
- GitHub Actions에서 워크플로를 실제로 돌려 보지는 않았습니다(명령은 이 VM에서 같은 순서로 실행해 확인). Python 3.14는 quiet-controller-plugin에서만 확인.

## 소유자를 위한 다음 단계
1. 브랜치를 검토하고 첫 CI 실행 결과를 확인하세요(특히 apt 패키지가 필요한 grimoire/aid/frieren/quiet-desktop-gtk job).
2. 실기에서: quiet-desktop 85°C 보호 수정과 클라이언트 오류 메시지를 MSI GL62에서 `verify_live.py --confirm-live`로 확인.
3. Adobe 호스트에서 typecast 패널(*_ms, BOM, 정렬)과 aid-vfx JSX를 빈 프로젝트로 한 번씩 실행.
4. 정적 위험 중 우선순위: hermes-pet Host 헤더 검사, quiet 보호 상태 영속화, 플러그인 RAPL 0.125 W 기준값 반올림, frieren `XDG_STATE_HOME` 지원.
5. typecast의 사용되지 않는 Premiere `.ts`와 `main.js` 중복을 하나로 정리하거나 빌드에 포함.
