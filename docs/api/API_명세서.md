# GOAL API 명세서

> 상태: Draft v0.1
>
> 작성 기준일: 2026-07-11
>
> 기계 판독용 계약: [openapi.yaml](./openapi.yaml)

## 1. 문서 목적과 범위

본 문서는 GOAL MVP의 HTTP API, 비동기 AI 작업과 WebSocket 이벤트 계약을 정의한다.
사용자 기능과 상태 규칙은 다음 문서를 기준으로 한다.

- [기획안](../product/기획안.md)
- [기능명세서](../product/기능명세서.md)
- [IA](../product/IA.md)
- [기술명세서](../architecture/기술명세서.md)

본 문서는 DB 테이블 구조를 정의하지 않으며 API에서 관찰 가능한 리소스와 동작만을 다룬다.

### 1.1 계약의 우선순위

1. 구현 전에는 본 문서와 `openapi.yaml`을 설계 계약으로 사용한다.
2. 구현 후에는 FastAPI가 생성하는 `/openapi.json`을 최종 기계 계약으로 사용한다.
3. 구현과 문서가 다르면 임의로 한쪽을 따르지 않고 차이를 검토한 후 둘을 함께 수정한다.

### 1.2 초안 가정과 미정 사항

다음은 API 설계를 위한 초안 가정이며 구현 전 확정이 필요하다.

- 버전 경로는 `/api/v1`을 사용한다.
- JSON 필드는 `snake_case`를 사용한다.
- 리소스 ID는 API에서 불투명 문자열로 취급한다. UUID 사용 여부는 DB 설계에서 확정한다.
- Google OAuth/OIDC authorization code 흐름 뒤 서버 세션을 만들고 HttpOnly Cookie로 인증한다.
- AI 요약과 채팅은 우선 `202 Accepted + AIJob`으로 표현한다. 개인 AI 출력은 요청자 전용 스트리밍 HTTP 또는 SSE를 권장하지만 전송 방식은 TBD이다.
- WebSocket과 오디오 스트리밍은 OpenAPI 표준 범위 밖이므로 본 문서와 YAML의 `x-websocket-channels`에 초안을 기록한다.

## 2. 공통 규칙

### 2.1 Base URL

```text
/api/v1
```

상태 확인 API는 버전 경로 밖의 기존 경로를 유지한다.

```text
GET /api/health
GET /api/health/db
```

### 2.2 인증과 사용자 식별

MVP 웹 인증은 서버 세션 Cookie를 사용한다.

```http
Cookie: goal_session=<opaque-session-id>
```

- Cookie 속성은 `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=604800`이며 기본 만료는 7일이다.
- 브라우저 JavaScript와 localStorage에 Google token 또는 서버 session ID를 저장하지 않는다.
- 서버에는 session ID의 hash, 사용자 ID, 만료와 폐기 시각만 보관하며 Google access token은 API 호출에 필요하지 않으면 저장하지 않는다.
- 상태 변경 요청은 허용된 `Origin`인지 확인한다.
- 서버는 요청 본문의 `user_id`를 신뢰하지 않는다.
- 현재 사용자는 인증 컨텍스트에서 확인한다.
- 사용자에게 전역 교수자·학생 역할을 부여하지 않는다.
- 권한은 요청 리소스가 속한 Course의 `PROFESSOR` 또는 `STUDENT` 멤버십으로 판단한다.
- 브라우저 WebSocket에는 access token을 직접 전달하지 않고 인증된 HTTP API가 발급한 60초 만료·1회용 티켓을 사용한다.

#### 2.2.1 Google 로그인 시작

```http
GET /api/v1/auth/google/start?return_to=/courses
```

- 서버는 state, nonce와 PKCE 검증 정보를 만들고 10분 만료 임시 `goal_oauth` Cookie를 설정한다.
- `return_to`는 같은 서비스의 허용된 상대 경로만 받으며 외부 URL은 거부한다.
- 성공하면 Google 로그인 화면으로 `302 Redirect`한다.

#### 2.2.2 Google callback

```http
GET /api/v1/auth/google/callback?code=<code>&state=<state>
```

- state, nonce와 PKCE를 검증한 뒤 User를 생성 또는 갱신한다.
- 기존 서버 세션이 있으면 session fixation을 막기 위해 새 session ID로 회전한다.
- 성공하면 `goal_session` Cookie를 설정하고 검증된 `return_to`로 `302 Redirect`한다.
- Provider 오류 원문과 token을 응답 또는 로그에 남기지 않는다.

#### 2.2.3 로그아웃

```http
POST /api/v1/auth/logout
```

- 서버 세션을 폐기하고 `goal_session` Cookie를 즉시 만료한다.
- 이미 로그아웃 상태인 반복 요청도 `204 No Content`를 반환한다.

### 2.3 콘텐츠 타입

| 용도             | Content-Type                               |
| ---------------- | ------------------------------------------ |
| JSON 요청·응답   | `application/json`                         |
| PDF 업로드       | `multipart/form-data`                      |
| PDF 열람         | `application/pdf`                          |
| 녹음 upload      | resumable upload protocol 확정 전 TBD      |
| 녹음 playback    | 녹음 codec·container 확정 전 TBD           |
| WebSocket 이벤트 | JSON text frame                            |
| 실시간 음성      | binary frame, MVP v1 PCM_S16LE 16 kHz mono |

### 2.4 시간과 정렬

- API 시각은 ISO 8601 UTC 문자열로 응답한다.
- 예: `2026-07-11T01:30:00Z`
- class의 날짜는 `YYYY-MM-DD`로 표현한다.
- 동일 시각 데이터의 안정적 정렬을 위해 `id`를 보조 정렬 키로 사용한다.

### 2.5 커서 페이지네이션

일반 목록 API는 기본적으로 다음 쿼리를 지원한다. Transcript와 Chat Message처럼 사용 패턴이 다른 목록은 해당 API 절에 별도 기본값을 명시한다.

| 필드     | 타입    | 기본값 | 설명                      |
| -------- | ------- | -----: | ------------------------- |
| `cursor` | string  |   없음 | 직전 응답의 `next_cursor` |
| `limit`  | integer |   `20` | `1`에서 `100` 사이        |

```json
{
  "items": [],
  "next_cursor": null
}
```

- 커서는 서버가 생성한 불투명 문자열이다.
- 클라이언트는 커서 내부 구조를 해석하지 않는다.

### 2.6 멱등성과 중복 제출

- `PUT` 반응 추가와 `DELETE` 반응 취소는 멱등적이다.
- class 종료, AI 작업 생성과 중복 제출 위험이 있는 `POST`는 `Idempotency-Key` 헤더를 지원한다.
- 서버는 정규화한 HTTP method·path·body로 `request_hash`를 계산한다.
- 같은 사용자·같은 경로·같은 키와 같은 `request_hash`의 재요청은 최초 응답의 HTTP status와 body를 그대로 반환한다.
- 동일 요청이 처리 중이면 중복 실행하지 않고 기존 처리 상태를 재사용하며, terminal 완료 후에는 저장된 응답을 재사용한다.
- 같은 키로 다른 `request_hash`를 보내면 `409 IDEMPOTENCY_KEY_REUSED`를 반환한다.
- terminal 완료 응답은 완료 시각부터 정확히 24시간 보관하고 재사용한다.

### 2.7 요청 ID

클라이언트는 선택적으로 `X-Request-ID`를 보낼 수 있다. 서버는 없거나 유효하지 않으면 새로 생성하고 응답 헤더에 반환한다.

## 3. 공통 응답과 오류

### 3.1 오류 응답

```json
{
  "error": {
    "code": "SESSION_NOT_LIVE",
    "message": "진행 중인 class에서만 질문할 수 있습니다.",
    "request_id": "req_01HXYZ",
    "details": null
  }
}
```

|  HTTP | 의미                       | 주요 코드                                                                                                                                                                                                                                                                                                                                          |
| ----: | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `400` | 요청 형식 오류             | `INVALID_REQUEST`, `INVALID_CURSOR`                                                                                                                                                                                                                                                                                                                |
| `401` | 인증 필요                  | `AUTHENTICATION_REQUIRED`, `INVALID_SESSION`                                                                                                                                                                                                                                                                                                       |
| `403` | Course 또는 역할 권한 없음 | `COURSE_ACCESS_DENIED`, `ROLE_REQUIRED`                                                                                                                                                                                                                                                                                                            |
| `404` | 리소스 없음                | `RESOURCE_NOT_FOUND`, `MATERIAL_NOT_FOUND`, `RECORDING_NOT_FOUND`, `RECORDING_UPLOAD_NOT_FOUND`                                                                                                                                                                                                                                                    |
| `409` | 상태 전이·중복 충돌        | `SESSION_STATE_CONFLICT`, `ACTIVE_SESSION_EXISTS`, `IDEMPOTENCY_KEY_REUSED`, `MEMBERSHIP_CONFLICT`, `AI_JOB_STATE_CONFLICT`, `AI_JOB_NOT_RETRYABLE`, `MATERIAL_PROCESSING_ACTIVE`, `MATERIAL_LIMIT_EXCEEDED`, `MATERIAL_DELETE_CONFLICT`, `RECORDING_STATE_CONFLICT`, `RECORDING_UPLOAD_CONFLICT`, `UPLOAD_OFFSET_MISMATCH`, `RECORDING_NOT_READY` |
| `410` | upload 만료                | `RECORDING_UPLOAD_EXPIRED`                                                                                                                                                                                                                                                                                                                         |
| `413` | 파일 크기 초과             | `FILE_TOO_LARGE`                                                                                                                                                                                                                                                                                                                                   |
| `415` | 파일 형식 오류             | `UNSUPPORTED_MEDIA_TYPE`, `UNSUPPORTED_RECORDING_FORMAT`                                                                                                                                                                                                                                                                                           |
| `416` | playback 범위 오류         | `RANGE_NOT_SATISFIABLE`                                                                                                                                                                                                                                                                                                                            |
| `422` | 필드 검증 실패             | `VALIDATION_ERROR`                                                                                                                                                                                                                                                                                                                                 |
| `429` | 요청 한도 초과             | `RATE_LIMITED`                                                                                                                                                                                                                                                                                                                                     |
| `500` | 서버 오류                  | `INTERNAL_ERROR`                                                                                                                                                                                                                                                                                                                                   |
| `503` | 의존 서비스 장애           | `DEPENDENCY_UNAVAILABLE`                                                                                                                                                                                                                                                                                                                           |

