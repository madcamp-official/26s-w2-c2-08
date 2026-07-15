# LMS 자동 재설계 결과 보고서

## 1. 실행 결과

5개 `Learning Management System (Community)` ZIP에서 추출한 32개 PNG를 읽기 전용
디자인 레퍼런스로 사용했다. 레퍼런스의 제품 기능이나 문구를 복사하지 않고,
`docs/design/lms-reference-profile.md`에 고정한 navy/slate/blue 색상, 흰색 surface,
cool-gray canvas, 조밀한 업무형 정보 구조, 작은 radius, 얕은 shadow와 얇은 border만
GOAL의 시각 언어로 가져왔다.

구현 우선순위는 다음 순서를 유지했다.

1. `frontend/src`의 production React UI
2. production route와 기존 typed API/TanStack Query/WebSocket 연결
3. React Testing Library/MSW 테스트와 실제 Vite 앱 screenshot
4. 정적 Prototype과 화면설계서 동기화

15개 화면 계약은 모두 production route에서 접근할 수 있다. Prototype이나 문서만
변경해 완료 처리한 화면은 없다. `/courses/:courseId`는 Course 역할로,
`/sessions/:sessionId`는 canonical Session status와 Course 역할로 view를 분기한다.
역할·상태를 위한 별도 URL은 추가하지 않았다.

## 2. Draft PR과 커밋 단위

모든 PR은 `main` 기준의 새 Draft PR로 생성했다. 선행 PR이 아직 병합되지 않은 경우
의존 관계를 PR 본문에 기록하고 다음 흐름을 계속 진행했다. merge, auto-merge,
force push와 history rewrite는 사용하지 않았다.

