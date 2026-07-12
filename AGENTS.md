# GOAL Repository Instructions

이 파일은 저장소 전체에 적용되는 AI 협업 규칙이다. 더 가까운 하위 디렉터리에
`AGENTS.md`가 생기면 그 파일의 구체적인 지침을 함께 적용한다.

## 1. 작업 시작

- 수정 전에 `git status --short --branch`로 현재 브랜치와 사용자 변경을 확인한다.
- 기존 변경은 사용자의 작업으로 간주하고 덮어쓰거나 임의로 정리하지 않는다.
- 낯선 영역을 수정하기 전에 루트 `README.md`, 관련 기준 문서와 가장 가까운 실행·테스트 진입점을 읽는다.
- 저장소에서 확인한 현재 구현과 문서에 적힌 MVP 목표를 구분한다. 목표 상태를 구현 완료로 보고하지 않는다.
- 문서에서 확인할 수 없는 제품·API·DB 결정을 임의로 확정하지 않고 `미정 사항`으로 남긴다.

## 2. 기준 문서 라우팅

| 변경 영역                     | 먼저 읽을 문서                                                         |
| ----------------------------- | ---------------------------------------------------------------------- |
| 제품 목표·MVP 범위            | `docs/product/기획안.md`, `docs/product/기능명세서.md`                 |
| 정보 구조·사용자 흐름         | `docs/product/IA.md`, `docs/product/화면설계서.md`                     |
| 정적 화면 Prototype           | `docs/prototypes/README.md`, 관련 `docs/prototypes/*.html`             |
| HTTP·WebSocket·인증·AIJob API | `docs/api/API_명세서.md`, `docs/api/openapi.yaml`                      |
| 테이블·제약·트랜잭션          | `docs/database/DB_스키마.md`, `docs/database/ERD.md`                   |
| 프로세스·저장·배포 경계       | `docs/architecture/기술명세서.md`, `docs/architecture/시스템구성도.md` |
| KCloud 운영 환경              | `docs/architecture/KCLOUD_VM_사양.md`                                  |
| 실행·검증 명령                | `README.md`, `Makefile`, `.github/workflows/ci.yml`                    |

계약의 책임은 다음 순서로 구분한다.

1. 제품 문서는 사용자 동작과 MVP 범위를 정의한다.
2. API 명세와 OpenAPI는 외부에서 관찰되는 계약을 정의한다.
3. DB 스키마와 ERD는 내부 저장 구조와 무결성을 정의한다.
4. 기술명세서와 시스템구성도는 실행 프로세스와 통신 경계를 정의한다.
5. 화면설계서와 Prototype은 위 계약을 사용자에게 표현하는 방식을 정의한다.

문서와 구현이 다르면 한쪽을 조용히 따르지 말고 차이를 확인한 뒤 필요한 문서를 함께 수정한다.

## 3. 문서 정합성

- endpoint·payload·event·인증·권한 변경 시 `API_명세서.md`와 `openapi.yaml`을 함께 검토한다.
- table·column·FK·index·삭제·보관·transaction 변경 시 `DB_스키마.md`와 `ERD.md`를 함께 검토한다.
- 사용자 흐름·MVP 범위·역할 변경 시 기획안·기능명세서·IA·화면설계서를 함께 검토한다.
- framework·process·storage·network 변경 시 기술명세서와 시스템구성도를 함께 검토한다.
- 화면 상태나 동작 변경 시 화면설계서와 해당 Prototype 또는 실제 UI를 함께 검토한다.
- 문서 간 용어, enum, 상태 전이, 권한, 식별자와 오류 표현을 동일하게 유지한다.
- SQLAlchemy 모델이나 Alembic migration은 사용자가 요청하거나 구현 범위에 명시된 경우에만 생성한다.

계약 변경이나 정합성 검토에는 `goal-contract-sync` Skill을 사용한다.

## 4. 구현 원칙

- 사용자 역할은 계정 전체가 아니라 Course별 `PROFESSOR` 또는 `STUDENT`로 판단한다.
- 실시간 기능에서는 지연시간, 재연결과 부분 실패가 일반 CRUD보다 중요한 요구사항임을 반영한다.
- PostgreSQL과 REST 조회 결과를 최종 진실로 두고 WebSocket 이벤트를 영구 상태 자체로 취급하지 않는다.
- AI 기능 장애가 Course 입장, 질문 저장, final Transcript와 기존 기록 조회를 막지 않게 경계를 유지한다.
- 정적 Prototype은 실제 OAuth, API, WebSocket, STT나 AI 모델을 호출하지 않는다.
- secret, 참여 코드 원문, 내부 storage key, provider 원문 오류와 개인정보를 fixture·로그·문서에 노출하지 않는다.
- 변경 범위를 요청된 기능에 한정하고 무관한 리팩터링과 포맷 변경을 섞지 않는다.