녹음 checksum 불일치의 공개 오류 코드는 `RECORDING_CHECKSUM_MISMATCH`로 고정한다. checksum algorithm, 검증 시점과 이 오류의 HTTP status는 resumable upload protocol과 함께 TBD이다.

### 3.2 AI 작업 수락 응답

```json
{
  "job": {
    "id": "job_01HXYZ",
    "session_id": "session_01HXYZ",
    "job_type": "LIVE_SUMMARY",
    "visibility": "REQUESTER_ONLY",
    "status": "PENDING",
    "attempt": 1,
    "version": 1,
    "progress": null,
    "retryable": false,
    "blocks_session_completion": false,
    "error": null,
    "target": {
      "resource_type": "SUMMARY",
      "resource_id": null,
      "resource_url": "/api/v1/sessions/session_01HXYZ/summaries"
    },
    "result": null,
    "created_at": "2026-07-11T01:30:00Z",
    "updated_at": "2026-07-11T01:30:00Z",
    "started_at": null,
    "finished_at": null
  }
}
```

### 3.3 현재 스캐폴딩과 목표 계약의 차이

- 현재 FastAPI 코드는 상태 확인 API만 구현되어 있고 나머지 경로는 설계 계약이다.
- 현재 `/api/health/db` 장애 응답과 FastAPI 기본 `422`는 `detail` 형식이다. 비즈니스 API 구현 시 공통 exception handler를 추가해 본 문서의 `error` envelope로 통일한다.
- 구현 후 CI에서 FastAPI `/openapi.json`과 `docs/api/openapi.yaml`의 path·method·schema 차이를 검사한다.

## 4. 상태와 권한 규칙

### 4.1 Course 역할

| 역할        | 권한                                                       |
| ----------- | ---------------------------------------------------------- |
| `PROFESSOR` | Course·class 생성, 자료 업로드, class 시작·종료, 질문 답변 |
| `STUDENT`   | class 입장, Transcript·자료 열람, 질문·반응, AI 기능       |

같은 사용자가 Course별로 다른 역할을 가질 수 있다.

- 계정 전역 역할은 없으며 모든 인증 사용자가 Course를 생성하거나 참여 코드로 참여할 수 있다.
- Course 생성자는 해당 Course의 유일한 `PROFESSOR`가 되며, Course에는 정확히 한 명의 교수자만 존재한다.
- MVP API는 교수자 추가·교체·탈퇴를 제공하지 않는다.

### 4.2 LectureSession

```text
READY → LIVE → PROCESSING → COMPLETED
```

| 요청        | 선행 상태    | 결과         |
| ----------- | ------------ | ------------ |
| class 시작  | `READY`      | `LIVE`       |
| class 종료  | `LIVE`       | `PROCESSING` |
| 후처리 완료 | `PROCESSING` | `COMPLETED`  |

- 다른 상태에서의 전이는 `409 SESSION_STATE_CONFLICT`로 거부한다.
- 한 Course에는 `READY`, `LIVE`, `PROCESSING` 중 하나인 active Session이 합계 최대 1개만 존재한다.
- active Session이 이미 있을 때 class 생성은 `409 ACTIVE_SESSION_EXISTS`로 거부한다.
- `PROCESSING`과 `COMPLETED`에서는 새 음성, 질문과 반응을 받지 않는다.
- 종료 시점에는 `SESSION_POSTPROCESSING`, `FINAL_SUMMARY`와 필요 시 마지막 `QUESTION_CLUSTERING` 중 녹음 upload에 의존하지 않는 공용 Job만 생성할 수 있다. HQ STT는 Recording upload complete 뒤에만 시작한다.
- 첫 `audio.start`로 Recording이 생긴 Session은 Recording이 `UPLOAD_PENDING` 또는 `UPLOADING`인 동안 `PROCESSING`을 유지한다. `UPLOADED` 또는 `FAILED`가 PR3에서 정의하는 녹음 저장 gate의 terminal 상태다.
- HQ STT를 어떤 Job type·완료 차단 상태로 표현할지, upload가 완료되지 않는 Recording을 언제 `FAILED`로 전이할지와 최종 Session 완료 조건은 PR4에서 확정한다. Recording이 없는 Session의 기존 공용 Job 완료 규칙은 유지한다.
- `SESSION_POSTPROCESSING`의 성공은 drain과 child Job 상태 수집이 끝났다는 뜻이며 `FINAL_SUMMARY`·`QUESTION_CLUSTERING`의 성공까지 의미하지 않는다.
- `FAILED` Job은 기록 화면에 오류와 재시도 상태를 표시하고, 재시도 중에도 Session은 `COMPLETED`를 유지한다.
- worker 장애로 `RUNNING`에 남은 Job은 watchdog이 timeout 후 `FAILED`로 바꿔 Session이 `PROCESSING`에 영구 정체되지 않게 한다.
- Session이 `COMPLETED`로 전환된 시각을 `completed_at`으로 공개한다. 그 전에는 `null`이다.

### 4.3 Question

```text
OPEN → SELECTED → ANSWERED
```

- 클러스터링 실패는 질문 상태에 영향을 주지 않는다.
- 답변 취소 시 `SELECTED → OPEN` 복귀를 허용하는 것으로 초안을 잡는다.

### 4.4 AIJob

```text
PENDING → RUNNING → SUCCEEDED
                  └→ FAILED
```

- 실패한 작업만 재시도할 수 있다.
- `visibility`는 `SHARED` 또는 `REQUESTER_ONLY`이며 `blocks_session_completion=true`인 Job은 반드시 `SHARED`이다.
- `job_type`을 작업의 공개 purpose로 사용하고 `progress.stage`에는 `QUEUED`, `EXTRACTING`, `GENERATING`, `FINALIZING` 등 사용자에게 공개해도 안전한 phase만 반환한다.
- provider 내부 단계, 프롬프트·응답 원문과 민감한 오류 정보는 공개하지 않는다.
- 재시도는 같은 Job 행의 `attempt`를 1 증가시키고 `PENDING`으로 되돌린다. `version`도 1 증가한다.
- 재시도 시 현재 실행 상태인 progress, error, `started_at`, `finished_at`을 `null`로 초기화하고 `retryable=false`로 되돌린다.
- worker 결과는 현재 Job의 `id`, `attempt`, 실행 token과 `RUNNING` 상태가 모두 일치할 때만 반영한다. 이전 attempt의 늦은 결과는 폐기한다.

## 5. 사용자 API

### 5.1 내 정보 조회

```http
GET /api/v1/me
```

- 권한: 인증 사용자
- 응답: 계정 ID, 표시 이름, 이메일, 프로필 이미지
- Google 프로필 필드와 수정 가능 필드는 인증 방식 확정 후 보완한다.

## 6. Course API

### 6.1 Course 목록

```http
GET /api/v1/courses?role=ALL&cursor=<cursor>&limit=20
```

- 권한: 인증 사용자
- `role`: `ALL`, `PROFESSOR`, `STUDENT`
- 현재 사용자가 참여한 Course만 반환한다.
- 각 항목에 Course별 현재 사용자 역할과 최근·진행 중 class 요약을 포함한다.

### 6.2 Course 생성

```http
POST /api/v1/courses
```

```json
{
  "title": "알고리즘",
  "semester": "2026 여름학기"
}
```

- 권한: 인증 사용자
- 성공: `201 Created`
- 생성자는 해당 Course의 유일한 `PROFESSOR`가 되며 Course 생성과 교수자 멤버십 생성을 원자적으로 처리한다.
- 서버가 영문 대문자 6자인 고유한 `join_code`를 생성한다.
- 참여 코드는 교수자 권한 응답에만 포함한다.

### 6.3 Course 참여

```http
POST /api/v1/courses/join
```

```json
{
  "join_code": "ABCXYZ"
}
```

- 권한: 인증 사용자
- 입력 앞뒤 공백을 제거하고 영문자를 대문자로 정규화한 뒤 `[A-Z]{6}`인지 검증한다. 구분자는 허용하지 않는다.
- 참여 코드는 만료되지 않는다. 회전된 이전 코드는 즉시 무효가 된다.
- 새 멤버십: `201 Created`
- 기존 학생 멤버십에 대한 재요청: `200 OK`
- 기존 교수자 멤버십을 학생으로 덮어쓰지 않는다.
- 유효하지 않은 코드는 존재 여부를 과도하게 노출하지 않는 공통 오류로 응답한다.

### 6.4 Course 상세

```http
GET /api/v1/courses/{course_id}
```

- 권한: Course 멤버
- 응답: Course 정보, 현재 사용자 역할과 현재 class 요약
- `current_session`은 `READY`, `LIVE`, `PROCESSING` 중 하나인 유일한 active Session이며 없으면 `null`이다.
- 완료 class 목록은 `GET /courses/{course_id}/sessions?status=COMPLETED`로 조회한다.
- `join_code`는 `PROFESSOR`에게만 반환한다.

### 6.5 Course 참여 코드 회전

```http
POST /api/v1/courses/{course_id}/join-code/rotate
Idempotency-Key: <key>
```

- 권한: 해당 Course를 처음 생성한 `PROFESSOR`만 가능하다.
- `Idempotency-Key`는 필수이며 2.6절의 24시간 규칙을 따른다.
- 성공: `200 OK`, 새 `join_code`를 포함한 Course를 반환한다.
- 새 코드는 영문 대문자 6자이며 이전 코드는 새 코드가 저장되는 즉시 무효가 된다.

### 6.6 Course 삭제

```http
DELETE /api/v1/courses/{course_id}
Idempotency-Key: <key>
```

- 권한: Course `PROFESSOR`
- `Idempotency-Key`는 필수이며 2.6절의 24시간 규칙을 따른다.
- Course에는 종료 상태나 종료 API가 없으며 삭제만 제공한다.
- active Session이 있는 Course의 삭제 허용 여부와 삭제·보관 방식은 미정이다. 이 정책을 확정하기 전에는 구현 계약을 추가로 정해야 한다.
- 삭제와 멱등성 완료 응답 저장을 한 transaction으로 처리해 Course가 사라진 뒤의 재요청도 기존 `204`를 반환한다.
- 삭제가 허용되는 Course의 성공 응답은 `204 No Content`이다.

