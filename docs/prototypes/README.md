# GOAL 화면 프로토타입

GOAL 1차 MVP의 화면 구조와 상태를 검토하기 위한 정적 HTML 프로토타입이다. 실제 API, Google OAuth, WebSocket, STT 또는 AI 모델을 호출하지 않으며 모든 내용은 검토용 목 데이터다.

## 확인 방법

1. `index.html`을 브라우저에서 연다.
2. `확인 가능` 상태인 화면을 선택한다.
3. 화면 상단의 `Prototype` 표시와 상태 전환 버튼을 확인한다.
4. 데스크톱 1440px, 태블릿 768px, 모바일 375px 너비에서 레이아웃을 점검한다.

로컬 정적 서버가 필요하면 저장소 루트에서 다음 명령을 사용할 수 있다.

```bash
python3 -m http.server 4173 --directory docs/prototypes
```

그런 다음 `http://127.0.0.1:4173/`에 접속한다.

## 구현 원칙

- 화면과 기능 범위는 `docs/product/IA.md`와 `docs/product/기능명세서.md`를 따른다.
- 역할은 계정 전체가 아니라 Course별 교수자·학생 역할로 표현한다.
- 정상 상태뿐 아니라 로딩, 빈 상태, 오류, 권한 없음과 재연결 상태를 함께 설계한다.
- 화면별 상세 동작은 `docs/product/화면설계서.md`를 기준으로 한다.
- 실제 기능과 혼동하지 않도록 각 화면에 `Static prototype`을 표시한다.

## 화면 진행표

| 사용자 흐름 | 화면                    | IA 노드                  | 파일                         | 상태      |
| ----------- | ----------------------- | ------------------------ | ---------------------------- | --------- |
| 서비스 진입 | 비로그인 메인           | `MAIN_PAGE`              | `main.html`                  | 확인 가능 |
| 서비스 진입 | 로그인 후 대시보드      | `MAIN_PAGE_AUTH`         | `dashboard.html`             | 확인 가능 |
| 서비스 진입 | 내 정보                 | `MY_INFO_PAGE`           | `my-info.html`               | 확인 가능 |
| Course      | Course 생성             | `COURSE_CREATE_PAGE`     | `course-create.html`         | 확인 가능 |
| Course      | Course 참여             | `COURSE_JOIN_PAGE`       | `course-join.html`           | 확인 가능 |
| Course      | 교수자 Course           | `COURSE_PAGE_PROF`       | `course-professor.html`      | 확인 가능 |
| Course      | 학생 Course             | `COURSE_PAGE_STUD`       | `course-student.html`        | 확인 가능 |
| 수업 준비   | class 생성·PDF          | `CLASS_CREATE_PAGE`      | `class-create.html`          | 확인 가능 |
| 실시간 수업 | 교수자 실시간 class     | `LIVE_CLASS_PAGE_PROF`   | `class-live-professor.html`  | 확인 가능 |
| 실시간 수업 | 학생 실시간 class       | `LIVE_CLASS_PAGE_STUD`   | `class-live-student.html`    | 확인 가능 |
| 수업 종료   | 기록 정리 중            | `CLASS_PROCESSING_STATE` | `class-processing.html`      | 확인 가능 |
| 수업 기록   | 교수자 완료 class       | `ENDED_CLASS_PAGE_PROF`  | `class-ended-professor.html` | 확인 가능 |
| 수업 기록   | 학생 완료 class·복습 AI | `ENDED_CLASS_PAGE_STUD`  | `class-ended-student.html`   | 확인 가능 |

## 인증·Course·READY class 정책 검토 경로

아래 링크는 query 조합으로도 서로 모순되지 않아야 하는 대표 상태다.

| 검토 항목                         | 대표 경로                                                                                                                                                                                                                    |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 인증 공통 대시보드 빈 목록        | [`dashboard.html?owned=empty&joined=empty`](dashboard.html?owned=empty&joined=empty)                                                                                                                                         |
| Course 생성·무기한 참여 코드      | [`course-create.html?state=success`](course-create.html?state=success)                                                                                                                                                       |
| 참여 코드 공통 실패               | [`course-join.html?state=invalid`](course-join.html?state=invalid)                                                                                                                                                           |
| owner 코드 회전·active class 없음 | [`course-professor.html?session=none`](course-professor.html?session=none)                                                                                                                                                   |
| 학생 READY 수동 대기              | [`course-student.html?session=ready`](course-student.html?session=ready)                                                                                                                                                     |
| PDF 없이 class 시작 가능          | [`class-create.html?stage=ready&materials=empty&start=idle`](class-create.html?stage=ready&materials=empty&start=idle)                                                                                                       |
| PROCESSING PDF로 시작 차단        | [`class-create.html?stage=ready&materials=processing&start=material-processing`](class-create.html?stage=ready&materials=processing&start=material-processing)                                                               |
| PDF 10개·용량·형식 오류           | [`materials=full`](class-create.html?stage=ready&materials=full), [`materials=size-error`](class-create.html?stage=ready&materials=size-error), [`materials=mime-error`](class-create.html?stage=ready&materials=mime-error) |
| Material 삭제 경합·이미 삭제      | [`materials=delete-conflict`](class-create.html?stage=ready&materials=delete-conflict), [`materials=delete-missing`](class-create.html?stage=ready&materials=delete-missing)                                                 |

참여 코드는 trim·대문자화 뒤 `[A-Z]{6}`이며 자동 만료되지 않는다. READY Material은 active `N/10`, 파일당 100 MB(100,000,000 bytes), 동일 이름 suffix, 권한 확인 원본 열기와 즉시 detach 목 상태를 제공한다. `PROCESSING` Material만 class 시작을 막고 PDF가 없거나 `UPLOADED`, `READY`, `FAILED`만 있으면 시작 가능하다.

## 프로토타입과 실제 구현의 경계

- 버튼과 입력은 화면 흐름 확인을 위한 로컬 상태만 변경한다.
- 새로고침하면 목 상태가 초기화될 수 있다.
- 참여 코드, 사용자, Course와 class 정보는 모두 예시다.
- 네트워크 요청이 필요한 동작은 결과를 모의 표시한다.
- 프로덕션 React 구현 시 API 명세, OpenAPI와 권한 규칙을 다시 확인해야 한다.
