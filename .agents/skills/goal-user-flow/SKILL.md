---
name: goal-user-flow
description: Implement or refine GOAL screens and connected user flows with one intentional commit per screen or shared component and one new Draft PR per completed flow. Use when the user asks to build static prototypes or production UI flows, continue the planned screen sequence, or explicitly automate the associated commits, push, and PR creation. Do not add work to an existing PR branch, wait for an earlier PR to merge, or merge a PR.
---

# GOAL User Flow

화면 구현을 검토 가능한 커밋으로 나누고 사용자 흐름마다 별도 Draft PR로 전달한다.

## 1. 권한과 범위 확인

1. `AGENTS.md`를 읽는다.
2. `git status --short --branch`, remote, upstream과 현재 브랜치의 기존 PR을 확인한다.
3. 기존 사용자 변경을 작업 범위에서 분리한다.
4. 사용자 흐름, 포함 화면, 공통 자산과 완료 조건을 확정한다.
5. 커밋·push·PR 생성이 요청이나 활성 Goal에 포함되지 않았다면 구현과 검증까지만 수행한다.

## 2. 기준 문서 읽기

작업 범위에 필요한 부분만 다음 순서로 읽는다.

1. `docs/product/IA.md`의 관련 화면 노드와 진입·이탈 흐름
2. `docs/product/화면설계서.md`의 해당 화면 절
3. `docs/product/기능명세서.md`와 `docs/product/기획안.md`의 관련 기능
4. `docs/prototypes/README.md`와 기존 공통 CSS·JavaScript 패턴
5. 화면이 사용하는 REST·WebSocket은 `docs/api/API_명세서.md`와 `docs/api/openapi.yaml`
6. 저장·권한·상태 제약이 필요하면 DB·아키텍처 문서

문서에서 확인되지 않는 UI 동작이나 계약을 임의로 확정하지 않고 미정 사항으로 남긴다.

## 3. 브랜치와 PR 분리

- 현재 브랜치가 open·closed·merged 상태를 포함한 기존 PR의 head이면 새 사용자 흐름 커밋을 추가하지 않는다.
- 범위 밖 tracked·untracked 변경이 있으면 제자리에서 branch를 전환하지 않고 별도 worktree를 사용하거나 처리 방향을 확인한다.
- 독립 흐름은 최신 기본 브랜치를 기준으로 고유한 새 브랜치를 만든다.
- 미병합 선행 PR에 의존하면 선행 head에서 새 브랜치를 만들되 새 PR을 별도로 생성한다.
- GitHub base 제약 때문에 선행 branch를 base로 사용할 수 없으면 기본 브랜치를 base로 사용하고 PR 본문에 stacked 의존성과 임시 중복 diff를 명시한다.
- 선행 PR 병합을 기다리지 않는다.
- PR 생성 후 자동 병합하거나 auto-merge를 활성화하지 않는다.

## 4. 커밋 계획

다음 단위로 작고 독립적인 커밋을 설계한다.

1. 여러 화면이 실제로 공유하는 token·layout·component
2. 화면 한 개와 그 화면에 직접 대응하는 `화면설계서.md` 변경
3. 해당 화면만을 위한 상태 fixture와 상호작용
4. 사용자 흐름 연결과 공통 탐색 인덱스 갱신

HTML, CSS와 JavaScript를 파일 종류만으로 분리하지 않는다. 각 화면 커밋은 단독으로 열고 검토할 수 있어야 한다. 무관한 문서, 다른 사용자 흐름과 포맷 변경을 섞지 않는다.

## 5. 화면 구현

- Course별 역할과 권한 차이를 표현한다.
- 정상뿐 아니라 loading, empty, partial failure, error, forbidden, expired와 연결 복구 상태를 필요한 범위에서 제공한다.
- 실시간 화면에서는 partial/final Transcript, 연결 상태와 AI 기능의 독립 실패를 구분한다.
- 1440px, 768px와 375px에서 핵심 기능을 숨기지 않고 재배치한다.
- keyboard focus, accessible name, live region, 44px 동작 영역과 reduced motion을 확인한다.
- 정적 Prototype에는 실제 API·OAuth·WebSocket·STT·AI 요청을 넣지 않고 `Static prototype` 경계를 유지한다.
- 실제 React 구현에서는 목 상태를 그대로 제품 계약으로 간주하지 않고 최신 API와 권한을 다시 확인한다.

## 6. 검증과 커밋

각 커밋 전에 다음을 수행한다.

1. 의도한 파일만 diff와 staged diff로 확인한다.
2. 변경한 HTML·CSS·JavaScript·Markdown에 저장소 formatter를 실행한다.
3. 관련 상태 전환과 화면 간 링크를 확인한다.
4. 1440px·768px·375px와 핵심 접근성을 확인한다.
5. `git diff --check`와 관련 테스트를 실행한다.
6. 검증이 성공한 화면 단위만 명시적으로 stage하고 구체적인 한국어 커밋을 만든다.

`git add -A`로 범위 밖 파일을 함께 추가하지 않는다. 실패한 검증을 숨기지 않는다.

## 7. Draft PR 생성

사용자 흐름이 완료되고 publish 권한이 있으면 다음을 수행한다.

1. 새 브랜치를 push한다.
2. 기존 PR을 재사용하지 않고 새로운 Draft PR을 만든다.
3. 한국어 본문에 배경, 화면·커밋별 변경, 구현 상태, 미구현 범위, 검증, 의존 PR과 리뷰 포인트를 기록한다.
4. PR의 base·head·commit·changed files가 계획한 범위인지 확인한다.
5. 실행 중인 CI와 실패한 check를 확인하되 PR을 병합하지 않는다.

## 8. 완료 보고

다음을 보고한다.

- 완료한 사용자 흐름과 화면
- 생성한 커밋과 브랜치
- 새 Draft PR URL 또는 publish하지 않은 이유
- 실행한 검증과 결과
- 선행 PR 의존성, 남은 미정 사항과 위험