## 7. Lecture Session API

### 7.1 class 목록

```http
GET /api/v1/courses/{course_id}/sessions?status=<status>&cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- 기본 정렬과 완료 목록 정렬은 `lecture_date DESC, started_at DESC NULLS FIRST, id DESC`이다. 같은 날짜의 완료 class는 실제 시작 시각으로 구분한다.
- 페이지 커서는 이 정렬 tuple 전체를 보존한다.
- `status`는 선택적이다.

### 7.2 class 생성

```http
POST /api/v1/courses/{course_id}/sessions
```

```json
{
  "title": "그래프 탐색과 최단 경로",
  "lecture_date": "2026-07-11"
}
```

- 권한: Course `PROFESSOR`
- 성공: `201 Created`, 상태 `READY`
- `title`은 선택적이다. 생략하거나 앞뒤 공백을 제거한 값이 빈 문자열이면 서버가 Course 제목·class 날짜·시각을 포함한 자동 제목을 생성한다.
- 자동 제목의 정확한 문자열 형식, `READY`에서 사용할 시각 원장과 timezone은 미정이다.
- 같은 날짜에 여러 class를 허용한다.
- 같은 Course에 `READY`, `LIVE`, `PROCESSING` Session이 이미 있으면 `409 ACTIVE_SESSION_EXISTS`를 반환한다.

### 7.3 class 상세

```http
GET /api/v1/sessions/{session_id}
```

- 권한: Course 멤버
- 응답: 세션 상태, 날짜와 시작·종료·완료 시각
- 자료, final Transcript, 질문·답변과 공용 AI 작업은 각 Session 하위 목록 API로 조회한다.

### 7.4 class 제목 수정

```http
PATCH /api/v1/sessions/{session_id}
```

```json
{
  "title": "그래프 탐색"
}
```

- 권한: Course `PROFESSOR`
- 모든 Session 상태에서 제목만 수정할 수 있다. `lecture_date`와 시작·종료·완료 시각은 수정할 수 없다.
- 앞뒤 공백을 제거한 제목이 빈 문자열이면 class 생성과 같은 자동 제목으로 되돌린다.
- 성공: `200 OK`, `version`이 증가한 Session을 반환한다. 별도 `If-Match` 계약은 도입하지 않는다.

### 7.5 class 삭제

```http
DELETE /api/v1/sessions/{session_id}
Idempotency-Key: <key>
```

- 권한: Course `PROFESSOR`
- `Idempotency-Key`는 필수이며 2.6절의 24시간 규칙을 따른다.
- `READY`, `COMPLETED`에서만 삭제할 수 있다.
- `LIVE`, `PROCESSING`에서는 `409 SESSION_STATE_CONFLICT`를 반환한다.
- 삭제와 멱등성 완료 응답 저장을 한 transaction으로 처리해 Session이 사라진 뒤의 재요청도 기존 `204`를 반환한다.
- 성공: `204 No Content`

### 7.6 class 시작

```http
POST /api/v1/sessions/{session_id}/start
```

- 권한: Course `PROFESSOR`
- 성공: `200 OK`, 상태 `LIVE`
- `READY`에서만 시작한다.
- 외부에서 연결된 강의자료가 0개여도 시작할 수 있다.
- 연결된 강의자료가 모두 `READY`, `UPLOADED`, `FAILED` 중 하나이면 시작할 수 있다. `READY` 자료만 AI 근거로 사용하고 `UPLOADED`, `FAILED` 자료는 제외한다.
- 연결된 강의자료가 하나라도 `PROCESSING`이면 `409 MATERIAL_PROCESSING_ACTIVE`를 반환하고 Session은 `READY`를 유지한다. 이미 분리된 자료는 시작 조건에 포함하지 않는다.
- Course의 유일한 active Session이 이 Session이므로 같은 Course의 다른 `READY`, `LIVE`, `PROCESSING` Session과 공존할 수 없다.

### 7.7 class 종료

```http
POST /api/v1/sessions/{session_id}/end
Idempotency-Key: <key>
```

- 권한: Course `PROFESSOR`
- `LIVE → PROCESSING`을 한 번만 적용한다.
- `CAPTURING` Answer가 남아 있으면 `409 ANSWER_CAPTURE_ACTIVE`를 반환하므로 먼저 완료하거나 취소해야 한다.
- 정상 클라이언트는 `audio.stop`과 `audio.stopped` 완료 후 호출한다. 종료 요청이 먼저 오면 서버가 새 audio frame을 차단하고 이미 받은 chunk만 drain한다.
- 종료 transaction이 commit되면 Session은 즉시 `PROCESSING`이 되고 새 audio 입력과 resume을 차단한다. 첫 `audio.start`에서 만든 논리 Recording은 `CAPTURING → UPLOAD_PENDING`으로 전이한다.
- 브라우저가 로컬 녹음을 확정한 뒤 15.3~15.5절의 resumable upload로 전송한다. Recording upload가 완료되기 전에는 HQ STT를 시작하지 않는다.
- 남은 live final Transcript drain과 녹음 upload에 의존하지 않는 종료 작업만 먼저 처리할 수 있다. HQ Transcript generation·canonical 교체·timeout·Answer 재매핑은 PR4에서 확정한다.
- 성공: `202 Accepted`, 갱신된 Session, nullable Recording과 이 시점에 생성된 Job을 반환한다.
- 재요청은 기존 Session, Recording과 Job 결과를 반환한다.

## 8. 강의자료 API

### 8.1 PDF 업로드

```http
POST /api/v1/sessions/{session_id}/materials
Content-Type: multipart/form-data
```

| 필드   | 타입   | 필수 | 설명     |
| ------ | ------ | ---: | -------- |
| `file` | binary |    Y | PDF 파일 |

- 권한: Course `PROFESSOR`
- Session 상태가 `READY`, `LIVE`, `COMPLETED`일 때 업로드할 수 있다. `PROCESSING`에서는 `409 SESSION_STATE_CONFLICT`를 반환한다.
- 파일 하나의 최대 크기는 십진수 `100000000` bytes이다. 초과하면 `413 FILE_TOO_LARGE`, MIME과 파일 signature가 PDF가 아니면 `415 UNSUPPORTED_MEDIA_TYPE`을 반환한다.
- 한 Session에 외부에서 연결된 강의자료는 최대 10개이다. 이미 10개이면 `409 MATERIAL_LIMIT_EXCEEDED`를 반환하며, 분리된 자료는 이 개수에 포함하지 않는다.
- 동일 내용의 파일 재업로드를 허용한다. `Idempotency-Key`가 없는 별도 요청 또는 서로 다른 키의 요청은 content hash가 같아도 새 Material을 생성한다.
- 서버는 업로드 파일명을 안전한 초기 `display_name`으로 정규화한다. 같은 Session의 연결된 자료와 충돌하면 확장자 앞에 ` (1)`, ` (2)` 순서로 사용 가능한 번호를 붙인다. 할당한 `display_name`은 업로드 시 저장하고 조회할 때 다시 계산하지 않는다.
- 성공: `202 Accepted`. Material을 `processing_status=UPLOADED`로 저장하고 `MATERIAL_PROCESSING` AIJob을 생성한다. 이 Job은 `visibility=SHARED`, `blocks_session_completion=false`이며, `COMPLETED` Session에 업로드해도 Session 상태는 바뀌지 않는다.
- 전처리 중에는 `PROCESSING`, 성공하면 `READY`, 실패하면 `FAILED`로 갱신한다. `READY` 자료만 새 AI 검색과 근거 생성에 사용할 수 있고 `UPLOADED`, `PROCESSING`, `FAILED` 자료는 제외한다.

### 8.2 자료 목록과 메타데이터

```http
GET /api/v1/sessions/{session_id}/materials
GET /api/v1/materials/{material_id}
```

- 권한: Course 멤버
- 외부에서 연결된 자료만 반환한다. 응답은 업로드 시 확정한 `display_name`, MIME, 크기, 페이지 수와 처리 상태를 포함한다.
- 분리된 자료의 단건 조회는 존재를 공개하지 않고 `404 MATERIAL_NOT_FOUND`를 반환한다.
- 내부 파일 경로, 스토리지 키와 `detached_at`은 응답하지 않는다.

### 8.3 PDF 열람

```http
GET /api/v1/materials/{material_id}/content
```

- 권한: Course 멤버
- 성공: `200 OK`, `application/pdf`
- `Content-Disposition` 파일명에는 저장된 `display_name`을 안전하게 인코딩해 사용한다.
- 분리된 자료는 `404 MATERIAL_NOT_FOUND`를 반환한다.
- 추후 객체 스토리지를 사용하면 짧은 만료 시간의 서명 URL 응답으로 변경할 수 있다.

### 8.4 자료 분리

```http
DELETE /api/v1/materials/{material_id}
Idempotency-Key: <key>
```

- 권한: Course `PROFESSOR`
- `Idempotency-Key`는 필수이며 2.6절의 24시간 규칙을 따른다.
- Session 상태가 `READY`, `LIVE`, `COMPLETED`일 때 분리할 수 있다. `PROCESSING`에서는 `409 SESSION_STATE_CONFLICT`를 반환한다.
- 동시 상태 변경이나 version 경합으로 분리를 확정할 수 없으면 `409 MATERIAL_DELETE_CONFLICT`를 반환한다. 클라이언트는 자료 목록을 다시 불러온 뒤 재시도한다.
- 성공: `204 No Content`. 응답 전에 외부 연결을 즉시 끊어 목록·단건·본문·수업 기록에서 제외하고 새 AI 검색과 근거 생성에도 사용하지 않는다.
- 동일한 멱등성 키와 요청의 재시도는 최초 `204`를 반환한다. 분리 완료 후 새 요청으로 접근하면 `404 MATERIAL_NOT_FOUND`를 반환한다.
- 파일 객체와 파생 chunk는 background cleanup으로 정리한다. 스토리지 키와 `detached_at`은 외부 API에 노출하지 않는다.
- 이미 저장된 Assistant 근거를 보존하는 경우 안전한 `label` snapshot은 남길 수 있지만 자료 `resource_url`은 `null`로 반환한다. 근거의 정확한 보관 기간·FK 정책과 `410 Gone` 도입 여부는 미정이다.

## 9. Transcript API

### 9.1 final Transcript 조회

```http
GET /api/v1/sessions/{session_id}/transcript?after_sequence=<n>&limit=100
```

- 권한: Course 멤버
- 영구 저장된 final Transcript만 반환한다.
- `after_sequence`보다 큰 구간을 `sequence` 오름차순으로 반환한다.
- WebSocket 재연결 후 누락 데이터 복구에 사용한다.
- partial Transcript는 DB 목록 API에서 제공하지 않는다.

## 10. 질문·반응 API

### 10.1 질문 목록

```http
GET /api/v1/sessions/{session_id}/questions?status=OPEN&sort=POPULAR&cursor=<cursor>&limit=50
```

- 권한: Course 멤버
- `sort`: `POPULAR`, `RECENT`
- 응답은 익명 질문, 반응 수, 답변 상태와 선택적 클러스터 요약을 포함한다.
- 클러스터 요약은 같은 클러스터링 결과를 식별하는 `generation`, 그 결과 안의 안정적 순서인 `ordinal`, 최종본 여부 `is_final`, 최종 확정 시각 `finalized_at`과 생성 provenance인 `created_by_job_id`, `created_by_job_attempt`를 포함한다.
- 현재 사용자의 반응 여부는 `reacted_by_me`로 표현한다.
- 교수자와 다른 학생에게 `author_id`, 이름, 이메일을 절대 반환하지 않는다.

### 10.2 질문 단건

```http
GET /api/v1/questions/{question_id}
```

- 권한: Course 멤버
- 목록과 같은 익명 Question 표현을 반환하며 작성자 식별 정보를 포함하지 않는다.

### 10.3 익명 질문 생성

```http
POST /api/v1/sessions/{session_id}/questions
Idempotency-Key: <key>
```

```json
{
  "content": "다익스트라에서 음수 가중치를 쓸 수 없는 이유가 궁금합니다."
}
```

- 권한: Course `STUDENT`
- Session이 `LIVE`일 때만 허용한다.
- 성공: `201 Created`
- 질문을 먼저 저장하고 `question.created`를 전파한 후 클러스터링을 비동기로 실행한다.
- 응답은 저장된 `question`과 공용 `clustering_job`을 함께 반환한다.
- 클러스터링 실패는 질문 생성 성공에 영향을 주지 않는다.

아래는 핵심 필드만 표시한 축약 예시이며 전체 필드는 `openapi.yaml`을 따른다.

```json
{
  "question": {
    "id": "question_01HXYZ",
    "content": "다익스트라에서 음수 가중치를 쓸 수 없는 이유가 궁금합니다.",
    "status": "OPEN"
  },
  "clustering_job": {
    "id": "job_01HXYZ",
    "job_type": "QUESTION_CLUSTERING",
    "status": "PENDING",
    "target": {
      "resource_type": "QUESTION",
      "resource_id": "question_01HXYZ",
      "resource_url": "/api/v1/questions/question_01HXYZ"
    },
    "result": null
  }
}
```

### 10.4 AI 질문 문장 작성 도움

```http
POST /api/v1/sessions/{session_id}/question-drafts
```

```json
{
  "draft": "음수 가중치 왜 안돼요?"
}
```

- 권한: Course `STUDENT`
- Session이 `LIVE`일 때만 허용한다.
- 성공: `200 OK`, 짧은 질문 문장 후보 목록
- 제안 문장을 실제 질문으로 자동 저장하지 않는다.
- 초안과 제안 보관 정책은 TBD이며 기본 제안은 미저장이다.

### 10.5 ‘나도 궁금해요’ 추가·취소

```http
PUT    /api/v1/questions/{question_id}/reaction
DELETE /api/v1/questions/{question_id}/reaction
```

- 권한: Course `STUDENT`
- Session이 `LIVE`일 때만 변경할 수 있다.
- 추가는 기존 반응이 있어도 `200 OK`를 반환한다.
- 취소는 기존 반응이 없어도 `204 No Content`를 반환한다.
- 자신이 작성한 질문에는 반응할 수 없다. 서버는 익명 표시와 별개로 이 규칙을 확인할 작성자 ID를 내부적으로 보관한다.

## 11. 교수자 답변 API

### 11.1 답변 목록

```http
GET /api/v1/sessions/{session_id}/answers?cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- 저장된 Answer를 `started_at ASC, id ASC` 순서로 반환한다.
- LIVE 재연결 시 질문 상태와 답변 연결을 REST로 복구하는 기준으로 사용한다.

