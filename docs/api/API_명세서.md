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
- Google OAuth/OIDC 또는 이메일·비밀번호 인증 뒤 서버 세션을 만들고 HttpOnly Cookie로 인증한다.
- AI 요약과 채팅은 `202 Accepted + AIJob`으로 수락하고 개인 AI 상태와 결과는 요청자가 Job·Summary·Chat REST API를 polling해 확인한다.
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
- 7일은 Google callback 또는 이메일 가입·로그인에서 발급한 절대 만료다. 일반 요청은 `last_seen_at`만 최대 5분 간격으로 갱신하고 세션 수명을 자동 연장하지 않는다.
- 브라우저 JavaScript와 localStorage에 Google token·이메일 비밀번호 또는 서버 session ID를 저장하지 않는다.
- 서버에는 session ID의 hash, 사용자 ID, 만료와 폐기 시각만 보관한다. Google access token과 이메일 비밀번호 원문은 API 호출에 필요하지 않으며 저장하지 않는다.
- 상태 변경 요청은 설정된 allowlist와 `scheme://host[:port]`가 정확히 일치하는 `Origin`을 필수로 요구한다. `Origin` 누락, `null`, 사용자 정보·path가 포함된 값과 allowlist 불일치는 `403 ORIGIN_NOT_ALLOWED`로 거부한다.
- 서버는 요청 본문의 `user_id`를 신뢰하지 않는다.
- 현재 사용자는 인증 컨텍스트에서 확인한다.
- 사용자에게 전역 교수자·학생 역할을 부여하지 않는다.
- 권한은 요청 리소스가 속한 Course의 `PROFESSOR` 또는 `STUDENT` 멤버십으로 판단한다.
- 브라우저 WebSocket에는 access token을 직접 전달하지 않고 인증된 HTTP API가 발급한 60초 만료·1회용 티켓을 사용한다.

#### 2.2.1 인증 공통 규칙

- Google OAuth/OIDC와 이메일·비밀번호 로그인은 모두 같은 내부 `User`와 7일 절대 만료
  HttpOnly `goal_session` Cookie를 사용한다. 로그인 성공 시 기존 Cookie가 있으면 새 token으로
  회전한다.
- 이메일은 trim·NFKC·casefold로 정규화한 값을 대표 이메일·로그인 식별자로 사용하며, 활성 User
  사이에서 유일하다. Google과 이메일 계정은 이메일이 같아도 자동 연결하지 않는다.
- 비밀번호는 원문을 저장·응답·로그에 남기지 않고 scrypt salt hash만 저장한다. 이메일 소유 확인,
  비밀번호 재설정, 로그인 방식 연결과 애플리케이션 내부 rate limit은 별도 인증·메일 인프라를
  결정한 뒤 추가한다.

#### 2.2.2 Google 로그인 시작

```http
GET /api/v1/auth/google/start?return_to=/courses
```

- 서버는 state, nonce와 PKCE 검증 정보를 만들고 10분 만료 임시 `goal_oauth` Cookie를 설정한다.
- `return_to`는 `/`로 시작하되 `//`, scheme·host, 제어 문자와 `/api` 경로가 없는 Frontend 상대 경로만 받는다. 외부 URL과 Backend API 경로는 `400 INVALID_RETURN_TO`로 거부한다.
- 성공하면 Google 로그인 화면으로 `302 Redirect`한다.

#### 2.2.3 Google callback

```http
GET /api/v1/auth/google/callback?code=<code>&state=<state>
```

- state, nonce와 PKCE를 검증한 뒤 User를 생성 또는 갱신한다.
- OAuth transaction은 callback 검증 transaction에서 먼저 `consumed_at`을 기록한다. 같은 state 또는 임시 Cookie의 재사용은 provider 호출 전에 `400 INVALID_OAUTH_TRANSACTION`으로 거부한다.
- 기존 서버 세션이 있으면 session fixation을 막기 위해 새 session ID로 회전한다.
- 성공하면 `goal_session` Cookie를 설정하고 설정된 Frontend origin에 검증된 `return_to`를 결합해 `302 Redirect`한다.
- 사용자가 Google 동의를 취소하면 임시 transaction을 소비한 뒤 Frontend `/login?auth_error=cancelled&return_to=...`로 redirect한다.
- token 교환·OIDC 검증 provider 장애는 `503 DEPENDENCY_UNAVAILABLE`, state·nonce·PKCE 불일치는 `400 INVALID_OAUTH_TRANSACTION`으로 변환한다.
- Provider 오류 원문과 token을 응답 또는 로그에 남기지 않는다.
- 새 Google identity의 이메일이 기존 이메일·비밀번호 계정에 이미 연결돼 있으면 자동 계정 합침
  대신 `409 IDENTITY_EMAIL_CONFLICT`를 반환한다.

#### 2.2.4 이메일 계정 가입

```http
POST /api/v1/auth/email/register
Origin: <AUTH_ALLOWED_ORIGINS 중 하나>
Content-Type: application/json

{
  "display_name": "김도현",
  "email": "dohyun@example.com",
  "password": "12자 이상의 비밀번호"
}
```

- 표시 이름은 NFC·trim 뒤 1~~100자, 이메일은 정규화 뒤 유효한 3~~254자, 비밀번호는 12~128자로
  검증한다.
- 새 User와 하나의 `user_password_credentials` 행, 서버 Session을 같은 transaction으로 만들고
  `201`과 `{ "user": { ... } }`를 반환한다.
- 활성 User가 해당 이메일을 이미 사용하면 `409 EMAIL_ALREADY_REGISTERED`를 반환한다. Google
  계정과의 자동 연결·비밀번호 설정은 하지 않는다.
- 상태 변경 요청이므로 정확한 Origin이 없거나 맞지 않으면 `403 ORIGIN_NOT_ALLOWED`다.

#### 2.2.5 이메일·비밀번호 로그인

```http
POST /api/v1/auth/email/login
Origin: <AUTH_ALLOWED_ORIGINS 중 하나>
Content-Type: application/json

{
  "email": "dohyun@example.com",
  "password": "12자 이상의 비밀번호"
}
```

- 성공하면 새 `goal_session` Cookie와 `{ "user": { ... } }`를 반환한다.
- 이메일이 없거나 비밀번호가 틀린 경우를 구분하지 않고 모두 `401 INVALID_CREDENTIALS`로
  반환한다. 서버는 존재하지 않는 이메일에도 동일한 password hash 비용을 수행한다.
- 기존 Session Cookie가 있으면 로그인 성공 transaction에서 폐기하고 새 token을 발급한다.

#### 2.2.6 로그아웃

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

일반 목록 API는 기본적으로 다음 쿼리를 지원한다.

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
- 커서는 Session과 필터·정렬 조건, 마지막 항목의 정렬 키와 `id`를 고정하는 keyset cursor다. 다른 Session·필터·정렬과 함께 재사용하면 `400 INVALID_CURSOR`를 반환한다.
- 목록은 다른 설명이 없으면 기본 `limit=20`, 최대 `100`을 사용하고 동일 정렬 값의 마지막 tie-breaker로 `id`를 사용한다.

### 2.6 멱등성과 중복 제출

- `PUT` 반응 추가와 `DELETE` 반응 취소는 멱등적이다.
- class 종료, AI 작업 생성과 중복 제출 위험이 있는 `POST`는 `Idempotency-Key` 헤더를 지원한다.
- 서버는 정규화한 HTTP method·path·body로 `request_hash`를 계산한다.
- 같은 사용자·같은 경로·같은 키와 같은 `request_hash`의 재요청은 최초 응답의 HTTP status와 body를 그대로 반환한다.
- 동일 요청이 처리 중이면 중복 실행하지 않는다. `PROCESSING` lease는 최초 수락 또는 마지막 인계 뒤 60초이며 lease가 유효하면 `409 IDEMPOTENCY_REQUEST_IN_PROGRESS`를 반환한다. lease가 만료된 record만 새 요청이 소유해 복구할 수 있다. terminal 완료 후에는 저장된 응답을 재사용한다.
- 같은 키로 다른 `request_hash`를 보내면 `409 IDEMPOTENCY_KEY_REUSED`를 반환한다.
- terminal 완료 응답은 완료 시각부터 정확히 24시간 보관하고 재사용한다.
- 단, LIVE Summary 요청·`mode=LIVE` Chat 생성·메시지와 관련 `LIVE_SUMMARY`·LIVE-mode `CHAT_RESPONSE` Job 재시도의 멱등성 원장은 `purge_on_session_end=true`로 범위를 표시한다. `LIVE → PROCESSING` transaction은 개인 LIVE 리소스·Job을 삭제하고 느린 결과를 fence한 뒤, terminal 멱등성 행을 삭제하지 않고 encrypted 응답을 `410 LIVE_AI_RESULT_PURGED`로 재작성한다. 같은 키·같은 request hash만 남은 24시간 동안 이 `410`을 replay하며 새 키는 상태 검증에 따라 `409 SESSION_STATE_CONFLICT`다. class 종료 요청 자체의 멱등성 원장과 FINAL Summary·`mode=REVIEW` Chat·관련 Job 재시도는 이 범위에 포함하지 않는다.

### 2.7 요청 ID

클라이언트는 선택적으로 `X-Request-ID`를 보낼 수 있다. 서버는 영문 대소문자, 숫자, `.`, `_`, `-`만 사용한 1~128자 값을 수용한다. 값이 없거나 이 형식에 맞지 않으면 서버가 `req_` 접두사의 새 불투명 ID를 생성하고, 성공·오류 응답의 header와 오류 body에 같은 값을 반환한다. 이 값은 요청 추적용일 뿐 인증·권한에 사용하지 않는다.

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

|  HTTP | 의미                         | 주요 코드                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----: | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `400` | 요청 형식 오류               | `INVALID_REQUEST`, `INVALID_CURSOR`, `INVALID_RETURN_TO`, `INVALID_OAUTH_TRANSACTION`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `401` | 인증 필요                    | `AUTHENTICATION_REQUIRED`, `INVALID_SESSION`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `403` | Origin·Course·역할 권한 없음 | `ORIGIN_NOT_ALLOWED`, `COURSE_ACCESS_DENIED`, `ROLE_REQUIRED`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `404` | 리소스 없음                  | `RESOURCE_NOT_FOUND`, `MATERIAL_NOT_FOUND`, `RECORDING_NOT_FOUND`, `RECORDING_UPLOAD_NOT_FOUND`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `409` | 상태 전이·중복 충돌          | `SESSION_STATE_CONFLICT`, `ACTIVE_SESSION_EXISTS`, `IDEMPOTENCY_KEY_REUSED`, `IDEMPOTENCY_REQUEST_IN_PROGRESS`, `MEMBERSHIP_CONFLICT`, `AI_JOB_STATE_CONFLICT`, `AI_JOB_NOT_RETRYABLE`, `AI_JOB_RETRY_SYSTEM_MANAGED`, `MATERIAL_PROCESSING_ACTIVE`, `MATERIAL_LIMIT_EXCEEDED`, `MATERIAL_DELETE_CONFLICT`, `RECORDING_STATE_CONFLICT`, `RECORDING_UPLOAD_CONFLICT`, `UPLOAD_OFFSET_MISMATCH`, `RECORDING_NOT_READY`, `ANSWER_CAPTURE_ACTIVE`, `ANSWER_ALREADY_EXISTS`, `ANSWER_TRANSCRIPT_NOT_READY`, `SUMMARY_TRANSCRIPT_NOT_READY`, `SUMMARY_SOURCE_UNAVAILABLE`, `CHAT_RESPONSE_IN_PROGRESS` |
| `410` | upload 만료                  | `RECORDING_UPLOAD_EXPIRED`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `413` | 파일 크기 초과               | `FILE_TOO_LARGE`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `415` | 파일 형식 오류               | `UNSUPPORTED_MEDIA_TYPE`, `UNSUPPORTED_RECORDING_FORMAT`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `416` | playback 범위 오류           | `RANGE_NOT_SATISFIABLE`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `422` | 필드 검증 실패               | `VALIDATION_ERROR`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `429` | 요청 한도 초과               | `RATE_LIMITED`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `500` | 서버 오류                    | `INTERNAL_ERROR`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `503` | 의존 서비스 장애             | `DEPENDENCY_UNAVAILABLE`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |

녹음 checksum 불일치의 공개 오류 코드는 `RECORDING_CHECKSUM_MISMATCH`로 고정한다. chunk와 전체 object는 모두 lowercase hexadecimal SHA-256으로 검증하며, 불일치는 `422`를 반환하고 기존 upload bytes·offset은 유지한다.

#### 3.1.1 질문·초안·Chat USER 텍스트 검증

서버는 세 입력에 동일한 순서를 적용한다.

1. 앞뒤 공백을 제거한다.
2. Unicode NFC로 정규화한다.
3. 정규화 결과의 Unicode code point 수를 검증한다.

| 필드                 | 최대 code point |
| -------------------- | --------------: |
| 실제 질문 `content`  |           `300` |
| AI 질문 초안 `draft` |           `500` |
| Chat USER `content`  |         `2,000` |

