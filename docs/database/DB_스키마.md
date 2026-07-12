# GOAL 데이터베이스 스키마

> 상태: Draft v0.1
>
> 작성 기준일: 2026-07-11
>
> ERD: [ERD.md](./ERD.md)

## 1. 문서 목적과 범위

본 문서는 GOAL MVP를 PostgreSQL 17과 pgvector로 구현하기 위한 물리 데이터 모델 초안이다. 테이블 책임, 컬럼, 타입, `NULL` 여부, PK/FK, 기본값, 제약조건, 인덱스, `ON DELETE` 정책과 주요 트랜잭션 규칙을 정의한다.

기준 문서는 다음과 같다.

- [기획안](../product/기획안.md)
- [기능명세서](../product/기능명세서.md)
- [IA](../product/IA.md)
- [API 명세서](../api/API_명세서.md)
- [OpenAPI](../api/openapi.yaml)
- [기술명세서](../architecture/기술명세서.md)

본 문서는 아직 SQLAlchemy 모델이나 Alembic migration을 생성하지 않는다. 구현 단계에서는 본 문서를 검토·승인한 뒤 모델과 migration을 별도 변경으로 작성한다.

### 1.1 데이터 계약 우선순위

1. 제품 문서는 사용자 동작과 MVP 범위를 결정한다.
2. API 문서는 외부에서 관찰되는 리소스·상태·권한을 결정한다.
3. 본 문서는 이를 보존하는 내부 저장 구조와 무결성 규칙을 결정한다.
4. API 응답 필드가 반드시 DB 컬럼과 1:1로 대응하는 것은 아니다. 계산·집계 필드는 별도로 표시한다.

### 1.2 이번 설계에서 확정한 결정

- Course 참여 코드는 복호화 가능한 암호문으로 저장한다.
- 참여 코드 입력 조회를 위해 정규화한 코드의 HMAC을 암호문과 별도로 저장한다.
- 한 Course에는 동시에 `LIVE`인 class가 최대 한 개다.
- 한 class에는 PDF를 여러 개 업로드할 수 있다.
- 질문 클러스터 변경 이력은 보관하지 않는다.
- 교수자가 클러스터를 선택해 답변을 시작하면 당시 질문 목록을 Answer에 snapshot한다.
- 수업 종료 후 현재 질문 배치를 최종 클러스터로 확정해 보관한다.
- 한 질문은 취소되지 않은 `CAPTURING` 또는 `COMPLETED` Answer에 최대 한 번만 연결된다. `CANCELLED` 시도는 Answer 개수에서 제외하고 snapshot만 보관한다.
- AIJob 재시도는 같은 행의 `attempt`를 증가시킨다.
- PDF·Transcript·Question·Answer 검색 단위는 공통 `knowledge_chunks` 테이블로 통합한다.
- Chat 근거는 `chat_message_evidence`가 `knowledge_chunks`를 참조한다.
- AIJob 결과는 각 결과 행의 `created_by_job_id`로 역참조한다.
- `source_type + source_id` 형태의 직접적인 다형 FK는 사용하지 않는다.
- partial Transcript와 음성 원본은 MVP에서 영구 저장하지 않는다.

## 2. PostgreSQL 공통 규칙

### 2.1 확장

| 확장       | 용도                                     |
| ---------- | ---------------------------------------- |
| `pgcrypto` | `gen_random_uuid()`와 암호화 보조 기능   |
| `vector`   | KnowledgeChunk 임베딩 저장과 유사도 검색 |

애플리케이션 비밀키와 HMAC pepper는 DB나 저장소에 저장하지 않고 환경 비밀 또는 KMS에서 관리한다.

### 2.2 명명·타입 규칙

| 항목                      | 규칙                                        |
| ------------------------- | ------------------------------------------- |
| 테이블·컬럼               | 복수형 테이블과 `snake_case` 컬럼           |
| PK                        | `uuid`, 기본값 `gen_random_uuid()`          |
| 시각                      | UTC 기준 `timestamptz`                      |
| 날짜                      | `date`                                      |
| 상태·역할                 | `text`와 이름 있는 `CHECK` 제약             |
| sequence·byte·millisecond | `bigint`                                    |
| 리소스 버전               | `bigint NOT NULL DEFAULT 1`, 갱신 시 1 증가 |
| 암호문·hash·nonce         | `bytea`                                     |
| 자유 형식 작업 정보       | 제한적으로 `jsonb` 사용                     |

PostgreSQL native ENUM은 값 추가·변경 시 migration 부담이 크므로 MVP에서는 `text + CHECK`를 사용한다. 애플리케이션에서는 동일한 값을 Python `StrEnum`으로 관리한다.

### 2.3 공통 컬럼

- 변경 가능한 핵심 리소스는 `created_at`, `updated_at`을 가진다.
- 실시간으로 갱신되는 `lecture_sessions`, `questions`, `answers`, `ai_jobs`는 `version`을 가진다.
- `updated_at`은 애플리케이션 또는 공통 DB trigger 중 한 방식으로 일관되게 갱신한다. MVP 권장안은 공통 trigger다.
- 사용자 콘텐츠의 hard delete API는 MVP에 포함하지 않는다. 사용자 탈퇴는 `users.deleted_at`과 식별정보 익명화를 우선 사용한다.

## 3. 상태와 코드 값

| 구분                                  | 허용 값                                      |
| ------------------------------------- | -------------------------------------------- |
| `course_members.role`                 | `PROFESSOR`, `STUDENT`                       |
| `lecture_sessions.status`             | `READY`, `LIVE`, `PROCESSING`, `COMPLETED`   |
| `lecture_materials.processing_status` | `UPLOADED`, `PROCESSING`, `READY`, `FAILED`  |
| `questions.status`                    | `OPEN`, `SELECTED`, `ANSWERED`               |
| `answers.status`                      | `CAPTURING`, `COMPLETED`, `CANCELLED`        |
| `lecture_summaries.summary_type`      | `LIVE`, `FINAL`                              |
| `lecture_summaries.visibility`        | `REQUESTER_ONLY`, `COURSE_MEMBERS`           |
| `chat_sessions.mode`                  | `LIVE`, `REVIEW`                             |
| `chat_messages.role`                  | `USER`, `ASSISTANT`                          |
| `ai_jobs.status`                      | `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`  |
| `ai_jobs.visibility`                  | `SHARED`, `REQUESTER_ONLY`                   |
| `realtime_tickets.scope`              | `SESSION_EVENTS_READ`, `SESSION_AUDIO_WRITE` |
| `user_auth_identities.provider`       | `GOOGLE`                                     |

AIJob 유형은 다음 값을 사용한다.

- `MATERIAL_PROCESSING`
- `QUESTION_CLUSTERING`
- `LIVE_SUMMARY`
- `FINAL_SUMMARY`
- `QUESTION_DRAFT_HELP`
- `CHAT_RESPONSE`
- `SESSION_POSTPROCESSING`

## 4. 테이블 구성 요약

| 영역          | 테이블                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------ |
| 사용자·인증   | `users`, `user_auth_identities`, `auth_sessions`, `oauth_transactions`, `realtime_tickets` |
| Course·class  | `courses`, `course_members`, `lecture_sessions`                                            |
| 자료·기록     | `lecture_materials`, `transcript_segments`, `transcript_gaps`, `knowledge_chunks`          |
| 질문·답변     | `question_clusters`, `questions`, `question_reactions`, `answers`, `answer_questions`      |
| AI 요약·채팅  | `lecture_summaries`, `chat_sessions`, `chat_messages`, `chat_message_evidence`             |
| 비동기·일관성 | `ai_jobs`, `idempotency_records`, `outbox_events`                                          |

## 5. 사용자·인증

### 5.1 `users`

서비스 사용자 본체다. 전역 교수자·학생 역할을 저장하지 않는다.

| 컬럼            | 타입          | NULL | 기본값              | 키·제약 | 설명              |
| --------------- | ------------- | ---: | ------------------- | ------- | ----------------- |
| `id`            | `uuid`        |    N | `gen_random_uuid()` | PK      | 사용자 ID         |
| `display_name`  | `text`        |    N | -                   | -       | 표시 이름         |
| `primary_email` | `text`        |    Y | `NULL`              | -       | 현재 대표 이메일  |
| `avatar_url`    | `text`        |    Y | `NULL`              | -       | 프로필 이미지 URL |
| `deleted_at`    | `timestamptz` |    Y | `NULL`              | -       | 탈퇴·익명화 시각  |
| `created_at`    | `timestamptz` |    N | `now()`             | -       | 생성 시각         |
| `updated_at`    | `timestamptz` |    N | `now()`             | -       | 갱신 시각         |

인덱스:

- `INDEX users_active_idx (id) WHERE deleted_at IS NULL`
- 이메일은 로그인 식별자가 아니므로 고유 제약을 두지 않는다. Google의 안정적인 식별자는 `user_auth_identities.provider_subject`다.

삭제 정책:

- 사용자 hard delete는 운영 관리 절차에서만 허용한다.
- 질문·Transcript·공용 기록을 보존하기 위해 사용자 콘텐츠 FK는 주로 `RESTRICT` 또는 `SET NULL`을 사용한다.
- 개인 Chat과 개인 LIVE Summary는 사용자 삭제 트랜잭션에서 함께 제거한다.

### 5.2 `user_auth_identities`

Google 계정과 내부 User를 분리한다. 이메일 변경과 향후 인증 제공자 추가에 대비한다.

| 컬럼               | 타입          | NULL | 기본값              | 키·제약         | 설명               |
| ------------------ | ------------- | ---: | ------------------- | --------------- | ------------------ |
| `id`               | `uuid`        |    N | `gen_random_uuid()` | PK              | 인증 identity ID   |
| `user_id`          | `uuid`        |    N | -                   | FK → `users.id` | 내부 사용자        |
| `provider`         | `text`        |    N | -                   | CHECK           | `GOOGLE`           |
| `provider_subject` | `text`        |    N | -                   | -               | OIDC `sub`         |
| `email_snapshot`   | `text`        |    Y | `NULL`              | -               | 최근 로그인 이메일 |
| `created_at`       | `timestamptz` |    N | `now()`             | -               | 생성 시각          |
| `updated_at`       | `timestamptz` |    N | `now()`             | -               | 갱신 시각          |

제약·인덱스:

- `UNIQUE (provider, provider_subject)`
- `UNIQUE (user_id, provider)`
- `INDEX user_auth_identities_user_idx (user_id)`
- `user_id ON DELETE CASCADE`

### 5.3 `auth_sessions`

`goal_session` Cookie의 원문을 저장하지 않고 hash만 저장한다.

| 컬럼           | 타입          | NULL | 기본값              | 키·제약         | 설명                    |
| -------------- | ------------- | ---: | ------------------- | --------------- | ----------------------- |
| `id`           | `uuid`        |    N | `gen_random_uuid()` | PK              | 세션 행 ID              |
| `user_id`      | `uuid`        |    N | -                   | FK → `users.id` | 소유 사용자             |
| `token_hash`   | `bytea`       |    N | -                   | UNIQUE          | Cookie token의 HMAC     |
| `expires_at`   | `timestamptz` |    N | -                   | CHECK           | 기본 발급 후 7일        |
| `revoked_at`   | `timestamptz` |    Y | `NULL`              | -               | 로그아웃·강제 폐기 시각 |
| `last_seen_at` | `timestamptz` |    Y | `NULL`              | -               | 마지막 사용 시각        |
| `created_at`   | `timestamptz` |    N | `now()`             | -               | 생성 시각               |

제약·인덱스:

- `CHECK (expires_at > created_at)`
- `CHECK (octet_length(token_hash) = 32)`
- `INDEX auth_sessions_user_active_idx (user_id, expires_at) WHERE revoked_at IS NULL`
- `INDEX auth_sessions_expiry_idx (expires_at)`
- `user_id ON DELETE CASCADE`

### 5.4 `oauth_transactions`

Google callback의 state·nonce·PKCE를 10분 동안 보관한다. PKCE verifier는 callback에서 필요하므로 암호화한다.

| 컬럼                       | 타입          | NULL | 기본값              | 키·제약     | 설명                          |
| -------------------------- | ------------- | ---: | ------------------- | ----------- | ----------------------------- |
| `id`                       | `uuid`        |    N | `gen_random_uuid()` | PK          | OAuth 시도 ID                 |
| `browser_binding_hash`     | `bytea`       |    N | -                   | UNIQUE      | 임시 `goal_oauth` Cookie hash |
| `state_hash`               | `bytea`       |    N | -                   | UNIQUE      | OAuth state HMAC              |
| `nonce_hash`               | `bytea`       |    N | -                   | -           | OIDC nonce HMAC               |
| `pkce_verifier_ciphertext` | `bytea`       |    N | -                   | -           | AES-GCM 암호문                |
| `pkce_verifier_nonce`      | `bytea`       |    N | -                   | -           | 암호화 nonce                  |
| `encryption_key_version`   | `smallint`    |    N | -                   | CHECK `> 0` | 키 버전                       |
| `return_to`                | `text`        |    N | `'/'`               | CHECK       | 검증된 내부 상대 경로         |
| `expires_at`               | `timestamptz` |    N | -                   | CHECK       | 발급 후 10분                  |
| `consumed_at`              | `timestamptz` |    Y | `NULL`              | -           | callback 사용 시각            |
| `created_at`               | `timestamptz` |    N | `now()`             | -           | 생성 시각                     |

제약·인덱스:

- `CHECK (return_to LIKE '/%' AND return_to NOT LIKE '//%')`
- `CHECK (expires_at > created_at)`
- `CHECK (expires_at <= created_at + interval '10 minutes')`
- `CHECK (octet_length(state_hash) = 32 AND octet_length(nonce_hash) = 32)`
- `CHECK (octet_length(pkce_verifier_nonce) = 12)`
- `INDEX oauth_transactions_expiry_idx (expires_at)`
- 사용 완료 또는 만료된 행은 정기 작업으로 삭제한다.

### 5.5 `realtime_tickets`

WebSocket upgrade에 사용하는 60초 만료·1회용 ticket의 hash와 scope를 저장한다.

| 컬럼            | 타입          | NULL | 기본값              | 키·제약                    | 설명                        |
| --------------- | ------------- | ---: | ------------------- | -------------------------- | --------------------------- |
| `id`            | `uuid`        |    N | `gen_random_uuid()` | PK                         | ticket 행 ID                |
| `ticket_hash`   | `bytea`       |    N | -                   | UNIQUE                     | ticket 원문 HMAC            |
| `user_id`       | `uuid`        |    N | -                   | FK → `users.id`            | 발급 사용자                 |
| `session_id`    | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 대상 class                  |
| `scope`         | `text`        |    N | -                   | CHECK                      | 이벤트 읽기 또는 audio 쓰기 |
| `resume_cursor` | `text`        |    Y | `NULL`              | -                          | 이벤트 재연결 cursor        |
| `expires_at`    | `timestamptz` |    N | -                   | CHECK                      | 발급 후 60초                |
| `used_at`       | `timestamptz` |    Y | `NULL`              | -                          | 최초 upgrade 사용 시각      |
| `created_at`    | `timestamptz` |    N | `now()`             | -                          | 생성 시각                   |

제약·인덱스:

- `CHECK (expires_at > created_at)`
- `CHECK (expires_at <= created_at + interval '60 seconds')`
- `CHECK (octet_length(ticket_hash) = 32)`
- `CHECK (scope = 'SESSION_EVENTS_READ' OR resume_cursor IS NULL)`
- `INDEX realtime_tickets_expiry_idx (expires_at)`
- `INDEX realtime_tickets_user_idx (user_id, created_at DESC)`
- `user_id ON DELETE CASCADE`
- `session_id ON DELETE CASCADE`

ticket 소비는 `UPDATE ... SET used_at = now() WHERE ticket_hash = :hash AND used_at IS NULL AND expires_at > now() RETURNING ...` 한 문장으로 처리한다.

## 6. Course·class

### 6.1 `courses`

한 학기 단위 수업방과 교수자에게 다시 표시할 참여 코드를 저장한다.

| 컬럼                           | 타입          | NULL | 기본값              | 키·제약         | 설명                          |
| ------------------------------ | ------------- | ---: | ------------------- | --------------- | ----------------------------- |
| `id`                           | `uuid`        |    N | `gen_random_uuid()` | PK              | Course ID                     |
| `title`                        | `text`        |    N | -                   | CHECK           | 과목명                        |
| `semester`                     | `text`        |    N | -                   | CHECK           | 표시용 학기                   |
| `created_by_user_id`           | `uuid`        |    N | -                   | FK → `users.id` | 생성 사용자                   |
| `join_code_lookup_hash`        | `bytea`       |    N | -                   | UNIQUE          | 정규화 코드의 HMAC-SHA-256    |
| `join_code_lookup_key_version` | `smallint`    |    N | -                   | CHECK `> 0`     | HMAC key 버전                 |
| `join_code_ciphertext`         | `bytea`       |    N | -                   | -               | AES-256-GCM 암호문과 auth tag |
| `join_code_nonce`              | `bytea`       |    N | -                   | -               | 암호화 nonce                  |
| `join_code_key_version`        | `smallint`    |    N | -                   | CHECK `> 0`     | 암호화 키 버전                |
| `join_code_expires_at`         | `timestamptz` |    Y | `NULL`              | -               | `NULL`이면 회전 전까지 유효   |
| `version`                      | `bigint`      |    N | `1`                 | CHECK `> 0`     | 리소스 버전                   |
| `created_at`                   | `timestamptz` |    N | `now()`             | -               | 생성 시각                     |
| `updated_at`                   | `timestamptz` |    N | `now()`             | -               | 갱신 시각                     |

암호화·조회 규칙:

1. 입력 코드는 trim 후 대문자로 정규화한다.
2. 정규화 값을 현재 단일 lookup HMAC key로 HMAC-SHA-256 계산해 `join_code_lookup_hash`로 조회한다.
3. 교수자 표시가 필요할 때만 ciphertext를 복호화한다.
4. AES-GCM associated data에는 `course_id`를 넣어 다른 Course 행으로 암호문을 옮겨도 복호화되지 않게 한다.
5. 암호화 키와 HMAC key는 서로 분리하고 DB 밖에서 관리한다.
6. lookup HMAC key 회전은 참여 코드 발급을 잠시 중단하고 전역 advisory lock을 잡은 뒤, 모든 Course의 lookup hash와 key version을 한 transaction에서 새 key로 재계산한 후에만 발급을 재개한다. 서로 다른 lookup key version을 장기간 섞어 두지 않는다.
7. 암호화 key는 lookup key와 독립적으로 행 단위 점진 회전할 수 있다.
8. MVP는 자동 만료를 사용하지 않고 Course 삭제 또는 교수자의 회전 전까지 유효하게 둔다.

제약·인덱스:

- `CHECK (length(btrim(title)) > 0)`
- `CHECK (length(btrim(semester)) > 0)`
- `CHECK (octet_length(join_code_lookup_hash) = 32)`
- `CHECK (octet_length(join_code_nonce) = 12)`
- `CHECK (join_code_expires_at IS NULL OR join_code_expires_at > created_at)`
- `created_by_user_id ON DELETE RESTRICT`
- 모든 Course가 같은 활성 lookup key version을 사용하므로 `join_code_lookup_hash`의 UNIQUE 인덱스가 정규화 참여 코드의 전역 중복과 극히 드문 digest 충돌을 막는다.

### 6.2 `course_members`

사용자와 Course의 N:M 관계 및 Course별 역할을 저장한다.

| 컬럼        | 타입          | NULL | 기본값  | 키·제약               | 설명                   |
| ----------- | ------------- | ---: | ------- | --------------------- | ---------------------- |
| `course_id` | `uuid`        |    N | -       | PK, FK → `courses.id` | Course                 |
| `user_id`   | `uuid`        |    N | -       | PK, FK → `users.id`   | 사용자                 |
| `role`      | `text`        |    N | -       | CHECK                 | `PROFESSOR`, `STUDENT` |
| `joined_at` | `timestamptz` |    N | `now()` | -                     | 참여 시각              |

제약·인덱스:

- PK `(course_id, user_id)`가 한 Course에서 역할 하나만 허용한다.
- `INDEX course_members_user_role_idx (user_id, role, course_id)`
- `course_id ON DELETE CASCADE`
- `user_id ON DELETE RESTRICT`; 탈퇴는 User 익명화를 우선한다.
- Course 생성 트랜잭션은 생성자를 `PROFESSOR`로 함께 삽입한다.
- 코드 참여는 기존 `PROFESSOR`를 `STUDENT`로 덮어쓰지 않는다.

### 6.3 `lecture_sessions`

Course 안의 날짜별 class와 상태 전이를 저장한다.

| 컬럼                  | 타입          | NULL | 기본값              | 키·제약           | 설명                         |
| --------------------- | ------------- | ---: | ------------------- | ----------------- | ---------------------------- |
| `id`                  | `uuid`        |    N | `gen_random_uuid()` | PK                | class ID                     |
| `course_id`           | `uuid`        |    N | -                   | FK → `courses.id` | 소속 Course                  |
| `created_by_user_id`  | `uuid`        |    N | -                   | FK → `users.id`   | 생성 교수자                  |
| `title`               | `text`        |    N | -                   | CHECK             | class 제목                   |
| `lecture_date`        | `date`        |    N | -                   | -                 | class 날짜                   |
| `status`              | `text`        |    N | `'READY'`           | CHECK             | 상태                         |
| `last_final_sequence` | `bigint`      |    N | `0`                 | CHECK `>= 0`      | 마지막 final Transcript 순번 |
| `version`             | `bigint`      |    N | `1`                 | CHECK `> 0`       | 실시간 리소스 버전           |
| `started_at`          | `timestamptz` |    Y | `NULL`              | -                 | 시작 시각                    |
| `ended_at`            | `timestamptz` |    Y | `NULL`              | -                 | 종료 요청 시각               |
| `completed_at`        | `timestamptz` |    Y | `NULL`              | -                 | 후처리 완료 시각             |
| `created_at`          | `timestamptz` |    N | `now()`             | -                 | 생성 시각                    |
| `updated_at`          | `timestamptz` |    N | `now()`             | -                 | 갱신 시각                    |

제약·인덱스:

- `UNIQUE (id, course_id)`; KnowledgeChunk의 범위 검증에 사용한다.
- `UNIQUE INDEX lecture_sessions_one_live_per_course_uq (course_id) WHERE status = 'LIVE'`
- `INDEX lecture_sessions_course_date_idx (course_id, lecture_date DESC, id DESC)`
- `INDEX lecture_sessions_course_status_idx (course_id, status, updated_at DESC)`
- `CHECK (length(btrim(title)) > 0)`
- `CHECK ((status = 'READY' AND started_at IS NULL AND ended_at IS NULL AND completed_at IS NULL) OR (status = 'LIVE' AND started_at IS NOT NULL AND ended_at IS NULL AND completed_at IS NULL) OR (status = 'PROCESSING' AND started_at IS NOT NULL AND ended_at IS NOT NULL AND completed_at IS NULL) OR (status = 'COMPLETED' AND started_at IS NOT NULL AND ended_at IS NOT NULL AND completed_at IS NOT NULL))`
- `CHECK (ended_at IS NULL OR ended_at >= started_at)`
- `CHECK (completed_at IS NULL OR completed_at >= ended_at)`
- `course_id ON DELETE CASCADE`
- `created_by_user_id ON DELETE RESTRICT`; 탈퇴 시 User 행 자체를 익명화한다.