### 11.2 답변 단건

```http
GET /api/v1/answers/{answer_id}
```

- 권한: Course 멤버
- 답변 상태, 대상 질문 snapshot과 Transcript 범위를 반환한다.
- 클러스터에서 시작한 Answer는 `source_cluster_id`와 선택 당시 대표 질문 문장을 그대로 보존한 `source_cluster_title_snapshot`을 반환한다. 직접 질문을 선택한 Answer에서는 두 필드가 모두 `null`이다.

### 11.3 답변 캡처 시작

```http
POST /api/v1/sessions/{session_id}/answers
Idempotency-Key: <key>
```

단일 질문 선택:

```json
{
  "target": {
    "type": "QUESTIONS",
    "question_ids": ["question_01HXYZ"]
  }
}
```

클러스터 선택:

```json
{
  "target": {
    "type": "CLUSTER",
    "cluster_id": "cluster_01HXYZ"
  }
}
```

- 권한: Course `PROFESSOR`
- Session이 `LIVE`일 때만 허용한다.
- 클러스터를 선택하면 선택 시점의 미답변 원본 질문과 대표 질문 문장의 정확한 text를 답변 대상으로 확정한다.
- 대상 질문을 `SELECTED`로 변경하고 선택 시점의 마지막 final sequence를 `capture_started_after_sequence`로 기록한다. 아직 final이 없으면 `0`이다.
- 실제 `start_sequence`는 선택 이후 처음 포함되는 final 구간이며 생성 전에는 `null`일 수 있다.
- 성공: `201 Created`, Answer 상태 `CAPTURING`
- Answer 상태와 클러스터 대상 스냅샷은 API 실행을 위한 초안 설계이다.

### 11.4 답변 완료

```http
POST /api/v1/answers/{answer_id}/complete
Idempotency-Key: <key>
```

교수자가 자동 후보를 그대로 확정하면 본문을 생략할 수 있다. 범위를 조정하면 다음 값을 보낸다.

```json
{
  "start_sequence": 110,
  "end_sequence": 128
}
```

- 권한: Course `PROFESSOR`
- 답변 시작 후 생성된 final Transcript 범위를 확정한다.
- 전달된 범위는 같은 Session에 속해야 하고 `start_sequence <= end_sequence`여야 한다.
- 확정할 final 구간이 하나도 없으면 `409 ANSWER_TRANSCRIPT_NOT_READY`를 반환한다.
- Answer를 `COMPLETED`, 연결된 질문을 `ANSWERED`로 변경한다.
- 재요청은 기존 완료 결과를 반환한다.
- 실시간 텍스트 답변의 MVP 포함 여부는 문서 간 차이가 있어 TBD이다.

### 11.5 답변 취소

```http
POST /api/v1/answers/{answer_id}/cancel
```

- 권한: Course `PROFESSOR`
- `CAPTURING`인 Answer를 `CANCELLED`로 변경하고 연결 질문을 `OPEN`으로 되돌린다.
- 답변 취소 기능은 복구 가능성을 위한 API 초안이며 제품 흐름 검토가 필요하다.

## 12. AI 요약 API

### 12.1 실시간 요약 요청

```http
POST /api/v1/sessions/{session_id}/summaries
Idempotency-Key: <key>
```

```json
{
  "summary_type": "LIVE",
  "range": {
    "start_sequence": null,
    "end_sequence": 128
  }
}
```

- 권한: Course 멤버. 실시간 UI는 학생 중심이지만 교수자 허용 여부는 TBD이다.
- `LIVE` Session에서 현재까지 또는 선택한 final Transcript 범위를 요약한다.
- 같은 Session에 연결되고 `READY`인 PDF 조각만 검색한다. `UPLOADED`, `PROCESSING`, `FAILED` 또는 분리된 자료는 제외한다.
- 성공: `202 Accepted`, AIJob 반환
- 완료 결과는 `summary.completed`와 요약 조회 API로 확인한다.

### 12.2 요약 조회

```http
GET /api/v1/sessions/{session_id}/summaries?summary_type=LIVE&cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- `summary_type`: `LIVE`, `FINAL`
- 성공한 `LIVE` 요약은 요청자 전용으로 반드시 저장하고, `FINAL` 요약은 Course 멤버에게 공개한다.
- Summary 저장이 완료돼 `result.resource_url`로 조회할 수 있을 때만 AIJob을 `SUCCEEDED`로 변경한다.
- 보관 기간이 끝나거나 사용자가 삭제하기 전까지 저장하며 구체 보관 기간·삭제 API는 개인정보 정책과 함께 확정한다.
- `FINAL`은 class 종료 후 생성된 강의 요약을 의미한다.

### 12.3 요약 단건 조회

```http
GET /api/v1/summaries/{summary_id}
```

- 저장된 `LIVE` 요약은 요청자만, `FINAL` 요약은 Course 멤버가 조회한다.
- AIJob의 `result.resource_url`이 이 경로를 가리킨다.

## 13. AI 채팅 API

### 13.1 대화 생성

```http
POST /api/v1/sessions/{session_id}/chats
```

```json
{
  "mode": "LIVE"
}
```

- 권한: Course 멤버. 교수자 사용 범위는 TBD이다.
- `mode`: `LIVE`, `REVIEW`
- `LIVE`는 진행 중 class, `REVIEW`는 정리 중·완료 class에서 사용하는 것을 초안으로 한다.
- 대화는 생성한 사용자 개인에게만 노출하는 것을 초안으로 한다.

### 13.2 대화 목록

```http
GET /api/v1/sessions/{session_id}/chats?cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- 현재 사용자가 생성한 대화만 반환한다.