- 정규화 결과가 0자이면 `422 VALIDATION_ERROR`, `details.reason=EMPTY_AFTER_NORMALIZATION`을 반환한다.
- 최대 길이를 넘으면 `422 VALIDATION_ERROR`, `details.reason=MAX_LENGTH_EXCEEDED`를 반환한다.
- `details`는 항상 `field`, `reason`, `max_length`, 정규화 후 code point 수인 `actual_length`를 포함한다.
- 서버는 초과 입력을 자르지 않고 대체 문자열도 반환하지 않는다. 클라이언트는 재입력을 위해 원본 입력을 유지한다.
- 저장 대상인 Question과 Chat USER Message의 `content`는 정규화 결과다. 초안은 영구 저장하지 않고 정규화 결과만 모델 입력으로 사용한다.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "입력 길이를 확인해 주세요.",
    "request_id": "req_01HXYZ",
    "details": {
      "field": "content",
      "reason": "MAX_LENGTH_EXCEEDED",
      "max_length": 2000,
      "actual_length": 2001
    }
  }
}
```

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
    "clustering": null,
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

- 현재 FastAPI 코드는 app factory와 `/api/health`, `/api/health/db` 상태 확인 API만 구현되어 있고 나머지 경로는 설계 계약이다.
- HTTP request ID middleware와 공통 exception handler는 구현됐다. `/api/health/db`의 PostgreSQL 장애, FastAPI validation 오류, framework HTTP 오류와 예상 밖 오류는 모두 본 문서의 `error` envelope로 반환하며 내부 예외 원문을 노출하지 않는다. 비즈니스 API는 이후 PR에서 이 handler에 `ApiError` 기반의 세부 오류 코드를 추가한다.
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
- Course 멤버인 `PROFESSOR`와 `STUDENT`는 동일한 개인 AI 권한을 갖는다. 두 역할 모두 `LIVE` Session에서 LIVE Summary·LIVE Chat을, `COMPLETED` Session에서 REVIEW Chat을 사용할 수 있다.

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
- Session 종료 transaction은 `SESSION_POSTPROCESSING`을 `PENDING`, `visibility=SHARED`, `blocks_session_completion=true`인 coordinator Job으로 먼저 생성한다. Recording이 있으면 upload·HQ source가 terminal이 될 때까지, 없으면 LIVE Transcript drain이 terminal이 될 때까지 worker가 이 Job을 claim하지 않는다.
- 첫 `audio.start`로 Recording이 생긴 Session은 Recording이 `UPLOAD_PENDING` 또는 `UPLOADING`인 동안 `PROCESSING`을 유지한다. upload complete는 `RECORDING_TRANSCRIPTION` Job과 `source=RECORDING`, `status=FINALIZING`인 Transcript version을 함께 만든다.
- `RECORDING_TRANSCRIPTION`은 `visibility=SHARED`, `blocks_session_completion=true`이다. 이 Job은 Segment·Gap과 Segment의 녹음 시간 mapping을 저장하고 정상 HQ version의 canonical 전환을 먼저 commit한다. 그 뒤 `SESSION_POSTPROCESSING`이 Answer mapping과 Knowledge 연결을 수행한다.
- Answer mapping 또는 Knowledge 재연결이 실패하면 `SESSION_POSTPROCESSING`만 `FAILED`로 격리한다. 이미 확정한 HQ Transcript·canonical을 되돌리지 않고 Answer의 원본 LIVE 범위를 보존한다.
- coordinator는 완료된 `VOICE` Answer마다 `ANSWER_ORGANIZATION`, `SHARED`, `blocks_session_completion=true` Job을 하나 만든다. 성공한 HQ mapping 범위를 우선하고, 없거나 실패했으면 Answer의 immutable 원본 LIVE 범위를 입력으로 고정한다. AI 정리 결과는 교수자가 작성한 `text_content`와 분리 저장하며 어느 attempt도 교수자 text를 덮어쓰지 않는다.
- HQ STT 실패나 timeout으로 Job과 최신 Transcript version이 `FAILED`여도 모든 blocking Job이 terminal이면 Session은 `COMPLETED`로 전환한다. class 시작 때 설정한 LIVE canonical 포인터는 그대로 보존하되, 이 LIVE version을 완료 기록의 final source로 인정해 Summary 등에 사용할지는 TBD이다.
- HQ가 `FINALIZED`, `EMPTY`, `FAILED` 중 어떤 terminal이든 coordinator를 깨운다. Recording source가 없으면 LIVE drain terminal 후 coordinator를 깨우되, 보존 LIVE canonical을 자동 최종 요약 source로 사용하지 않는다. coordinator는 가능한 Answer mapping·Knowledge 재연결을 처리하고, 자신의 terminal 전이·적용 가능한 downstream blocking Job 생성·outbox를 같은 transaction에 commit한다.
- `FINAL_SUMMARY`는 최신 HQ source가 `source=RECORDING`, `status=FINALIZED`, final Segment 1건 이상일 때만 자동 생성한다. RECORDING `EMPTY`면 Job 없이 `NO_FINAL_TRANSCRIPT`를 확정한다. Recording source가 처음부터 없으면 LIVE drain terminal 직후, Recording은 있지만 HQ가 `FAILED`이거나 `ended_at + 10분`까지 결과가 없으면 해당 시점에 Job 없이 `SUMMARY_SOURCE_UNAVAILABLE`을 확정한다. 종료 transaction에서 이미 만든 독립 가능한 최종 clustering은 계속 실행한다.
- Session 완료 조건은 coordinator terminal transaction이 child blocking Job을 등록한 뒤에만 재평가한다. 따라서 coordinator를 먼저 terminal로 관찰한 순간 새 child가 늦게 생기는 조기 `COMPLETED` race를 허용하지 않는다.
- `RUNNING` Job worker는 15초마다 내부 heartbeat로 lease를 갱신한다. 60초 동안 갱신되지 않은 lease는 watchdog이 해당 Job을 `FAILED`로 전환한다. 이는 16절의 20초 WebSocket ping과 별개인 worker 종료 관찰 계약이다.
- `RECORDING_TRANSCRIPTION`을 제외한 일반 후처리 Job의 기본 실행 상한은 `started_at + 5분`이다. HQ STT `RECORDING_TRANSCRIPTION` 개별 Job timeout은 이 기본값에서 제외하며 정확한 상한은 TBD이다. 이와 무관하게 Session 전체 상한은 `ended_at + 10분`으로 유지한다. 이 시점에 watchdog은 Session과 coordinator를 잠근 뒤, coordinator를 terminal로 바꾸기 전에 아직 생성하지 않은 적용 가능한 downstream blocking Job을 `status=FAILED`, `retryable=true`, `started_at=null`, `finished_at=now`, `error.code=SESSION_PROCESSING_TIMEOUT`으로 생성하고 outbox를 남긴다. 누락된 FINAL clustering을 합성할 때는 `input_through_sequence=requested_sequence`, `base_revision=current_revision`, `final_answered_through_at=lecture_sessions.ended_at`으로 원래 종료 상한을 복원한다. 단, 생성 자격이 확정된 RECORDING `FINALIZED` source의 누락 `FINAL_SUMMARY` Job은 합성하지 않고 원장 무결성 오류로 분류한다.
- 같은 watchdog transaction에서 RECORDING `FINALIZED`·final Segment 1건 이상인데 `FINAL_SUMMARY` Job이 없으면 Final Summary 상태를 `DATA_INTEGRITY_ERROR`, `reason=null`로 기록하고 Job은 합성하지 않는다. RECORDING `EMPTY`면 `NO_FINAL_TRANSCRIPT`, HQ 결과·Recording source가 없거나 `FAILED`면 `SUMMARY_SOURCE_UNAVAILABLE`을 기록한 뒤 coordinator·남은 Recording·upload gate·blocking Job을 `FAILED` terminal로 바꾼다. 그 후에만 실패와 무결성 상태를 포함해 모든 gate가 terminal인지 재평가해 Session을 `COMPLETED`로 전환한다.
- `SESSION_POSTPROCESSING`의 성공은 Answer mapping·Knowledge 재연결과 downstream Job 예약이 끝났다는 뜻이며 `FINAL_SUMMARY`·`QUESTION_CLUSTERING`의 성공까지 의미하지 않는다.
- `ANSWER_ORGANIZATION`도 다른 blocking Job과 마찬가지로 `SUCCEEDED|FAILED` terminal이면 완료 판정을 막지 않는다. 실패 결과는 Answer별로 표시하고 같은 Job 행의 `attempt + 1`로 나중에 재시도하며 Session을 `PROCESSING`으로 되돌리지 않는다. 10분 watchdog은 적용 대상 Answer에 Job이 아직 없으면 `SESSION_PROCESSING_TIMEOUT` 실패 Job을 먼저 합성한다.
- `COMPLETED` 후 실패한 `RECORDING_TRANSCRIPTION`을 재시도해도 같은 Job 행의 `attempt + 1`과 새 `RECORDING` Transcript version을 사용한다. 이 재시도가 성공하면 같은 `SESSION_POSTPROCESSING` coordinator 행을 `attempt + 1`로 자동 requeue하고 Session 상태와 `completed_at`은 유지한다. 복구 coordinator는 새 canonical HQ version에 대한 Answer mapping과 canonical Knowledge 연결을 멱등 재조정하고, 새로 자격을 얻었지만 아직 없는 `FINAL_SUMMARY` Job을 생성한다. 기존 `ANSWER_ORGANIZATION` Job·결과의 immutable source를 바꾸거나 자동 재생성하지 않는다.
- Session 종료 transaction은 active 또는 `retry_job_id`에 예약된 LIVE `QUESTION_CLUSTERING` 실행·재시도를 Session·attempt·run token fence로 정지하고 느린 결과 commit을 거부한다. 이 LIVE Job은 같은 종료 transaction에서 만드는 FINAL clustering Job이 입력을 대체하므로 `SUPERSEDED`, `retryable=false`로 terminal 처리한다. 같은 종료 transaction은 FINAL 대상이 1건 이상이면 종료 시점 `requested_through_sequence`와 `ended_at`을 각각 학생 질문·완료 Answer 대표질문의 최초 attempt input 상한으로 저장한 `FINAL` clustering Job을 `SHARED`, `blocks_session_completion=true`로 즉시 생성한다. FINAL Job은 Recording upload·HQ Transcript·coordinator를 기다리지 않고 독립 실행한다. 학생 질문 상한은 모든 attempt에서 유지하고, 실패한 FINAL을 교수가 명시적으로 재시도할 때만 `base_revision`과 Answer 시각 상한을 현재 값으로 다시 캡처한다. 대표질문은 현재 중앙인지 과거 child인지와 무관하게 해당 attempt 상한까지 `COMPLETED` Answer가 있으면 포함한다. FINAL 성공은 대상 input 각각이 정확히 한 Cluster에 한 번씩만 들어감을 의미하며, 분류할 수 없는 input도 누락하지 않고 하나의 안정적인 `기타` Cluster에 배치한다. 대상 0건의 Job·빈 generation 표현은 TBD이다.
- `FAILED` Job은 기록 화면에 오류와 재시도 상태를 표시한다. `COMPLETED` 후 재시도해도 Session을 `PROCESSING`으로 되돌리지 않는다.
- Session이 `COMPLETED`로 전환된 시각을 `completed_at`으로 공개한다. 그 전에는 `null`이다.

### 4.3 Question·AI 대표질문

```text
OPEN → SELECTED → ANSWERED
```

- 상태는 학생이 등록한 Question과 AI가 생성한 RepresentativeQuestion에 동일하게 적용한다.
- Answer는 한 번에 위 두 target 중 정확히 하나만 선택한다. 대표질문에 답변해도 클러스터 child 질문은 `ANSWERED`로 바뀌지 않는다.
- 클러스터링 실패는 질문·대표질문 상태와 현재 클러스터를 되돌리지 않는다.
- 답변 취소는 `CAPTURING` Answer 행을 삭제하고 학생 질문과 현재 `ACTIVE` 대표질문 target만 `SELECTED → OPEN`으로 복귀한다. 이미 `PRESERVED`인 과거 대표질문은 공개 membership에서 즉시 제거하고 11.6절의 폐기 규칙을 따른다. `CANCELLED` Answer 리소스나 이력은 남기지 않는다.

### 4.4 AIJob

```text
PENDING → RUNNING → SUCCEEDED
                  ├→ FAILED
                  ├→ CANCELLED
                  └→ SUPERSEDED
```

- `FAILED`만 작업 정책과 권한 검사를 통과하면 재시도할 수 있다. watchdog의 worker lease 만료와 일반 Job 실행 timeout도 `FAILED`이며 안전한 오류 code를 보관한다.
- `CANCELLED`는 대체 작업 없이 명시적으로 중단한 terminal 상태다. `SUPERSEDED`는 새 logical Job 또는 generation이 기존 실행을 대체한 terminal 상태다. 두 상태는 `retryable=false`이며 같은 행을 재시도할 수 없다.
- `LIVE → PROCESSING`에서 실행·재시도 예약된 LIVE `QUESTION_CLUSTERING`은 같은 종료 transaction에서 만드는 FINAL clustering Job이 대체하므로 `SUPERSEDED`로 끝낸다. 이전 run token과 retry 예약을 지워 늦은 결과를 막는다.
- `visibility`는 `SHARED` 또는 `REQUESTER_ONLY`이며 `blocks_session_completion=true`인 Job은 반드시 `SHARED`이다.
- `job_type`을 작업의 공개 purpose로 사용하고 `progress.stage`에는 `QUEUED`, `EXTRACTING`, `GENERATING`, `FINALIZING` 등 사용자에게 공개해도 안전한 phase만 반환한다.
- provider 내부 단계, 프롬프트·응답 원문과 민감한 오류 정보는 공개하지 않는다.
- 재시도는 같은 Job 행의 `attempt`를 1 증가시키고 `PENDING`으로 되돌린다. `version`도 1 증가한다.
- 재시도 시 현재 실행 상태인 progress, error, `started_at`, `finished_at`을 `null`로 초기화하고 `retryable=false`로 되돌린다.
- worker 결과는 현재 Job의 `id`, `attempt`, 실행 token과 `RUNNING` 상태가 모두 일치할 때만 반영한다. 이전 attempt의 늦은 결과는 폐기한다.
- Session당 `QUESTION_CLUSTERING` `PENDING|RUNNING` Job은 합계 하나만 허용한다. `LIVE_INCREMENTAL`은 Session 완료를 막지 않고 `FINAL`만 `blocks_session_completion=true`이다.
- LIVE clustering 실패는 적용 watermark를 전진시키지 않고 대기 상태를 유지한다. 시스템 재시도는 같은 Job 행의 `attempt + 1`을 사용하며 backoff·최대 시도 횟수는 TBD이다.

## 5. 사용자 API

### 5.1 내 정보 조회

```http
GET /api/v1/me
```

- 권한: 인증 사용자
- 응답: 계정 ID, 표시 이름, 이메일, 프로필 이미지
- 사용자가 수정할 수 있는 프로필 필드의 범위는 TBD이다.

### 5.2 계정 탈퇴

```http
DELETE /api/v1/me
```

- 권한: 인증 사용자. exact Origin allowlist를 검사한다. 성공 응답은 현재 서버 Session cookie를 만료시키므로 같은 browser 요청의 재시도는 새 인증 없이는 `401`이다.
- 삭제되지 않은 owner Course가 하나라도 있으면 `409 OWNED_COURSE_REQUIRES_DELETION`이다. 서버가 owner Course를 자동 삭제하지 않는다.
- 성공하면 모든 인증 세션·OAuth identity·비밀번호 credential·Course membership·reaction·계정 멱등 응답을 정리하고, User row는 이메일·avatar를 지우고 표시 이름을 `탈퇴한 사용자`로 바꾼 tombstone으로 남긴다. 기존 질문·Answer와 완료 기록의 내부 참조는 유지하지만 탈퇴 계정으로 다시 인증할 수 없다.
- 탈퇴는 복구하지 않으며 같은 외부 identity 또는 이메일은 새 계정으로만 다시 가입할 수 있다.

## 6. Course API

### 6.1 Course 목록

```http
GET /api/v1/courses?role=ALL&cursor=<cursor>&limit=20
```

- 권한: 인증 사용자
- `role`: `ALL`, `PROFESSOR`, `STUDENT`
- 현재 사용자가 참여한 Course만 반환한다.
- 각 항목에 Course별 현재 사용자 역할과 최근·진행 중 class 요약을 포함한다.
- 목록은 `created_at DESC, id DESC`로 안정적으로 정렬한다.

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
- `Idempotency-Key`는 선택 사항이다. 제공한 요청에만 2.6절의 멱등성 원장을 적용한다.
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
- `Idempotency-Key`는 선택 사항이다. 제공한 요청에만 2.6절의 멱등성 원장을 적용한다.
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
- `READY`, `LIVE`, `PROCESSING` Session이 하나라도 있으면 `409 COURSE_HAS_ACTIVE_SESSION`이다. `COMPLETED` Session만 남은 Course는 삭제할 수 있다.
- 성공 commit과 동시에 모든 Course API·WebSocket 재연결·참여 코드 조회는 `404 RESOURCE_NOT_FOUND`로 접근을 차단한다. 복구 API는 없다. Course와 완료 기록은 참조 무결성을 위해 내부 tombstone으로 남기며, PDF·녹음 final object는 deletion ledger가 멱등적으로 정리한다.
- 삭제와 멱등성 완료 응답 저장을 한 transaction으로 처리해 Course가 사라진 뒤의 재요청도 기존 `204`를 반환한다.
- 삭제가 허용되는 Course의 성공 응답은 `204 No Content`이다.

### 6.7 Course 전체 강의자료 archive

```http
GET /api/v1/courses/{course_id}/materials?cursor=<cursor>&limit=20
```

- 권한: Course 멤버. 인증되지 않은 요청은 `401`, 존재하는 Course의 비멤버는 `403 COURSE_ACCESS_DENIED`, 존재하지 않거나 삭제된 Course는 `404 RESOURCE_NOT_FOUND`다.
- 현재 active Session이 있으면 그 Session을 먼저 두고, 완료 class는 `started_at DESC, id DESC`로 정렬한다. 같은 Session의 Material은 `created_at ASC, id ASC`다.
- 현재 연결된 Material만 반환하며 detached Material, 내부 storage key·path와 물리 object URL은 반환하지 않는다. Material이 없는 Session은 응답 항목을 만들지 않는다.
- 각 항목은 `session`, `material`, nullable `content_url`, nullable `download_url`을 포함한다. `UPLOADED`, `PROCESSING`, `READY`는 각각 기본 inline 본문 URL과 `disposition=attachment` 다운로드 URL을 제공한다. `FAILED`는 두 URL이 모두 `null`이고 상태만 제공한다.
- zip 일괄 다운로드는 제공하지 않는다.
- 응답은 `items`, `next_cursor`이며 cursor는 Course ID, archive 종류, 정렬 위치에 묶인다. 다른 Course·archive·필터에 재사용하거나 변조하면 `400 INVALID_CURSOR`다.

### 6.8 Course 전체 Transcript archive

```http
GET /api/v1/courses/{course_id}/transcripts?cursor=<cursor>&limit=20
```

- 권한과 cursor 오류는 6.7절과 같다.
- `LIVE`, `PROCESSING`, `COMPLETED` Session을 반환한다. active Session이 있으면 먼저 두고 완료 class는 `started_at DESC, id DESC`로 정렬한다. `READY`는 아직 Transcript가 없으므로 제외한다.
- 각 항목은 `session`과 `RecordTranscriptIndex` 형태의 `transcript`를 포함한다. 최신 처리 상태와 canonical 선택을 분리해 표시하고, HQ 실패 뒤 보존된 LIVE canonical을 HQ 성공으로 표현하지 않는다.
- Segment·Gap 본문은 이 응답에 embed하지 않는다. 클라이언트는 사용자가 class를 선택하거나 펼칠 때 `transcript.timeline_url`을 따라 9.3절의 기존 timeline cursor API를 지연 조회한다.
- Transcript 파일 다운로드 URL은 제공하지 않는다.

### 6.9 Course 전체 공용 FINAL Summary archive

```http
GET /api/v1/courses/{course_id}/summaries?cursor=<cursor>&limit=20
```

- 권한과 cursor 오류는 6.7절과 같다.
- `PROCESSING`, `COMPLETED` Session을 반환한다. active `PROCESSING` Session이 있으면 먼저 두고 완료 class는 `started_at DESC, id DESC`로 정렬한다.
- 각 항목은 `session`, `FinalSummaryState`인 `state`, nullable `summary`, nullable `summary_url`을 포함한다. `state.status=AVAILABLE`일 때만 `summary`와 `summary_url`이 non-null이다.
- SQL 조회 단계와 public schema 모두 `summary_type=FINAL`, `visibility=COURSE_MEMBERS`, `requester_user_id=null`인 공용 결과만 허용한다. 요청자 전용 LIVE Summary·Chat·Message·Evidence·개인 AIJob은 포함하지 않는다.
- provider 원문 오류는 반환하지 않고 12절의 안전한 FINAL Summary 상태와 오류 코드만 공개한다.

### 6.10 Course 전체 Q&A archive

```http
GET /api/v1/courses/{course_id}/qna?cursor=<cursor>&limit=20
```

- 권한과 cursor 오류는 6.7절과 같다.
- 현재 active Session이 있으면 먼저 두고 완료 class는 `started_at DESC, id DESC`로 정렬한다. 같은 class 안에서는 `occurred_at DESC`, 동일 시각이면 target ID 내림차순으로 정렬한다.
- 항목은 `target_type` discriminator로 `STUDENT_QUESTION`과 `AI_REPRESENTATIVE_QUESTION`을 구분한다. 두 유형 모두 class 요약, immutable `target_text_snapshot`, nullable 또는 완료된 공개 Answer, class 기록으로 이동하는 `record_url`을 포함한다. 공개 Answer는 표시용 `id`, `answer_type`, `status=COMPLETED`, 교수자 `text_content`, content-only `organization`, `completed_at`만 반환한다.
- 학생 질문은 작성자 식별정보 없이 모두 포함한다. 미답변 질문은 `answer=null`, 답변된 질문은 `status=COMPLETED`인 Answer만 포함한다. 학생 Question 공개 표현에도 계정 ID·이름·이메일을 추가하지 않는다.
- AI 대표질문은 `status=COMPLETED` Answer가 있는 `ACTIVE`·`PRESERVED` target만 포함하고 Answer의 immutable snapshot을 질문 문구로 사용한다. `CAPTURING`·취소 Answer와 `DISCARDED` 대표질문은 완료 Answer 원장이 남아 있어도 제외한다. Answer·clustering·provider Job ID, attempt·retry 상태, Transcript version·segment ID, 모델·prompt provenance는 공개하지 않는다.
- archive는 읽기 전용이다. Answer 작성·수정·철회와 실패 Job 재시도는 기존 class 기록 API와 화면에서 수행한다.

## 7. Lecture Session API

### 7.1 class 목록

```http
GET /api/v1/courses/{course_id}/sessions?status=<status>&cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- 목록은 `started_at DESC NULLS LAST, id DESC`로 안정 정렬한다. `status=COMPLETED` 목록의 active Session은 Course의 `current_session`으로 별도 조회하므로 완료 목록에 섞이지 않는다.
- 페이지 커서는 Course ID, 선택한 status와 마지막 `started_at`·Session ID를 보존한다. 다른 Course나 status에 재사용하거나 변조하면 `400 INVALID_CURSOR`다.
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
- `title`은 선택적이다. 생략하거나 앞뒤 공백을 제거한 값이 빈 문자열이면 서버가 `Course 제목 · YYYY.MM.DD HH:mm` 자동 제목을 생성한다. `YYYY.MM.DD`는 요청의 `lecture_date`, `HH:mm`은 생성 시 기록한 `created_at`을 기본 timezone `Asia/Seoul`로 표시한 값이다.
- 자동 제목은 생성 시 확정해 저장하며, 이후 시작·종료·완료 상태 전이나 빈 제목 수정에서도 같은 `created_at` 기준 값을 사용한다.
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
- 앞뒤 공백을 제거한 제목이 빈 문자열이면 class 생성 때의 `created_at` 기준으로 계산한 같은 자동 제목으로 되돌린다.
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
- 시작 transaction은 `source=LIVE`, `status=FINALIZING`인 첫 Transcript version을 만들고 `canonical_transcript_version_id`를 이 version으로 설정한다. 실시간 REST·RAG 기본 source는 이 LIVE canonical이다.