같은 날짜의 class는 제목이 다를 수 있으므로 여러 개를 허용한다. 동시 시작 요청은 partial UNIQUE 인덱스로 최종 차단하고, 서비스는 `409 SESSION_STATE_CONFLICT`로 변환한다.

## 7. 자료·Transcript

### 7.1 `lecture_materials`

class에 업로드한 PDF 원본 메타데이터와 전처리 상태를 저장한다. class당 여러 행을 허용한다.

| 컬럼                       | 타입          | NULL | 기본값              | 키·제약                    | 설명                     |
| -------------------------- | ------------- | ---: | ------------------- | -------------------------- | ------------------------ |
| `id`                       | `uuid`        |    N | `gen_random_uuid()` | PK                         | Material ID              |
| `session_id`               | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class               |
| `uploaded_by_user_id`      | `uuid`        |    Y | `NULL`              | FK → `users.id`            | 업로드 교수자            |
| `original_filename`        | `text`        |    N | -                   | CHECK                      | 표시용 원본 파일명       |
| `mime_type`                | `text`        |    N | `'application/pdf'` | CHECK                      | PDF MIME                 |
| `byte_size`                | `bigint`      |    N | -                   | CHECK `> 0`                | 파일 크기                |
| `storage_key`              | `text`        |    N | -                   | UNIQUE                     | 서버 생성 스토리지 키    |
| `page_count`               | `integer`     |    Y | `NULL`              | CHECK `> 0`                | 전처리 후 페이지 수      |
| `processing_status`        | `text`        |    N | `'UPLOADED'`        | CHECK                      | 전처리 상태              |
| `processed_by_job_id`      | `uuid`        |    Y | `NULL`              | 복합 FK                    | 성공한 Material 처리 Job |
| `processed_by_job_attempt` | `integer`     |    Y | `NULL`              | CHECK `> 0`                | 처리 당시 Job attempt    |
| `version`                  | `bigint`      |    N | `1`                 | CHECK `> 0`                | 상태 버전                |
| `created_at`               | `timestamptz` |    N | `now()`             | -                          | 업로드 시각              |
| `updated_at`               | `timestamptz` |    N | `now()`             | -                          | 갱신 시각                |

제약·인덱스:

- `UNIQUE (id, session_id)`; KnowledgeChunk의 동일 Session FK에 사용한다.
- `UNIQUE INDEX lecture_materials_processed_by_job_uq (processed_by_job_id) WHERE processed_by_job_id IS NOT NULL`; Material 처리 Job 하나는 Material 하나만 확정한다.
- `CHECK (mime_type = 'application/pdf')`
- `CHECK (length(btrim(original_filename)) > 0)`
- `CHECK ((processed_by_job_id IS NULL) = (processed_by_job_attempt IS NULL))`
- `CHECK (processing_status <> 'READY' OR processed_by_job_id IS NOT NULL)`
- `CHECK (processing_status <> 'READY' OR page_count IS NOT NULL)`
- `INDEX lecture_materials_session_idx (session_id, created_at, id)`
- `INDEX lecture_materials_processing_idx (processing_status, updated_at) WHERE processing_status IN ('UPLOADED', 'PROCESSING', 'FAILED')`
- `session_id ON DELETE CASCADE`
- `uploaded_by_user_id ON DELETE SET NULL`
- `(processed_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

Session별 개수 UNIQUE 제약을 두지 않는다. 원본 파일 삭제는 DB 행 삭제와 별도로 스토리지 정리 작업을 실행해야 한다.

### 7.2 `transcript_segments`

DB에 확정된 final Transcript만 저장한다. partial STT는 저장하지 않는다.

| 컬럼                     | 타입          | NULL | 기본값              | 키·제약                    | 설명                           |
| ------------------------ | ------------- | ---: | ------------------- | -------------------------- | ------------------------------ |
| `id`                     | `uuid`        |    N | `gen_random_uuid()` | PK                         | Segment ID                     |
| `session_id`             | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                     |
| `sequence`               | `bigint`      |    N | -                   | CHECK `> 0`                | Session 내 확정 순번           |
| `utterance_id`           | `text`        |    N | -                   | -                          | partial/final 치환용 발화 ID   |
| `start_ms`               | `bigint`      |    N | -                   | CHECK `>= 0`               | class 시작 기준 시각           |
| `end_ms`                 | `bigint`      |    N | -                   | CHECK                      | 종료 시각                      |
| `text`                   | `text`        |    N | -                   | CHECK                      | 확정 텍스트                    |
| `created_by_job_id`      | `uuid`        |    Y | `NULL`              | 복합 FK                    | Job 결과인 경우 원인 Job       |
| `created_by_job_attempt` | `integer`     |    Y | `NULL`              | CHECK `> 0`                | 생성 당시 Job attempt snapshot |
| `created_at`             | `timestamptz` |    N | `now()`             | -                          | 저장 시각                      |

제약·인덱스:

- `UNIQUE (session_id, sequence)`
- `UNIQUE (session_id, utterance_id)`
- `UNIQUE (id, session_id)`; Answer와 KnowledgeChunk의 동일 Session FK에 사용한다.
- `CHECK (end_ms >= start_ms)`
- `CHECK (length(btrim(utterance_id)) > 0)`
- `CHECK (length(btrim(text)) > 0)`
- `CHECK ((created_by_job_id IS NULL) = (created_by_job_attempt IS NULL))`
- `INDEX transcript_segments_time_idx (session_id, start_ms, id)`
- `session_id ON DELETE CASCADE`
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

### 7.3 `transcript_gaps`

재연결 실패나 audio resume 거부로 서버가 받지 못한 구간을 표시한다. 음성 원본은 저장하지 않는다.

| 컬럼         | 타입          | NULL | 기본값              | 키·제약                    | 설명                                                                            |
| ------------ | ------------- | ---: | ------------------- | -------------------------- | ------------------------------------------------------------------------------- |
| `id`         | `uuid`        |    N | `gen_random_uuid()` | PK                         | Gap ID                                                                          |
| `session_id` | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                                                                      |
| `start_ms`   | `bigint`      |    N | -                   | CHECK `>= 0`               | 추정 누락 시작                                                                  |
| `end_ms`     | `bigint`      |    Y | `NULL`              | CHECK                      | 추정 누락 종료                                                                  |
| `reason`     | `text`        |    N | -                   | CHECK                      | `SERVER_STATE_LOST`, `SEQUENCE_GAP`, `CLIENT_DISCONNECTED`, `BACKPRESSURE_DROP` |
| `details`    | `jsonb`       |    N | `'{}'::jsonb`       | -                          | 민감정보 없는 진단 정보                                                         |
| `created_at` | `timestamptz` |    N | `now()`             | -                          | 감지 시각                                                                       |

제약·인덱스:

- `CHECK (end_ms IS NULL OR end_ms >= start_ms)`
- `INDEX transcript_gaps_session_time_idx (session_id, start_ms)`
- `session_id ON DELETE CASCADE`

## 8. 질문·클러스터·답변

### 8.1 `question_clusters`

Session의 현재 질문 클러스터를 저장한다. 클러스터 membership 이력 테이블은 만들지 않는다.

| 컬럼                     | 타입          | NULL | 기본값              | 키·제약                    | 설명                             |
| ------------------------ | ------------- | ---: | ------------------- | -------------------------- | -------------------------------- |
| `id`                     | `uuid`        |    N | `gen_random_uuid()` | PK                         | Cluster ID                       |
| `session_id`             | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                       |
| `title`                  | `text`        |    N | -                   | CHECK                      | 대표 제목                        |
| `summary`                | `text`        |    Y | `NULL`              | -                          | 대표 설명                        |
| `ordinal`                | `integer`     |    N | -                   | CHECK `>= 0`               | 같은 Job 결과 안의 안정적인 순서 |
| `is_final`               | `boolean`     |    N | `false`             | -                          | 종료 후 확정 여부                |
| `finalized_at`           | `timestamptz` |    Y | `NULL`              | CHECK                      | 최종 확정 시각                   |
| `created_by_job_id`      | `uuid`        |    N | -                   | 복합 FK                    | 생성한 클러스터링 Job            |
| `created_by_job_attempt` | `integer`     |    N | -                   | CHECK `> 0`                | 생성 당시 attempt                |
| `created_at`             | `timestamptz` |    N | `now()`             | -                          | 생성 시각                        |
| `updated_at`             | `timestamptz` |    N | `now()`             | -                          | 갱신 시각                        |

제약·인덱스:

- `UNIQUE (id, session_id)`
- `CHECK (length(btrim(title)) > 0)`
- `CHECK ((is_final AND finalized_at IS NOT NULL) OR (NOT is_final AND finalized_at IS NULL))`
- `UNIQUE (created_by_job_id, created_by_job_attempt, ordinal)`
- `INDEX question_clusters_session_idx (session_id, is_final DESC, created_at, id)`
- `INDEX question_clusters_job_idx (created_by_job_id)`
- `session_id ON DELETE CASCADE`
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`; 결과가 남아 있는 Job만 독립 삭제할 수 없고 Session 전체 삭제 transaction은 허용한다.

재클러스터링은 새 Cluster 행을 만든 뒤 `questions.cluster_id`를 새 현재 값으로 갱신한다. 교체된 Cluster는 Answer가 선택했던 행이어도 삭제한다. 선택 당시 Cluster ID·제목과 질문 membership은 Answer snapshot에 남는다. 수업 종료 후 새 final Cluster만 `is_final = true`로 표시하고 그 시점의 `questions.cluster_id`를 최종 배치로 보존한다. 이후 final 결과를 다시 확정하면 대체된 final Cluster도 삭제해 일반 변경 이력을 만들지 않는다.

### 8.2 `questions`

익명으로 공개되는 질문과 내부 작성자·현재 클러스터를 저장한다.

| 컬럼             | 타입          | NULL | 기본값              | 키·제약                    | 설명               |
| ---------------- | ------------- | ---: | ------------------- | -------------------------- | ------------------ |
| `id`             | `uuid`        |    N | `gen_random_uuid()` | PK                         | Question ID        |
| `session_id`     | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class         |
| `author_user_id` | `uuid`        |    N | -                   | FK → `users.id`            | 외부 비공개 작성자 |
| `cluster_id`     | `uuid`        |    Y | `NULL`              | 복합 FK                    | 현재 Cluster       |
| `content`        | `text`        |    N | -                   | CHECK                      | 질문 내용          |
| `status`         | `text`        |    N | `'OPEN'`            | CHECK                      | 상태               |
| `reaction_count` | `integer`     |    N | `0`                 | CHECK `>= 0`               | 반응 집계 cache    |
| `version`        | `bigint`      |    N | `1`                 | CHECK `> 0`                | 실시간 리소스 버전 |
| `created_at`     | `timestamptz` |    N | `now()`             | -                          | 생성 시각          |
| `updated_at`     | `timestamptz` |    N | `now()`             | -                          | 갱신 시각          |

제약·인덱스:

- `UNIQUE (id, session_id)`
- `(cluster_id, session_id) FK → question_clusters(id, session_id) ON DELETE SET NULL (cluster_id)`; Cluster 삭제 시 `session_id`는 유지하고 `cluster_id`만 `NULL` 처리한다. PostgreSQL 15 이상의 column-list `SET NULL`을 사용한다.
- `CHECK (length(btrim(content)) > 0)`
- `INDEX questions_recent_idx (session_id, status, created_at DESC, id DESC)`
- `INDEX questions_popular_idx (session_id, status, reaction_count DESC, created_at DESC, id DESC)`
- `INDEX questions_cluster_idx (session_id, cluster_id, status, created_at, id)`
- `session_id ON DELETE CASCADE`
- `author_user_id ON DELETE RESTRICT`; 탈퇴 사용자는 익명화한다.

`reaction_count`는 인기순 저지연 조회를 위해 저장한다. 반응 행 변경과 같은 트랜잭션에서 원자적으로 증감하고, 운영 점검에서 실제 `COUNT(*)`와 불일치를 복구한다.

### 8.3 `question_reactions`

학생별 ‘나도 궁금해요’ 반응을 저장한다.

| 컬럼          | 타입          | NULL | 기본값  | 키·제약                 | 설명        |
| ------------- | ------------- | ---: | ------- | ----------------------- | ----------- |
| `question_id` | `uuid`        |    N | -       | PK, FK → `questions.id` | 질문        |
| `user_id`     | `uuid`        |    N | -       | PK, FK → `users.id`     | 반응 사용자 |
| `created_at`  | `timestamptz` |    N | `now()` | -                       | 반응 시각   |

제약·인덱스:

- PK `(question_id, user_id)`가 중복 반응을 막는다.
- `INDEX question_reactions_user_idx (user_id, created_at DESC)`
- `question_id ON DELETE CASCADE`
- `user_id ON DELETE CASCADE`
- 자기 질문 반응 금지는 다른 행의 `author_user_id`를 비교해야 하므로 서비스 트랜잭션에서 검증한다.

### 8.4 `answers`

교수자의 음성 답변 캡처와 확정 Transcript 범위를 저장한다.

| 컬럼                             | 타입          | NULL | 기본값              | 키·제약                    | 설명                            |
| -------------------------------- | ------------- | ---: | ------------------- | -------------------------- | ------------------------------- |
| `id`                             | `uuid`        |    N | `gen_random_uuid()` | PK                         | Answer ID                       |
| `session_id`                     | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                      |
| `professor_user_id`              | `uuid`        |    Y | `NULL`              | FK → `users.id`            | 답변 교수자                     |
| `status`                         | `text`        |    N | `'CAPTURING'`       | CHECK                      | 상태                            |
| `source_cluster_id_snapshot`     | `uuid`        |    Y | `NULL`              | 의도적으로 FK 없음         | 선택 당시 Cluster ID snapshot   |
| `source_cluster_title_snapshot`  | `text`        |    Y | `NULL`              | -                          | Cluster 삭제 후에도 남길 제목   |
| `capture_started_after_sequence` | `bigint`      |    N | -                   | CHECK `>= 0`               | 선택 시점 마지막 final sequence |
| `start_segment_id`               | `uuid`        |    Y | `NULL`              | 복합 FK                    | 확정 범위 첫 Segment            |
| `end_segment_id`                 | `uuid`        |    Y | `NULL`              | 복합 FK                    | 확정 범위 마지막 Segment        |
| `version`                        | `bigint`      |    N | `1`                 | CHECK `> 0`                | 실시간 리소스 버전              |
| `started_at`                     | `timestamptz` |    N | `now()`             | -                          | 캡처 시작 시각                  |
| `completed_at`                   | `timestamptz` |    Y | `NULL`              | -                          | 완료 시각                       |
| `cancelled_at`                   | `timestamptz` |    Y | `NULL`              | -                          | 취소 시각                       |
| `created_at`                     | `timestamptz` |    N | `now()`             | -                          | 생성 시각                       |
| `updated_at`                     | `timestamptz` |    N | `now()`             | -                          | 갱신 시각                       |

제약·인덱스:

- `UNIQUE (id, session_id)`
- `UNIQUE INDEX answers_one_capturing_per_session_uq (session_id) WHERE status = 'CAPTURING'`
- `(start_segment_id, session_id) FK → transcript_segments(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(end_segment_id, session_id) FK → transcript_segments(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `CHECK ((start_segment_id IS NULL) = (end_segment_id IS NULL))`
- `CHECK ((source_cluster_id_snapshot IS NULL) = (source_cluster_title_snapshot IS NULL))`
- `CHECK ((status = 'CAPTURING' AND completed_at IS NULL AND cancelled_at IS NULL AND start_segment_id IS NULL) OR (status = 'COMPLETED' AND completed_at IS NOT NULL AND cancelled_at IS NULL AND start_segment_id IS NOT NULL) OR (status = 'CANCELLED' AND cancelled_at IS NOT NULL AND completed_at IS NULL AND start_segment_id IS NULL))`
- `CHECK (completed_at IS NULL OR completed_at >= started_at)`
- `CHECK (cancelled_at IS NULL OR cancelled_at >= started_at)`
- `INDEX answers_session_started_idx (session_id, started_at, id)`
- `session_id ON DELETE CASCADE`
- `professor_user_id ON DELETE SET NULL`

API의 `start_sequence`, `end_sequence`는 두 Segment를 join해 계산한다. 범위 순서와 같은 Session 여부는 완료 트랜잭션에서 검증한다.

`source_cluster_id_snapshot`은 더 이상 존재하지 않을 수 있는 과거 Cluster의 식별값이므로 FK를 걸지 않는다. Answer 시작 transaction에서 Cluster가 같은 Session의 현재 행인지 검증한 뒤 ID·제목을 기록하며 이후 수정하지 않는다. 실제 답변 대상의 원장은 `answer_questions`다.

### 8.5 `answer_questions`

Answer가 직접 선택하거나 Cluster 선택 시점에 포함한 질문 목록을 immutable snapshot으로 저장한다.

| 컬럼          | 타입          | NULL | 기본값  | 키·제약      | 설명                             |
| ------------- | ------------- | ---: | ------- | ------------ | -------------------------------- |
| `answer_id`   | `uuid`        |    N | -       | PK, 복합 FK  | Answer                           |
| `question_id` | `uuid`        |    N | -       | PK, 복합 FK  | Question                         |
| `session_id`  | `uuid`        |    N | -       | 복합 FK      | 동일 Session 검증                |
| `position`    | `integer`     |    N | -       | CHECK `>= 0` | snapshot 표시 순서               |
| `released_at` | `timestamptz` |    Y | `NULL`  | -            | Answer 취소로 질문을 해제한 시각 |
| `created_at`  | `timestamptz` |    N | `now()` | -            | snapshot 시각                    |

제약·인덱스:

- PK `(answer_id, question_id)`
- `(answer_id, session_id) FK → answers(id, session_id) ON DELETE CASCADE`
- `(question_id, session_id) FK → questions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `UNIQUE (answer_id, position)`
- `CHECK (released_at IS NULL OR released_at >= created_at)`
- `UNIQUE INDEX answer_questions_one_active_answer_uq (question_id) WHERE released_at IS NULL`
- `INDEX answer_questions_question_idx (question_id, created_at DESC)`

한 질문에는 취소되지 않은 Answer가 최대 하나다. Answer 취소 시 행을 삭제하지 않고 `released_at`을 기록해 audit snapshot을 남긴 뒤 Question을 `OPEN`으로 돌린다. 이후 다른 Answer가 해당 질문을 선택할 수 있다.

## 9. 비동기 작업

### 9.1 `ai_jobs`

PDF 처리, 클러스터링, 요약, Chat 응답과 Session 후처리 상태를 저장한다. 재시도는 같은 행을 사용한다.

| 컬럼                        | 타입          | NULL | 기본값              | 키·제약                    | 설명                         |
| --------------------------- | ------------- | ---: | ------------------- | -------------------------- | ---------------------------- |
| `id`                        | `uuid`        |    N | `gen_random_uuid()` | PK                         | AIJob ID                     |
| `session_id`                | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 작업 범위 class              |
| `requester_user_id`         | `uuid`        |    Y | `NULL`              | FK → `users.id`            | 개인 작업 요청자             |
| `job_type`                  | `text`        |    N | -                   | CHECK                      | 작업 유형                    |
| `visibility`                | `text`        |    N | -                   | CHECK                      | `SHARED`, `REQUESTER_ONLY`   |
| `status`                    | `text`        |    N | `'PENDING'`         | CHECK                      | 작업 상태                    |
| `attempt`                   | `integer`     |    N | `1`                 | CHECK `> 0`                | 현재 시도 번호               |
| `version`                   | `bigint`      |    N | `1`                 | CHECK `> 0`                | 상태 이벤트 버전             |
| `target_material_id`        | `uuid`        |    Y | `NULL`              | 복합 FK                    | 자료 처리 대상               |
| `target_question_id`        | `uuid`        |    Y | `NULL`              | 복합 FK                    | 실시간 클러스터링 시작 질문  |
| `target_chat_id`            | `uuid`        |    Y | `NULL`              | 복합 FK                    | Chat 응답 대상               |
| `dedupe_key_hash`           | `bytea`       |    Y | `NULL`              | -                          | 논리 작업 중복 방지 키       |
| `available_at`              | `timestamptz` |    N | `now()`             | -                          | worker가 실행할 수 있는 시각 |
| `blocks_session_completion` | `boolean`     |    N | `false`             | -                          | Session 완료 판정 대상 여부  |
| `run_token`                 | `uuid`        |    Y | `NULL`              | -                          | 현재 worker lease token      |
| `lease_expires_at`          | `timestamptz` |    Y | `NULL`              | -                          | worker lease 만료            |
| `progress_stage`            | `text`        |    Y | `NULL`              | -                          | 작업별 단계 코드             |
| `progress_percent`          | `smallint`    |    Y | `NULL`              | CHECK `0..100`             | 계산 가능한 경우 진행률      |
| `retryable`                 | `boolean`     |    N | `false`             | -                          | 재시도 가능 여부             |
| `error_code`                | `text`        |    Y | `NULL`              | -                          | 안전한 오류 코드             |
| `error_message`             | `text`        |    Y | `NULL`              | -                          | 민감정보 없는 오류 메시지    |
| `created_at`                | `timestamptz` |    N | `now()`             | -                          | 생성 시각                    |
| `updated_at`                | `timestamptz` |    N | `now()`             | -                          | 갱신 시각                    |
| `started_at`                | `timestamptz` |    Y | `NULL`              | -                          | 현재/마지막 시도 시작        |
| `finished_at`               | `timestamptz` |    Y | `NULL`              | -                          | 현재/마지막 시도 종료        |

다형 관계 회피:

- 공통 `target_type + target_id`를 두지 않는다.
- Job 범위는 `session_id`, 구체 대상은 `target_material_id`, `target_question_id`, `target_chat_id`라는 실제 FK로 표현한다.
- Summary와 Session 후처리는 `session_id` 자체가 target이다.
- 결과는 Job에 generic result ID를 저장하지 않고 결과 테이블의 `created_by_job_id`로 조회한다.

제약·인덱스:

- `UNIQUE (id, session_id)`; 모든 결과가 원인 Job과 같은 Session인지 검증할 때 사용한다.
- `CHECK (num_nonnulls(target_material_id, target_question_id, target_chat_id) <= 1)`
- `CHECK (target_material_id IS NULL OR job_type = 'MATERIAL_PROCESSING')`
- `CHECK (target_question_id IS NULL OR job_type = 'QUESTION_CLUSTERING')`
- `CHECK (target_chat_id IS NULL OR job_type = 'CHAT_RESPONSE')`
- `CHECK (job_type <> 'MATERIAL_PROCESSING' OR target_material_id IS NOT NULL)`
- `CHECK (job_type <> 'CHAT_RESPONSE' OR target_chat_id IS NOT NULL)`
- `CHECK ((visibility = 'REQUESTER_ONLY' AND requester_user_id IS NOT NULL) OR visibility = 'SHARED')`
- `CHECK (NOT blocks_session_completion OR visibility = 'SHARED')`
- `CHECK (progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100)`
- `CHECK ((run_token IS NOT NULL) = (status = 'RUNNING'))`
- `CHECK ((lease_expires_at IS NOT NULL) = (status = 'RUNNING'))`
- `CHECK ((status = 'PENDING' AND started_at IS NULL AND finished_at IS NULL AND error_code IS NULL AND error_message IS NULL) OR (status = 'RUNNING' AND started_at IS NOT NULL AND finished_at IS NULL AND error_code IS NULL AND error_message IS NULL) OR (status = 'SUCCEEDED' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND error_code IS NULL AND error_message IS NULL) OR (status = 'FAILED' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND error_code IS NOT NULL))`
- `CHECK (finished_at IS NULL OR finished_at >= started_at)`
- `CHECK (dedupe_key_hash IS NULL OR octet_length(dedupe_key_hash) = 32)`
- `UNIQUE INDEX ai_jobs_dedupe_uq (session_id, job_type, dedupe_key_hash) WHERE dedupe_key_hash IS NOT NULL`
- `UNIQUE INDEX ai_jobs_one_active_chat_response_uq (target_chat_id) WHERE job_type = 'CHAT_RESPONSE' AND status IN ('PENDING', 'RUNNING')`
- `UNIQUE INDEX ai_jobs_one_active_material_processing_uq (target_material_id) WHERE job_type = 'MATERIAL_PROCESSING' AND status IN ('PENDING', 'RUNNING')`
- `INDEX ai_jobs_session_shared_idx (session_id, status, job_type, created_at DESC) WHERE visibility = 'SHARED'`
- `INDEX ai_jobs_requester_idx (requester_user_id, status, created_at DESC) WHERE requester_user_id IS NOT NULL`
- `INDEX ai_jobs_claim_idx (available_at, created_at, id) WHERE status = 'PENDING'`
- `INDEX ai_jobs_lease_idx (lease_expires_at) WHERE status = 'RUNNING'`
- `session_id ON DELETE CASCADE`
- `requester_user_id ON DELETE RESTRICT`; User 행은 기본적으로 익명화하며 hard delete workflow는 개인 Job을 삭제하고 공유 Job의 requester를 명시적으로 `NULL` 처리한 뒤 진행한다.
- `(target_material_id, session_id) FK → lecture_materials(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(target_question_id, session_id) FK → questions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(target_chat_id, session_id) FK → chat_sessions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

typed target FK는 target만 독립 삭제하는 것은 막고 Session aggregate 전체 삭제는 한 transaction에서 허용한다.

`dedupe_key_hash`는 목적별 HMAC으로 계산한다. 입력에는 `session_id`, `job_type`, `visibility`, `REQUESTER_ONLY`이면 `requester_user_id`, 세 typed target, 처리할 Transcript 범위와 정규화된 논리 입력 digest를 포함한다. 따라서 다른 사용자나 다른 Session의 개인 작업이 같은 Job으로 합쳐지지 않는다.

재시도 규칙:

```text
FAILED → PENDING
attempt = attempt + 1
version = version + 1
available_at = now() 또는 backoff 종료 시각
run_token, lease_expires_at, progress, error, started_at, finished_at = NULL
```

worker는 실행 시작 시 새 `run_token`과 lease를 기록한다. 결과 저장과 성공 전이는 `WHERE id = :id AND status = 'RUNNING' AND attempt = :attempt AND run_token = :run_token` 조건으로 수행해 이전 attempt의 늦은 응답이 최신 결과를 덮어쓰지 못하게 한다.
성공·실패 terminal 전이에서는 `run_token`, `lease_expires_at`을 `NULL`로 정리한다.

### 9.2 Job 결과 역참조 규칙

| Job 결과                     | 결과 테이블           | 규칙                                              |
| ---------------------------- | --------------------- | ------------------------------------------------- |
| PDF 처리 상태                | `lecture_materials`   | `processed_by_job_id`, `processed_by_job_attempt` |
| PDF·Transcript·Q&A 검색 조각 | `knowledge_chunks`    | `created_by_job_id`, `created_by_job_attempt`     |
| 질문 클러스터                | `question_clusters`   | 같은 Job에서 여러 행 가능                         |
| LIVE/FINAL 요약              | `lecture_summaries`   | Job당 한 결과                                     |
| Assistant 답변               | `chat_messages`       | Job당 한 Assistant Message                        |
| 선택적 STT 후처리 결과       | `transcript_segments` | streaming 직접 저장이면 Job FK는 `NULL` 가능      |

Job 결과 행 삽입 또는 Material 상태 확정과 `ai_jobs.status = 'SUCCEEDED'` 전이는 같은 DB 트랜잭션에서 수행한다. 실패한 attempt가 만든 중간 결과는 commit하지 않는다. `chat_message_evidence`처럼 결과 aggregate의 종속 행은 상위 `chat_messages.created_by_job_id`를 통해 같은 Job에 귀속된다.

결과 commit은 복합 FK의 같은 Session 조건에 더해 Job의 현재 `attempt`, `run_token`, `job_type`, `visibility`, requester와 정확한 typed target을 대조한다. 서비스 검증과 deferred constraint trigger의 공통 규칙은 다음과 같다.

- Material 상태와 Material source Chunk: `MATERIAL_PROCESSING`, `target_material_id = material_id`
- Cluster: `QUESTION_CLUSTERING`; final 여부는 종료 후처리 요청과 일치
- LIVE Summary: `LIVE_SUMMARY`, `REQUESTER_ONLY`, Job requester와 Summary requester가 동일
- FINAL Summary: `FINAL_SUMMARY`, `SHARED`, Summary requester는 `NULL`
- Assistant Message·Evidence: `CHAT_RESPONSE`, `target_chat_id = chat_id`, Job requester와 Chat owner가 동일
- Transcript·Question·Answer source Chunk: 허용된 producer Job 유형과 실제 source가 현재 처리 입력 범위에 포함

## 10. 공통 검색 지식

### 10.1 `knowledge_chunks`

PDF, final Transcript, Question과 Answer를 같은 RAG 검색 단위로 통합한다. `source_type + source_id` 대신 실제 nullable FK를 사용하며 정확히 한 source 계열만 값이 있어야 한다.

| 컬럼                          | 타입                    | NULL | 기본값              | 키·제약      | 설명                        |
| ----------------------------- | ----------------------- | ---: | ------------------- | ------------ | --------------------------- |
| `id`                          | `uuid`                  |    N | `gen_random_uuid()` | PK           | KnowledgeChunk ID           |
| `course_id`                   | `uuid`                  |    N | -                   | 복합 FK      | 검색 Course 범위            |
| `session_id`                  | `uuid`                  |    N | -                   | 복합 FK      | 검색 class 범위             |
| `material_id`                 | `uuid`                  |    Y | `NULL`              | 복합 FK      | PDF source                  |
| `transcript_start_segment_id` | `uuid`                  |    Y | `NULL`              | 복합 FK      | Transcript source 범위 시작 |
| `transcript_end_segment_id`   | `uuid`                  |    Y | `NULL`              | 복합 FK      | Transcript source 범위 끝   |
| `question_id`                 | `uuid`                  |    Y | `NULL`              | 복합 FK      | Question source             |
| `answer_id`                   | `uuid`                  |    Y | `NULL`              | 복합 FK      | Answer source               |
| `chunk_index`                 | `integer`               |    N | -                   | CHECK `>= 0` | source 내 순번              |
| `page_number`                 | `integer`               |    Y | `NULL`              | CHECK `> 0`  | Material source 페이지      |
| `content`                     | `text`                  |    N | -                   | CHECK        | 검색 텍스트                 |
| `token_count`                 | `integer`               |    Y | `NULL`              | CHECK `>= 0` | 모델 tokenizer 기준         |
| `embedding`                   | `vector(EMBEDDING_DIM)` |    N | -                   | -            | 임베딩                      |
| `embedding_model`             | `text`                  |    N | -                   | -            | 모델·버전 식별자            |
| `created_by_job_id`           | `uuid`                  |    N | -                   | 복합 FK      | 생성 Job                    |
| `created_by_job_attempt`      | `integer`               |    N | -                   | CHECK `> 0`  | 생성 attempt                |
| `created_at`                  | `timestamptz`           |    N | `now()`             | -            | 생성 시각                   |

범위·source 제약:

- `CHECK ((transcript_start_segment_id IS NULL) = (transcript_end_segment_id IS NULL))`
- `CHECK (num_nonnulls(material_id, transcript_start_segment_id, question_id, answer_id) = 1)`
- `CHECK (page_number IS NULL OR material_id IS NOT NULL)`
- `(session_id, course_id) FK → lecture_sessions(id, course_id) ON DELETE CASCADE`
- `(material_id, session_id) FK → lecture_materials(id, session_id) ON DELETE CASCADE`
- `(transcript_start_segment_id, session_id) FK → transcript_segments(id, session_id) ON DELETE CASCADE`
- `(transcript_end_segment_id, session_id) FK → transcript_segments(id, session_id) ON DELETE CASCADE`
- `(question_id, session_id) FK → questions(id, session_id) ON DELETE CASCADE`
- `(answer_id, session_id) FK → answers(id, session_id) ON DELETE CASCADE`
- source가 `NULL`인 복합 FK는 PostgreSQL 기본 `MATCH SIMPLE`에 따라 검사하지 않는다.
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

고유·조회 인덱스:

- `UNIQUE (id, session_id)`
- `UNIQUE INDEX knowledge_chunks_material_ordinal_uq (material_id, chunk_index) WHERE material_id IS NOT NULL`
- `UNIQUE INDEX knowledge_chunks_transcript_ordinal_uq (session_id, transcript_start_segment_id, transcript_end_segment_id, chunk_index) WHERE transcript_start_segment_id IS NOT NULL`
- `UNIQUE INDEX knowledge_chunks_question_ordinal_uq (question_id, chunk_index) WHERE question_id IS NOT NULL`
- `UNIQUE INDEX knowledge_chunks_answer_ordinal_uq (answer_id, chunk_index) WHERE answer_id IS NOT NULL`
- `INDEX knowledge_chunks_scope_idx (course_id, session_id)`
- `INDEX knowledge_chunks_job_idx (created_by_job_id, created_by_job_attempt)`
- embedding 모델과 차원을 확정한 뒤 `USING hnsw (embedding vector_cosine_ops)` 인덱스를 생성한다.

Transcript 범위의 시작·끝 순서와 같은 Session 여부는 복합 FK와 constraint trigger로 검증한다. 모든 vector 검색은 `course_id = :course_id AND session_id = :session_id`를 먼저 강제한다. `course_id`는 vector filter 성능을 위한 의도적 중복이며 `(session_id, course_id)` FK가 불일치를 막는다.

## 11. 요약·AI Chat

### 11.1 `lecture_summaries`

성공한 LIVE/FINAL 요약을 보관한다. LIVE는 요청자 전용, FINAL은 Course 멤버 공유다.

| 컬럼                      | 타입          | NULL | 기본값              | 키·제약                    | 설명            |
| ------------------------- | ------------- | ---: | ------------------- | -------------------------- | --------------- |
| `id`                      | `uuid`        |    N | `gen_random_uuid()` | PK                         | Summary ID      |
| `session_id`              | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class      |
| `requester_user_id`       | `uuid`        |    Y | `NULL`              | FK → `users.id`            | LIVE 요청자     |
| `created_by_job_id`       | `uuid`        |    N | -                   | 복합 FK                    | 생성 Job        |
| `created_by_job_attempt`  | `integer`     |    N | -                   | CHECK `> 0`                | 생성 attempt    |
| `summary_type`            | `text`        |    N | -                   | CHECK                      | `LIVE`, `FINAL` |
| `visibility`              | `text`        |    N | -                   | CHECK                      | 공개 범위       |
| `content`                 | `text`        |    N | -                   | CHECK                      | 요약 본문       |
| `source_start_segment_id` | `uuid`        |    Y | `NULL`              | 복합 FK                    | 선택 범위 시작  |
| `source_end_segment_id`   | `uuid`        |    Y | `NULL`              | 복합 FK                    | 선택 범위 종료  |
| `model_name`              | `text`        |    Y | `NULL`              | -                          | 모델 식별자     |
| `prompt_version`          | `text`        |    Y | `NULL`              | -                          | 프롬프트 버전   |
| `created_at`              | `timestamptz` |    N | `now()`             | -                          | 생성 시각       |

제약·인덱스:

- `UNIQUE (created_by_job_id)`; 한 Summary Job은 결과 하나만 만든다.
- `CHECK ((summary_type = 'LIVE' AND visibility = 'REQUESTER_ONLY' AND requester_user_id IS NOT NULL) OR (summary_type = 'FINAL' AND visibility = 'COURSE_MEMBERS' AND requester_user_id IS NULL))`
- `CHECK ((source_start_segment_id IS NULL) = (source_end_segment_id IS NULL))`
- `CHECK (length(btrim(content)) > 0)`
- `(source_start_segment_id, session_id) FK → transcript_segments(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(source_end_segment_id, session_id) FK → transcript_segments(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- 시작 Segment의 `sequence <=` 끝 Segment의 `sequence`를 결과 commit과 deferred constraint trigger로 검증한다.
- `INDEX lecture_summaries_session_type_idx (session_id, summary_type, created_at DESC, id DESC)`
- `INDEX lecture_summaries_requester_idx (requester_user_id, session_id, created_at DESC) WHERE requester_user_id IS NOT NULL`
- `session_id ON DELETE CASCADE`
- `requester_user_id ON DELETE CASCADE`; 개인 LIVE Summary를 함께 삭제한다.
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

같은 FINAL Summary Job의 retry는 동일 Job 행을 쓰므로 성공 결과도 최대 한 행이다. MVP는 Session별 하나의 논리 FINAL Summary Job을 dedupe한다. 향후 명시적 재생성 기능이 추가되어 새 Job을 허용할 때만 여러 결과 행을 보관하고 `(created_at DESC, id DESC)`로 최신 결과를 선택한다.

### 11.2 `chat_sessions`

사용자 개인 AI 대화와 Session 범위를 저장한다.

| 컬럼            | 타입          | NULL | 기본값              | 키·제약                    | 설명             |
| --------------- | ------------- | ---: | ------------------- | -------------------------- | ---------------- |
| `id`            | `uuid`        |    N | `gen_random_uuid()` | PK                         | Chat ID          |
| `session_id`    | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 지식 범위 class  |
| `owner_user_id` | `uuid`        |    N | -                   | FK → `users.id`            | 대화 소유자      |
| `mode`          | `text`        |    N | -                   | CHECK                      | `LIVE`, `REVIEW` |
| `version`       | `bigint`      |    N | `1`                 | CHECK `> 0`                | 대화 버전        |
| `created_at`    | `timestamptz` |    N | `now()`             | -                          | 생성 시각        |
| `updated_at`    | `timestamptz` |    N | `now()`             | -                          | 최근 메시지 시각 |

제약·인덱스:

- `UNIQUE (id, session_id)`
- `INDEX chat_sessions_owner_idx (owner_user_id, session_id, updated_at DESC, id DESC)`
- `session_id ON DELETE CASCADE`
- `owner_user_id ON DELETE CASCADE`

### 11.3 `chat_messages`

Chat의 사용자·Assistant 메시지를 순서대로 저장한다.

| 컬럼                     | 타입          | NULL | 기본값              | 키·제약     | 설명                    |
| ------------------------ | ------------- | ---: | ------------------- | ----------- | ----------------------- |
| `id`                     | `uuid`        |    N | `gen_random_uuid()` | PK          | Message ID              |
| `chat_id`                | `uuid`        |    N | -                   | 복합 FK     | 소속 Chat               |
| `session_id`             | `uuid`        |    N | -                   | 복합 FK     | 근거 범위 검증          |
| `sequence`               | `bigint`      |    N | -                   | CHECK `> 0` | Chat 내 순서            |
| `role`                   | `text`        |    N | -                   | CHECK       | `USER`, `ASSISTANT`     |
| `content`                | `text`        |    N | -                   | CHECK       | 메시지 본문             |
| `created_by_job_id`      | `uuid`        |    Y | `NULL`              | 복합 FK     | Assistant 생성 Job      |
| `created_by_job_attempt` | `integer`     |    Y | `NULL`              | CHECK `> 0` | 생성 attempt            |
| `model_name`             | `text`        |    Y | `NULL`              | -           | Assistant 모델          |
| `prompt_version`         | `text`        |    Y | `NULL`              | -           | Assistant 프롬프트 버전 |
| `created_at`             | `timestamptz` |    N | `now()`             | -           | 생성 시각               |

제약·인덱스:

- `UNIQUE (chat_id, sequence)`
- `UNIQUE (id, session_id)`
- `UNIQUE INDEX chat_messages_created_by_job_uq (created_by_job_id) WHERE created_by_job_id IS NOT NULL`
- `(chat_id, session_id) FK → chat_sessions(id, session_id) ON DELETE CASCADE`
- `CHECK (length(btrim(content)) > 0)`
- `CHECK ((role = 'USER' AND created_by_job_id IS NULL AND created_by_job_attempt IS NULL) OR (role = 'ASSISTANT' AND created_by_job_id IS NOT NULL AND created_by_job_attempt IS NOT NULL))`
- `INDEX chat_messages_chat_sequence_idx (chat_id, sequence)`
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

Chat row를 `SELECT ... FOR UPDATE`로 잠근 뒤 다음 sequence를 할당한다. AIJob 결과 Message 삽입과 Job 성공 전이는 한 트랜잭션으로 처리한다.

### 11.4 `chat_message_evidence`

Assistant Message가 실제로 사용한 공통 KnowledgeChunk를 순위와 함께 저장한다.

| 컬럼                 | 타입               | NULL | 기본값  | 키·제약         | 설명                                   |
| -------------------- | ------------------ | ---: | ------- | --------------- | -------------------------------------- |
| `chat_message_id`    | `uuid`             |    N | -       | PK, 복합 FK     | Assistant Message                      |
| `knowledge_chunk_id` | `uuid`             |    N | -       | 복합 FK         | 사용한 Chunk                           |
| `session_id`         | `uuid`             |    N | -       | 복합 FK         | 동일 Session 검증                      |
| `rank`               | `integer`          |    N | -       | PK, CHECK `> 0` | 근거 순위                              |
| `relevance_score`    | `double precision` |    Y | `NULL`  | -               | 검색 점수 snapshot                     |
| `label`              | `text`             |    Y | `NULL`  | -               | 페이지·Transcript 시각 표시용 snapshot |
| `created_at`         | `timestamptz`      |    N | `now()` | -               | 저장 시각                              |

제약·인덱스:

- PK `(chat_message_id, rank)`
- `UNIQUE (chat_message_id, knowledge_chunk_id)`; Chunk 전체에 대한 단독 UNIQUE는 두지 않는다.
- `(chat_message_id, session_id) FK → chat_messages(id, session_id) ON DELETE CASCADE`
- `(knowledge_chunk_id, session_id) FK → knowledge_chunks(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- Evidence 생성 시 대상 Message가 `ASSISTANT`인지 서비스에서 확인한다.

## 12. 요청 멱등성·이벤트 발행

### 12.1 `idempotency_records`

`Idempotency-Key`가 필요한 쓰기 요청의 처리 상태와 재응답 데이터를 저장한다. Course 생성 응답처럼 참여 코드를 포함할 수 있으므로 응답 본문을 평문 `jsonb`로 보관하지 않는다.

| 컬럼                       | 타입          | NULL | 기본값              | 키·제약         | 설명                                |
| -------------------------- | ------------- | ---: | ------------------- | --------------- | ----------------------------------- |
| `id`                       | `uuid`        |    N | `gen_random_uuid()` | PK              | 멱등성 처리 ID                      |
| `user_id`                  | `uuid`        |    N | -                   | FK → `users.id` | 요청 사용자                         |
| `http_method`              | `text`        |    N | -                   | CHECK           | 대문자 HTTP method                  |
| `route_key`                | `text`        |    N | -                   | CHECK           | path parameter를 정규화한 route ID  |
| `idempotency_key_hash`     | `bytea`       |    N | -                   | -               | 원문 key의 HMAC                     |
| `request_hash`             | `bytea`       |    N | -                   | -               | 정규화 요청 method·path·body hash   |
| `state`                    | `text`        |    N | `'PROCESSING'`      | CHECK           | `PROCESSING`, `COMPLETED`, `FAILED` |
| `locked_until`             | `timestamptz` |    Y | `NULL`              | -               | 처리 주체 lease 만료                |
| `response_status`          | `smallint`    |    Y | `NULL`              | CHECK           | 완료된 HTTP status                  |
| `response_body_ciphertext` | `bytea`       |    Y | `NULL`              | -               | AES-GCM 응답 본문                   |
| `response_body_nonce`      | `bytea`       |    Y | `NULL`              | -               | 암호화 nonce                        |
| `response_key_version`     | `smallint`    |    Y | `NULL`              | CHECK `> 0`     | 응답 암호화 키 버전                 |
| `expires_at`               | `timestamptz` |    N | -                   | CHECK           | record 만료 시각                    |
| `created_at`               | `timestamptz` |    N | `now()`             | -               | 최초 요청 시각                      |
| `updated_at`               | `timestamptz` |    N | `now()`             | -               | 처리 상태 갱신 시각                 |

제약·인덱스:

- `UNIQUE (user_id, http_method, route_key, idempotency_key_hash)`
- `CHECK (http_method IN ('POST', 'PUT', 'PATCH', 'DELETE'))`
- `CHECK (length(btrim(route_key)) > 0)`
- `CHECK (response_status IS NULL OR response_status BETWEEN 100 AND 599)`
- `CHECK (octet_length(idempotency_key_hash) = 32 AND octet_length(request_hash) = 32)`
- `CHECK (response_body_nonce IS NULL OR octet_length(response_body_nonce) = 12)`
- `CHECK ((response_body_ciphertext IS NULL AND response_body_nonce IS NULL AND response_key_version IS NULL) OR (response_body_ciphertext IS NOT NULL AND response_body_nonce IS NOT NULL AND response_key_version IS NOT NULL))`
- `CHECK (state <> 'COMPLETED' OR response_status IS NOT NULL)`
- `CHECK (expires_at > created_at)`
- `INDEX idempotency_records_expiry_idx (expires_at)`
- `user_id ON DELETE CASCADE`

같은 key로 다른 `request_hash`가 오면 `409 IDEMPOTENCY_KEY_REUSED`를 반환한다. `PROCESSING` record의 lease가 유효하면 중복 처리를 시작하지 않는다. 완료 응답은 기본 24시간 재사용하되 실제 보관 시간은 운영 정책 확정값으로 조정한다.

### 12.2 `outbox_events`

도메인 변경과 WebSocket·작업 큐·스토리지 정리 메시지 발행 사이의 유실을 막는 transactional outbox다. `source_type + source_id` 관계를 만들지 않고, Session 범위가 있는 이벤트만 실제 FK로 연결한다.

| 컬럼               | 타입          | NULL | 기본값              | 키·제약                    | 설명                                      |
| ------------------ | ------------- | ---: | ------------------- | -------------------------- | ----------------------------------------- |
| `id`               | `uuid`        |    N | `gen_random_uuid()` | PK                         | event ID와 WebSocket cursor 원본          |
| `session_id`       | `uuid`        |    Y | `NULL`              | FK → `lecture_sessions.id` | Session 범위 이벤트                       |
| `partition_key`    | `text`        |    N | -                   | CHECK                      | 순서 보장을 위한 안정적인 routing key     |
| `event_type`       | `text`        |    N | -                   | CHECK                      | API 명세의 event type 또는 내부 task type |
| `resource_version` | `bigint`      |    Y | `NULL`              | CHECK `> 0`                | 실시간 리소스 버전 snapshot               |
| `payload`          | `jsonb`       |    N | `'{}'::jsonb`       | -                          | 민감정보를 제외한 발행 payload            |
| `available_at`     | `timestamptz` |    N | `now()`             | -                          | 발행 가능 시각                            |
| `published_at`     | `timestamptz` |    Y | `NULL`              | -                          | broker·gateway 전달 완료 시각             |
| `publish_attempt`  | `integer`     |    N | `0`                 | CHECK `>= 0`               | 발행 시도 횟수                            |
| `last_error_code`  | `text`        |    Y | `NULL`              | -                          | 안전한 마지막 오류 코드                   |
| `created_at`       | `timestamptz` |    N | `now()`             | -                          | transaction commit 대상 생성 시각         |

제약·인덱스:

- `CHECK (length(btrim(partition_key)) > 0)`
- `CHECK (length(btrim(event_type)) > 0)`
- `INDEX outbox_events_unpublished_idx (available_at, created_at, id) WHERE published_at IS NULL`
- `INDEX outbox_events_session_replay_idx (session_id, created_at, id) WHERE session_id IS NOT NULL`
- `session_id ON DELETE SET NULL`; 스토리지 삭제 같은 보상 task는 원 리소스 삭제 후에도 남아야 한다.

`partition_key`는 `session:{uuid}` 또는 내부 queue key이며 도메인 FK를 흉내 내는 resource ID가 아니다. 발행자는 최소 한 번(at-least-once) 전달하므로 소비자는 `outbox_events.id`로 중복 제거한다. 공유 event payload에는 참여 코드, 질문 작성자 ID, 개인 Summary·Chat 본문을 넣지 않는다.

## 13. API 계산 필드와 조회 규칙

API 응답의 다음 필드는 별도 DB 컬럼을 만들지 않고 권한이 확인된 query에서 계산한다.

| API 필드                                | 계산 기준                                                                                                    |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `Course.role`                           | 현재 사용자의 `course_members.role`                                                                          |
| `Course.current_session`                | 해당 Course의 `LIVE` Session, 없으면 가장 최근 진행 상태를 API 계약에 맞게 선택                              |
| `Question.cluster`                      | `questions.cluster_id`로 현재 `question_clusters` join                                                       |
| `Question.reacted_by_me`                | 현재 사용자의 `question_reactions` 존재 여부                                                                 |
| `Question.reaction_count`               | `questions.reaction_count`; 원장은 `question_reactions`                                                      |
| `Answer.question_ids`                   | 해당 Answer의 모든 `answer_questions`를 `position` 순으로 반환; `released_at`은 현재 유효 연결 판정에만 사용 |
| `Answer.start_sequence`, `end_sequence` | `start_segment_id`, `end_segment_id`의 `transcript_segments.sequence`                                        |
| `AIJob.target`                          | `session_id`와 세 개의 typed target FK 중 값이 있는 FK                                                       |
| `AIJob.result`                          | 결과 테이블의 `created_by_job_id`; generic result FK는 없음                                                  |
| `SessionRecord`                         | Session, 자료, final Transcript, Answer, FINAL Summary를 권한에 맞게 조립                                    |
| `ChatEvidence.source_kind`              | `knowledge_chunks`에서 값이 있는 typed source FK로 안전하게 파생                                             |

목록 조회는 동일 정렬 값에서 `id`를 마지막 tie-breaker로 사용하고 cursor에도 포함한다. Chat vector 검색은 반드시 SQL 안에서 `course_id`와 `session_id`를 제한하며, 검색 후 애플리케이션에서 다른 Session 결과를 제거하는 방식을 사용하지 않는다.

## 14. 주요 트랜잭션·동시성 규칙

### 14.1 Course 생성과 참여

Course 생성은 다음 항목을 한 트랜잭션으로 처리한다.

1. `idempotency_records`를 선점하고 동일 요청인지 확인한다.
2. 서버가 참여 코드를 생성하고 정규화한다.
3. HMAC lookup hash와 AES-256-GCM 암호문을 만든다.
4. `courses`와 생성자의 `course_members(PROFESSOR)`를 함께 삽입한다.
5. 암호화한 응답과 멱등성 완료 상태를 기록한다.

참여 시 HMAC으로 Course를 찾고 `join_code_expires_at`을 확인한 뒤 Course 또는 멤버 행을 잠근다. `(course_id, user_id)`를 멱등 upsert하되 기존 `PROFESSOR` 역할을 `STUDENT`로 변경하지 않는다. HMAC UNIQUE 충돌이 난 코드 생성은 새 코드를 만들어 제한 횟수만큼 재시도한다.

### 14.2 class 생성·시작

- class 생성은 동일 날짜에도 여러 행을 허용한다.
- 시작은 `status = 'READY'` 조건으로 갱신하고 `started_at`, `version`을 함께 변경한다.
- 동시 시작 경쟁의 최종 방어선은 `lecture_sessions_one_live_per_course_uq`다. 충돌은 `409 SESSION_STATE_CONFLICT`로 변환한다.
- 실시간 audio ticket은 시작 권한과 `LIVE` 상태를 확인한 뒤 별도 짧은 트랜잭션에서 발급한다.

### 14.3 PDF 업로드와 전처리

파일 저장 성공 후 `lecture_materials`, `MATERIAL_PROCESSING` Job, outbox event를 같은 DB 트랜잭션으로 만든다. DB commit에 실패하면 업로드한 object를 보상 삭제한다. 반대로 DB 삭제 시에는 `storage_key`를 담은 삭제 outbox task를 같은 트랜잭션에 남긴다. `storage_key`만 UNIQUE이며 같은 내용의 PDF 재업로드는 허용한다.

처리 성공 transaction은 Job의 `target_material_id`가 갱신할 Material ID와 일치하는지 확인하고, KnowledgeChunk 삽입, Material `READY`/`processed_by_job_id` 갱신, Job `SUCCEEDED` 전환을 함께 commit한다.

### 14.4 Transcript 저장

- streaming STT의 partial 결과는 메모리·WebSocket 전송에만 사용하고 DB에 넣지 않는다.
- final 결과는 `(session_id, utterance_id)` upsert 또는 insert-on-conflict로 중복 저장을 막는다.
- 새 `sequence`는 `UPDATE lecture_sessions SET last_final_sequence = last_final_sequence + 1 ... RETURNING last_final_sequence`로 원자 할당하고 Segment insert를 같은 짧은 트랜잭션에서 처리한다.
- 끊김으로 복구할 수 없는 구간은 텍스트를 추측해 채우지 않고 `transcript_gaps`에 남긴다.

### 14.5 질문·반응·클러스터링

- 질문 생성과 `QUESTION_CLUSTERING` Job/outbox 등록을 같은 트랜잭션으로 처리한다.
- 반응 추가·삭제는 `(question_id, user_id)` 실제 삽입·삭제 성공 여부에 따라 `questions.reaction_count`를 같은 트랜잭션에서 `+1/-1` 한다.
- 자기 질문 반응 금지는 Question을 읽어 작성자를 비교하는 조건부 DML 또는 constraint trigger로 보장한다.
- 재클러스터링 worker는 Session과 대상 Question들을 잠그고 새 Cluster 행을 삽입한 뒤 `questions.cluster_id`를 한 번에 교체한다. 교체가 끝난 뒤 대체된 non-final Cluster를 모두 삭제한다. Answer의 Cluster ID·제목과 AnswerQuestion membership snapshot은 유지된다.
- 수업 종료 후 final clustering 결과는 새 Cluster 행에 `is_final = true`, `finalized_at`을 기록하고 질문 FK를 원자적으로 교체한다. 현재 final Cluster는 Session 삭제 전까지 보관한다. 나중에 final 결과를 다시 확정하면 새 세트를 commit한 뒤 대체된 final 세트를 삭제한다.
- 클러스터 membership 변경 이력이나 과거 질문→Cluster 매핑은 저장하지 않는다.

### 14.6 Answer 시작·완료·취소

Answer 시작은 다음 순서로 처리한다.

1. Session을 잠그고 `LIVE`인지, 요청자가 해당 Course의 `PROFESSOR`인지 확인한다.
2. `CAPTURING` Answer가 없는지 확인한다. 경쟁 요청은 partial UNIQUE가 최종 차단한다.
3. 직접 선택된 질문 또는 선택 Cluster의 현재 질문을 잠근다.
4. `answers`를 만들고 선택 시점 마지막 final Transcript `sequence`를 `capture_started_after_sequence`에 저장한다.
5. 질문 ID와 표시 순서를 `answer_questions`에 snapshot하고 Question 상태를 `SELECTED`로 바꾼다.
6. Answer와 질문 event를 outbox에 기록하고 commit한다.

완료 시 첫·마지막 Segment를 잠그고 둘이 Answer와 같은 Session인지, `start.sequence <= end.sequence`, `start.sequence > capture_started_after_sequence`인지 검증한다. 이를 deferrable constraint trigger로도 이중 검증한다. Answer를 `COMPLETED`, 대상 질문을 `ANSWERED`로 바꾸고 outbox event를 함께 기록한다.

취소 시 Answer를 `CANCELLED`로 바꾸고 해당 `answer_questions.released_at`을 채운 뒤 질문을 `OPEN`으로 되돌린다. 따라서 “질문당 Answer 1개”는 취소되지 않은 활성·완료 연결이 최대 하나라는 뜻이며, 취소 snapshot은 감사용으로 남는다.

### 14.7 class 종료와 후처리 완료

종료 요청은 Session 행을 `FOR UPDATE`로 잠근 뒤 다음을 한 트랜잭션에서 수행한다.

1. `LIVE` 상태이고 `CAPTURING` Answer가 없는지 확인한다.
2. `PROCESSING`, `ended_at`, 새 `version`으로 바꿔 추가 audio를 차단한다.
3. final clustering, FINAL Summary, 공통 KnowledgeChunk 등 필수 후처리 Job을 `blocks_session_completion = true`로 생성한다.
4. 공유 상태 event와 idempotency 응답을 기록한다.

각 blocking Job이 terminal 상태가 될 때 worker는 먼저 같은 Session 행을 잠근다. 미완료 blocking Job이 없으면 Session을 `COMPLETED`로 바꾸고 `completed_at`을 기록한다. 일부 Job이 최종 실패해도 Session은 완료될 수 있지만 실패 Job과 마지막 성공 결과를 그대로 노출해 재시도할 수 있게 한다. 동시에 끝나는 worker 경쟁을 보정하는 reconciliation 작업도 둔다. 완료 후 Job을 다시 시도해도 Session을 `PROCESSING`으로 되돌리지 않는다.

### 14.8 AIJob claim·재시도·결과 commit

- worker claim은 `status = 'PENDING' AND available_at <= now()`를 `FOR UPDATE SKIP LOCKED`로 선택한다.
- claim 시 `RUNNING`, `run_token`, `lease_expires_at`, `started_at`을 함께 기록한다.
- heartbeat는 현재 `run_token`이 일치할 때만 lease를 연장한다.
- 결과 테이블 삽입과 Job `SUCCEEDED` 전이는 같은 트랜잭션이다.
- 결과 commit 조건에는 `id`, `attempt`, `run_token`, `RUNNING` 상태를 모두 포함한다.
- 실패는 안전한 code/message만 저장하며 원문 PDF, 질문, prompt, provider 응답을 오류 칼럼이나 로그에 넣지 않는다.
- 재시도는 `FAILED` Job에만 허용하며 새 Job을 만들지 않고 같은 행에서 `attempt + 1` 후 `PENDING`으로 전환한다. 실패 attempt의 부분 결과는 commit하지 않으므로 retry가 기존 성공 결과를 덮어쓰지 않는다. 성공 결과 재생성 기능은 MVP retry와 분리된 명시적 후속 정책으로 다룬다.

### 14.9 Chat 메시지와 근거

사용자 Message 생성 시 `chat_sessions` 행을 잠가 다음 sequence를 발급하고 `CHAT_RESPONSE` Job을 함께 만든다. Assistant 결과 transaction은 Message, `chat_message_evidence`, Job 성공을 함께 commit한다. Evidence는 검색 시점 Chunk ID와 순위의 snapshot이며, 근거 source의 변경 여부와 무관하게 해당 답변이 사용한 Chunk를 가리킨다.

### 14.10 Outbox 발행

도메인 행과 outbox 행을 같은 transaction에 저장하고 commit 후 publisher가 발행한다. 발행 완료 전 장애가 나면 같은 event를 재발행할 수 있으므로 client와 내부 consumer는 event ID와 resource version으로 중복·역순을 처리한다.

## 15. 보안·보관·삭제 정책

### 15.1 민감정보

- 참여 코드, OAuth PKCE verifier, 멱등성 응답은 AES-256-GCM으로 암호화한다.
- 검색이 필요한 token·code는 원문 대신 목적별로 분리된 HMAC을 저장한다.
- 참여 코드, 인증 token, ticket, prompt 원문은 애플리케이션 로그와 outbox payload에 남기지 않는다. 질문 원문은 로그에 남기지 않고, 멤버용 실시간 event 계약에 필요한 경우에만 최소 payload로 24시간 이내 보관한다.
- Course 상세에서 참여 코드를 복호화하는 경로는 `PROFESSOR` 권한을 다시 확인하고 접근 audit을 남긴다.
- DB 계정은 API·worker·migration 역할을 분리하고 최소 권한을 부여한다.

### 15.2 권장 보관 기간

| 데이터                                   | MVP 권장값                                | 처리                               |
| ---------------------------------------- | ----------------------------------------- | ---------------------------------- |
| `oauth_transactions`                     | 생성 후 10분                              | 사용 완료·만료 후 정기 삭제        |
| `realtime_tickets`                       | 생성 후 60초                              | 사용 완료·만료 후 정기 삭제        |
| `auth_sessions`                          | 발급 후 7일                               | 만료·폐기 후 정기 삭제             |
| `idempotency_records`                    | 완료 후 24시간                            | 암호문 포함 정기 삭제              |
| 발행 완료 `outbox_events`                | 24시간                                    | replay window 후 정기 삭제         |
| PDF·Transcript·질문·Answer·FINAL Summary | Course 수명                               | Course 관리 삭제·정책 만료 시 삭제 |
| 개인 LIVE Summary·Chat                   | 계정 또는 Course 수명 중 먼저 도달한 시점 | 사용자 탈퇴·Course 삭제 시 삭제    |
| 실패 `ai_jobs`                           | Course 수명                               | 진단 가능한 안전한 metadata만 보관 |

보관 기간은 제품의 개인정보 정책 확정 전 운영 기본값이며, 외부 공개 전 법무·운영 검토로 확정한다.

### 15.3 삭제 순서와 `ON DELETE`

- Course 관리 삭제는 `course_members`, `lecture_sessions`와 Session 하위 데이터를 cascade한다.
- Session 삭제는 Material, Transcript, Gap, Cluster, Question, Answer, Summary, Chat, KnowledgeChunk와 Job을 함께 정리한다.
- Question 삭제는 Reaction을 cascade한다. 공유 질문 보존을 위해 User 탈퇴가 Question 삭제로 이어지지는 않는다.
- Chat 삭제는 Message와 Evidence를 cascade한다.
- 독립적인 `ai_jobs` 삭제는 결과 행의 deferred `NO ACTION` FK 때문에 commit되지 않는다. Session 전체 삭제에서는 Job과 결과가 같은 transaction에서 함께 제거된다.
- KnowledgeChunk 단독 삭제는 Evidence가 참조하면 deferred `NO ACTION` FK가 막는다. 재색인 시 기존 Chunk를 즉시 삭제하지 말고 새 Chunk·Evidence 처리 정책을 먼저 적용한다.
- PDF object는 DB cascade로 삭제되지 않는다. 삭제 transaction의 storage cleanup outbox를 통해 멱등 삭제한다.
- User 탈퇴는 우선 `users.deleted_at`을 기록하고 이름·이메일·avatar를 익명값으로 교체한다. 인증 identity/session과 개인 Chat·LIVE Summary·REQUESTER_ONLY Job은 같은 deferred transaction에서 제거하고, 공유 질문·Answer 작성자 FK는 익명화된 동일 User 행을 가리키게 유지한다.
- `courses.created_by_user_id`, `course_members.user_id`, `lecture_sessions.created_by_user_id`, `questions.author_user_id` 등 공유 `RESTRICT` 참조가 하나라도 있으면 User 행은 영구 tombstone으로 유지하고 hard delete하지 않는다. hard delete는 모든 공유·Reaction·개인 참조가 전혀 없는 계정만 허용한다.

MVP에는 Course·class·질문의 일반 사용자 hard delete API를 추가하지 않는다. 운영 삭제 기능을 만들 때는 위 cascade와 object storage 보상 작업을 하나의 관리 workflow로 구현한다.

## 16. 인덱스 운영 원칙

- B-tree 복합 인덱스의 선두 컬럼은 권한·범위 조건인 `course_id`, `session_id`, `owner_user_id`를 우선한다.
- partial UNIQUE는 애플리케이션 선조회로 대체하지 않는다. Course당 `LIVE` 하나, Session당 `CAPTURING` Answer 하나, 질문당 미해제 Answer 하나는 DB가 최종 보장한다.
- `questions.reaction_count`와 최신 cursor는 실시간 hot path를 위해 저장하되 원장과 reconciliation한다.
- HNSW는 embedding model과 차원이 확정된 뒤 생성한다. Session 범위 B-tree를 함께 두고 실제 데이터 분포로 `ef_search`, `m`, `ef_construction`을 조정한다.
- production index 추가·교체는 가능한 경우 `CREATE INDEX CONCURRENTLY`를 사용하고 migration transaction 제약을 별도로 처리한다.
- `EXPLAIN (ANALYZE, BUFFERS)`로 최근 질문, 인기 질문, final Transcript cursor, Job claim, Chat vector 검색을 우선 검증한다.

## 17. 모델·migration 생성 순서

이 문서 승인 후 SQLAlchemy 모델과 Alembic migration은 다음 순서로 나눈다.

1. `pgcrypto`, `vector` 확장과 공통 `updated_at` trigger
2. User, Course, CourseMember, LectureSession
3. 인증 Session·OAuth·RealtimeTicket, Material, Transcript, Gap, ChatSession
4. Question을 Cluster FK 없이 우선 생성
5. AIJob을 생성하되 Material의 `processed_by_job_id`, Transcript의 `created_by_job_id` 같은 순환 FK는 보류
6. QuestionCluster, Answer, AnswerQuestion과 보류한 복합·순환 FK 추가
7. KnowledgeChunk, LectureSummary, ChatMessage, ChatMessageEvidence
8. IdempotencyRecord, OutboxEvent
9. CHECK, partial UNIQUE, 조회 인덱스와 constraint trigger 추가
10. embedding 차원 확정 후 pgvector 타입과 HNSW 인덱스 추가

하나의 거대한 migration 대신 스키마 생성, 순환 FK, 비동기 인덱스를 분리한다. downgrade에서도 외부 object를 자동 복구할 수 없으므로 storage 변화는 별도 runbook으로 다룬다.

## 18. 미정 사항

문서와 사용자 결정만으로 확정할 수 없는 항목은 다음과 같다.

| 항목                                    | 현재 문서 표현                               | 확정 시점                           |
| --------------------------------------- | -------------------------------------------- | ----------------------------------- |
| 참여 코드 alphabet·길이                 | trim·uppercase·HMAC lookup까지만 확정        | 참여 코드 생성기 구현 전            |
| 참여 코드 회전·만료 UI                  | `join_code_expires_at` nullable, 기본 무기한 | Course 관리 기능 확장 전            |
| embedding model·차원                    | `vector(EMBEDDING_DIM)` placeholder          | 모델 선택 후 첫 vector migration 전 |
| vector index parameter                  | HNSW 사용 방향만 확정                        | staging 데이터 부하 시험 후         |
| 개인 LIVE Summary·Chat 정확한 보관 기간 | 계정/Course 수명 이내 권장                   | 개인정보 정책 확정 전               |
| idempotency·outbox replay 보관 기간     | 각각 24시간 권장                             | 운영 SLO 확정 전                    |

위 항목을 확정하기 전에는 placeholder를 실제 SQLAlchemy 타입이나 irreversible migration으로 굳히지 않는다.

### 18.1 API 문서 후속 동기화

이번 사용자 결정으로 기존 API 문서의 다음 TBD는 해소됐다. 이 작업에서는 DB 문서만 작성하므로 OpenAPI는 변경하지 않았으며, 다음 API 명세 변경 때 동기화한다.

- Course당 동시 `LIVE` class는 1개다.
- class당 PDF는 여러 개다.
- 질문당 취소되지 않은 활성·완료 Answer는 최대 1개다.
- AIJob retry는 같은 Job ID에서 `attempt`를 증가시킨다.
- Chat Evidence의 저장 식별자는 `knowledge_chunk_id`다. API에 source 표시가 필요하면 KnowledgeChunk의 typed FK에서 `source_kind`, label, 안전한 link를 파생한다.
- AIJob `result` link는 결과 테이블의 `created_by_job_id` 역조회로 조립한다.

## 19. 구현 전 검토 체크리스트

- [ ] API 상태값과 DB `CHECK` 값이 일치하는가?
- [ ] 참여 코드 암호화 키와 lookup HMAC key가 분리되어 있는가?
- [ ] Course당 `LIVE` 하나를 partial UNIQUE로 검증하는가?
- [ ] Session당 PDF 개수에 불필요한 UNIQUE가 없는가?
- [ ] 클러스터 이력 테이블 없이 Answer 시작 snapshot만 보관하는가?
- [ ] 취소되지 않은 질문–Answer 연결이 질문당 하나인가?
- [ ] 모든 AI 생성 root 결과 행에 `created_by_job_id`, `created_by_job_attempt`가 있는가? (입력 Material 상태는 `processed_by_*`, Evidence는 상위 Assistant Message를 통해 귀속)
- [ ] Job 재시도가 같은 행의 `attempt` 증가와 run token 검증을 사용하는가?
- [ ] Chat Evidence가 공통 KnowledgeChunk만 참조하는가?
- [ ] DB에 generic `source_type + source_id` FK가 없는가?
- [ ] vector 검색이 SQL 단계에서 Course·Session 범위를 제한하는가?
- [ ] partial Transcript와 음성 원본을 영구 저장하지 않는가?
- [ ] 삭제 transaction이 object storage 정리 outbox를 남기는가?