### 13.3 대화 단건

```http
GET /api/v1/chats/{chat_id}
```

- 권한: 대화 소유자이면서 현재 Course 멤버인 사용자
- 다른 학생 또는 교수자의 개인 대화 존재를 공개하지 않는다.

### 13.4 메시지 전송

```http
POST /api/v1/chats/{chat_id}/messages
Idempotency-Key: <key>
```

```json
{
  "content": "음수 가중치가 있을 때는 어떤 알고리즘을 써야 해?"
}
```

- 권한: 대화 소유자이자 Course 멤버
- 서버는 같은 Session에 연결되고 `READY`인 PDF, final Transcript와 Q&A만 검색한다. `UPLOADED`, `PROCESSING`, `FAILED` 또는 분리된 자료는 제외한다.
- 근거가 부족하면 확인할 수 없음을 응답한다.
- 성공: `202 Accepted`, 사용자 Message와 AIJob 반환
- AI 토큰 스트리밍 방식은 TBD이다.

### 13.5 메시지 목록

```http
GET /api/v1/chats/{chat_id}/messages?cursor=<cursor>&limit=50
```

- 권한: 대화 소유자
- 정렬: `sequence ASC`
- Assistant Message는 사용자에게 안전한 근거 유형, 표시용 `label` snapshot, 권한 검사를 거치는 상대 링크 `resource_url`과 모델 정보를 포함할 수 있다.
- 분리된 Material 근거를 보존하면 `label` snapshot은 유지하고 `resource_url`은 `null`로 반환한다. 내부 chunk ID와 스토리지 키는 노출하지 않는다.

## 14. AI 작업 API

### 14.1 작업 조회

```http
GET /api/v1/jobs/{job_id}
```

- 권한: 작업의 Session에 접근 가능하고 해당 Job의 공개 범위에 포함되는 사용자
- 응답: 작업 유형, 상태, 진행률, 오류, 대상·결과 리소스 링크, 시작·종료 시각
- 오류 메시지는 민감한 입력과 외부 모델 응답 원문을 포함하지 않는다.

### 14.2 작업 재시도

```http
POST /api/v1/jobs/{job_id}/retry
Idempotency-Key: <key>
```

- 권한: 요청형 작업은 요청자, 공유 후처리 작업은 Course `PROFESSOR`를 초안으로 한다.
- `FAILED`인 작업만 재시도한다.
- `retryable=false`인 작업은 `409 AI_JOB_NOT_RETRYABLE`, `FAILED`가 아닌 작업은 `409 AI_JOB_STATE_CONFLICT`를 반환한다.
- 성공: `202 Accepted`, 같은 Job ID와 `attempt + 1`, `status=PENDING`인 Job을 반환한다.
- 현재 시도의 progress, error, `started_at`, `finished_at`은 `null`, `retryable`은 `false`로 초기화된다.
- 이전 attempt worker의 늦은 결과는 Job ID·attempt·실행 token·`RUNNING` 상태를 대조해 반영하지 않는다.

### 14.3 Session 공용 작업 목록