### 7.7 class 종료

```http
POST /api/v1/sessions/{session_id}/end
Idempotency-Key: <key>
```

- 권한: Course `PROFESSOR`
- `LIVE → PROCESSING`을 한 번만 적용한다.
- **현재 구현 범위:** 종료 transaction은 `PROCESSING` 상태, SHARED·blocking `SESSION_POSTPROCESSING` coordinator와 조건부 FINAL clustering Job을 함께 저장한다. 별도 후처리 Worker는 HQ source terminal 뒤 Answer mapping·Knowledge 재색인·Answer organization·FINAL Summary를 예약하고, 저장된 completion predicate로만 `COMPLETED` 전이를 수행한다.
- `CAPTURING` Answer가 남아 있으면 `409 ANSWER_CAPTURE_ACTIVE`를 반환하므로 먼저 완료하거나 취소해야 한다.
- 정상 클라이언트도 종료 확인 즉시 이 API를 호출한다. 동시에 `audio.stop`을 전송하고 MediaRecorder의 마지막 fragment를 flush한 뒤 pause해 로컬 녹음 마감을 준비한다. `202` 또는 REST 조정으로 종료 상태가 확인되면 녹음을 finalize하고, 요청 실패 후 `LIVE`가 확인되면 같은 MediaRecorder instance를 resume한다. `audio.stopped`, 로컬 finalize와 drain 완료를 HTTP 호출의 선행조건으로 두지 않는다. 서버는 종료 transaction에서 새 audio frame을 차단하고 이미 받은 chunk만 별도로 drain한다.
- 종료 transaction이 commit되면 Session은 즉시 `PROCESSING`이 되고 새 audio 입력과 resume을 차단한다. 첫 `audio.start`에서 만든 논리 Recording은 `CAPTURING → UPLOAD_PENDING`으로 전이한다.
- 같은 transaction에서 모든 개인 LIVE Summary, `mode=LIVE` Chat·Message·Evidence, `REQUESTER_ONLY LIVE_SUMMARY` Job과 LIVE Chat에 귀속된 `REQUESTER_ONLY CHAT_RESPONSE` Job을 삭제한다. 늦게 도착한 Worker 결과는 Job·target·Session state·attempt·run token fence를 통과하지 못해 저장되지 않는다. 종료 후 이전 개인 LIVE 리소스·Job ID의 polling·단건 조회는 존재를 숨기는 `404 RESOURCE_NOT_FOUND`다. `purge_on_session_end=true` terminal 멱등성 행은 삭제하지 않고 encrypted 응답을 `410 LIVE_AI_RESULT_PURGED`로 바꿔 terminal 시각부터 남은 24시간 동안 같은 키·같은 request hash에만 replay한다. 새 키 요청은 Session 상태 검증에 따라 `409 SESSION_STATE_CONFLICT`다. FINAL Summary, `mode=REVIEW` Chat과 관련 Job·멱등성 원장은 영향받지 않는다.
- 브라우저가 로컬 녹음을 확정한 뒤 15.3~15.5절의 resumable upload로 전송한다. Recording upload가 완료되기 전에는 HQ STT를 시작하지 않는다.
- 같은 transaction에서 SHARED·blocking `SESSION_POSTPROCESSING` coordinator를 `PENDING`으로 생성한다. FINAL 대상이 1건 이상이면 4.2절의 종료 시점 입력 상한을 고정한 SHARED·blocking `FINAL` `QUESTION_CLUSTERING` Job도 같은 transaction에서 함께 생성한다. Recording/HQ 또는 Recording이 없는 경우 LIVE Transcript source가 terminal이 되기 전에는 coordinator를 claim하지 않지만, FINAL clustering은 source와 독립적으로 즉시 실행할 수 있다.
- coordinator는 source terminal 후 Answer mapping·Knowledge 재연결을 수행하고 자신의 terminal 전이와 downstream blocking Job 생성·outbox를 같은 transaction에 commit한다. HQ Transcript version·canonical 전환과 Answer 재매핑은 9절과 11절을 따른다.
- 성공: `202 Accepted`, 갱신된 Session, nullable Recording과 종료 transaction에서 생성된 coordinator 및 조건부 FINAL clustering Job을 `jobs[]`로 반환한다.
- class 종료 요청 자체의 멱등 재요청은 기존 Session, Recording과 Job 결과를 반환한다.

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
- 저장소 또는 멱등성 응답 암호화 설정을 사용할 수 없으면 `503`을 반환하며, 파일 경로·storage key·provider 원문 오류는 응답하지 않는다.

### 8.2 자료 목록과 메타데이터

```http
GET /api/v1/sessions/{session_id}/materials?cursor=<cursor>&limit=20
GET /api/v1/materials/{material_id}
```

- 권한: Course 멤버
- 외부에서 연결된 자료만 반환한다. 응답은 업로드 시 확정한 `display_name`, MIME, 크기, 페이지 수와 처리 상태를 포함한다.
- 목록은 `created_at ASC, id ASC`로 안정적으로 정렬하고 `items`, `next_cursor`를 반환한다.
- 인증되지 않은 요청은 `401`을 반환한다. 목록에서 비멤버는 `403 COURSE_ACCESS_DENIED`, 존재하지 않는 Session은 `404`를 반환한다. 단건 조회에서는 비멤버·권한 밖 요청, 분리되거나 존재하지 않는 자료를 모두 `404 MATERIAL_NOT_FOUND`로 응답해 존재를 숨긴다.
- 내부 파일 경로, 스토리지 키와 `detached_at`은 응답하지 않는다.

### 8.3 PDF 열람

```http
GET /api/v1/materials/{material_id}/content?disposition=inline|attachment
```

- 권한: Course 멤버
- `disposition` 기본값은 `inline`이다. `inline`은 브라우저 열람, `attachment`는 개별 파일 다운로드를 뜻한다. 다른 값은 `422 VALIDATION_ERROR`다.
- 성공: `200 OK`, `application/pdf`
- 연결되고 `processing_status`가 `UPLOADED`, `PROCESSING`, `READY`인 Material만 본문을 반환한다. `FAILED`는 사용할 수 없는 자료이므로 원본을 반환하지 않는다.
- `Content-Disposition`은 요청한 disposition과 저장된 `display_name`을 안전하게 인코딩한 파일명을 함께 사용한다.
- 인증되지 않은 요청은 `401`을 반환한다. 비멤버·권한 밖 요청, `FAILED`, 분리되거나 존재하지 않는 자료는 모두 `404 MATERIAL_NOT_FOUND`로 응답해 존재를 숨긴다.
- 저장소가 일시적으로 읽히지 않으면 `503 STORAGE_UNAVAILABLE`을 반환한다.
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
- 멱등성 응답 암호화 설정을 사용할 수 없으면 `503 DEPENDENCY_UNAVAILABLE`을 반환한다. 이미 commit된 분리는 파일 삭제 재시도 실패와 무관하게 `204`를 유지한다.
- 이미 저장된 Assistant 근거를 보존하는 경우 안전한 `label` snapshot은 남길 수 있지만 자료 `link`는 `null`로 반환한다. 근거의 정확한 보관 기간·FK 정책과 `410 Gone` 도입 여부는 미정이다.

## 9. Transcript API

### 9.1 Transcript version과 canonical 전환

영구 Transcript는 Session 안에서 단조 증가하는 `version`을 가진 `TranscriptVersion`으로 관리한다.

| 상태         | 의미                                                                    |
| ------------ | ----------------------------------------------------------------------- |
| `FINALIZING` | LIVE drain 또는 녹음 기반 HQ STT가 아직 final Segment·Gap을 확정하는 중 |
| `FINALIZED`  | 하나 이상의 final Segment를 포함해 version이 확정됨                     |
| `FAILED`     | 해당 version의 Transcript 처리가 실패함                                 |
| `EMPTY`      | 정상 처리를 끝냈지만 final Segment가 0건임. final Gap은 있을 수 있음    |

- `source`는 `LIVE` 또는 `RECORDING`이다. LIVE partial은 저장하지 않고 LIVE final만 해당 version의 Segment가 된다.
- TranscriptVersion metadata는 소스·상태·version과 해당 version 안의 마지막 final Segment 순번인 `last_sequence`를 공개한다. Segment가 없으면 `0`이다.
- Session은 nullable `canonical_transcript_version_id`로 기본 열람에 사용할 canonical version을 가리킨다. `READY`에서는 `null`일 수 있지만 class 시작 transaction이 LIVE version을 만들고 즉시 이 포인터를 설정한다. 응답의 `is_canonical`은 이 포인터에서 계산한다.
- Transcript aggregate는 최신 처리 version인 `current_version`의 상태를 별도로 공개한다. 따라서 최신 HQ version이 `FAILED`이면 aggregate `status=FAILED`이면서 canonical 포인터는 기존 LIVE version을 계속 가리킨다. aggregate status와 canonical 포인터를 같은 값으로 추정하지 않는다.
- Session 시작 transaction이 canonical로 설정한 LIVE version은 `FINALIZING`이다. audio runtime은 final Segment·Gap을 이 version에 기록하고 Session 종료 transaction은 새 frame을 fence한 뒤 Segment 유무로 `FINALIZED` 또는 `EMPTY`로 확정한다. 이 LIVE terminal 상태는 Recording이 없는 class의 coordinator source gate다.
- Recording upload complete는 다음 version의 `RECORDING`/`FINALIZING` row와 `RECORDING_TRANSCRIPTION` Job을 같은 transaction에서 생성한다.
- 실패한 `RECORDING_TRANSCRIPTION`을 재시도하면 같은 Job ID의 `attempt + 1`과 새 `RECORDING`/`FINALIZING` Transcript version을 사용한다. 이전 실패 version은 provenance로 보존하고 성공 `result`는 현재 attempt의 version을 가리킨다. `COMPLETED` 후 재시도 성공은 같은 `SESSION_POSTPROCESSING` coordinator 행을 `attempt + 1`로 자동 requeue하며 Session 상태를 되돌리지 않는다.
- `RECORDING_TRANSCRIPTION` 성공 commit은 Segment·Gap, Segment의 녹음 시간 mapping, version 상태, aggregate current version과 canonical 포인터를 먼저 하나의 결과로 공개한다. 성공 version은 `FINALIZED` 또는 `EMPTY`이다.
- `RECORDING_TRANSCRIPTION` 실패·timeout transaction은 해당 attempt의 staged Segment·Gap을 제거하거나 rollback하고 `last_sequence=0`, version `FAILED`, Job `FAILED`를 함께 commit한다. aggregate는 `FAILED`로 표시하되 canonical 포인터를 실패 version으로 강제하지 않는다.
- canonical 전환 후 `SESSION_POSTPROCESSING`이 Answer mapping과 Knowledge 재연결을 별도로 commit한다. 후처리 실패는 HQ Transcript·canonical 결과를 rollback하지 않는다.
- HQ `FAILED` 뒤에도 기존 LIVE canonical 포인터를 변경하지 않고 실패 version을 canonical로 강제하지 않는다. 실패한 HQ version과 LIVE version은 모두 version 목록에서 provenance와 함께 조회한다. 보존된 LIVE canonical을 완료 기록의 final source로 사용할지는 TBD이다.
- `transcript.version.updated`는 aggregate 상태, current version 또는 canonical 포인터 변경을 알리는 invalidation event다. WebSocket payload보다 REST 조회를 최종 진실로 사용한다.

### 9.2 Transcript version 목록

```http
GET /api/v1/sessions/{session_id}/transcript/versions?cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- version 내림차순, ID 내림차순의 안정적인 순서로 LIVE·RECORDING version metadata를 반환한다.
- 실패한 HQ version과 canonical에서 교체된 LIVE version도 숨기지 않는다.

### 9.3 canonical 또는 지정 version 타임라인 조회

```http
GET /api/v1/sessions/{session_id}/transcript?transcript_version_id=<id>&start_sequence=<n>&end_sequence=<n>&cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- `transcript_version_id`를 생략하면 canonical version을, canonical 포인터가 `null`이면 current version을 선택한다. 지정하면 같은 Session에 속한 과거 version도 조회할 수 있다. HQ `FAILED`에서 기본 조회가 LIVE version을 반환해도 aggregate `status=FAILED`를 함께 공개하며, 이를 Summary final source 사용 확정으로 해석하지 않는다.
- `start_sequence`와 `end_sequence`는 안정적인 Transcript 범위 anchor이며 두 값을 항상 함께 사용한다. 이 범위를 지정할 때는 `transcript_version_id`도 필수이고, 두 sequence가 같은 version의 final Segment이며 `start_sequence <= end_sequence`임을 검증한다. anchor가 있는 요청은 해당 inclusive Segment 범위와 그 범위의 class 시간축에 걸친 Gap만 페이지닝하고 cursor에 version·anchor 범위를 함께 고정한다.
- Chat Evidence의 `TRANSCRIPT` link는 cursor 없이 `/api/v1/sessions/{session_id}/transcript?transcript_version_id={transcript_version_id}&start_sequence={start_sequence}&end_sequence={end_sequence}` 순서의 canonical 상대 경로를 사용한다. Segment ID 단건 경로를 Evidence anchor로 사용하지 않는다.
- 응답은 최신 상태를 담은 `transcript`, 실제 타임라인 source인 `selected_version`, `segments`, `gaps`, `next_cursor`를 포함한다. partial은 포함하지 않는다.
- 페이지 경계는 Segment·Gap을 합친 논리 타임라인에서 한 번만 계산하고, 해당 페이지를 응답에서 `segments[]`와 `gaps[]`로 나눠 준다. 따라서 `segments.length + gaps.length <= limit`이며 두 배열에 따로 독립 cursor를 두지 않는다.
- 클라이언트가 한 페이지를 하나의 타임라인으로 표시할 때는 두 배열을 다시 `start_ms ASC`, 같은 시각의 `SEGMENT` 우선, `id ASC`로 merge한다. `next_cursor`는 이 merge 순서의 마지막 항목을 기준으로 한다.
- `FAILED` HQ version은 상태·provenance만 조회하고 완성되지 않은 Segment·Gap은 반환하지 않아 두 배열이 모두 비어 있다.
- `EMPTY` version은 `last_sequence=0`이지만 재처리 후에도 남은 `is_final=true` Gap이 있을 수 있어 `gaps`를 반환할 수 있다.
- 합친 타임라인은 `start_ms ASC`, 같은 시각이면 `SEGMENT` 우선, 그 뒤 `id ASC`의 안정적인 순서를 사용한다. cursor는 version과 이 위치를 함께 고정하는 불투명 값이다.
- 첫 페이지 뒤 canonical 포인터가 바뀌어도 cursor가 가리키는 version의 다음 페이지를 반환한다. 명시한 `transcript_version_id`와 cursor의 version이 다르면 `400 INVALID_CURSOR`이다.
- Segment는 nullable `recording_start_ms`, `recording_end_ms`를 공개하고 녹음 위치가 확정된 문장은 이 offset으로 playback seek한다. Gap은 class 시간축의 `start_ms`, nullable `end_ms`와 canonical 후보에 남은 최종 gap인지 나타내는 `is_final`을 공개하며 recording offset을 임의 환산하지 않는다. `is_final=true`이면 `end_ms`는 반드시 non-null이다.
- WebSocket 재연결과 `transcript.version.updated` 뒤 REST canonical 복구에 사용한다.

### 9.4 Transcript Segment 단건 조회

```http
GET /api/v1/transcript-segments/{segment_id}
```

- 권한: 해당 Segment가 속한 Course 멤버
- final Segment ID를 직접 조회하는 경로다. Chat Evidence는 이 단건 경로 대신 9.3절의 Session·version·sequence 범위 anchor를 사용한다.
- 인증되지 않은 요청은 `401`을 반환한다. 비멤버·권한 밖 요청, 비가시·삭제되거나 존재하지 않는 Segment는 모두 `404 RESOURCE_NOT_FOUND`로 응답해 존재를 숨긴다.

## 10. 질문·클러스터·반응 API

### 10.1 질문 목록