| 단위 | Draft PR                                                        | 화면/책임                                                           | 주요 커밋                                             |
| ---- | --------------------------------------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------- |
| PR00 | [#69](https://github.com/madcamp-official/26s-w2-c2-08/pull/69) | Reference Profile, token, AppShell, 공통 UI, 실제 앱 시각 검증 기반 | `331c20b`, `3e4cfb5`, `478c5a4`, `3bb7098`, `5bdf513` |
| PR01 | [#70](https://github.com/madcamp-official/26s-w2-c2-08/pull/70) | MAIN_PAGE, LOGIN_PAGE, EMAIL_SIGNUP_PAGE                            | `7ff61d2`, `004a065`, `638f3b0`, `4a31bca`            |
| PR02 | [#71](https://github.com/madcamp-official/26s-w2-c2-08/pull/71) | MAIN_PAGE_AUTH, MY_INFO_PAGE                                        | `2aec563`, `219dfdc`, `464708d`, `9cd1051`            |
| PR03 | [#72](https://github.com/madcamp-official/26s-w2-c2-08/pull/72) | COURSE_CREATE_PAGE, COURSE_JOIN_PAGE                                | `2e46940`, `2cf84e5`, `cd39dfd`                       |
| PR04 | [#73](https://github.com/madcamp-official/26s-w2-c2-08/pull/73) | COURSE_PAGE_PROF, COURSE_PAGE_STUD, CLASS_CREATE_PAGE/READY         | `9b2b97a`, `df28224`, `9780e2e`                       |
| PR05 | [#78](https://github.com/madcamp-official/26s-w2-c2-08/pull/78) | LIVE_CLASS_PAGE_PROF, LIVE_CLASS_PAGE_STUD                          | `b5f19a4`, `688531c`, `e122fd8`, `7277fc8`, `ac0586c` |
| PR06 | [#79](https://github.com/madcamp-official/26s-w2-c2-08/pull/79) | CLASS_PROCESSING_STATE                                              | `5f4a525`, `9a9f29d`                                  |
| PR07 | [#83](https://github.com/madcamp-official/26s-w2-c2-08/pull/83) | ENDED_CLASS_PAGE_PROF, ENDED_CLASS_PAGE_STUD, 최종 일관성/검증      | `fcb4c98`, `b1ed807`, `2fb30f0`, `36df7f9`            |

공통 기반은 PR00에, 화면 하나와 그 화면의 테스트·Prototype·화면설계 변경은 가능한
한 개의 한국어 커밋에 묶었다. CI나 최신 `main` 계약 동기화, 전체 검증에서 발견한
회귀 수정은 원인을 추적할 수 있도록 별도 커밋으로 분리했다.

## 3. 화면별 production 결과

`반복`의 `2+`는 baseline 확인, production 구현 후 재촬영, 마지막 전체 일관성 패스를
포함해 최소 두 번 이상 실제 앱 화면을 비교했다는 뜻이다. 각 결과는 실제 Vite route를
MSW network fixture로 재현했으며 production bundle에는 demo state switch를 넣지 않았다.

| 화면 ID                | production route/조건                                                      | production component                       | 커밋/PR         | 반복 | 검증 상태                                                  |
| ---------------------- | -------------------------------------------------------------------------- | ------------------------------------------ | --------------- | ---- | ---------------------------------------------------------- |
| MAIN_PAGE              | `/`, signed out                                                            | `FoundationPage` public view               | `7ff61d2` / #70 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| LOGIN_PAGE             | `/login`                                                                   | `LoginPage`                                | `004a065` / #70 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| EMAIL_SIGNUP_PAGE      | `/signup`                                                                  | `SignupPage`                               | `638f3b0` / #70 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| MAIN_PAGE_AUTH         | `/`, signed in                                                             | `FoundationPage` → `Dashboard`             | `2aec563` / #71 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| MY_INFO_PAGE           | `/account`, auth guard                                                     | `AccountPage`                              | `219dfdc` / #71 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| COURSE_CREATE_PAGE     | `/courses/new`, auth guard                                                 | `CourseCreatePage`                         | `2e46940` / #72 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| COURSE_JOIN_PAGE       | `/courses/join`, auth guard                                                | `CourseJoinPage`                           | `2cf84e5` / #72 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| COURSE_PAGE_PROF       | `/courses/:courseId`, `PROFESSOR`                                          | `CourseDetailPage` → `ProfessorCourseView` | `9b2b97a` / #73 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| COURSE_PAGE_STUD       | `/courses/:courseId`, `STUDENT`                                            | `CourseDetailPage` → `StudentCourseView`   | `df28224` / #73 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| CLASS_CREATE_PAGE      | `/courses/:courseId/sessions/new`; 생성 후 `/sessions/:sessionId`, `READY` | `SessionCreatePage`, `ReadyClassView`      | `9780e2e` / #73 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| LIVE_CLASS_PAGE_PROF   | `/sessions/:sessionId`, `LIVE` + `PROFESSOR`                               | `ProfessorLiveClassView`                   | `688531c` / #78 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| LIVE_CLASS_PAGE_STUD   | `/sessions/:sessionId`, `LIVE` + `STUDENT`                                 | `StudentLiveClassView`                     | `e122fd8` / #78 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| CLASS_PROCESSING_STATE | `/sessions/:sessionId`, `PROCESSING`; 두 Course 역할                       | `ProcessingClassView`                      | `5f4a525` / #79 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| ENDED_CLASS_PAGE_PROF  | `/sessions/:sessionId`, `COMPLETED` + `PROFESSOR`                          | `ProfessorEndedClassView`                  | `b1ed807` / #83 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |
| ENDED_CLASS_PAGE_STUD  | `/sessions/:sessionId`, `COMPLETED` + `STUDENT`                            | `StudentEndedClassView`                    | `b1ed807` / #83 | 2+   | `PRODUCTION_RENDERED` `CONTRACT_WIRED` `VISUALLY_VERIFIED` |

## 4. 시각·접근성 검증

`frontend/e2e/foundation.visual.spec.ts`는 15개 계약을 16개 역할 시나리오로 펼쳤다.
PROCESSING은 교수자·학생 모두를 별도 fixture로 확인한다. 각 시나리오는
1440px, 768px, 375px 실제 Vite 앱 screenshot을 생성하며, 결과 파일명은
`<SCREEN_ID>--<viewport>.png` 형식을 사용한다.

- production visual: 72개 case 중 64개 통과, 단일 viewport 전용 interaction case
  8개는 의도적으로 skip
- Prototype visual: 12개 case 중 10개 통과, 단일 viewport 전용 interaction case
  2개는 의도적으로 skip
- 모든 화면에서 가로 overflow, 의도하지 않은 잘림과 겹침을 자동 검사
- 44px touch target, visible focus, dialog focus 이동/복귀와 Escape 닫기를 검사
- `prefers-reduced-motion`에서 transition/animation을 제거
- 역할 전용 control, loading, empty, error, forbidden, reconnect, disabled와 부분 실패를
  route/component 테스트 또는 시각 fixture로 검증
- 1440px와 375px 전체 화면을 육안 비교하고, 768px 결과는 같은 hard check와
  screenshot diff 대상으로 검증

완료 화면은 녹음 권한 사전 확인, native play/Transcript seek 시 요청별 재인증,
재생 오류 복구, 교수자 녹음 삭제 dialog, 텍스트 Answer 생성·수정·철회와 cursor
다음 페이지의 부분 실패를 독립 상태로 표현한다. 한 영역의 실패가 Transcript,
질문, 자료와 다른 정상 기록을 가리지 않는다.

## 5. 자동 검증 결과

| 검증                               | 결과                                                          |
| ---------------------------------- | ------------------------------------------------------------- |
| `make skills-check`                | 2개 공통 Skill 동기화/형식 통과                               |
| `make docs-check`                  | 14개 Markdown 통과                                            |
| Backend Ruff lint/format           | 198개 Backend 파일과 docs script 통과                         |
| Backend unit                       | 96 passed                                                     |
| Backend contract                   | 9 passed                                                      |
| Backend integration                | 74 passed                                                     |
| Backend migration                  | 2 passed                                                      |
| Frontend ESLint/Prettier/typecheck | 통과                                                          |
| OpenAPI generated schema 비교      | 통과                                                          |
| Frontend Vitest                    | 42 files, 261 passed                                          |
| Frontend production build          | 통과; 기존 500 kB chunk size 경고만 존재                      |
| `git diff --check`                 | 통과                                                          |

전체 DB integration에서 Answer 완료 요청 시각이 캡처 시작 시각보다 수 ms 앞서는
wall-clock 경합을 재현했다. DB의 기존 `completed_at >= started_at` 계약을 바꾸지 않고
완료 시각을 시작 시각에 clamp했으며, 시작 시각을 의도적으로 1초 앞으로 이동하는
회귀 테스트와 전체 Backend 검증을 통과했다(`36df7f9`).

## 6. Integration gap과 남은 위험

다음 항목은 endpoint나 상태를 발명하지 않고 현재 계약이 제공하는 범위까지만
production UI에 반영했다. 화면 구현 누락과 구분하기 위해 `INTEGRATION_GAP`으로 남긴다.

1. `MAIN_PAGE_AUTH` — Course 목록 응답에는 학생 역할의 완료 수업 기록 개수가 없다.
   UI는 임의 집계를 표시하지 않고 실제 Course/역할/진행 상태만 표시한다.
   `INTEGRATION_GAP`
2. `LIVE_CLASS_PAGE_PROF` — 브라우저 로컬 녹음의 terminal failure를 즉시 서버에
   확정하는 별도 endpoint가 없다. UI는 기존 upload/session 상태와 서버 watchdog
   계약에 따른 복구 상태를 제공하며 새 endpoint를 만들지 않았다. `INTEGRATION_GAP`

두 항목 모두 해당 production route, 안전한 unavailable/error 표현과 테스트가
존재한다. Backend 계약이 추가될 때 typed client/query 연결을 확장해야 한다.

## 7. 최종 일관성 및 격리 감사

- token, AppShell, navigation, Button, Field, Card, Status, Dialog, Toast, Skeleton을
  production 공통 component로 사용한다.
- Transcript, Question, Answer, material, recording, 개인 AI와 후처리 작업은 같은
  상태 색상·간격·heading 규칙을 공유한다.
- READY, LIVE, PROCESSING, COMPLETED와 Course별 PROFESSOR/STUDENT 의미를 변경하지
  않았다.
- API wrapper, TanStack Query hook과 WebSocket 계층을 우선 재사용했고 production
  bundle에 fake data나 fixture 분기를 추가하지 않았다.
- 정적 Prototype과 화면설계서는 production 구현 뒤 동기화했다.
- 원본 5개 ZIP과 Figma 원본은 수정하지 않았다.
- 원래 작업트리는 시작/종료 시 동일하게 `main...origin/main [ahead 31]`이며 기존
  수정 6개와 untracked `typescript`를 그대로 보존했다.
- 모든 구현·검증·커밋은 격리 worktree와 `design/lms-*` 브랜치에서만 수행했다.
- 8개 PR은 리뷰용 Draft로 유지하며 자동 병합하지 않는다.