```http
GET /api/v1/sessions/{session_id}/jobs?job_type=<type>&status=<status>&cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- 자료 처리, 질문 클러스터링과 Session 후처리처럼 참여자가 상태를 알아야 하는 공용 Job만 반환한다. HQ STT Job의 공개 계약은 PR4에서 추가한다.
- 개인 LIVE 요약, 질문 초안과 Chat Job은 포함하지 않는다.
- 질문 클러스터링 실패를 재연결 후 발견하고 교수자가 재시도할 때 사용한다.

## 15. 수업 기록 API

### 15.1 통합 기록 조회

```http
GET /api/v1/sessions/{session_id}/record
```

- 권한: Course 멤버
- 허용 Session 상태: `PROCESSING`, `COMPLETED`
- 응답: Session, 권한에 따라 노출하는 안전한 Recording 메타데이터, 외부에서 연결된 자료 메타데이터, final Transcript, 최신 최종 요약, 질문·반응·클러스터·답변, 후처리 Job 상태
- `jobs`에는 자료 처리·Session 후처리 같은 공용 Job만 포함하고 개인 요약·질문 초안·Chat Job은 포함하지 않는다.
- 일부 AI 작업이 실패해도 연결된 PDF, Transcript와 Q&A는 반환한다. 분리된 자료는 즉시 제외한다.
- 응답 크기가 커지면 통합 API는 요약만 반환하고 세부 리소스 API로 분리한다.

### 15.2 녹음 메타데이터 조회

```http
GET /api/v1/sessions/{session_id}/recording
```

- 첫 성공 `audio.start` 전에는 Recording이 없고, 성공 뒤에는 Session당 외부에 정확히 하나의 논리 Recording aggregate를 만들고 `CAPTURING`으로 전이한다. 같은 `client_stream_id`의 reconnect는 이 Recording을 재사용한다.
- Recording은 브라우저 로컬 녹음과 upload·HQ STT·playback의 외부 상태를 나타낸다. 이 논리 cardinality는 DB row나 object storage cardinality를 확정하지 않는다. 물리 저장물이 파일 하나인지 여러 fragment·row와 manifest인지는 TBD이며 외부 API에 노출하지 않는다.
- 응답은 `id`, `session_id`, 공개 상태, `version`, nullable `content_type`·`byte_size`·`duration_ms`·`playback_url`과 생성·갱신 시각만 포함한다. storage key, 서버 경로, fragment key와 manifest는 포함하지 않는다.
- 모든 조회에서 현재 인증과 Course 접근 권한을 다시 확인한다. 녹음 동의와 교수자·학생별 세부 접근 범위는 TBD이다.
- Recording이 없거나 존재를 공개하지 않으면 `404 RECORDING_NOT_FOUND`를 반환한다.

| 상태             | 의미                                                                |
| ---------------- | ------------------------------------------------------------------- |
| `CAPTURING`      | 첫 publisher가 같은 microphone source로 live PCM과 로컬 녹음을 생성 |
| `UPLOAD_PENDING` | Session 종료 후 로컬 녹음 upload 시작을 기다림                      |
| `UPLOADING`      | resumable upload가 진행 중                                          |
| `UPLOADED`       | 논리 녹음 upload가 완결되어 playback과 HQ STT 시작이 가능           |
| `FAILED`         | capture·upload·storage 검증 중 하나가 실패한 terminal 상태          |

### 15.3 resumable upload 초기화

```http
POST /api/v1/sessions/{session_id}/recording/uploads
Idempotency-Key: <key>
Content-Type: application/json
```

```json
{
  "client_stream_id": "stable-client-stream-id",
  "content_type": "audio/format-tbd",
  "total_bytes": 12345678,
  "duration_ms": 3600000
}
```

- 15.3~15.5절의 init·offset 조회·chunk·complete operation은 모두 provisional 초안이다. resource lifecycle과 오류 의미를 연결하지만 미정인 wire 세부를 규범 계약으로 간주하지 않는다.
- `Idempotency-Key`는 필수이며 같은 요청의 재실행은 기존 upload를 반환한다.
- 첫 publisher와 같은 `client_stream_id`를 사용하는 Course `PROFESSOR`만 초기화할 수 있다.
- Session은 `PROCESSING`, Recording은 `UPLOAD_PENDING`이어야 한다. 아니면 `409 RECORDING_STATE_CONFLICT`를 반환한다.
- 이미 다른 active upload가 있으면 `409 RECORDING_UPLOAD_CONFLICT`를 반환한다.
- 성공: `201 Created`. Recording을 `UPLOADING`으로 바꾸고 불투명 upload ID, 현재 byte offset, 전체 byte 수와 만료 시각을 반환한다.
- codec·container와 허용 `content_type`, 브라우저 로컬 저장 방식, 최대 크기와 정확한 expiry 값은 TBD이다.

### 15.4 upload offset 조회와 chunk 전송

```http
GET /api/v1/recording-uploads/{upload_id}
PATCH /api/v1/recording-uploads/{upload_id}
```

- 위 `GET`과 `PATCH`는 resource와 오류 형태를 연결하기 위한 비규범적 protocol 초안이다. offset 조회를 `GET` 또는 `HEAD`로 할지, chunk method·offset header·request Content-Type·응답 status·chunk 크기는 TBD이다.
- offset 조회는 최소한 upload ID, 상태, `offset_bytes`, `total_bytes`, `expires_at`을 반환해야 한다.
- chunk 요청은 서버가 확인한 현재 byte offset에서만 이어 쓴다. 다른 offset이면 `409 UPLOAD_OFFSET_MISMATCH`와 안전한 현재 offset을 반환한다.
- upload가 없거나 존재를 공개하지 않으면 `404 RECORDING_UPLOAD_NOT_FOUND`, 만료됐으면 `410 RECORDING_UPLOAD_EXPIRED`를 반환한다.
- codec·container 검증에 실패하면 `415 UNSUPPORTED_RECORDING_FORMAT`을 반환한다. 검사 시점과 지원 형식은 TBD이다.
- 각 요청은 인증, Course 권한과 최초 publisher 연결을 다시 검증한다. 내부 임시 경로와 storage key는 반환하거나 로그에 남기지 않는다.

RecordingUpload의 공개 상태는 `ACTIVE`, `COMPLETED`, `EXPIRED`, `FAILED`이다. 정확한 expiry 값, 만료·실패 후 Recording 전이와 새 upload 재시작 정책은 TBD이다.

### 15.5 upload 완료

```http
POST /api/v1/recording-uploads/{upload_id}/complete
Idempotency-Key: <key>
```

- `Idempotency-Key`는 필수이다. 동일 요청은 최초 응답을 재사용하고 새 Job을 중복 생성하지 않는다.
- 서버가 전체 byte 수와 선택된 checksum 규칙을 만족하는지 확인한 뒤 논리 Recording을 `UPLOADED`로 확정한다.
- 같은 transaction에서 Recording을 `UPLOADED`로 확정하고 HQ STT 시작을 요청한다. HQ STT의 구체 Job type·응답·상태와 Transcript 결과 계약은 PR4에서 확정한다.
- 성공: `202 Accepted`, `UPLOADED` Recording을 반환한다.
- checksum 불일치는 `RECORDING_CHECKSUM_MISMATCH`를 사용한다. checksum algorithm, 전달 위치, 검증 시점과 HTTP status는 TBD이다.
- HQ Transcript generation·canonical 교체·timeout, Answer 재매핑과 Segment recording offset 스키마는 PR4 범위다.

### 15.6 녹음 playback

```http
GET /api/v1/recordings/{recording_id}/playback
Range: bytes=<start>-<end>
```

- 요청마다 현재 인증, Course 접근과 향후 녹음 접근 정책을 다시 검증한다.
- `UPLOADED` Recording만 재생할 수 있다. 그 전에는 `409 RECORDING_NOT_READY`, 없거나 비가시면 `404 RECORDING_NOT_FOUND`를 반환한다.
- 전체 재생은 `200 OK`, 유효한 byte Range 재생은 `206 Partial Content`를 사용한다. 범위가 유효하지 않으면 `416 RANGE_NOT_SATISFIABLE`을 반환한다.
- proxy streaming과 권한 확인 뒤 짧은 opaque signed delivery URL로 redirect하는 방식은 TBD이다. 어느 방식이든 내부 storage key와 서버 경로를 외부에 노출하지 않는다.
- 응답 MIME은 codec·container 결정 후 확정한다. 이번 범위에는 별도 녹음 다운로드 API와 Transcript 문장 seek offset을 추가하지 않는다.

## 16. WebSocket과 음성 스트리밍

스트리밍 STT는 MVP 필수 기능이다. OpenAPI 3.1은 WebSocket 양방향 메시지 계약을 표준적으로 표현하지 못하므로 이 장을 실시간 계약의 기준으로 사용하고, `openapi.yaml`의 `x-websocket-channels`는 구현 참고용 비표준 확장으로 취급한다. 계약이 안정되면 AsyncAPI 분리를 검토한다.

가장 중요한 원칙은 다음과 같다.

> WebSocket과 개인 AI 스트림은 알림·스트리밍 전송 수단이고, DB와 REST 조회 결과가 최종 진실이다. 연결이 끊겨도 REST로 저장 결과를 복구할 수 있어야 한다.

### 16.1 전송 경계

| 전송 경로                                   | 방향                   | 사용자             | 책임                                                    |
| ------------------------------------------- | ---------------------- | ------------------ | ------------------------------------------------------- |
| `WS /api/v1/ws/sessions/{session_id}`       | 주로 서버 → 클라이언트 | Course 멤버        | Transcript, 질문, 반응, 답변과 Session의 공용 변경 알림 |
| `WS /api/v1/ws/sessions/{session_id}/audio` | 양방향                 | Course `PROFESSOR` | 저지연 PCM 전송과 ack·backpressure·resume 제어          |
| 개인 AI 스트림 경로 TBD                     | 서버 → 요청자          | AI 요청자          | 개인 요약·채팅의 delta와 완료 알림                      |

- 질문 생성, 반응, 답변과 Session 상태 변경 같은 비즈니스 명령은 REST API로 수행한다.
- Session event WS와 audio WS는 별도 연결·티켓·책임을 유지한다. event WS로 audio frame이나 upload chunk를 보내지 않고 audio WS로 Session 공용 event를 broadcast하지 않는다.
- 첫 publisher의 같은 microphone source를 `PCM_S16LE` 16 kHz mono 500 ms live 경로와 브라우저 로컬 binary 녹음 경로로 동시에 분기한다. 로컬 녹음은 Session 종료 뒤 15.3~15.5절의 HTTP upload로 전송한다.
- 일반 Session 채널에 교수자 음성 원본을 broadcast하지 않는다.
- 개인 요약과 AI 채팅 결과를 Session 공용 채널에 broadcast하지 않는다.
- 개인 AI 스트림은 streaming HTTP 또는 SSE를 권장한다. MVP에서 polling만 구현해도 완료 결과는 Job과 리소스 REST API로 복구할 수 있어야 한다.

### 16.2 인증과 연결 권한

- Session 이벤트 채널: 해당 Session의 Course 멤버
- 음성 채널: 해당 Session의 Course `PROFESSOR`이면서 Session 상태가 `LIVE`
- 첫 성공 `audio.start`의 `client_stream_id`가 LIVE Session의 publisher를 claim한다. claim과 Recording `CAPTURING` 전이는 원자적으로 처리한다.
- 이미 claim된 Session에 다른 `client_stream_id`가 `audio.start`를 보내면 `AUDIO_PUBLISHER_CONFLICT`를 전송하고 WebSocket close code `4409`로 그 연결을 종료한다. active publisher의 식별정보는 오류에 포함하지 않는다.
- 동일한 `client_stream_id`는 새 1회용 ticket으로 네트워크 reconnect와 sequence resume을 시도할 수 있다. 비정상 단절의 lease 만료, 재획득과 명시적 takeover는 TBD이다.
- 연결 시점뿐 아니라 재연결과 권한 변경 시점에도 멤버십을 다시 확인한다.
- 브라우저 WebSocket은 임의의 `Authorization` 헤더를 설정하기 어렵기 때문에 MVP는 단기·1회용 티켓 방식을 사용한다.

```http
POST /api/v1/realtime-tickets
```

```json
{
  "session_id": "session_01HXYZ",
  "scope": "SESSION_AUDIO_WRITE"
}
```

```json
{
  "ticket": "single-use-secret",
  "session_id": "session_01HXYZ",
  "scope": "SESSION_AUDIO_WRITE",
  "expires_at": "2026-07-11T01:31:00Z"
}
```

- scope는 `SESSION_EVENTS_READ`, `SESSION_AUDIO_WRITE` 중 하나다.
- Session 이벤트 재연결은 티켓 요청의 `resume_cursor`에 마지막 event cursor를 넣는다. 신규 연결과 audio scope에서는 생략한다.
- 티켓은 발급 후 60초 안에 한 번만 해당 Session과 scope의 WebSocket upgrade에 사용할 수 있다.
- 서버는 티켓 원문 대신 hash와 사용·만료 상태만 저장한다.
- `SESSION_AUDIO_WRITE`는 발급 시점에 Course `PROFESSOR`이고 Session이 `LIVE`여야 한다.
- 연결은 `?ticket=<one-time-ticket>`을 사용하며 서버·프록시는 query와 티켓 응답을 반드시 마스킹하고 캐시하지 않는다.
- access token은 WebSocket URL에 직접 넣지 않는다.
- 티켓을 소모한 뒤 재연결하려면 정상 HTTP 인증으로 새 티켓을 발급받는다.

### 16.3 공통 서버 이벤트 envelope

```json
{
  "schema_version": 1,
  "event_id": "evt_01HXYZ",
  "type": "transcript.final",
  "session_id": "session_01HXYZ",
  "cursor": "opaque_resume_cursor",
  "resource_version": 14,
  "correlation_id": "req_or_job_01HXYZ",
  "occurred_at": "2026-07-11T01:30:00Z",
  "data": {}
}
```

| 필드               | 필수 | 설명                                                        |
| ------------------ | ---: | ----------------------------------------------------------- |
| `schema_version`   |    Y | 이벤트 envelope 버전. 초안은 `1`                            |
| `event_id`         |    Y | 중복 수신 제거용 불투명 ID                                  |
| `type`             |    Y | 이벤트 종류                                                 |
| `session_id`       |    Y | 이벤트 범위 Session                                         |
| `cursor`           |    Y | best-effort 재생용 불투명 커서. 미지원 시 `null`            |
| `resource_version` |    Y | 리소스 최신 버전 비교용. 해당 없으면 `null`                 |
| `correlation_id`   |    Y | 원인이 된 HTTP request ID 또는 AIJob ID. 해당 없으면 `null` |
| `occurred_at`      |    Y | 서버 기준 UTC 발생 시각                                     |
| `data`             |    Y | 이벤트별 payload                                            |

- 전달은 at-least-once일 수 있다. 클라이언트는 `event_id`로 중복을 제거한다.
- 같은 리소스의 `resource_version`이 현재 값보다 작으면 오래된 갱신으로 보고 무시한다.
- `cursor`는 권한 필터 때문에 중간 값이 비어 보일 수 있으므로 연속 정수로 해석하지 않는다.
- 익명 질문 이벤트에 작성자 ID, 이름, 이메일을 포함하지 않는다.

### 16.4 Session 이벤트

| 이벤트               | 주요 `data`                                                            | 공개 범위                          |
| -------------------- | ---------------------------------------------------------------------- | ---------------------------------- |
| `connection.ready`   | connection_id, role, server_time, heartbeat_interval_ms, resume_status | 연결 사용자                        |
| `resync.required`    | reason, resources                                                      | 연결 사용자                        |
| `transcript.partial` | 임시 utterance와 revision                                              | Course 멤버                        |
| `transcript.final`   | 저장된 TranscriptSegment                                               | Course 멤버                        |
| `transcript.status`  | STT 상태, last_final_sequence, 선택적 lag_ms                           | Course 멤버                        |
| `question.created`   | 익명 Question                                                          | Course 멤버                        |
| `question.updated`   | 익명 Question                                                          | Course 멤버                        |
| `reaction.updated`   | question_id, reaction_count                                            | Course 멤버                        |
| `answer.updated`     | Answer                                                                 | Course 멤버                        |
| `session.updated`    | LectureSession                                                         | Course 멤버                        |
| `recording.updated`  | 안전한 SessionRecording 메타데이터                                     | 녹음 접근 정책이 허용한 사용자     |
| `job.updated`        | AIJob                                                                  | 공용 자료·후처리 Job의 허용 사용자 |

개인 LIVE 요약, 질문 작성 초안과 Chat Job은 공용 `job.updated`로 노출하지 않고 요청자 전용 polling 또는 스트림에서만 전달한다.
Protocol 오류는 공통 event envelope 밖의 `error` control message로 연결 사용자에게만 보낸다.

연결 완료 envelope에서 `type`과 `data`만 발췌한 예시:

```json
{
  "type": "connection.ready",
  "data": {
    "connection_id": "conn_01HXYZ",
    "role": "STUDENT",
    "server_time": "2026-07-11T01:30:00Z",
    "heartbeat_interval_ms": 20000,
    "resume_status": "FRESH"
  }
}
```

`resume_status` 후보는 `FRESH`, `REPLAYED`, `RESYNC_REQUIRED`이다. MVP heartbeat 간격은 20초로 두고 서버가 `connection.ready`에서 전달한다.

### 16.5 partial·final Transcript payload

`transcript.partial`은 같은 utterance의 최신 인식 결과를 덮어쓰는 일시 데이터다.

```json
{
  "utterance_id": "utt_01HXYZ",
  "revision": 4,
  "audio_sequence_start": 120,
  "audio_sequence_end": 132,
  "start_ms": 41000,
  "end_ms": 44750,
  "text": "다익스트라 알고리즘은"
}
```

- DB에 저장하거나 재연결 시 재생하지 않는다.
- 클라이언트는 `utterance_id`를 key로 사용하고 더 큰 `revision`만 반영한다.
- `audio_sequence`와 저장 Transcript의 `sequence`를 혼용하지 않는다.

`transcript.final`은 DB commit 후에만 전파한다.

```json
{
  "utterance_id": "utt_01HXYZ",
  "segment": {
    "id": "segment_01HXYZ",
    "session_id": "session_01HXYZ",
    "sequence": 38,
    "start_ms": 41000,
    "end_ms": 45200,
    "text": "다익스트라 알고리즘은 음수 가중치를 허용하지 않습니다.",
    "created_at": "2026-07-11T01:30:00Z"
  }
}
```

- final을 받으면 같은 `utterance_id`의 partial 표시를 제거한다.
- 저장 실패 시 final 이벤트를 보내지 않는다.
- Session 종료 직후 상태가 먼저 `PROCESSING`으로 바뀌고 STT drain 과정의 final 이벤트가 더 올 수 있다. `transcript.status=FINALIZED` 전에는 final 생성이 끝났다고 가정하지 않는다.

STT 상태 후보는 `LISTENING`, `DEGRADED`, `FINALIZING`, `FINALIZED`, `STOPPED`이다.

### 16.6 재연결과 누락 복구

1. 클라이언트는 최근 event `cursor`, 리소스 버전과 마지막 final Transcript `sequence`를 메모리에 보관한다.
2. 연결이 끊기면 0, 1, 2, 5, 10, 30초 상한과 jitter를 둔 backoff로 재연결한다.
3. `POST /realtime-tickets` 요청의 `resume_cursor`에 최근 cursor를 넣어 새 티켓을 발급하고 연결한다.
4. 서버가 짧은 버퍼에서 재생할 수 있으면 현재 권한으로 필터한 이벤트를 재전달한다.
5. 커서가 만료됐거나 서버 재시작으로 재생할 수 없으면 `resync.required`를 보낸다.
6. 클라이언트는 `Session → Recording → final Transcript → Questions/Answers → 본인의 Jobs/Chats` 순서로 REST를 다시 조회한다.

partial Transcript는 복구 대상이 아니다. 재연결할 때 기존 partial 표시를 제거하고 다음 partial 또는 final을 기다린다. Redis나 영구 event log를 MVP 필수로 확정하지 않았으므로 이벤트 replay는 best-effort이고 REST 복구가 필수다.

서버는 20초마다 WebSocket ping을 보내고 연속 두 번 pong을 확인하지 못하면 연결을 종료한다. 애플리케이션 JSON heartbeat를 별도로 중복 전송하지 않는다.

### 16.7 음성 업로드 흐름

음성 WebSocket 연결 후 다음 순서를 사용한다.

1. 클라이언트가 JSON `audio.start`를 보낸다.
2. 서버가 첫 `client_stream_id`를 publisher로 claim하고 논리 Recording을 `CAPTURING`으로 만든다. 다른 stream의 경쟁 요청은 `AUDIO_PUBLISHER_CONFLICT`와 `4409`로 거부한다.
3. 서버가 Recording ID, claim 결과, 협상 형식과 전송 한도를 담은 `audio.ready`를 반환한다.
4. 클라이언트는 같은 microphone source를 live PCM 경로와 브라우저 로컬 녹음 경로로 분기하고, live 경로에서 sequence가 포함된 binary audio chunk를 전송한다.
5. 서버가 주기적으로 `audio.ack`와 필요 시 flow control을 보낸다.
6. 교수자가 class를 종료하면 클라이언트가 `audio.stop`을 보내고 로컬 녹음을 확정하며, 서버는 live 큐를 drain한다.
7. 마지막 live final Transcript 저장 후 서버가 `audio.stopped`와 `transcript.status=FINALIZED`를 보낸다.
8. 클라이언트가 class 종료 HTTP를 호출한 뒤 Recording resumable upload를 시작한다.

MVP v1 오디오 전송 형식은 `PCM_S16LE`, 16 kHz, mono, 500 ms chunk로 고정한다. STT 모델 어댑터가 필요하면 서버 내부에서 변환하며 wire format을 변경하려면 protocol version을 올린다.

```json
{
  "type": "audio.start",
  "request_id": "req_audio_01HXYZ",
  "data": {
    "client_stream_id": "stable-client-stream-id",
    "format": {
      "encoding": "PCM_S16LE",
      "sample_rate_hz": 16000,
      "channels": 1
    },
    "chunk_duration_ms": 500,
    "resume_from_sequence": null
  }
}
```

```json
{
  "type": "audio.ready",
  "stream_id": "stream_01HXYZ",
  "recording_id": "recording_01HXYZ",
  "publisher_status": "CLAIMED",
  "accepted_format": {
    "encoding": "PCM_S16LE",
    "sample_rate_hz": 16000,
    "channels": 1
  },
  "max_chunk_bytes": 32768,
  "max_in_flight": 10,
  "last_received_sequence": null,
  "last_processed_sequence": null
}
```

`audio.ack` 예시:

```json
{
  "type": "audio.ack",
  "received_through": 132,
  "processed_through": 128,
  "queue_depth_ms": 1700
}
```

binary frame은 14-byte header와 audio payload로 구성한다. header의 정수는 network byte order(big-endian), payload sample은 `PCM_S16LE`이다.

```text
1 byte protocol_version
1 byte flags (MVP v1은 0으로 고정)
4 bytes uint32 chunk_sequence
8 bytes uint64 captured_offset_ms
remaining bytes PCM_S16LE 16000 Hz mono payload
```

- `protocol_version`은 `1`, 기본 payload는 500 ms 분량인 16,000 bytes이고 전체 frame은 16,014 bytes다. `audio.ready.max_chunk_bytes`는 header를 포함한 전체 frame 상한이다.
- `chunk_sequence`는 `client_stream_id`별 `0`부터 시작해 frame마다 1씩 증가한다. `captured_offset_ms`는 해당 client stream 시작 기준 단조 증가 시각이다.
- 클라이언트는 ack 전 최근 5초 audio를 ring buffer로 보관한다.
- 재연결 시 같은 `client_stream_id`를 사용하고 `resume_from_sequence`에는 마지막 `audio.ack.received_through`를 넣은 뒤 그 다음 sequence부터 재전송한다.
- 서버는 `(session_id, client_stream_id, chunk_sequence)`로 중복 chunk를 제거한다.
- 서버 상태가 사라져 live PCM resume을 할 수 없으면 `audio.resume_rejected`를 보내고 교수자 화면에 live Transcript gap을 알린다. 브라우저 로컬 녹음과 이후 HQ Transcript가 이 gap을 어떻게 보정하는지는 PR4에서 확정한다.
- 큐가 한도를 넘으면 `audio.flow_control` 또는 재시도 가능한 `AUDIO_BACKPRESSURE` 오류를 보내고 오래된 음성을 무한 적재하지 않는다.
- ack 주기, `max_in_flight`, 최대 queue와 `max_chunk_bytes`는 서버가 `audio.ready`에서 통지한다.
- audio WS의 PCM frame은 live STT 전송용이며 영구 녹음의 원본으로 취급하지 않는다. 영구 녹음은 같은 microphone source의 브라우저 로컬 branch를 15.3~15.5절로 upload해 저장한다.

교수자가 class 종료를 누르면 클라이언트는 `audio.stop`과 로컬 녹음 확정을 시작하고 `audio.stopped`를 기다린 뒤 HTTP 종료 API를 호출한다. 종료 API가 먼저 호출되거나 대기 timeout이 발생해도 서버는 Session을 즉시 `PROCESSING`으로 전환하고 새 binary frame·audio 연결·resume을 차단하며, 이미 받은 chunk만 drain한다. Recording은 `UPLOAD_PENDING`이 되고 upload complete 전에는 HQ STT를 시작하지 않는다. 연결 손실로 받지 못한 live chunk는 gap으로 기록해 교수자에게 표시한다.

녹음 또는 upload 중 tab 종료 warning과 로컬 데이터 유실 안내는 화면 책임이다. 브라우저 로컬 저장 방식과 warning 해제 조건은 TBD이며 WebSocket control message로 만들지 않는다.

### 16.8 개인 AI 결과 스트리밍

LIVE 요약과 Chat은 REST 요청을 `202 Accepted + AIJob`으로 수락하고, 완료 결과를 DB에 저장해 REST로 조회 가능하게 한다. 체감 지연을 낮추기 위한 delta 전송은 요청자 전용이어야 한다.

| 후보 이벤트              | data                                                                |
| ------------------------ | ------------------------------------------------------------------- |
| `job.updated`            | job_id, status, attempt, progress, error, updated_at                |
| `summary.delta`          | job_id, summary_id, chunk_index, delta, transcript_through_sequence |
| `summary.completed`      | job_id, 저장된 Summary                                              |
| `chat.message.started`   | job_id, chat_id, assistant_message_id, context_through_sequence     |
| `chat.message.delta`     | job_id, assistant_message_id, chunk_index, delta                    |
| `chat.message.completed` | job_id, 저장된 Assistant Message                                    |

- 생성 실패는 `job.updated`의 `FAILED`로 표현하고 별도 실패 이벤트를 중복 정의하지 않는다.
- `SUCCEEDED` Job은 `result.resource_type`, `result.resource_id`, `result.resource_url`로 생성 결과를 가리킨다. Summary와 Assistant Message도 원인 `job_id`를 보관한다.
- 스트림이 끊기면 `GET /jobs/{job_id}`의 `result`와 Summary·Chat REST API로 완료 상태를 복구한다.
- MVP는 같은 Chat에서 동시에 하나의 Assistant 생성 Job만 허용하며 진행 중 요청이 있으면 `409 CHAT_RESPONSE_IN_PROGRESS`를 반환한다.
- 스트리밍 HTTP, SSE 또는 요청자 target WebSocket 중 실제 전송 방식과 URL은 TBD이다.

### 16.9 실시간 오류와 종료 코드

복구 가능한 protocol·audio 오류는 다음 형식으로 보내고 가능하면 연결을 유지한다.

```json
{
  "type": "error",
  "code": "AUDIO_BACKPRESSURE",
  "message": "음성 처리 속도를 조절하고 있습니다.",
  "retryable": true,
  "request_id": "req_audio_01HXYZ"
}
```

| close code | 의미                                   |
| ---------: | -------------------------------------- |
|     `4400` | 잘못된 control message                 |
|     `4401` | 인증 또는 ticket 오류                  |
|     `4403` | Session 접근·역할 권한 없음            |
|     `4404` | Session 없음                           |
|     `4408` | 인증 또는 heartbeat timeout            |
|     `4409` | Session 상태 또는 audio publisher 충돌 |
|     `4429` | 연결·전송 rate limit                   |
|     `1011` | 서버 내부 오류                         |

주요 오류 코드는 `REALTIME_TICKET_EXPIRED`, `SESSION_ACCESS_DENIED`, `SESSION_NOT_LIVE`, `AUDIO_PUBLISHER_CONFLICT`, `UNSUPPORTED_AUDIO_FORMAT`, `AUDIO_CHUNK_TOO_LARGE`, `AUDIO_SEQUENCE_GAP`, `AUDIO_BACKPRESSURE`, `STT_UNAVAILABLE`, `RESYNC_REQUIRED`이다. AI 작업 실패는 Session WebSocket 연결 오류가 아니므로 Job을 `FAILED`로 변경하고 핵심 실시간 연결은 유지한다.

## 17. 기능–API 추적표

| 기능 ID               | 기능            | HTTP API                               | WebSocket                                     |
| --------------------- | --------------- | -------------------------------------- | --------------------------------------------- |
| AUTH                  | Google 로그인   | Auth start·callback·logout             | —                                             |
| PRE-T-01              | Course 생성     | `POST /courses`                        | —                                             |
| PRE-T-02              | 참여 코드 발급  | Course 생성·상세·참여 코드 회전        | —                                             |
| PRE-T-03              | class 관리      | class 생성·제목 수정·삭제              | —                                             |
| PRE-T-04              | PDF 관리        | Material 목록·업로드·열람·분리 API     | `job.updated`                                 |
| PRE-T-05              | class 시작      | `POST /sessions/{id}/start`            | `session.updated`                             |
| PRE-S-01              | 코드 참여       | `POST /courses/join`                   | —                                             |
| PRE-S-02              | class 확인      | `GET /courses/{id}/sessions`           | —                                             |
| PRE-S-03              | 진행 class 입장 | `GET /sessions/{id}`                   | Session WS                                    |
| LIVE_AUDIO_STREAM     | 교수자 STT·녹음 | realtime ticket, Recording upload API  | audio WS, `transcript.*`, `recording.updated` |
| LIVE-T-01 / LIVE-S-01 | Transcript      | `GET /sessions/{id}/transcript`        | `transcript.*`                                |
| LIVE-T-02 / LIVE-S-04 | 질문 확인       | `GET /sessions/{id}/questions`         | `question.*`                                  |
| LIVE-T-03             | 클러스터        | 질문 목록, `GET /sessions/{id}/jobs`   | `question.updated`, `job.updated`             |
| LIVE-T-04             | 인기 질문       | 질문 `sort=POPULAR`                    | `reaction.updated`                            |
| LIVE-T-05~07          | 답변 선택·완료  | Answer API                             | `answer.updated`                              |
| LIVE-T-08             | class 종료      | `POST /sessions/{id}/end`              | `session.updated`, `job.updated`              |
| LIVE-S-02 / LIVE-S-07 | 현재 요약       | Summary API                            | 요청자 전용 AI stream TBD                     |
| LIVE-S-03             | 익명 질문       | `POST /sessions/{id}/questions`        | `question.created`                            |
| LIVE-S-05             | 반응            | Reaction API                           | `reaction.updated`                            |
| LIVE-S-06 / LIVE-S-08 | 실시간 AI 채팅  | Chat API                               | 요청자 전용 AI stream TBD                     |
| LIVE-S-09             | 질문 작성 도움  | `POST /sessions/{id}/question-drafts`  | —                                             |
| POST-01~05            | 수업 기록       | record·Recording metadata·playback API | `recording.updated`, `job.updated`            |
| POST-06               | 복습 AI         | `mode=REVIEW` Chat API                 | `job.updated`                                 |
| POST-07               | 이전 class      | `GET /courses/{id}/sessions`           | —                                             |
| POST-08               | PDF 다시 보기   | Material API                           | —                                             |

## 18. 보안과 개인정보

- 익명 질문 API와 WebSocket은 작성자 ID, 이름, 이메일을 공개하지 않는다.
- 서버 로그에 인증 토큰, WebSocket 티켓, 참여 코드, 질문 원문과 프롬프트 원문을 남기지 않는다.
- AI 모델 입력에 학생의 실제 식별 정보를 포함하지 않는다.
- 모든 Material, Recording, RecordingUpload, Transcript, Question, Answer, Summary, Chat과 Job 접근은 현재 인증과 Course 접근 권한을 검증한다.
- 개인 요약·질문 초안·Chat 이벤트와 Job 상태는 Session 전체에 broadcast하지 않는다.
- PDF·녹음의 스토리지 키, 서버 파일 경로, fragment key·manifest와 Material의 `detached_at`은 외부 API에 노출하지 않는다.

## 19. 미정 사항

| 항목               | 현재 상태                                                                                                 | 결정 시 영향                 |
| ------------------ | --------------------------------------------------------------------------------------------------------- | ---------------------------- |
| ID 형식            | 불투명 string                                                                                             | OpenAPI `format`, DB PK      |
| class 자동 제목    | 정확한 문자열 형식·`READY` 시각 원장·timezone TBD                                                         | Session 생성·제목 수정 응답  |
| active Course 삭제 | active Session 보유 시 삭제·보관 방식 TBD                                                                 | Course 삭제 응답·트랜잭션    |
| Material 표시명    | suffix와 업로드 시 영구 확정은 결정; 허용 문자·Unicode 정규화·대소문자 충돌 비교 규칙 TBD                 | 업로드·목록·다운로드 파일명  |
| Material 분리 근거 | 안전한 label snapshot과 `resource_url=null` 방향만 확정; 정확한 근거 보관 기간·FK·`410 Gone` 정책 TBD     | Chat 근거·DB 삭제 정책       |
| 답변 형식          | MVP 텍스트 답변 여부 TBD                                                                                  | Answer 요청·응답             |
| 개인 AI 데이터     | 교수자 LIVE 사용·보관·삭제 TBD                                                                            | Summary·Chat 권한·수명       |
| AI 응답 전송       | 폴링·SSE·WebSocket TBD                                                                                    | Chat·Summary 응답            |
| 녹음 형식·저장     | codec·container·브라우저 로컬 저장·최대 크기, 물리 단일 파일 또는 fragment+manifest 구조 TBD              | upload 검증·storage·playback |
| 녹음 upload        | offset 조회 `GET`/`HEAD`, chunk method·header·Content-Type·크기, checksum algorithm·status, expiry 값 TBD | resumable protocol·정리      |
| 오디오 publisher   | 첫 `client_stream_id` claim과 동일 stream resume은 확정; 비정상 단절 lease·재획득·takeover TBD            | 중복 탭·장치 충돌            |
| 실시간 임계값      | `DEGRADED` 기준, audio stop timeout과 event replay window TBD                                             | 상태 표시·종료·재연결        |
| 녹음 정책·전달     | 동의, 역할별 접근, 보관·삭제와 playback proxy 또는 opaque signed URL 방식 TBD                             | 권한·개인정보·Range 전송     |
| HQ Transcript 연계 | generation·canonical 교체·HQ timeout·Answer 재매핑·Segment recording offset schema는 PR4에서 확정         | Transcript·Answer·AI 후처리  |
| 이벤트 재생        | event log 보존 여부 TBD                                                                                   | 재연결 프로토콜              |
| 개인 AI 스트림     | streaming HTTP·SSE·target WS TBD                                                                          | delta·재연결 계약            |
| 레이트 리미트      | 임계치 TBD                                                                                                | `429` 헤더·재시도            |

## 20. 검토 체크리스트

- [ ] Google callback의 state·nonce·PKCE와 session rotation 테스트가 있는가?
- [ ] WebSocket 티켓의 60초 만료·1회 사용·scope 검증 테스트가 있는가?
- [ ] 모든 MVP 기능 ID가 HTTP API 또는 WebSocket에 연결됐는가?
- [ ] 모든 상태 변경 API에 선행 상태와 `409` 규칙이 있는가?
- [ ] 익명 질문의 모든 응답·이벤트에서 작성자 식별자가 제거됐는가?
- [ ] LIVE Summary와 개인 Chat·Job이 요청자 외 사용자에게 노출되지 않는가?
- [ ] 리스트 API의 정렬과 커서 규칙이 일관되는가?
- [ ] `POST` 상태 변경과 AI 작업의 멱등성이 정의됐는가?
- [ ] AI 실패가 Course·Question·Transcript 핵심 기능을 차단하지 않는가?
- [ ] 종료 공용 Job이 모두 terminal이면 실패가 있어도 Session이 `COMPLETED`가 되는가?
- [ ] 첫 audio publisher claim·동일 stream resume·다른 stream `4409` 거부가 원자적인가?
- [ ] Recording upload·playback의 모든 응답과 로그에서 storage key·서버 경로·fragment 구성이 제거됐는가?
- [ ] `openapi.yaml`과 FastAPI `/openapi.json`의 자동 비교 방법이 있는가?