```http
GET /api/v1/sessions/{session_id}/questions?status=OPEN&sort=POPULAR&cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- `sort=POPULAR`은 `reaction_count DESC, created_at DESC, id DESC`, `sort=RECENT`는 `created_at DESC, id DESC`로 정렬한다. 응답은 익명 질문, 반응 수, 답변 상태와 nullable 현재 `cluster_id`를 포함한다.
- LIVE에서 `reaction_count`가 바뀌면 `POPULAR` 순위는 페이지 사이에 재배치될 수 있으므로 이 정렬은 전체 목록 snapshot이 아니다. `reaction.updated`를 받으면 첫 페이지를 새로 조회한다. `/record`의 질문 경로는 수업 종료 후 불변 키만 쓰는 `sort=RECENT`를 사용한다.
- 현재 사용자의 반응 여부는 `reacted_by_me`로 표현하고 `author_id`, 이름, 이메일은 절대 반환하지 않는다.
- 동일한 문장의 질문을 서로 다른 학생이 등록할 수 있으며 중복 content를 제거하지 않는다.

### 10.2 질문 단건

```http
GET /api/v1/questions/{question_id}
```

- 권한: Course 멤버
- 목록과 같은 익명 Question 표현을 반환하며 작성자 식별 정보를 포함하지 않는다.
- 인증되지 않은 요청은 `401`을 반환한다. 비멤버·권한 밖 요청, 비가시·삭제되거나 존재하지 않는 Question은 모두 `404 RESOURCE_NOT_FOUND`로 응답해 존재를 숨긴다.

### 10.3 익명 질문 생성과 자동 clustering 요청

```http
POST /api/v1/sessions/{session_id}/questions
Idempotency-Key: <key>
```

```json
{
  "content": "다익스트라에서 음수 가중치를 쓸 수 없는 이유가 궁금합니다."
}
```

- 권한: Course `STUDENT`. Session이 `LIVE`일 때만 허용한다.
- 서버는 3.1.1절에 따라 앞뒤 공백 제거·Unicode NFC 정규화 후 `1..300` code point를 검증한다. 초과·빈 결과는 잘라 저장하지 않고 안정적인 `422 VALIDATION_ERROR` details를 반환하며, Question `content`에는 정규화 결과를 저장한다.
- Question 행과 Session 내 증가 `clustering_sequence`, `requested_through_sequence` 갱신을 먼저 commit하고 `question.created`를 전파한다.
- active clustering Job과 현재 backlog을 소유한 retryable `FAILED` Job이 모두 없으면 시스템이 `LIVE_INCREMENTAL` Job을 즉시 하나 생성한다. `PENDING|RUNNING` Job이나 `retry_job_id`가 있으면 새 Job을 만들지 않고 pending watermark만 남긴다. retry Job은 기존 captured watermark로 `attempt + 1`을 수행하고, 성공 후에도 requested가 applied보다 크면 추가 질문을 위한 새 Job을 만든다.
- 성공은 클러스터링 성공과 무관하게 `201 Created`이다. 응답은 `question`과 현재 `clustering_state`를 반환하며 active Job이 없으면 `active_job_id=null`일 수 있다.

아래는 핵심 필드만 표시한 축약 예시이며 전체 필드는 OpenAPI의 `QuestionCreateResponse`를 따른다.

```json
{
  "question": {
    "id": "question_01HXYZ",
    "content": "다익스트라에서 음수 가중치를 쓸 수 없는 이유가 궁금합니다.",
    "status": "OPEN"
  },
  "clustering_state": {
    "pending": true,
    "requested_through_sequence": 42,
    "applied_through_sequence": 39,
    "active_job_id": "job_01HXYZ",
    "retry_job_id": null
  }
}
```

### 10.4 AI 질문 문장 작성 도움

```http
POST /api/v1/sessions/{session_id}/question-drafts
```

- 권한: Course `STUDENT`. Session이 `LIVE`일 때만 허용한다.
- 초안은 3.1.1절에 따라 앞뒤 공백 제거·Unicode NFC 정규화 후 `1..500` code point를 검증한다. 초과·빈 결과는 잘라내지 않고 안정적인 `422 VALIDATION_ERROR` details를 반환한다. AI 제안은 각각 `1..300`자이며 정규화한 초안은 영구 저장하지 않는다.
- `200 OK`에서 짧은 질문 문장 후보를 직접 반환하고 Question·AIJob·초안을 저장하지 않는다. 제안을 실제 질문으로 등록하려면 10.3 API를 다시 호출한다.
- 서버는 내부 `question-draft-help-v1` prompt version과 5초 deadline을 사용한다. provider timeout·가용성·rate limit·잘못된 결과는 provider 원문 없이 `503 AI_PROVIDER_UNAVAILABLE`으로 반환하며, 학생 초안은 화면에 남긴다. 실제 외부 또는 local LLM runtime 선택은 아직 미정이다.

### 10.5 ‘나도 궁금해요’ 추가·취소

```http
PUT    /api/v1/questions/{question_id}/reaction
DELETE /api/v1/questions/{question_id}/reaction
```

- 권한: Course `STUDENT`. Session이 `LIVE`일 때만 변경할 수 있다.
- 추가는 기존 반응이 있어도 `200 OK`, 취소는 반응이 없어도 `204 No Content`이다.
- 자신이 작성한 질문에는 반응할 수 없고 대표질문 반응은 MVP에 포함하지 않는다.

### 10.6 클러스터 generation 목록

```http
GET /api/v1/sessions/{session_id}/question-clusters?scope=CURRENT&cursor=<cursor>&limit=20
```

- 권한: Course 멤버. `scope` 기본값은 LIVE의 `CURRENT`이고 `FINAL`은 후처리 최종 generation을 선택한다.
- 응답은 `clustering_state`, generation 메타데이터, `ordinal ASC, id ASC`로 정렬한 Cluster, `next_cursor`를 포함한다.
- `clustering_state`는 requested·applied watermark, current revision, `pending`, active Job ID, retry-reserved Job ID, 마지막 clustering Job ID·attempt·mode·status를 포함한다. active와 retry ID는 동시에 non-null일 수 없고 scheduler가 retry를 requeue하면 같은 ID가 retry 필드에서 active 필드로 이동한다.
- Cluster는 중앙에 표시할 immutable `representative_question`, child 개수와 members 조회 경로, 선택 generation을 공개한 `clustering_state.current_revision` projection인 `revision`, `is_final`, `finalized_at`, 생성 Job provenance를 반환한다. 대표질문의 `created_in_generation`은 해당 immutable 문장을 처음 만든 Cluster generation이며 이후 `PRESERVED` child로 이동해도 바뀌지 않는다. `lifecycle_status=ACTIVE|PRESERVED`와 Answer 상태인 `status=OPEN|SELECTED|ANSWERED`는 서로 독립이다.
- 공개 Cluster `id`는 LIVE generation 사이 같은 semantic Cluster가 계승하는 logical ID다. 새 LIVE Cluster와 모든 입력을 다시 배치하는 FINAL Cluster는 새 logical ID를 사용하고, 내부 generation row ID는 노출하지 않는다.
- LIVE Job은 captured watermark까지의 **새 학생 질문만** 기존 Cluster에 배치하고 기존 질문을 다른 Cluster로 옮기지 않는다. 새 member가 추가된 Cluster의 대표질문만 새 immutable 행으로 생성한다.
- Job 실행 중 등록된 질문은 다음 Job에 한꺼번에 처리한다. 대표질문 생성까지 성공해야 watermark를 적용하고 Job을 `SUCCEEDED`로 끝낸다.
- 답변 없는 교체 대표질문은 폐기한다. 새 generation 공개 transaction부터 Cluster 중앙·child, 대표질문 단건 조회와 새 RAG 검색에서 즉시 제외한다. Evidence 참조가 없으면 hard delete하고, 있으면 내부 `DISCARDED` tombstone과 해당 KnowledgeChunk만 provenance로 보존하되 `ChatEvidence.source_kind`·`label`은 유지하고 `link=null`로 반환한다. 마지막 Evidence를 삭제하는 transaction은 tombstone과 Chunk도 원자적으로 hard delete해 `DISCARDED`는 항상 Evidence가 1개 이상일 때만 남는다. `DISCARDED`는 내부 정리 상태이며 공개 `lifecycle_status`는 `ACTIVE|PRESERVED`만 유지한다.
- `CAPTURING` 대표질문은 Answer가 종료될 때까지 child로 보존하고, `COMPLETED` Answer가 있는 과거 대표질문은 일반 child 질문처럼 보존한다.
- FINAL Job은 성공 commit 전에 eligible 학생 질문과 cutoff까지 Answer가 완료된 AI 대표질문의 예상 집합과 공개 membership이 일치하는지 검증한다. 각 input은 정확히 한 번 등장해야 하며 누락·중복이 있으면 Job을 `SUCCEEDED`로 바꾸지 않는다. 모델이 분류하지 못한 input은 누락 대신 하나의 명시적이고 안정적인 `기타` Cluster에 배치하며 이 중앙 표시문은 임의 생성 문구가 아닌 정확한 `기타`를 사용한다.
- FINAL 대상 학생 질문과 답변된 AI 대표질문이 모두 0건일 때 Job 생략 여부, 빈 성공 결과 원장과 `generation` 표현은 TBD이다.
- 잘못된 UUID·`scope`·cursor·`limit` 형식은 `422 VALIDATION_ERROR`로 거부하고, 서명은 맞지 않거나 다른 generation의 cursor는 `400 INVALID_CURSOR`로 처리한다.

### 10.7 클러스터 child 목록

```http
GET /api/v1/sessions/{session_id}/question-clusters/{cluster_id}/members?cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- generation 안에서 유일한 `ordinal ASC`로 안정적으로 정렬한다. 공개 `ordinal`은 DB membership `position` projection이다. member 공개 discriminator는 `source_kind`이고 값은 `STUDENT_QUESTION` 또는 답변이 있어 보존된 `AI_REPRESENTATIVE`이다. 내부 typed FK 이름과 `AI_REPRESENTATIVE_QUESTION`을 이 membership enum으로 노출하지 않는다.
- 경로의 `{cluster_id}`는 해당 `{session_id}` 안에서 공개하는 logical ID이며, 서버는 Session·logical ID로 요청 scope의 현재 물리 generation row를 해석한다. 다른 Session의 logical ID는 일치하지 않는 리소스로 처리한다. generation 교체 중 기존 cursor 만료·재시작 정책은 TBD이다.
- 대표질문과 각 child의 Answer 상태는 독립적이다. 공통 `limit`은 기본 20·최대 100이다. generation 교체 중 기존 cursor의 만료·재시작 정책과 큰 마인드맵의 preload page 수·점진 loading·자동 축소 layout은 TBD이다.
- 잘못된 Session·Cluster UUID 또는 `limit` 형식은 `422 VALIDATION_ERROR`다.

### 10.8 AI 대표질문 단건 조회

```http
GET /api/v1/representative-questions/{representative_question_id}
```

- 권한: 해당 대표질문이 속한 Course 멤버
- 현재 Cluster 중앙 대표질문과 Answer target으로 보존된 과거 대표질문을 ID로 조회한다. generation 배열 위치나 pagination cursor에 의존하지 않는다.
- 응답의 `created_in_generation`(정수, 1 이상)은 이 immutable 대표질문이 처음 생성된 Cluster generation을 나타내며 `PRESERVED`로 바뀌어도 유지한다.
- 인증되지 않은 요청은 `401`을 반환한다. 비멤버·권한 밖 요청, 비가시·존재하지 않는 대표질문, 교체 후 폐기되었거나 `PRESERVED` Answer 취소로 공개에서 제거된 대표질문은 모두 `404 RESOURCE_NOT_FOUND`로 응답해 존재를 숨긴다. Evidence provenance용 내부 tombstone이 남아도 같다.
- 잘못된 대표질문 UUID는 `422 VALIDATION_ERROR`다.

## 11. 교수자 답변 API

### 11.1 답변 목록·단건

```http
GET /api/v1/sessions/{session_id}/answers?cursor=<cursor>&limit=20
GET /api/v1/answers/{answer_id}
```

- 권한: Course 멤버. 목록은 `started_at ASC, id ASC`로 정렬한다.
- Answer는 `VOICE|TEXT` 유형, `CAPTURING|COMPLETED` 상태, `STUDENT_QUESTION|AI_REPRESENTATIVE_QUESTION` 중 정확히 하나인 target과 immutable `target_text_snapshot`을 반환한다.
- `VOICE` Answer는 원본 LIVE Transcript 범위와 nullable canonical mapping을 공개하며 교수자 text를 보강해도 그 범위를 유지한다. Transcript 필드가 모두 `null`인 경우는 text-only `TEXT` Answer다.
- `organization_state`는 `TEXT`의 `NOT_APPLICABLE`, LIVE voice의 `NOT_STARTED`, PROCESSING에서 source 선택 전 Job ID 없는 `WAITING_SOURCE`, 생성된 `ANSWER_ORGANIZATION` Job의 `PENDING|RUNNING|SUCCEEDED|FAILED` 중 하나다. 성공할 때만 별도 AI 정리 결과와 실제 사용한 Transcript 범위를 반환한다. 적용 대상의 필수 Job 또는 성공 결과 원장이 누락되면 Answer 자체는 유지하고 `DATA_INTEGRITY_ERROR`로 표시하되 내부 오류 원문은 노출하지 않는다.
- `text_content`는 교수자가 직접 작성한 설명이고 AI 정리 결과와 다른 원장이다. 둘 다 있으면 화면은 교수자 text를 우선 표시하되 AI 정리본과 원본 음성 범위를 별도 표기로 유지한다.
- 클러스터 대표질문을 선택한 순간의 문구를 snapshot하며 이후 대표질문 교체와 무관하게 변경하지 않는다.
- Answer는 target당 최대 하나다. 대표질문 Answer는 child Question의 답변 여부에 영향을 주지 않는다.
- Answer 단건 조회에서 인증되지 않은 요청은 `401`을 반환한다. 비멤버·권한 밖 요청, 비가시·취소·삭제되거나 존재하지 않는 Answer는 모두 `404 RESOURCE_NOT_FOUND`로 응답해 존재를 숨긴다.

### 11.2 LIVE 음성 답변 캡처 시작

```http
POST /api/v1/sessions/{session_id}/answers
Idempotency-Key: <key>
```

```json
{
  "answer_type": "VOICE",
  "target": {
    "type": "AI_REPRESENTATIVE_QUESTION",
    "representative_question_id": "representative_question_01HXYZ"
  }
}
```

- 권한: Course `PROFESSOR`. `VOICE`는 Session `LIVE`에서만 허용한다.
- 해당 target을 `SELECTED`로 바꾸고 선택 시점의 exact text와 마지막 final sequence를 snapshot한다. Session당 `CAPTURING` Answer와 target당 취소되지 않은 Answer는 각각 최대 하나다.
- Session에 다른 capture가 있으면 `409 ANSWER_CAPTURE_ACTIVE`, target에 이미 Answer가 있으면 `409 ANSWER_ALREADY_EXISTS`다.
- Answer가 시작한 LIVE Transcript version을 `source_transcript_version_id`로 고정하고 `201 Created`, `CAPTURING`을 반환한다.

학생 질문을 선택할 때는 target만 다른 형태다.

```json
{
  "answer_type": "VOICE",
  "target": {
    "type": "STUDENT_QUESTION",
    "question_id": "question_01HXYZ"
  }
}
```

### 11.3 LIVE 음성 답변 완료

```http
POST /api/v1/answers/{answer_id}/complete
Idempotency-Key: <key>
```

- 권한: Course `PROFESSOR`. 본문을 생략하면 선택 후 자동 후보를, 본문을 보내면 같은 source TranscriptVersion의 `start_sequence <= end_sequence` 범위를 확정한다.
- final 구간이 없으면 `409 ANSWER_TRANSCRIPT_NOT_READY`다. 성공하면 Answer와 **선택한 target 하나만** `COMPLETED`, `ANSWERED`로 바꾼다.
- canonical 전환 뒤에도 원본 LIVE 범위를 유지하고 `SESSION_POSTPROCESSING`이 mapping을 `PENDING → SUCCEEDED|FAILED`로 완료한다. mapping 실패는 HQ Transcript를 rollback하지 않는다.

### 11.4 COMPLETED 텍스트 답변 생성·보강

아직 Answer가 없고 `status=OPEN`인 학생 질문에만 새 text-only Answer를 생성한다.

```http
POST /api/v1/sessions/{session_id}/answers
Idempotency-Key: <key>
```

```json
{
  "answer_type": "TEXT",
  "target": {
    "type": "STUDENT_QUESTION",
    "question_id": "question_01HXYZ"
  },
  "text_content": "음수 간선은 현재까지의 최단 거리를 확정하는 가정을 깨뜨립니다."
}
```

- 권한: Course `PROFESSOR`. `TEXT`는 Session `COMPLETED`에서 미답변 `STUDENT_QUESTION`을 target으로만 생성하며 즉시 `COMPLETED`로 저장한다. FINAL·복습 화면에서만 보이는 AI 대표질문이나 미답변 `ACTIVE` 대표질문은 새 text-only target이 아니다.
- 이미 완료된 음성·텍스트 Answer에 텍스트를 추가·교체할 때는 다음 API를 사용한다.

```http
PATCH /api/v1/answers/{answer_id}
```

```json
{
  "text_content": "복습용으로 추가한 텍스트 설명입니다.",
  "expected_version": 3
}
```

- Session `COMPLETED`의 기존 `COMPLETED` Answer만 수정하고 `version`을 증가시킨다. 학생 질문 target의 기존 완료 Answer와, 완료된 Answer target이기 때문에 `PRESERVED`로 보존된 AI 대표질문의 기존 완료 Answer에 `text_content`를 추가·교체할 수 있다. target·snapshot·원본 음성 범위는 바꾸지 않는다. 이 필드는 교수자 작성 text이므로 AI 정리 Job의 성공·재시도·늦은 결과가 덮어쓰지 않는다.
- `text_content`는 trim·Unicode NFC 정규화 뒤 1~2,000자여야 한다. `expected_version`이 현재 값과 다르면 `409 ANSWER_VERSION_CONFLICT`이며 `details.current_version`, `details.current_text_content`를 반환한다. 서버는 사용자의 로컬 초안을 덮어쓰지 않으므로 UI는 충돌 메시지와 함께 작성 중 내용을 유지한다.
- 철회는 빈 문자열 PATCH가 아니라 다음 endpoint를 사용한다. text-only Answer는 hard delete하고 학생 질문 target을 `OPEN`으로 되돌린다. voice-backed Answer는 `text_content`만 `null`로 지우고 target·snapshot·음성 범위는 유지한다.

