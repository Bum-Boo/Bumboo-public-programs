# Claude·Codex 구독 오케스트레이션

2026-10-10 적용. 실행기: `agent-orchestrate`. 설정은 `~/.config/agent-orchestrate/config.json`, 대기열과 결과는 `~/.local/state/agent-orchestrate/`에 있어요.

## 기본 흐름

`pipeline`은 제출 시 입력 사본을 만들고 **Codex 작성 → configured personal host 검사 → Claude 독립 검수** 순서로 실행해요. Claude가 `approve`를 반환하고 검사가 통과해야 `ready`가 돼요. `ready`는 결과를 검토할 수 있다는 뜻이에요. 작업별 `work/`를 원본에 자동 반영하지 않아요. 반영하는 에이전트는 현재 원본 변경과 다른 소유자의 작업을 확인하고, 해당 프로젝트의 절차에 따라 필요한 부분을 적용해요.

`research`는 Codex와 Claude가 같은 입력을 서로 다른 관점에서 읽고 각자의 결과를 남겨요. 모델 호출은 최대 2개, 작업은 최대 2개가 동시에 실행돼요. `compute`는 모델을 호출하지 않고 configured personal host에 최대 2개의 독립 argv 검사를 제출해요. configured personal host의 기존 전체 호스트 큐가 2개 작업·합계 8스레드 제한을 관리해요.

Codex가 현재 세션에서 이미 작성한 코드는 `kind: review`로 제출하면 Claude만 독립 검수해요. `checks`를 넣으면 검수 전에 configured personal host 검사를 실행해요. `prompt`에 원래 요구사항과 검토할 파일·근거를 명시해요. 기존 코드 작성자를 다시 호출하지 않아요.

Linux의 기존 ChatGPT·Claude 구독 로그인만 사용해요. API 키 환경변수를 제거하고 로그인 방식을 확인해요. Claude `--bare`와 유료 API 폴백은 사용하지 않아요. configured personal host WSL의 모델 CLI 로그인이 없어도 연산 작업은 실행돼요. 모델 추론은 Linux에서 실행하므로 Linux가 켜져 있고 사용자 서비스가 실행될 수 있어야 해요.

## 제출과 결과 확인

명세의 `source`는 좁은 프로젝트 폴더로 바꿔요. 검증 명령은 shell 문자열 대신 argv 배열로 적어요. 명령·입력 범위는 제출하는 에이전트가 검토해요. 실행기는 범용 명령 샌드박스가 아니에요.

```sh
agent-orchestrate submit /absolute/task.json
agent-orchestrate status
agent-orchestrate show JOB_ID
cat ~/.local/state/agent-orchestrate/latest.md
```

명세 예시:

```json
{
  "title": "명확한 과업 이름",
  "kind": "pipeline",
  "source": "/absolute/narrow/project",
  "schedule": "night",
  "prompt": "수정할 파일·행동·수용 기준을 구체적으로 적어요.",
  "checks": [["python3", "-m", "unittest", "-v"]]
}
```

`schedule: now`는 1분 간격 작업기가 집어 가요. `night`는 매일 **23:30 Asia/Seoul**에 실행 대상으로 풀려요. 야간 해제는 영속 기록되어 기존 작업이 실행 중이어도 사라지지 않아요. 기본 하루 최대 **4개 작업**(작업당 모델 최대 2회), 모델별 **15분**, 원격 검사 대기 **20분**이에요. 실패한 작업을 자동 반복하거나 더 비싼 공급자로 바꾸지 않아요. 대기 중인 작업은 `agent-orchestrate cancel JOB_ID`로 취소할 수 있어요.

확인할 상태: `queued` 대기, `running` 실행, `ready` 결과 검토 가능, `needs_changes` Claude 수정 요청, `blocked` 오류·복구 확인 필요, `cancelled` 대기 취소. `source_changed_since_submit: true`면 원본이 제출 이후 변경됐어요. 반영 전에 현재 변경과 충돌을 확인해요.

## 변경 자동화

5분 간격 감시가 등록된 작업환경 문서와 GitHub 저장소의 PR 변경을 확인해요. 처음 실행은 기준점만 저장해요. 같은 문서 해시·PR base/head 조합으로 중복 제출하지 않아요. 문서 변경은 관련 운영 안내의 수정 제안을 야간 대기열로 보내요. PR 변경은 정확한 base/head의 diff를 받아 두 관점의 읽기 전용 검토를 제출해요. PR 전체 맥락을 보장하지 않으며 병합·GitHub 댓글·푸시를 수행하지 않아요. 결과는 로컬에 남아요.

기본 문서 범위는 이 프로젝트의 README·이 안내·예제 JSON이며, PR 범위는 `example-owner/example-repo`예요. 다른 프로젝트는 소유권과 현재 지침을 확인한 뒤 설정의 `watches`에 추가해요. 학습 기록을 저장하는 사용자 지침은 이 코드/운영 문서 감시와 별도예요. 볼트·대화 감시를 설치하지 않아요.

## 중단·복구

```sh
systemctl --user stop agent-orchestrate-worker.timer agent-orchestrate-night.timer agent-orchestrate-watch.timer
systemctl --user status agent-orchestrate-worker.service
agent-orchestrate show JOB_ID
agent-remote info himmel REMOTE_JOB_ID
agent-remote logs himmel REMOTE_JOB_ID
```

작업기는 단일 실행 잠금을 사용해요. 이전 실행이 중단되면 그 작업을 `blocked`로 바꾸고 원격 제출 로그의 job ID를 복구해요. 살아 있는 이전 작업 프로세스 그룹이 있으면 새 작업을 시작하지 않아요. 원격 제출의 응답이 끊겼다면 기록된 이름/ID와 `agent-remote jobs himmel`을 대조해요. 동일 작업을 바로 재제출하지 않아요. 원격 성공은 `completed`, `exit_code: 0`, 자원 해제까지 확인하고 새로운 로컬 디렉터리에 결과를 가져와요.

결과·로그는 사용자 전용 상태 폴더에 보관돼요. 인증파일·공통 캐시·Git 메타데이터·심볼릭 링크는 기존 agent-remote 제외 규칙을 따라 입력에서 제외해요. 비표준 이름의 비밀파일은 제출 전에 직접 제외하거나 입력 폴더를 좁혀야 해요. 원격 Mac은 이 실행기에 사용하지 않아요.

사용자 서비스: `agent-orchestrate-worker.timer`(1분), `agent-orchestrate-watch.timer`(5분), `agent-orchestrate-night.timer`(23:30). 전부 끄려면 위 stop 명령 뒤 같은 이름으로 `disable`을 실행해요. 서비스와 타이머의 원본은 `systemd/`에 있어요.

## 공식 자료

- [Codex 비대화형 실행](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Claude 비대화형 실행](https://code.claude.com/docs/en/headless)
- [Codex 하위 에이전트](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Claude Routines](https://code.claude.com/docs/en/routines): 이번 구현은 로컬 CLI와 systemd 예약을 사용해요.