## 5. Git·커밋·PR 규칙

- 커밋, push와 PR 생성은 사용자가 명시적으로 요청했거나 활성 Goal이 그 작업을 포함할 때만 수행한다.
- 실행 권한이 주어진 뒤에는 커밋마다 다시 확인을 요구하지 않고 합의된 작업 단위대로 진행한다.
- 작업 전 현재 브랜치가 open·closed·merged 상태를 포함한 기존 PR의 head인지 확인한다.
- 서로 다른 사용자 흐름은 기존 PR 브랜치에 추가하지 않고 새로운 브랜치와 새로운 Draft PR로 분리한다.
- 이전 PR의 병합을 기다리지 않는다. 선행 PR에 의존하면 새 브랜치를 만들고 PR 본문에 의존 관계와 임시 중복 diff 가능성을 명시한다.
- 독립적인 작업은 최신 기본 브랜치에서 새 브랜치를 만든다.
- 범위 밖 변경이 남은 worktree에서는 제자리에서 branch를 전환하지 않는다. 별도 worktree를 사용하거나 변경 소유자와 처리 방향을 확인한다.
- 화면 작업은 공통 자산을 별도 선행 커밋으로 두고, 화면 하나와 그 화면의 설계 문서 변경을 하나의 검토 가능한 커밋으로 묶는다.
- `git add -A`로 모든 변경을 무차별 스테이징하지 않는다. 의도한 경로만 추가하고 staged diff를 확인한다.
- 한국어 커밋 메시지를 기본으로 하되 코드 식별자와 명확한 기술 용어는 영어를 유지한다.
- PR 본문은 배경, 변경 파일, 주요 동작, 미구현 범위, 검증 결과, 리뷰 포인트와 의존 PR을 한국어로 작성한다.
- PR을 자동으로 병합하거나 auto-merge를 활성화하지 않는다. PR 생성과 검증 상태 확인 후 결과를 보고한다.
- force push, history rewrite와 파괴적 Git 명령은 명시적 승인 없이 수행하지 않는다.

화면별 커밋과 사용자 흐름별 PR 작업에는 `goal-user-flow` Skill을 사용한다.

## 6. 검증

- 가장 좁고 신호가 높은 검증부터 실행하고 위험 범위에 맞게 확대한다.
- 코드 변경은 관련 테스트·lint·format·typecheck·build를 실행한다. 전체 기준은 `make check`와 CI를 참고한다.
- DB 변경은 migration 적용과 관련 테스트를 확인한다.
- 문서 변경은 formatter, 상대 경로 링크, Mermaid 또는 YAML parser, `git diff --check`를 확인한다.
- Prototype 변경은 관련 상태 전환과 1440px·768px·375px 레이아웃, 키보드 focus, reduced motion과 핵심 접근성을 확인한다.
- 실행하지 못한 검증과 남은 위험은 최종 보고에 명시한다.
- 테스트가 실패한 상태를 성공으로 보고하지 않는다. 의도한 TDD red 단계라면 작업 종료 전에 green으로 만들거나 잔여 실패를 명시한다.

## 7. 공통 Skill 관리

- 공통 Skill의 원본은 `agent-skills/<skill-name>/SKILL.md`다.
- Codex 발견 경로는 `.agents/skills/<skill-name>/SKILL.md`다.
- Claude Code 발견 경로는 `.claude/skills/<skill-name>/SKILL.md`다.
- 공통 `SKILL.md`에는 `name`과 `description`만 YAML frontmatter로 사용하고 제품 전용 문법을 넣지 않는다.
- 원본 Skill을 수정하면 두 발견 경로의 복사본을 같은 변경에서 갱신하고 byte 단위로 동일한지 확인한다.
- 상세 제품 계약을 Skill에 복사하지 말고 관련 기준 문서를 직접 읽도록 안내한다.
- 자동 커밋, 자동 branch 전환, 자동 push와 자동 merge를 Hook으로 활성화하지 않는다.