```http
DELETE /api/v1/answers/{answer_id}/text
Idempotency-Key: <key>
```

- 철회 후 공개 취소 이력은 남기지 않는다. 같은 멱등 키의 재요청은 24시간 동안 같은 `204 No Content`를 반환한다.

### 11.5 음성 Answer AI 정리

- 교수자가 별도로 실행하지 않는다. `SESSION_POSTPROCESSING` coordinator가 완료된 `VOICE` Answer마다 `ANSWER_ORGANIZATION` Job을 자동 생성한다.
- 성공한 canonical mapping이 있으면 그 HQ Segment 범위를, 없으면 Answer에 고정된 원본 LIVE Segment 범위를 최초 생성 transaction에서 input으로 저장한다. 재시도도 같은 source와 같은 Job 행을 사용한다.
- 성공 결과는 질문 snapshot과 교수자의 발화 범위를 바탕으로 만든 정리문, 실제 source version·범위, model·prompt provenance를 반환한다. 결과 행과 Job `SUCCEEDED`는 원자적으로 저장한다.
- 모델 입력은 immutable `target_text_snapshot`과 Job에 고정한 음성 Transcript 범위만 사용한다. 수업 후 수정 가능한 교수자 `text_content`는 표시·별도 검색 원본일 뿐 최초 실행과 재시도 입력에 포함하지 않는다.
- Job 실패·timeout은 Answer 원본과 교수자 `text_content`를 유지한 채 `FAILED`로 격리한다. Course 교수자는 완료 기록에서 같은 Job의 `attempt + 1` 재시도를 할 수 있고 Session은 `PROCESSING`으로 돌아가지 않는다.
- 성공한 AI 정리 결과의 수동 재생성은 MVP에서 제공하지 않는다. 정리문 형식·최대 길이·model·prompt·품질 기준은 TBD이다.

### 11.6 LIVE 답변 취소

```http
POST /api/v1/answers/{answer_id}/cancel
Idempotency-Key: <key>
```

- 권한: Course `PROFESSOR`. `CAPTURING` Answer를 hard delete한다. 학생 질문과 현재 `ACTIVE` 대표질문 target은 `OPEN`으로 복귀하고, 이미 `PRESERVED`인 과거 대표질문은 membership·Cluster·단건 조회·RAG에서 즉시 제거한 후 `204 No Content`를 반환한다.
- 취소된 Answer는 목록·단건 API나 완료 기록에 노출하지 않는다. 멱등 재요청은 24시간 멱등 응답으로 `204`를 재사용하고, 키 없이 삭제된 ID를 조회하면 `404`다.
- 취소 시점에 이미 중앙 대표가 아닌 미답변 AI 대표질문은 함께 폐기한다. Evidence 참조가 없으면 hard delete하고, 있으면 내부 `DISCARDED` tombstone·KnowledgeChunk를 남기되 해당 Evidence는 `source_kind`·`label`을 유지하고 `link=null`로 반환한다. 마지막 Evidence를 삭제하는 transaction은 tombstone과 Chunk도 원자적으로 hard delete해 `DISCARDED`는 항상 Evidence가 1개 이상일 때만 남는다. 서버는 본문 없는 `answer.deleted` tombstone 이벤트로 열린 화면을 무효화한다.
- `PRESERVED` 대표질문 membership을 삭제하는 transaction은 clustering state의 `current_revision + 1`과 `clustering.updated` outbox를 함께 기록한다. 기존 active 또는 retry-reserved LIVE Job은 `CLUSTER_REVISION_CHANGED`, `retryable=false`로 fence하고 pending 질문이 있으면 현재 revision의 fresh Job을 자동 생성한다.

## 12. AI 요약 API

| 개인 AI 기능 | `PROFESSOR` | `STUDENT` | 허용 Session 상태 | 다른 상태                    |
| ------------ | ----------- | --------- | ----------------- | ---------------------------- |
| LIVE Summary | 허용        | 허용      | `LIVE`            | `409 SESSION_STATE_CONFLICT` |
| LIVE Chat    | 허용        | 허용      | `LIVE`            | `409 SESSION_STATE_CONFLICT` |
| REVIEW Chat  | 허용        | 허용      | `COMPLETED`       | `409 SESSION_STATE_CONFLICT` |

개인 AI 리소스와 `REQUESTER_ONLY` Job은 생성자/요청자에게만 노출하며, 비소유자·비요청자·비멤버에는 `404`를 반환한다.

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

- 권한: Course 멤버. `PROFESSOR`와 `STUDENT`에게 동일하게 허용한다.
- `LIVE` Session에서 현재까지 또는 선택한 final Transcript 범위를 요약한다.
- 같은 Session에 연결되고 `READY`인 PDF 조각만 검색한다. `UPLOADED`, `PROCESSING`, `FAILED` 또는 분리된 자료는 제외한다.
- 요청 범위에 final Segment가 0건이면 AIJob을 만들지 않고 `409 SUMMARY_TRANSCRIPT_NOT_READY`와 `아직 확정된 강의 내용이 없습니다. 잠시 후 다시 시도해 주세요.`를 반환한다.
- 요약 source Transcript version이 `FAILED`이면 AIJob을 만들지 않고 `409 SUMMARY_SOURCE_UNAVAILABLE`와 `Transcript 처리 문제로 요약을 만들지 못했습니다.`를 반환한다.
- 요청 범위에 final Segment가 1건 이상이면 `202 Accepted`, AIJob을 반환한다.
- 요청자는 `GET /jobs/{job_id}`를 polling하고 `SUCCEEDED` 결과 URL의 요약 조회 API로 저장된 최종 결과만 확인한다. 생성 중인 부분 문장·token은 저장·공유·streaming하지 않는다.
- 인증되지 않은 요청은 `401`을 반환한다. 비멤버에게는 Session 존재를 숨기고 `404 RESOURCE_NOT_FOUND`를 반환한다.

### 12.2 요약 조회

```http
GET /api/v1/sessions/{session_id}/summaries?summary_type=LIVE&cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- `summary_type`: `LIVE`, `FINAL`. 이 query는 필수이며 필터 없이 두 유형을 섞어 상태를 반환하지 않는다.
- 응답은 `items`, `next_cursor`와 필수 `summary_status`, `summary_reason`을 포함한다. `summary_type=LIVE`에서 Session이 `READY`이거나 `LIVE`이면서 요청·저장 Summary가 아직 없는 정상 상태는 `summary_status=NOT_STARTED`, `summary_reason=null`이다. `summary_type=FINAL`은 아래 `/record.summary.state`의 상태·이유를 그대로 projection하며 `NOT_STARTED`를 사용하지 않는다.
- 목록은 `created_at DESC, id DESC`로 안정적으로 정렬한다.
- 성공한 `LIVE` 요약은 요청자 전용으로 반드시 저장하고, `FINAL` 요약은 Course 멤버에게 공개한다.
- Summary 저장이 완료돼 `result.resource_url`로 조회할 수 있을 때만 AIJob을 `SUCCEEDED`로 변경한다.
- `LIVE → PROCESSING` 전이 transaction이 `LIVE` Summary·해당 Job을 즉시 삭제해 목록과 새 RAG 대상에서 사라지게 하고, 느린 Worker 결과는 fence한다. 삭제된 기존 Summary·Job ID의 단건 조회·polling은 `404 RESOURCE_NOT_FOUND`이며, 같은 key·request hash의 purge-scoped terminal 멱등성 재요청은 원래 TTL 동안 `410 LIVE_AI_RESULT_PURGED`를 replay한다.
- `FINAL`은 class 종료 후 생성된 강의 요약을 의미한다.
- `FINAL_SUMMARY` Job은 최신 HQ TranscriptVersion이 `source=RECORDING`, `status=FINALIZED`, final Segment 1건 이상일 때만 자동 생성한다. canonical LIVE version이 `FINALIZED`여도 자동 생성 근거로 사용하지 않는다.
- 유효한 RECORDING `FINALIZED` source와 final Segment가 있지만 필수 `FINAL_SUMMARY` Job이 없으면 watchdog도 실패 Job을 합성하지 않는다. `/record.summary.state.status=DATA_INTEGRITY_ERROR`, `reason=null`, `summary_url=null`로 원장 누락을 안전하게 표시한다.
- 최신 RECORDING TranscriptVersion이 정상 `EMPTY`이면 `FINAL_SUMMARY` Job을 만들지 않는다. 통합 기록 응답은 `/record.summary.state.status=NOT_APPLICABLE`, `reason.code=NO_FINAL_TRANSCRIPT`, `summary_url=null`, message `요약할 강의 내용이 없습니다.`를 반환한다.
- Recording source가 처음부터 없으면 LIVE drain terminal 직후, Recording은 있지만 최신 RECORDING TranscriptVersion이 `FAILED`이거나 `ended_at + 10분`까지 HQ 결과가 없으면 해당 시점에 `FINAL_SUMMARY` Job 없이 상태를 확정한다. `/record.summary.state.status=FAILED`, reason code `SUMMARY_SOURCE_UNAVAILABLE`, `summary_url=null`, message `Transcript 처리 문제로 요약을 만들지 못했습니다.`를 반환한다.
- HQ 무결과·미생성에서 보존된 LIVE canonical을 완료 기록·Summary final source로 사용할지는 TBD이며, 현재 자동 `FINAL_SUMMARY`는 LIVE를 source로 사용하지 않는다.
- 저장된 Summary는 생성에 사용한 `source_transcript_version_id`를 보존한다.
- `/record.summary.state`는 다음 원장 조합만 반환한다. `DATA_INTEGRITY_ERROR`는 provider 오류가 아니라 서버 원장 불일치를 감춘 안전한 상태이며 `reason=null`, `summary_url=null`이다.

| source·Job·결과 조건                                                                                                                                                      | `status`               | `reason`                     | Job 없음의 의미         |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | ---------------------------- | ----------------------- |
| HQ source gate가 아직 terminal이 아닌 `PROCESSING`                                                                                                                        | `PENDING`              | `null`                       | 정상 대기               |
| `PROCESSING`의 attempt 관계없이 active한 Job 또는 `COMPLETED` 후 명시적 Summary 재시도 Job(`attempt>1`)이 `PENDING`, `RUNNING`                                            | `PENDING`              | `null`                       | 해당 없음               |
| HQ retry 성공 후 `SESSION_POSTPROCESSING attempt>1` 복구가 active이며 eligible source의 Job이 아직 없거나, 복구가 새 `FINAL_SUMMARY attempt=1`을 생성해 active            | `PENDING`              | `null`                       | 정상 복구 중            |
| `FINAL_SUMMARY` Job과 저장 Summary가 일치하고 Job이 `SUCCEEDED`                                                                                                           | `AVAILABLE`            | `null`                       | 해당 없음               |
| `FINAL_SUMMARY` Job이 `FAILED`                                                                                                                                            | `FAILED`               | `null`                       | 해당 없음               |
| 최신 RECORDING TranscriptVersion이 정상 `EMPTY`                                                                                                                           | `NOT_APPLICABLE`       | `NO_FINAL_TRANSCRIPT`        | 정상적으로 Job 생략     |
| Recording source 없음, RECORDING `FAILED` 또는 10분까지 HQ 미완료                                                                                                         | `FAILED`               | `SUMMARY_SOURCE_UNAVAILABLE` | 정상적으로 Job 생략     |
| 복구 coordinator가 terminal인데 eligible source에 Job이 없음, `SUCCEEDED` Job에 Summary 결과가 없음, 복구와 무관한 `COMPLETED` 최초 Job이 active이거나 필수 원장이 불일치 | `DATA_INTEGRITY_ERROR` | `null`                       | 서버 데이터 무결성 오류 |

### 12.3 요약 단건 조회

```http
GET /api/v1/summaries/{summary_id}
```

- 저장된 `LIVE` 요약은 요청자만, `FINAL` 요약은 Course 멤버가 조회한다. 미인증은 `401`, 개인 요약의 비요청자·비멤버와 Session 종료로 삭제된 기존 LIVE Summary ID에는 존재 여부를 숨기는 `404`를 반환한다.
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

- 권한: Course 멤버. `PROFESSOR`와 `STUDENT`에게 동일하게 허용한다.
- `mode`: `LIVE`, `REVIEW`
- `LIVE`는 Session이 `LIVE`일 때만, `REVIEW`는 Session이 `COMPLETED`일 때만 생성한다. mode와 Session 상태가 다르면 `409 SESSION_STATE_CONFLICT`를 반환한다. `PROCESSING`에서는 두 mode 모두 생성하지 않는다.
- 대화는 생성한 사용자 개인에게만 노출한다. LIVE Chat의 멱등성 원장은 `purge_on_session_end=true`로 범위를 표시한다. 종료 뒤 기존 terminal 키·동일 request hash는 `410 LIVE_AI_RESULT_PURGED`를 24시간 replay하고, 새 키 요청은 `409 SESSION_STATE_CONFLICT`다.
- 인증되지 않은 요청은 `401`을 반환한다. 비멤버에게는 Session 존재를 숨기고 `404 RESOURCE_NOT_FOUND`를 반환한다.

### 13.2 대화 목록

```http
GET /api/v1/sessions/{session_id}/chats?cursor=<cursor>&limit=20
```

- 권한: Course 멤버이면서 현재 사용자가 생성한 대화
- 현재 사용자가 생성한 대화만 반환한다.
- 비멤버에게는 Session 존재를 숨기고 `404`를 반환한다. class 종료로 LIVE Chat이 삭제되면 목록에서 즉시 사라진다.

### 13.3 대화 단건

```http
GET /api/v1/chats/{chat_id}
```

- 권한: 대화 소유자이면서 현재 Course 멤버인 사용자
- 비소유자·비멤버와 Session 종료로 삭제된 기존 LIVE Chat ID에는 존재를 공개하지 않고 `404`를 반환한다.

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
- 서버는 3.1.1절에 따라 `content`의 앞뒤 공백 제거·Unicode NFC 정규화 후 1~2,000 code point를 검증한다. 초과·빈 결과는 잘라 저장하지 않고 `422 VALIDATION_ERROR`와 안정적인 details를 반환하며, USER Message `content`에는 정규화 결과를 저장한다.
- Chat mode와 Session 상태는 메시지 수락 시점에도 다시 검증한다. `LIVE` Chat은 Session `LIVE`, `REVIEW` Chat은 Session `COMPLETED`에서만 허용하며 다르면 `409 SESSION_STATE_CONFLICT`를 반환한다. Session 종료 transaction이 먼저 LIVE Chat을 삭제한 경쟁에서 이전 ID 요청은 존재를 숨기는 `404`를 반환한다. 이미 terminal인 동일 멱등 요청은 `410 LIVE_AI_RESULT_PURGED`를 replay한다.
- 서버는 같은 Session에 연결되고 `READY`인 PDF, final Transcript와 Q&A만 검색한다. `UPLOADED`, `PROCESSING`, `FAILED` 또는 분리된 자료는 제외한다.
- 근거가 부족하면 확인할 수 없음을 응답한다.
- 성공: `202 Accepted`. 앞뒤 공백 제거·Unicode NFC 정규화·검증을 거친 사용자 Message, `REQUESTER_ONLY CHAT_RESPONSE` AIJob, outbox와 terminal 멱등성 응답을 한 transaction에서 commit하고 함께 반환한다. USER Message의 `response_job_id`는 Job ID와 같고 Job `target.resource_type=CHAT_MESSAGE`, `target.resource_id=USER Message ID`로 immutable 입력 turn을 가리킨다.
- 요청자는 반환된 Job ID를 16.8절 규칙으로 polling하고 `SUCCEEDED` Job의 `result.resource_url`로 저장된 최종 Assistant Message를 조회한다. 생성 중 token·부분 Assistant Message는 저장·공유·streaming하지 않는다.
- 인증되지 않은 요청은 `401`을 반환한다. 비소유자·비멤버와 Session 종료로 삭제된 기존 LIVE Chat ID에는 존재를 숨기고 `404 RESOURCE_NOT_FOUND`를 반환한다.

### 13.5 메시지 목록

```http
GET /api/v1/chats/{chat_id}/messages?cursor=<cursor>&limit=20
```

- 권한: 대화 소유자이면서 현재 Course 멤버인 사용자
- 정렬: `sequence ASC`
- 비소유자·비멤버와 Session 종료로 삭제된 기존 LIVE Chat·Message ID에는 존재를 숨기고 `404`를 반환한다.
- `USER` Message는 앞뒤 공백 제거·Unicode NFC 정규화된 1~2,000자 `content`, non-null `response_job_id`, `job_id=null`, `model_name=null`, `prompt_version=null`, `evidence=[]`다. `ASSISTANT` Message는 빈 문자열이 아닌 최종 `content`, 생성 원인 non-null `job_id`, `response_job_id=null`을 반환한다. Assistant content에는 USER용 2,000자 상한을 적용하지 않으며 Evidence는 0개 이상일 수 있고 모델·프롬프트 공개 정책에 따라 `model_name`, `prompt_version`은 null일 수 있다.
- 새로고침 후에도 USER Message의 `response_job_id`로 같은 turn Job을 polling할 수 있다. Job의 `target` 단건 URL은 해당 USER Message를, `SUCCEEDED result` URL은 해당 ASSISTANT Message를 가리킨다.
- Assistant Message의 Evidence는 `source_kind`, 안전한 `label` snapshot, 권한 검사를 거치는 nullable 상대 경로 `link`만 공개한다. DB 식별자인 `knowledge_chunk_id`, 내부 typed FK 구분, storage key·path와 pagination cursor는 포함하지 않는다.
- 공개 `source_kind`는 정확히 `MATERIAL`, `TRANSCRIPT`, `QUESTION`, `ANSWER` 중 하나다. 학생 질문과 AI 대표질문의 내부 구분은 둘 다 `QUESTION`으로 projection하며 별도 공개 enum으로 노출하지 않는다.
- `label`은 Evidence 생성 시점에 저장한 non-empty 표시용 snapshot이다. 자료명·페이지, Transcript 시간 범위, “학생 질문”·“AI 대표질문”·“교수자 답변”처럼 사용자가 이해할 정보만 포함하고 학생 식별정보나 내부 ID·경로를 포함하지 않는다. 정확한 문자열 format은 UI locale에 맡긴다.
- `source_kind`와 non-null `link`는 아래 4개 공개 조합 중 정확히 하나여야 한다. 외부 URL이나 다른 종류의 경로를 섞은 조합은 계약 위반이며, 공개 이동 대상이 없을 때만 같은 종류에서 `link=null`을 사용한다.

| `source_kind` | `link` 형태                                                                                                                                          |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MATERIAL`    | `/api/v1/materials/{material_id}/content` + 페이지가 있으면 `#page={page_number}`                                                                    |
| `TRANSCRIPT`  | `/api/v1/sessions/{session_id}/transcript?transcript_version_id={transcript_version_id}&start_sequence={start_sequence}&end_sequence={end_sequence}` |
| `QUESTION`    | 학생 질문은 `/api/v1/questions/{question_id}`, AI 대표질문은 `/api/v1/representative-questions/{representative_question_id}`                         |
| `ANSWER`      | `/api/v1/answers/{answer_id}`                                                                                                                        |

- `TRANSCRIPT` link의 version ID와 inclusive sequence 범위는 같은 Evidence source snapshot에서 가져오며 Segment ID·배열 순번·cursor를 사용하지 않는다. `QUESTION` link가 어느 질문 경로를 사용해도 `source_kind`는 `QUESTION`으로 같다.
- source가 분리·삭제되었거나 현재 사용자에게 안전한 이동 경로를 제공할 수 없으면 `source_kind`·`label`은 유지하고 `link=null`로 반환한다. 분리된 Material과 폐기된 AI 대표질문은 새 AI 검색에 사용하지 않는다. Evidence가 참조하는 폐기 대표질문의 내부 tombstone·Chunk는 provenance로만 보존하며 공개 Evidence는 `source_kind=QUESTION`, 저장한 `label`, `link=null`로 표시한다. `GET /api/v1/representative-questions/{id}`는 항상 `404`를 반환하고, 마지막 Evidence 삭제와 tombstone·Chunk hard delete는 같은 transaction에서 원자 처리한다.

### 13.6 메시지 단건 조회

```http
GET /api/v1/chat-messages/{message_id}
```

- 현재도 Course 멤버인 Chat 소유자만 조회한다.
- `CHAT_RESPONSE` Job이 `SUCCEEDED`일 때 `result.resource_url`은 이 경로를 가리킨다. 요청자는 Job polling 후 이 GET으로 저장된 최종 Assistant Message를 복구한다.
- 비소유자·비멤버와 Session 종료로 삭제된 기존 LIVE Message ID에는 존재를 숨기고 `404`를 반환한다.

## 14. AI 작업 API

### 14.1 작업 조회

```http
GET /api/v1/jobs/{job_id}
```

- 권한: 작업의 Session에 접근 가능하고 해당 Job의 공개 범위에 포함되는 사용자
- 응답: 작업 유형, 상태, 진행률, 오류, 대상·결과 리소스 링크, 결과 비가용 사유, 시작·종료 시각
- `REQUESTER_ONLY` Job은 요청자에게만 노출한다. 비요청자·비멤버와 Session 종료로 삭제된 기존 개인 LIVE Job ID에는 존재 여부를 숨기고 `404`를 반환한다. 삭제된 Job을 만든 mutation의 동일 terminal 멱등 요청만 24시간 `410 LIVE_AI_RESULT_PURGED`를 replay한다.
- `CHAT_RESPONSE` Job의 `target` 리소스는 요청 transaction이 저장한 정확한 USER Message이며 모든 attempt에서 변경하지 않는다. `SUCCEEDED result`는 저장된 최종 ASSISTANT Message를 가리킨다.
- 일반 이력을 보관하지 않는 성공 `QUESTION_CLUSTERING` generation이 새 결과로 교체되면 과거 Job은 `SUCCEEDED`를 유지하되 `result=null`, `result_unavailable_reason=SUPERSEDED`다. 이는 Job 실패나 데이터 오류가 아니다.
- 오류 메시지는 민감한 입력과 외부 모델 응답 원문을 포함하지 않는다.

### 14.2 작업 재시도

```http
POST /api/v1/jobs/{job_id}/retry
Idempotency-Key: <key>
```

- 권한: 요청형 작업은 요청자, 공유 후처리 작업은 Course `PROFESSOR`다.
- `FAILED`인 작업만 재시도한다.
- `retryable=false`인 작업은 `409 AI_JOB_NOT_RETRYABLE`, `FAILED`가 아닌 작업은 `409 AI_JOB_STATE_CONFLICT`를 반환한다.
- `LIVE_INCREMENTAL` 클러스터링의 retry-reserved Job은 시스템 scheduler가 전용 transaction으로 재시도한다. 사용자가 이 endpoint를 호출하면 `409 AI_JOB_RETRY_SYSTEM_MANAGED`를 반환한다.
- `FINAL` 클러스터링의 공개 재시도는 원래 실패가 완료 판정에 반영되어 Session이 `COMPLETED`가 된 뒤에만 허용한다. 아직 `PROCESSING`이면 `409 AI_JOB_STATE_CONFLICT`를 반환한다.
- 성공: `202 Accepted`, 같은 Job ID와 `attempt + 1`, `status=PENDING`인 Job을 반환한다.
- 현재 시도의 progress, error, `started_at`, `finished_at`은 `null`, `retryable`은 `false`로 초기화된다.
- 이전 attempt worker의 늦은 결과는 Job ID·attempt·실행 token·`RUNNING` 상태를 대조해 반영하지 않는다.
- `CHAT_RESPONSE` 재시도는 같은 Job 행의 `target` USER Message를 변경하지 않고 원본 입력으로 재사용한다. 새 USER Message를 생성하지 않는다.
- `ANSWER_ORGANIZATION`은 Course 교수자만 실패 Job을 재시도하며 Answer에 고정된 source 범위를 재사용한다. 이미 성공한 Job은 재생성하지 않는다.
- 실패한 `RECORDING_TRANSCRIPTION`은 이 기존 공용 retry endpoint의 Course `PROFESSOR` 권한으로만 재시도하며 별도 HQ 전용 endpoint나 교수자 control을 추가하지 않는다. `COMPLETED` 후 성공하면 서버가 같은 `SESSION_POSTPROCESSING` coordinator 행을 `attempt + 1`로 자동 requeue해 Answer mapping·canonical Knowledge 연결·새로 eligible한 `FINAL_SUMMARY`를 멱등 복구한다. 사용자가 coordinator를 따로 retry할 필요가 없다.

### 14.3 Session 공용 작업 목록

```http
GET /api/v1/sessions/{session_id}/jobs?job_type=<type>&status=<status>&cursor=<cursor>&limit=20
```

- 권한: Course 멤버
- 자료 처리, 질문 클러스터링, `ANSWER_ORGANIZATION`, `RECORDING_TRANSCRIPTION`과 Session 후처리처럼 참여자가 상태를 알아야 하는 공용 Job만 반환한다.
- 목록은 `created_at DESC, id DESC`로 안정적으로 정렬하며 `job_type`, `status`를 cursor에 고정한다.
- 잘못된 Session UUID·`job_type`·`status`·cursor·`limit` 형식 또는 `limit` 범위는 `422 VALIDATION_ERROR`다. 형식은 맞지만 서명이 틀리거나 현재 필터와 맞지 않는 cursor는 `400 INVALID_CURSOR`다.
- 개인 LIVE 요약과 Chat Job은 포함하지 않는다. 질문 초안은 동기 `200` 응답이며 Job이 아니다.
- `QUESTION_CLUSTERING`은 `clustering_mode`, input watermark, base revision을 공개한다. LIVE 실패 재시도는 시스템이 같은 Job 행의 `attempt + 1`로 수행한다. Session 종료가 대체한 LIVE 실행은 `SUPERSEDED`, `retryable=false`로 다시 실행하지 않는다. 최종 clustering 실패는 `COMPLETED` 기록에서 교수자가 같은 Job 행을 재시도할 수 있고 Session을 `PROCESSING`으로 되돌리지 않는다.
- 현재 generation을 만든 성공 `QUESTION_CLUSTERING`의 result는 단일 Cluster가 아니라 `resource_type=QUESTION_CLUSTER_GENERATION`, 문자열 generation 번호인 `resource_id`, 해당 scope Cluster 목록 `resource_url`을 반환한다. 새 generation으로 교체되면 과거 Job은 `SUPERSEDED` 규칙을 따른다.
- FINAL Job은 최초 실행의 `final_answered_through_at=Session.ended_at`을 공개한다. 실패 뒤 Course 교수자가 같은 Job을 명시적으로 재시도하면 학생 질문 watermark만 유지하고, `base_revision`은 현재 revision으로, Answer 상한은 재시도 수락 시각으로 다시 캡처해 실패 후 새로 답변된 AI 대표질문도 입력에 포함한다. 이미 성공한 FINAL을 수업 종료 뒤 text Answer 때문에 다시 만드는 정책은 TBD이다.
- FINAL `SUCCEEDED`는 해당 attempt의 eligible input set과 Cluster membership이 일치해 모든 input이 정확히 한 번씩 등장함을 보장한다. 분류 불가 input은 하나의 명시적인 `기타` Cluster에 배치하며 누락·중복이나 `기타` 분산이 있으면 성공으로 commit하지 않는다.
- `RECORDING_TRANSCRIPTION`은 `target.resource_type=RECORDING`, `visibility=SHARED`, `blocks_session_completion=true`이다. 성공하면 `result.resource_type=TRANSCRIPT_VERSION`과 지정 version 조회 URL을 반환한다.
- `SESSION_POSTPROCESSING`은 Session 종료 transaction에서 `PENDING`으로 생성되는 SHARED·blocking coordinator다. source terminal 전에는 claim하지 않고, 자신의 terminal 전이와 downstream blocking Job 생성을 같은 transaction에 commit한다.
- `ANSWER_ORGANIZATION`은 `target.resource_type=ANSWER`, `visibility=SHARED`, `blocks_session_completion=true`다. 성공 `result`도 Answer 단건 URL을 가리키며 그 응답의 `organization_state.organization`에서 저장 결과를 조회한다.

## 15. 수업 기록 API

### 15.1 통합 기록 조회

```http
GET /api/v1/sessions/{session_id}/record
```

- 권한: Course 멤버
- 허용 Session 상태: `PROCESSING`, `COMPLETED`
- 잘못된 Session UUID는 `422 VALIDATION_ERROR`다.
- `/record`는 큰 배열을 담는 aggregate가 아니라 수업 기록의 유한한 manifest·index다. Session과 권한이 허용한 nullable Recording 메타데이터는 직접 반환하지만 Summary 본문과 Material·Transcript Segment·Gap·질문·Cluster·Answer·Job 배열은 포함하지 않는다.
- 대신 각 영역의 `total_count`와 cursor 목록 `list_url`을 반환한다. Transcript는 선택 version의 `selected_version_id`, `segment_count`, `gap_count`, `timeline_url`, `versions_url`을, Cluster는 `clustering_state`와 `CURRENT`·`FINAL` 각각의 count·URL을 반환한다. 모든 URL은 `session_id`와 필요한 stable filter를 포함하고 cursor나 배열 순번을 포함하지 않는다.
- `transcript.selected_version_id`가 non-null이면 `timeline_url`은 정확히 `/api/v1/sessions/{session_id}/transcript?transcript_version_id={selected_version_id}` 형태로 같은 ID를 고정한다. `selected_version_id=null`이면 query 없는 `/api/v1/sessions/{session_id}/transcript`만 반환한다.
- 기록의 질문 `list_url`은 종료 후 불변인 `created_at DESC, id DESC`를 쓰는 `sort=RECENT`를 포함한다. 개별 목록은 기본 20·최대 100의 불투명 keyset cursor로 독립 조회한다.
- `total_count`와 상태는 `/record` 응답 transaction 시점의 정보이며 목록 전체를 snapshot token으로 잠그지 않는다. `PROCESSING`의 상태·개수가 바뀌면 `/record`를 다시 조회한다.
- 공용 Job `total_count`와 `list_url`에는 자료 처리·Session 후처리 등 SHARED Job만 포함하고 개인 요약·Chat Job은 포함하지 않는다. 질문 초안은 동기 `200` 응답이므로 Job이 아니다.
- 일부 AI 작업이 실패해도 연결된 PDF, Transcript와 Q&A의 count·상태·조회 경로는 반환한다. 분리된 Material은 즉시 count와 목록에서 제외한다.

| `/record` 필드      | 의미                                                                                        |
| ------------------- | ------------------------------------------------------------------------------------------- |
| `session`           | 현재 Session 상태·시각·제목                                                                 |
| `recording`         | 권한이 허용한 nullable Recording 메타데이터와 안정적인 `recording_url`                      |
| `materials`         | 현재 연결된 Material `total_count`, `list_url`                                              |
| `transcript`        | nullable aggregate·`selected_version_id`, Segment·Gap count, `timeline_url`, `versions_url` |
| `summary`           | 최종 Summary 상태(`DATA_INTEGRITY_ERROR` 포함), nullable `summary_url`, `summaries_url`     |
| `questions`         | 학생 질문 `total_count`, `sort=RECENT`인 `list_url`                                         |
| `question_clusters` | clustering state, `CURRENT`·`FINAL` 각각의 `total_count`, `list_url`                        |
| `answers`           | Answer `total_count`, `list_url`                                                            |
| `jobs`              | 공용 AIJob `total_count`, `list_url`                                                        |

### 15.2 녹음 메타데이터 조회

```http
GET /api/v1/sessions/{session_id}/recording
```

- 첫 성공 `audio.start` 전에는 Recording이 없고, 성공 뒤에는 Session당 외부에 정확히 하나의 논리 Recording aggregate를 만들고 `CAPTURING`으로 전이한다. 같은 `client_stream_id`의 reconnect는 이 Recording을 재사용한다.
- Recording은 브라우저 로컬 녹음과 upload·HQ STT·playback의 외부 상태를 나타낸다. MVP는 하나의 `RecordingUpload`가 하나의 비공개 temporary object를 이어 쓰고, 완료 시 하나의 final object로 promote하는 논리 manifest를 사용한다. part·fragment 행과 물리 key는 만들거나 외부 API에 노출하지 않는다.
- 응답은 `id`, `session_id`, 공개 상태, `version`, nullable `content_type`·`byte_size`·`duration_ms`·`playback_url`과 생성·갱신 시각만 포함한다. storage key, 서버 경로, fragment key와 manifest는 포함하지 않는다.
- 모든 조회에서 현재 인증과 Course 접근 권한을 다시 확인한다. MVP에서 현재 Course 멤버는 metadata와 playback을 조회할 수 있고, upload는 첫 publisher인 Course `PROFESSOR`만 수행한다. 브라우저는 capture 전에 녹음 동의를 받고 PR-22 UI는 Blob을 IndexedDB에만 저장한다. 보관 정책은 PR-28 범위이며 이 HTTP API와 브라우저 동의는 법적 동의를 증명하지 않는다.
- Recording이 없거나 존재를 공개하지 않으면 `404 RECORDING_NOT_FOUND`를 반환한다.

### 15.2.1 녹음 조기 삭제와 보관

```http
DELETE /api/v1/sessions/{session_id}/recording
Idempotency-Key: <key>
```

- 권한: 해당 Course를 생성한 `PROFESSOR`. Session이 `COMPLETED`이고 final object가 있는 Recording만 삭제할 수 있다. 다른 상태는 `409 RECORDING_DELETE_CONFLICT`다.
- 완료 시점부터 30일 뒤에도 같은 삭제 흐름을 자동 실행한다. 성공 commit 뒤 metadata·playback은 즉시 `404 RECORDING_NOT_FOUND`이고, final object는 내부 deletion ledger가 재시도해 삭제한다.
- 삭제는 복구하지 않으며 Transcript·Question·Answer와 완료 기록의 다른 영역은 유지한다.

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
  "content_type": "audio/webm",
  "total_bytes": 12345678,
  "duration_ms": 3600000
}
```

- `Idempotency-Key`는 필수이며 같은 요청의 재실행은 기존 upload를 반환한다.
- 첫 publisher와 같은 `client_stream_id`를 사용하는 Course `PROFESSOR`만 초기화할 수 있다.
- 정상 종료 직후에는 Session `PROCESSING`과 Recording `UPLOAD_PENDING`에서 초기화한다. 만료·실패한 같은 논리 녹음의 복구는 `UPLOAD_PENDING|UPLOADING|FAILED`에서 새 upload를 만들 수 있고, 10분 watchdog 뒤 Session이 이미 `COMPLETED`여도 복구를 허용하되 Session 상태를 되돌리지 않는다. `CAPTURING|UPLOADED` 또는 그 밖의 조합은 `409 RECORDING_STATE_CONFLICT`다.
- 이미 다른 active upload가 있으면 `409 RECORDING_UPLOAD_CONFLICT`를 반환한다.
- 허용 `content_type`은 parameter를 제외하고 정규화한 `audio/webm`, `audio/mp4`다. `total_bytes`는 1~100,000,000 bytes, `duration_ms`는 0 이상이어야 한다. 다른 형식은 `415 UNSUPPORTED_RECORDING_FORMAT`, 크기 위반은 `413 FILE_TOO_LARGE`다.
- 성공: `201 Created`. Recording을 `UPLOADING`으로 바꾸고 불투명 upload ID, 현재 byte offset, 전체 byte 수와 생성 시각부터 정확히 24시간 뒤의 만료 시각을 반환한다.

### 15.4 upload offset 조회와 chunk 전송

```http
GET /api/v1/recording-uploads/{upload_id}
PATCH /api/v1/recording-uploads/{upload_id}
Upload-Offset: <현재 서버 offset>
X-Chunk-SHA256: <64자 lowercase hex>
Content-Type: application/octet-stream
```

- `GET`은 upload ID, 상태, `offset_bytes`, `total_bytes`, `expires_at`을 반환한다. 서버 또는 DB 재시작 뒤에도 이 offset이 재개 위치의 진실이다.
- `PATCH`는 최대 8,388,608 bytes의 binary chunk를 받는다. `Upload-Offset`과 `X-Chunk-SHA256`은 필수이며 chunk checksum은 SHA-256 lowercase hex다.
- chunk 자체가 8,388,608 bytes를 넘으면 `413 FILE_TOO_LARGE`로 거부한다. `offset + chunk byte`가 `total_bytes`를 넘으면 `409 UPLOAD_OFFSET_MISMATCH`를 반환한다.
- chunk 요청은 서버가 확인한 현재 byte offset에서만 이어 쓴다. 다른 offset이면 `409 UPLOAD_OFFSET_MISMATCH`와 안전한 현재 offset을 반환한다.
- upload가 없거나 존재를 공개하지 않으면 `404 RECORDING_UPLOAD_NOT_FOUND`, 만료됐으면 `410 RECORDING_UPLOAD_EXPIRED`를 반환한다.
- checksum 형식·chunk checksum 불일치는 `422 RECORDING_CHECKSUM_MISMATCH`를 반환하며 bytes를 이어 쓰지 않는다.
- 각 요청은 인증, Course 권한과 최초 publisher 연결을 다시 검증한다. 내부 임시 경로와 storage key는 반환하거나 로그에 남기지 않는다.

RecordingUpload의 공개 상태는 `ACTIVE`, `COMPLETED`, `EXPIRED`, `FAILED`이다. 만료된 active upload는 temporary object 정리 후 `EXPIRED`로 terminal 처리되고 Recording을 `UPLOAD_PENDING`으로 되돌린다. 실패 terminal도 새 init을 허용하며 동시에 active upload는 하나뿐이다.

### 15.5 upload 완료

```http
POST /api/v1/recording-uploads/{upload_id}/complete
Idempotency-Key: <key>
Content-Type: application/json

{"sha256":"<전체 녹음의 64자 lowercase hex>"}
```

- `Idempotency-Key`는 필수이다. 동일 요청은 최초 응답을 재사용하고 새 Job을 중복 생성하지 않는다.
- 서버가 전체 byte 수와 선택된 checksum 규칙을 만족하는지 확인한 뒤 논리 Recording을 `UPLOADED`로 확정한다.
- 같은 transaction에서 Recording을 `UPLOADED`로 확정하고 `source=RECORDING`, `status=FINALIZING`인 다음 Transcript version과 `RECORDING_TRANSCRIPTION` Job을 생성한다.
- Job은 `target=RECORDING`, `visibility=SHARED`, `blocks_session_completion=true`이며 성공 후 `result=TRANSCRIPT_VERSION`을 가리킨다.
- 성공: `202 Accepted`, `UPLOADED` Recording, 생성된 Transcript version과 Job을 반환한다. 같은 멱등 요청은 세 리소스를 그대로 재사용한다.
- 전체 object SHA-256이 request의 `sha256`과 다르면 `422 RECORDING_CHECKSUM_MISMATCH`를 반환하고 Upload는 재시도 가능한 `ACTIVE` 상태를 유지한다.
- Transcript version·canonical 전환, Segment recording offset과 Gap final 표시는 `RECORDING_TRANSCRIPTION`, 그 후 Answer 재매핑·Knowledge 연결은 `SESSION_POSTPROCESSING` 계약을 따른다.

### 15.6 녹음 playback

```http
GET /api/v1/recordings/{recording_id}/playback
Range: bytes=<start>-<end>
```

- 요청마다 현재 인증과 Course 접근을 다시 검증한다. MVP에서는 현재 Course 멤버가 재생할 수 있고 upload 권한과 분리된 별도 download API는 제공하지 않는다.
- `UPLOADED` Recording만 재생할 수 있다. 그 전에는 `409 RECORDING_NOT_READY`, 없거나 비가시면 `404 RECORDING_NOT_FOUND`를 반환한다.
- 전체 재생은 `200 OK`, 유효한 byte Range 재생은 `206 Partial Content`를 사용한다. 범위가 유효하지 않으면 `416 RANGE_NOT_SATISFIABLE`을 반환한다.
- API는 final object를 proxy stream한다. `audio/webm` 또는 `audio/mp4` MIME을 유지하고 `Accept-Ranges`, `Content-Length`, 필요한 경우 `Content-Range`를 반환한다. 내부 storage key와 서버 경로를 외부에 노출하지 않는다.
- Transcript 문장 seek는 9절의 nullable recording offset을 사용한다.

## 16. WebSocket과 음성 스트리밍

스트리밍 STT는 MVP 필수 기능이다. OpenAPI 3.1은 WebSocket 양방향 메시지 계약을 표준적으로 표현하지 못하므로 이 장을 실시간 계약의 기준으로 사용하고, `openapi.yaml`의 `x-websocket-channels`는 구현 참고용 비표준 확장으로 취급한다. 계약이 안정되면 AsyncAPI 분리를 검토한다.

가장 중요한 원칙은 다음과 같다.

> WebSocket은 Session 공용 실시간 알림·음성 전송 수단이고, DB와 REST 조회 결과가 최종 진실이다. 개인 AI 결과는 REST polling으로만 확인한다.

#### 현재 구현 범위 (PR-12, PR-14)

`POST /api/v1/realtime-tickets`의 `SESSION_EVENTS_READ`·`SESSION_AUDIO_WRITE`와 두
WebSocket 경로가 구현됐다. FastAPI 프로세스의 publisher는 commit된 `outbox_events`에서
`session.updated`, 공용 `job.updated`, 익명 `question.created`·`question.updated`,
`reaction.updated`, `clustering.updated`, `transcript.final`을 전달한다. `transcript.partial`은
DB·Outbox에 저장하지 않는 연결 중 임시 event이며 replay 대상이 아니다. audio 경로는 단일
교수자 publisher claim, 고정 PCM frame 검증, 영속 ACK, reconnect fence, final Segment·Gap
저장과 deterministic fake STT를 제공한다. 실제 외부 STT provider 선택·별도 process 배포는
아직 미정이다. publisher memory는 원장이 아니며, cursor replay가 500개를 넘거나 cursor를
찾을 수 없으면 `resync.required`로 REST 복구를 요구한다.

### 16.1 전송 경계

| 전송 경로                                   | 방향                   | 사용자             | 책임                                                    |
| ------------------------------------------- | ---------------------- | ------------------ | ------------------------------------------------------- |
| `WS /api/v1/ws/sessions/{session_id}`       | 주로 서버 → 클라이언트 | Course 멤버        | Transcript, 질문, 반응, 답변과 Session의 공용 변경 알림 |
| `WS /api/v1/ws/sessions/{session_id}/audio` | 양방향                 | Course `PROFESSOR` | 저지연 PCM 전송과 ack·backpressure·resume 제어          |

- 질문 생성, 반응, 답변과 Session 상태 변경 같은 비즈니스 명령은 REST API로 수행한다.
- Session event WS와 audio WS는 별도 연결·티켓·책임을 유지한다. event WS로 audio frame이나 upload chunk를 보내지 않고 audio WS로 Session 공용 event를 broadcast하지 않는다.
- 첫 publisher의 같은 microphone source를 `PCM_S16LE` 16 kHz mono 500 ms live 경로와 브라우저 로컬 binary 녹음 경로로 동시에 분기한다. 로컬 녹음은 Session 종료 뒤 15.3~15.5절의 HTTP upload로 전송한다.
- 일반 Session 채널에 교수자 음성 원본을 broadcast하지 않는다.
- 개인 요약과 AI 채팅 결과를 Session 공용 채널에 broadcast하지 않는다.
- 개인 AI Job과 결과는 요청자가 `GET /jobs/{job_id}`와 Summary·Chat REST API를 polling해 확인한다. MVP는 별도 delta 스트림을 제공하지 않는다.

### 16.2 인증과 연결 권한

- Session 이벤트 채널: 해당 Session의 Course 멤버
- 음성 채널: 해당 Session의 Course `PROFESSOR`이면서 Session 상태가 `LIVE`
- 첫 성공 `audio.start`의 `client_stream_id`가 LIVE Session의 publisher를 claim한다. claim과 Recording `CAPTURING` 전이는 원자적으로 처리한다.
- 이미 claim된 Session에 다른 `client_stream_id`가 `audio.start`를 보내면 `AUDIO_PUBLISHER_CONFLICT`를 전송하고 WebSocket close code `4409`로 그 연결을 종료한다. active publisher의 식별정보는 오류에 포함하지 않는다.
- 동일한 `client_stream_id`는 새 1회용 ticket으로 네트워크 reconnect와 sequence resume을 시도할 수 있다. MVP v1은 첫 claim을 Session 종료까지 다른 탭·장치에 넘기지 않는다. 서버는 마지막 수신 frame마다 45초 liveness 시각을 갱신하지만, 그 시각 만료는 같은 stream의 reconnect를 막지 않을 뿐 다른 `client_stream_id`의 takeover 근거가 되지 않는다.
- 연결 시점뿐 아니라 재연결과 권한 변경 시점에도 멤버십을 다시 확인한다.
- 브라우저 WebSocket은 임의의 `Authorization` 헤더를 설정하기 어렵기 때문에 MVP는 단기·1회용 티켓 방식을 사용한다.
- 티켓 발급은 상태를 만드는 `POST`이므로 일반 인증 규칙과 같이 정확한 `Origin` allowlist를
  요구하며, 응답은 `Cache-Control: no-store`다.

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

| 이벤트                       | 주요 `data`                                                            | 공개 범위                          |
| ---------------------------- | ---------------------------------------------------------------------- | ---------------------------------- |
| `connection.ready`           | connection_id, role, server_time, heartbeat_interval_ms, resume_status | 연결 사용자                        |
| `resync.required`            | reason, resources                                                      | 연결 사용자                        |
| `transcript.partial`         | 임시 utterance와 revision                                              | Course 멤버                        |
| `transcript.final`           | 저장된 TranscriptSegment                                               | Course 멤버                        |
| `transcript.status`          | live STT 상태와 현재 LIVE TranscriptVersion 상태                       | Course 멤버                        |
| `transcript.version.updated` | 영구 TranscriptVersion 상태·canonical 변경                             | Course 멤버                        |
| `question.created`           | 익명 Question                                                          | Course 멤버                        |
| `question.updated`           | 익명 Question                                                          | Course 멤버                        |
| `clustering.updated`         | watermark·revision·generation·active/last Job 상태                     | Course 멤버                        |
| `reaction.updated`           | question_id, reaction_count                                            | Course 멤버                        |
| `answer.updated`             | Answer                                                                 | Course 멤버                        |
| `answer.deleted`             | answer_id, target_type, target_id                                      | Course 멤버                        |
| `session.updated`            | LectureSession                                                         | Course 멤버                        |
| `recording.updated`          | 안전한 SessionRecording 메타데이터                                     | 녹음 접근 정책이 허용한 사용자     |
| `job.updated`                | AIJob                                                                  | 공용 자료·후처리 Job의 허용 사용자 |

개인 LIVE 요약과 Chat Job은 공용 `job.updated`로 노출하지 않고 요청자의 Job·Summary·Chat REST polling에서만 확인한다. 질문 작성 초안은 동기 REST 응답으로 완료한다.
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
    "transcript_version_id": "transcript_version_01HXYZ",
    "item_type": "SEGMENT",
    "sequence": 38,
    "start_ms": 41000,
    "end_ms": 45200,
    "recording_start_ms": 41020,
    "recording_end_ms": 45220,
    "text": "다익스트라 알고리즘은 음수 가중치를 허용하지 않습니다.",
    "created_at": "2026-07-11T01:30:00Z"
  }
}
```

- final을 받으면 같은 `utterance_id`의 partial 표시를 제거한다.
- 저장 실패 시 final 이벤트를 보내지 않는다.
- Session 종료 직후 상태가 먼저 `PROCESSING`으로 바뀌고 STT drain 과정의 final 이벤트가 더 올 수 있다. `transcript.status`의 영구 version 상태가 `FINALIZED` 또는 `EMPTY`가 되기 전에는 LIVE final 생성이 끝났다고 가정하지 않는다.

live STT 전송 상태 후보는 `LISTENING`, `DEGRADED`, `FINALIZING`, `FINALIZED`, `STOPPED`이다. 이는 9절의 영구 `TranscriptVersion.status`와 별개이며 `transcript.status` payload는 두 상태를 구분해 전달한다.

HQ STT는 개별 `transcript.final`을 실시간으로 쏟아내 canonical 전환 중간 결과를 노출하지 않는다. `RECORDING_TRANSCRIPTION` commit 후 `transcript.version.updated`와 `job.updated`를 보내고, 클라이언트는 전용 Transcript REST로 HQ version·canonical을 복구한다. Answer mapping과 Knowledge 연결은 그 뒤 `SESSION_POSTPROCESSING`에서 별도로 완료된다.

### 16.6 재연결과 누락 복구

1. 클라이언트는 최근 event `cursor`, 리소스 버전과 마지막 final Transcript `sequence`를 메모리에 보관한다.
2. 연결이 끊기면 0, 1, 2, 5, 10, 30초 상한과 jitter를 둔 backoff로 재연결한다.
3. `POST /realtime-tickets` 요청의 `resume_cursor`에 최근 cursor를 넣어 새 티켓을 발급하고 연결한다.
4. 서버가 짧은 버퍼에서 재생할 수 있으면 현재 권한으로 필터한 이벤트를 재전달한다.
5. 커서가 만료됐거나 서버 재시작으로 재생할 수 없으면 `resync.required`를 보낸다.
6. 클라이언트는 `Session → Recording → TranscriptVersion·타임라인 → Questions/Answers → 본인의 Jobs/Chats` 순서로 REST를 다시 조회한다.

partial Transcript는 복구 대상이 아니다. 재연결할 때 기존 partial 표시를 제거하고 다음 partial 또는 final을 기다린다. Redis나 영구 event log를 MVP 필수로 확정하지 않았으므로 이벤트 replay는 best-effort이고 REST 복구가 필수다.

현재 Uvicorn 실행은 20초 ping·40초 pong timeout으로 연결을 감시한다. 애플리케이션 JSON heartbeat를 별도로 중복 전송하지 않는다.

### 16.7 음성 업로드 흐름

음성 WebSocket 연결 후 다음 순서를 사용한다.

1. 클라이언트가 JSON `audio.start`를 보낸다.
2. 서버가 첫 `client_stream_id`를 publisher로 claim하고 논리 Recording을 `CAPTURING`으로 만든다. 다른 stream의 경쟁 요청은 `AUDIO_PUBLISHER_CONFLICT`와 `4409`로 거부한다.
3. 서버가 Recording ID, claim 결과, 협상 형식과 전송 한도를 담은 `audio.ready`를 반환한다.
4. 클라이언트는 같은 microphone source를 live PCM 경로와 브라우저 로컬 녹음 경로로 분기하고, live 경로에서 sequence가 포함된 binary audio chunk를 전송한다.
5. 서버가 주기적으로 `audio.ack`와 필요 시 flow control을 보낸다.
6. 교수자가 class 종료를 확인하면 클라이언트는 종료 HTTP를 즉시 호출하고, `audio.stop` 전송과 MediaRecorder fragment flush·pause를 best-effort 병행한다. 서버는 종료 transaction commit과 함께 새 audio frame·audio 연결·resume을 차단하고 이미 받은 live 큐만 별도로 drain한다.
7. 종료 HTTP가 `202 Accepted`를 반환하면 Session은 이미 `PROCESSING`이다. active publisher는 pause한 로컬 녹음을 finalize해 `UPLOAD_PENDING` Recording의 resumable upload에 인계한다. 응답 유실·실패 후 REST가 `LIVE`를 확인하면 같은 MediaRecorder instance를 resume한다. `audio.stopped`와 로컬 finalize를 기다려 Session 전이를 늦추지 않는다.
8. 마지막 live final 저장과 drain이 끝나면 서버는 `audio.stopped`와 LIVE version의 `FINALIZED` 또는 `EMPTY` 상태를 담은 `transcript.status`를 보낸다. 이 후속 상태는 이미 commit된 Session 종료를 되돌리지 않는다.

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
  "max_in_flight": 1,
  "last_received_sequence": null,
  "last_processed_sequence": null
}
```

`audio.ack` 예시:

```json
{
  "type": "audio.ack",
  "received_through": 132,
  "processed_through": 132,
  "queue_depth_ms": 0
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
- 재연결 시 같은 `client_stream_id`를 사용하고 `resume_from_sequence`에는 가장 최근에 확인한 영속 watermark(`audio.ack.received_through` 또는 정상 `audio.stopped.last_received_sequence`)를 넣은 뒤 그 다음 sequence부터 재전송한다. 첫 frame 전 watermark는 공개 계약에서 `null`이다.
- 서버는 `(session_id, client_stream_id, chunk_sequence)`로 중복 chunk를 제거한다.
- reconnect의 `resume_from_sequence`은 서버가 영속적으로 ACK한 마지막 sequence와 같아야 한다. 다르면 `audio.resume_rejected`의 `SEQUENCE_EXPIRED`를 보내고 누락 구간을 LIVE TranscriptVersion의 `SEQUENCE_GAP`으로 남긴다. 이후 HQ version의 Segment·Gap은 LIVE version을 덮어쓰지 않고 별도 version에 귀속된다.
- reconnect 시 영속 `last_processed_sequence`가 `last_received_sequence`보다 작으면, 재시작·연결 손실 뒤 STT relay 상태를 복원할 수 없다고 판단한다. 서버는 `audio.resume_rejected`의 `SERVER_STATE_LOST`와 final `Gap`을 남긴다. 이미 DB에 저장한 final Segment는 REST로 다시 조회한다.
- 현재 runtime은 application PCM 대기열을 두지 않고 한 frame의 STT handoff가 끝난 뒤 다음 frame을 읽는다. 따라서 `max_in_flight`는 `1`, `queue_depth_ms`는 항상 `0`이고 클라이언트는 ACK 뒤 다음 frame을 보낸다. STT handoff는 5초를 넘기면 재시도 가능한 `STT_UNAVAILABLE`로 끝나며 received watermark만 남긴다. 다중 frame queue와 `audio.flow_control`은 후속 확장 범위다.
- `max_chunk_bytes`는 header를 포함해 32,768 bytes이며 ACK는 각 수락 frame 뒤 전송한다. 이 값과 `max_in_flight`는 `audio.ready`에도 통지한다.
- audio WS의 PCM frame은 live STT 전송용이며 영구 녹음의 원본으로 취급하지 않는다. 영구 녹음은 같은 microphone source의 브라우저 로컬 branch를 15.3~15.5절로 upload해 저장한다.

교수자가 class 종료를 확인하면 클라이언트는 HTTP 종료 API를 즉시 호출하면서 `audio.stop`과 MediaRecorder fragment flush·pause를 best-effort 병행한다. HTTP 성공 또는 REST 조정으로 종료가 확인된 뒤에만 로컬 녹음을 finalize하고, `LIVE`면 같은 instance를 resume한다. `audio.stopped`는 현재 영속 watermark를 반환하지만 HTTP 종료의 선행조건이 아니다. 현재 브라우저 구현의 20초 ACK 대기는 멈춘 socket을 정리하기 위한 client 안전 상한이며, TBD인 server audio stop timeout이나 protocol 임계값을 확정하지 않는다. 서버는 Session을 즉시 `PROCESSING`으로 전환하고 새 binary frame·audio 연결·resume을 차단한다. 종료와 경합한 provider 결과는 저장하지 않고 `BACKPRESSURE_DROP` final Gap으로 남긴다. 종료 transaction은 LIVE version을 terminal로 확정하고 Recording은 `UPLOAD_PENDING`이 된다. upload complete 전에는 HQ STT를 시작하지 않으며, HQ canonical 전환은 Batch STT worker가 담당한다. 연결 손실로 받지 못한 live chunk는 Gap으로 기록하되 후처리 HQ version과 구분한다.

녹음 또는 upload 중 tab 종료 warning과 로컬 데이터 유실 안내는 화면 책임이다. 브라우저 로컬 저장 방식과 warning 해제 조건은 TBD이며 WebSocket control message로 만들지 않는다.

### 16.8 개인 AI 결과 polling

- LIVE Summary와 Chat turn은 REST 요청을 `202 Accepted + AIJob`으로 수락한다. Chat 생성 자체는 AI 실행이 아니므로 `201`을 반환한다.
- 요청자는 `GET /api/v1/jobs/{job_id}`를 polling해 `PENDING|RUNNING|SUCCEEDED|FAILED|CANCELLED|SUPERSEDED`를 확인한다. 구체 polling 간격은 서버 `429`·`Retry-After` 정책과 클라이언트 backoff를 따르며 수치는 TBD이다.
- 개인 AI는 성공한 최종 Summary 또는 Assistant Message만 DB에 저장한다. 부분 문장·token·중간 출력은 저장하거나 공용 WebSocket으로 보내지 않고 SSE·streaming HTTP·개인 WS도 제공하지 않는다.
- `SUCCEEDED` Job은 `result.resource_type`, `result.resource_id`, `result.resource_url`로 저장 결과를 가리킨다. 요약 또는 Assistant Message는 원인 `job_id`를 보관하며 요청자는 이 URL을 다시 GET해 결과를 복구한다.
- 생성 실패는 Job `FAILED`와 안전한 `error`로 표시하며 별도 개인 이벤트를 정의하지 않는다.
- MVP는 같은 Chat에서 동시에 하나의 Assistant 생성 Job만 허용하며 진행 중 요청이 있으면 `409 CHAT_RESPONSE_IN_PROGRESS`를 반환한다.
- `LIVE → PROCESSING` transition은 개인 LIVE 결과·Chat·Message·Evidence·Job을 함께 삭제하고 늦은 Worker 결과를 fence한다. 전이 후 기존 ID로 Summary·Chat·Message·Job을 조회·polling하면 `404 RESOURCE_NOT_FOUND`다. `purge_on_session_end=true` terminal 멱등성 행은 남은 24시간 동안 상태를 `410 LIVE_AI_RESULT_PURGED`로 재작성해 같은 키·같은 request hash에만 replay하고, 새 키 요청은 `409 SESSION_STATE_CONFLICT`다. FINAL·REVIEW 데이터는 유지한다.
- 개인 AI mutation은 잠금 전 조회에서 후보 ID만 찾고, canonical row를 잠근 뒤 Session 상태·소유권·Job attempt·run token을 다시 검증한다. purge 대상 LIVE 작업은 `purge_on_session_end=true` 멱등성 row prefix를 먼저 잠근다. 이후 LIVE `CHAT_RESPONSE`는 Session → Chat → target USER Message → AIJob, LIVE Summary는 Session → AIJob 순서로 잠근다. REVIEW `CHAT_RESPONSE`는 purge prefix 없이 Session → Chat → target USER Message → AIJob 순서를 사용한다. 종료 purge는 멱등성 row prefix → Session → LIVE Summary → LIVE Chat → Message → Evidence → 관련 requester-only AIJob aggregate 순서를 따른다.

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

| 기능 ID               | 기능                 | HTTP API                                                        | WebSocket                                                        |
| --------------------- | -------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------- |
| AUTH                  | Google·이메일 로그인 | Google start·callback, email register·login, logout             | —                                                                |
| PRE-T-01              | Course 생성          | `POST /courses`                                                 | —                                                                |
| PRE-T-02              | 참여 코드 발급       | Course 생성·상세·참여 코드 회전                                 | —                                                                |
| PRE-T-03              | class 관리           | class 생성·제목 수정·삭제                                       | —                                                                |
| PRE-T-04              | PDF 관리             | Material 목록·업로드·열람·분리 API                              | `job.updated`                                                    |
| PRE-T-05              | class 시작           | `POST /sessions/{id}/start`                                     | `session.updated`                                                |
| PRE-S-01              | 코드 참여            | `POST /courses/join`                                            | —                                                                |
| PRE-S-02              | class 확인           | `GET /courses/{id}/sessions`                                    | —                                                                |
| PRE-S-03              | 진행 class 입장      | `GET /sessions/{id}`                                            | Session WS                                                       |
| LIVE_AUDIO_STREAM     | 교수자 STT·녹음      | realtime ticket, Recording upload API                           | audio WS, `transcript.*`, `recording.updated`                    |
| LIVE-T-01 / LIVE-S-01 | Transcript           | Transcript version·타임라인 API                                 | `transcript.*`                                                   |
| LIVE-T-02 / LIVE-S-04 | 질문 확인            | `GET /sessions/{id}/questions`                                  | `question.*`                                                     |
| LIVE-T-03             | 클러스터             | Cluster generation·member API, Session Job API                  | `clustering.updated`, `question.updated`, `job.updated`          |
| LIVE-T-04             | 인기 질문            | 질문 `sort=POPULAR`                                             | `reaction.updated`                                               |
| LIVE-T-05~07          | 답변 선택·완료       | Answer 생성·완료·취소 API                                       | `answer.updated`, `answer.deleted`                               |
| LIVE-T-08             | class 종료           | `POST /sessions/{id}/end`                                       | `session.updated`, `job.updated`                                 |
| LIVE-S-02 / LIVE-S-07 | 현재 요약            | Summary API, Job polling                                        | —                                                                |
| LIVE-S-03             | 익명 질문            | `POST /sessions/{id}/questions`                                 | `question.created`                                               |
| LIVE-S-05             | 반응                 | Reaction API                                                    | `reaction.updated`                                               |
| LIVE-S-06 / LIVE-S-08 | 실시간 AI 채팅       | Chat API, Job polling                                           | —                                                                |
| LIVE-S-09             | 질문 작성 도움       | `POST /sessions/{id}/question-drafts`                           | —                                                                |
| POST-01~05            | 수업 기록            | record·Recording·Transcript version·Answer AI 정리·playback API | `recording.updated`, `transcript.version.updated`, `job.updated` |
| POST-06               | 복습 AI              | `mode=REVIEW` Chat API, Job polling                             | —                                                                |
| POST-07               | 이전 class           | `GET /courses/{id}/sessions`                                    | —                                                                |
| POST-08               | PDF 다시 보기        | Material API                                                    | —                                                                |
| POST-ANSWER           | 종료 후 텍스트 답변  | Answer 생성·수정 API                                            | `answer.updated`                                                 |
| COURSE-ARCHIVE-01     | Course workspace     | Course 상세·완료 class cursor API                               | —                                                                |
| COURSE-ARCHIVE-02     | Course PDF archive   | `GET /courses/{id}/materials`, Material content                 | —                                                                |
| COURSE-ARCHIVE-03     | Transcript archive   | `GET /courses/{id}/transcripts`, Session timeline API           | —                                                                |
| COURSE-ARCHIVE-04     | FINAL Summary 모음   | `GET /courses/{id}/summaries`, Summary 단건                     | —                                                                |
| COURSE-ARCHIVE-05     | Course Q&A archive   | `GET /courses/{id}/qna`, class record API                       | —                                                                |

## 18. 보안과 개인정보

- 익명 질문 API와 WebSocket은 작성자 ID, 이름, 이메일을 공개하지 않는다.
- 서버 로그에 인증 토큰, WebSocket 티켓, 참여 코드, 질문 원문과 프롬프트 원문을 남기지 않는다.
- AI 모델 입력에 학생의 실제 식별 정보를 포함하지 않는다.
- 모든 Material, Recording, RecordingUpload, Transcript, Question, Answer, Summary, Chat과 Job 접근은 현재 인증과 Course 접근 권한을 검증한다.
- 개인 요약·Chat Job 상태는 Session 전체에 broadcast하지 않는다. 질문 초안은 동기 REST 응답에서만 반환한다.
- 개인 Summary·Chat·Message·`REQUESTER_ONLY` Job 조회는 해당 소유자/요청자와 현재 Course 멤버십을 재검증한다. 비소유자·비요청자·비멤버에는 `404`로 응답해 존재 여부를 숨긴다. Session 종료로 삭제된 기존 LIVE 리소스·Job은 소유자에게도 `404 RESOURCE_NOT_FOUND`다.
- PDF·녹음의 스토리지 키, 서버 파일 경로, fragment key·manifest와 Material의 `detached_at`은 외부 API에 노출하지 않는다.
- Chat Evidence는 현재 사용자의 Course 권한과 source 상태를 다시 검증한 `link`만 제공한다. `knowledge_chunk_id`, pagination cursor, 배열 위치와 학생 식별정보는 노출하지 않는다.

## 19. 미정 사항

| 항목                               | 현재 상태                                                                                                                                                                                       | 결정 시 영향                  |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| ID 형식                            | 불투명 string                                                                                                                                                                                   | OpenAPI `format`, DB PK       |
| Material 표시명                    | suffix와 업로드 시 영구 확정은 결정; 허용 문자·Unicode 정규화·대소문자 충돌 비교 규칙 TBD                                                                                                       | 업로드·목록·다운로드 파일명   |
| Material 분리 근거                 | 안전한 label snapshot과 `link=null` 방향만 확정; 정확한 근거 보관 기간·FK·`410 Gone` 정책 TBD                                                                                                   | Chat 근거·DB 삭제 정책        |
| 종료 후 텍스트 Answer              | `COMPLETED`에서 생성·보강은 확정; 최대 길이, 빈 문자열·삭제, KnowledgeChunk 재생성 세부 정책 TBD                                                                                                | Answer 요청·응답              |
| 음성 Answer AI 정리                | Answer별 자동 SHARED blocking Job·HQ 우선/LIVE fallback·실패 재시도·교수자 text 분리는 확정; 정리문 형식·최대 길이·model·prompt·품질 기준과 KnowledgeChunk 재색인 여부·producer·transaction TBD | Answer 응답·AI worker·검색    |
| LIVE clustering 실패 재시도        | pending watermark·같은 Job 행 `attempt + 1` 재사용은 확정; backoff·최대 attempt 횟수 TBD                                                                                                        | Job scheduler·운영 UI         |
| 클러스터 품질·대형 마인드맵        | cursor 기본 20·최대 100은 확정; 유사도 threshold·model·prompt·품질 지표, generation 교체 중 cursor 만료·재시작, preload page 수·점진 loading·자동 축소 layout TBD                               | AI worker·Cluster 화면        |
| FINAL clustering 입력 0건          | Job 생략 또는 모델 호출 없는 성공 빈 원장, `final_generation`·`finalized_at` 표현 TBD                                                                                                           | coordinator·Cluster 응답      |
| 녹음 형식·저장                     | codec·container·브라우저 로컬 저장·최대 크기, 물리 단일 파일 또는 fragment+manifest 구조 TBD                                                                                                    | upload 검증·storage·playback  |
| 녹음 upload                        | offset 조회 `GET`/`HEAD`, chunk method·header·Content-Type·크기, checksum algorithm·status, expiry 값 TBD                                                                                       | resumable protocol·정리       |
| 오디오 publisher                   | 첫 `client_stream_id` claim과 동일 stream resume은 확정; 비정상 단절 lease·재획득·takeover TBD                                                                                                  | 중복 탭·장치 충돌             |
| 실시간 임계값                      | `DEGRADED` 기준, audio stop timeout과 event replay window TBD                                                                                                                                   | 상태 표시·종료·재연결         |
| HQ Transcript 실패 후 final source | `RECORDING_TRANSCRIPTION` 실패 version과 LIVE canonical은 모두 보존; LIVE를 완료 기록·Summary final source로 사용할지 TBD                                                                       | Transcript·Summary·복구 UI    |
| HQ STT 개별 Job timeout            | 일반 후처리 기본 5분에서 `RECORDING_TRANSCRIPTION`은 제외; HQ 개별 상한은 TBD. heartbeat 15초·lease 60초·Session 전체 10분은 확정                                                               | Worker watchdog·운영 모니터링 |
| Answer 재매핑 세부                 | canonical 전체 범위 mapping 상태는 공개; 일부 매핑·미매핑 이유 enum과 수동 복구 정책 TBD                                                                                                        | Answer 응답·완료 기록 UI      |
| 이벤트 재생                        | event log 보존 여부 TBD                                                                                                                                                                         | 재연결 프로토콜               |
| 레이트 리미트                      | 임계치 TBD                                                                                                                                                                                      | `429` 헤더·재시도             |

## 20. 검토 체크리스트

- [ ] Google callback의 state·nonce·PKCE와 session rotation 테스트가 있는가?
- [ ] WebSocket 티켓의 60초 만료·1회 사용·scope 검증 테스트가 있는가?
- [ ] 모든 MVP 기능 ID가 HTTP API 또는 WebSocket에 연결됐는가?
- [ ] 모든 상태 변경 API에 선행 상태와 `409` 규칙이 있는가?
- [ ] 익명 질문의 모든 응답·이벤트에서 작성자 식별자가 제거됐는가?
- [ ] 질문은 300자, 초안은 500자, 제안은 300자를 서버에서 검증하고 초과 입력을 자동 절단하지 않는가?
- [ ] Session당 active clustering Job이 하나이고, 실행 중 질문이 다음 watermark로 coalesce되며 LIVE에서 기존 질문을 옮기지 않는가?
- [ ] 종료 transaction이 LIVE clustering 결과 commit을 fence하고, 모든 학생 질문과 완료 Answer가 있는 대표질문만 FINAL input으로 사용하는가?
- [ ] Answer가 하나의 typed target만 가지고 대표질문 답변이 child 상태를 바꾸지 않으며, 취소 행을 조회로 노출하지 않는가?
- [ ] 완료된 VOICE Answer마다 `ANSWER_ORGANIZATION` 원장이 생기고, 고정 source의 결과·실패·attempt가 Answer별로 복구되며 교수자 text를 덮어쓰지 않는가?
- [ ] LIVE Summary와 개인 Chat·Job이 요청자 외 사용자에게 노출되지 않는가?
- [ ] 리스트 API의 정렬과 커서 규칙이 일관되는가?
- [ ] `POST` 상태 변경과 AI 작업의 멱등성이 정의됐는가?
- [ ] AI 실패가 Course·Question·Transcript 핵심 기능을 차단하지 않는가?
- [ ] `RECORDING_TRANSCRIPTION`이 SHARED·blocking이고 실패 terminal 뒤에도 Session이 `COMPLETED`가 되는가?
- [ ] Transcript cursor가 canonical 전환 중에도 최초 version에 고정되고 Segment·Gap을 중복·누락 없이 반환하는가?
- [ ] HQ Segment recording offset·Gap `is_final`·canonical이 먼저 commit되고, Answer mapping·Knowledge 재연결 실패가 HQ 결과를 rollback하지 않으며 partial mapping enum을 임의 노출하지 않는가?
- [ ] HQ 실패·timeout에 staged Segment·Gap이 남지 않고 `last_sequence=0`·version/Job `FAILED`가 함께 commit되며, `EMPTY`의 final Gap은 조회되는가?
- [ ] `FINAL_SUMMARY`가 RECORDING `FINALIZED`+Segment 1건 이상에서만 생성되고 EMPTY·FAILED·HQ 무결과·Recording 없음을 구분하는가?
- [ ] worker heartbeat 15초·lease 60초, 일반 후처리 Job 기본 5분, HQ 개별 timeout TBD, Session 10분 상한이 구분되고 timeout child Job 생성·summary state·coordinator/gate `FAILED`·Session `COMPLETED` 순서가 잠금 안에서 지켜지는가?
- [ ] `COMPLETED` HQ retry 성공이 같은 coordinator를 자동 requeue하고 Answer mapping·canonical Knowledge·새 FINAL Summary를 멱등 복구하되 기존 Answer organization source를 바꾸지 않는가?
- [ ] 10분 watchdog이 누락된 VOICE Answer별 `ANSWER_ORGANIZATION` 실패 Job을 만든 뒤 완료를 평가하는가?
- [ ] 첫 audio publisher claim·동일 stream resume·다른 stream `4409` 거부가 원자적인가?
- [ ] Recording upload·playback의 모든 응답과 로그에서 storage key·서버 경로·fragment 구성이 제거됐는가?
- [ ] `openapi.yaml`과 FastAPI `/openapi.json`의 자동 비교 방법이 있는가?
