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

- Course 생성자는 해당 Course의 유일한 `PROFESSOR`이자 owner다. 교수자 추가와 owner 이전은 제공하지 않는다.
- 한 Course에는 `READY`, `LIVE`, `PROCESSING` 상태인 class가 합계 최대 한 개다.
- 같은 날짜의 class는 순차적으로 여러 개 만들 수 있고 완료 기록은 실제 `started_at` 내림차순으로 구분한다.
- class 제목은 모든 상태에서 수정할 수 있고 날짜와 상태 전이 시각은 사용자 수정 대상이 아니다.
- `READY`, `COMPLETED` class는 aggregate 단위 hard delete를 허용한다.
- Course 참여 코드는 복호화 가능한 암호문으로 저장한다.
- 참여 코드 입력 조회를 위해 정규화한 코드의 HMAC을 암호문과 별도로 저장한다.
- 참여 코드는 앞뒤 공백 제거와 대문자 정규화 후 `[A-Z]{6}`이며 만료 없이 owner만 회전한다. 회전 이력은 보관하지 않는다.
- 멱등성 완료·실패 응답은 terminal 전이 시각부터 정확히 24시간 재사용한다.
- 한 class에는 연결 상태인 PDF를 최대 10개까지 둘 수 있고, PDF가 0개여도 class를 시작할 수 있다.
- 연결된 Material 중 `PROCESSING`이 하나라도 있으면 class 시작을 거부한다. `READY`, `UPLOADED`, `FAILED`와 PDF 0개는 시작을 막지 않는다.
- PDF 한 파일의 최대 크기는 decimal `100000000` bytes다. 같은 내용과 같은 원본 파일명 재업로드는 허용한다.
- 질문 클러스터 변경 이력은 보관하지 않는다.
- 교수자가 클러스터를 선택해 답변을 시작하면 당시 질문 목록을 Answer에 snapshot한다.
- 수업 종료 후 현재 질문 배치를 최종 클러스터로 확정해 보관한다.
- 한 질문은 취소되지 않은 `CAPTURING` 또는 `COMPLETED` Answer에 최대 한 번만 연결된다. `CANCELLED` 시도는 Answer 개수에서 제외하고 snapshot만 보관한다.
- AIJob 재시도는 같은 행의 `attempt`를 증가시킨다.
- PDF·Transcript·Question·Answer 검색 단위는 공통 `knowledge_chunks` 테이블로 통합한다.
- Chat 근거는 `chat_message_evidence`가 `knowledge_chunks`를 참조한다.
- AIJob 결과는 각 결과 행의 `created_by_job_id`로 역참조한다.
- `source_type + source_id` 형태의 직접적인 다형 FK는 사용하지 않는다.
- partial Transcript는 영구 저장하지 않지만, 첫 `audio.start`가 만든 논리
  Recording과 종료 후 resumable upload로 확정한 강의 음성은 MVP 영구
  원장에 남긴다.
- 한 Session에는 논리 `session_recordings` 행을 최대 하나만 두고, 첫
  publisher의 `client_stream_id` HMAC claim과 Recording `CAPTURING` 전이를 같은
  transaction에서 확정한다.
- 다른 `client_stream_id`는 거부하고 같은 ID의 재연결·resume만 허용한다.
  lease 만료·재획득·takeover는 미정이다.
- Recording upload 완결 전에는 HQ STT 후속 처리를 시작하지 않는다.
  구체 AIJob type·target·result, HQ Transcript version·canonical 교체·Segment 녹음
  offset·Answer 재매핑은 PR4 계약에서 확정한다.
- Recording과 Upload의 내부 storage key, 물리 경로, fragment key와 manifest는
  API 응답·공유 event·애플리케이션 로그에 노출하지 않는다.

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
- 실시간으로 갱신되는 `lecture_sessions`, `session_recordings`, `questions`,
  `answers`, `ai_jobs`는 `version`을 가진다.
- `updated_at`은 애플리케이션 또는 공통 DB trigger 중 한 방식으로 일관되게 갱신한다. MVP 권장안은 공통 trigger다.
- Course와 `READY`·`COMPLETED` class를 제외한 사용자 콘텐츠의 일반 hard delete API는 MVP에 포함하지 않는다. 사용자 탈퇴는 `users.deleted_at`과 식별정보 익명화를 우선 사용한다.

## 3. 상태와 코드 값

| 구분                                  | 허용 값                                                          |
| ------------------------------------- | ---------------------------------------------------------------- |
| `course_members.role`                 | `PROFESSOR`, `STUDENT`                                           |
| `lecture_sessions.status`             | `READY`, `LIVE`, `PROCESSING`, `COMPLETED`                       |
| `lecture_materials.processing_status` | `UPLOADED`, `PROCESSING`, `READY`, `FAILED`                      |
| `session_recordings.status`           | `CAPTURING`, `UPLOAD_PENDING`, `UPLOADING`, `UPLOADED`, `FAILED` |
| `recording_uploads.status`            | `ACTIVE`, `COMPLETED`, `EXPIRED`, `FAILED`                       |
| `questions.status`                    | `OPEN`, `SELECTED`, `ANSWERED`                                   |
| `answers.status`                      | `CAPTURING`, `COMPLETED`, `CANCELLED`                            |
| `lecture_summaries.summary_type`      | `LIVE`, `FINAL`                                                  |
| `lecture_summaries.visibility`        | `REQUESTER_ONLY`, `COURSE_MEMBERS`                               |
| `chat_sessions.mode`                  | `LIVE`, `REVIEW`                                                 |
| `chat_messages.role`                  | `USER`, `ASSISTANT`                                              |
| `ai_jobs.status`                      | `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`                      |
| `ai_jobs.visibility`                  | `SHARED`, `REQUESTER_ONLY`                                       |
| `realtime_tickets.scope`              | `SESSION_EVENTS_READ`, `SESSION_AUDIO_WRITE`                     |
| `user_auth_identities.provider`       | `GOOGLE`                                                         |

AIJob 유형은 다음 값을 사용한다.

- `MATERIAL_PROCESSING`
- `QUESTION_CLUSTERING`
- `LIVE_SUMMARY`
- `FINAL_SUMMARY`
- `CHAT_RESPONSE`
- `SESSION_POSTPROCESSING`

## 4. 테이블 구성 요약

| 영역          | 테이블                                                                                                                       |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 사용자·인증   | `users`, `user_auth_identities`, `auth_sessions`, `oauth_transactions`, `realtime_tickets`                                   |
| Course·class  | `courses`, `course_members`, `lecture_sessions`                                                                              |
| 자료·기록     | `lecture_materials`, `session_recordings`, `recording_uploads`, `transcript_segments`, `transcript_gaps`, `knowledge_chunks` |
| 질문·답변     | `question_clusters`, `questions`, `question_reactions`, `answers`, `answer_questions`                                        |
| AI 요약·채팅  | `lecture_summaries`, `chat_sessions`, `chat_messages`, `chat_message_evidence`                                               |
| 비동기·일관성 | `ai_jobs`, `idempotency_records`, `outbox_events`                                                                            |

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

한 학기 단위 수업방, 불변 owner와 교수자에게 다시 표시할 현재 참여 코드를 저장한다. Course 종료·보관 상태는 두지 않는다.

| 컬럼                           | 타입          | NULL | 기본값              | 키·제약         | 설명                          |
| ------------------------------ | ------------- | ---: | ------------------- | --------------- | ----------------------------- |
| `id`                           | `uuid`        |    N | `gen_random_uuid()` | PK              | Course ID                     |
| `title`                        | `text`        |    N | -                   | CHECK           | 과목명                        |
| `semester`                     | `text`        |    N | -                   | CHECK           | 표시용 학기                   |
| `created_by_user_id`           | `uuid`        |    N | -                   | FK → `users.id` | 불변 교수자 owner             |
| `join_code_lookup_hash`        | `bytea`       |    N | -                   | UNIQUE          | 정규화 코드의 HMAC-SHA-256    |
| `join_code_lookup_key_version` | `smallint`    |    N | -                   | CHECK `> 0`     | HMAC key 버전                 |
| `join_code_ciphertext`         | `bytea`       |    N | -                   | -               | AES-256-GCM 암호문과 auth tag |
| `join_code_nonce`              | `bytea`       |    N | -                   | -               | 암호화 nonce                  |
| `join_code_key_version`        | `smallint`    |    N | -                   | CHECK `> 0`     | 암호화 키 버전                |
| `version`                      | `bigint`      |    N | `1`                 | CHECK `> 0`     | 리소스 버전                   |
| `created_at`                   | `timestamptz` |    N | `now()`             | -               | 생성 시각                     |
| `updated_at`                   | `timestamptz` |    N | `now()`             | -               | 갱신 시각                     |

암호화·조회 규칙:

1. 입력 코드는 trim 후 대문자로 정규화하고 `[A-Z]{6}`인지 검사한다. 구분자와 소문자는 정규화 결과 밖에 남기지 않는다.
2. 정규화 값을 현재 단일 lookup HMAC key로 HMAC-SHA-256 계산해 `join_code_lookup_hash`로 조회한다.
3. 교수자 표시가 필요할 때만 ciphertext를 복호화한다.
4. AES-GCM associated data에는 `course_id`를 넣어 다른 Course 행으로 암호문을 옮겨도 복호화되지 않게 한다.
5. 암호화 키와 HMAC key는 서로 분리하고 DB 밖에서 관리한다.
6. lookup HMAC key 회전은 참여 코드 발급을 잠시 중단하고 전역 advisory lock을 잡은 뒤, 모든 Course의 lookup hash와 key version을 한 transaction에서 새 key로 재계산한 후에만 발급을 재개한다. 서로 다른 lookup key version을 장기간 섞어 두지 않는다.
7. 암호화 key는 lookup key와 독립적으로 행 단위 점진 회전할 수 있다.
8. 참여 코드는 자동 만료하지 않는다. owner의 제품 기능상 코드 회전은 Course row를 잠근 뒤 새 hash·ciphertext·nonce로 현재 값을 원자 교체하고 `version`을 증가시킨다.
9. 코드 회전이 commit되면 이전 코드는 즉시 무효이며 이전 hash·ciphertext와 회전 이력은 보관하지 않는다. 제품 코드 회전과 6·7항의 비밀키 회전은 서로 다른 작업이다.

제약·인덱스:

- `CHECK (length(btrim(title)) > 0)`
- `CHECK (length(btrim(semester)) > 0)`
- `CHECK (octet_length(join_code_lookup_hash) = 32)`
- `CHECK (octet_length(join_code_nonce) = 12)`
- `created_by_user_id ON DELETE RESTRICT`
- `created_by_user_id`는 Course 생성 후 변경하지 않는다.
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
- `UNIQUE INDEX course_members_one_professor_per_course_uq (course_id) WHERE role = 'PROFESSOR'`; Course당 교수자를 최대 한 명으로 제한한다.
- `INDEX course_members_user_role_idx (user_id, role, course_id)`
- `course_id ON DELETE CASCADE`
- `user_id ON DELETE RESTRICT`; 탈퇴는 User 익명화를 우선한다.
- Course 생성 트랜잭션은 생성자를 유일한 `PROFESSOR`로 함께 삽입한다.
- deferrable constraint trigger는 transaction 종료 시 삭제되지 않은 모든 Course에 `PROFESSOR` membership이 정확히 하나이고 그 `user_id`가 `courses.created_by_user_id`와 같은지 검증한다. Course aggregate 삭제에서는 부모 행이 없으면 검사를 건너뛴다.
- owner membership 삭제·역할 변경과 다른 교수자 추가는 금지하며 owner 이전은 제공하지 않는다.
- 코드 참여는 항상 `STUDENT` membership만 만들고 기존 owner를 `STUDENT`로 덮어쓰지 않는다.

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
- `UNIQUE INDEX lecture_sessions_one_active_per_course_uq (course_id) WHERE status IN ('READY', 'LIVE', 'PROCESSING')`
- `INDEX lecture_sessions_course_history_idx (course_id, lecture_date DESC, started_at DESC, id DESC)`
- `INDEX lecture_sessions_course_status_idx (course_id, status, updated_at DESC)`
- `CHECK (length(btrim(title)) > 0)`
- `CHECK ((status = 'READY' AND started_at IS NULL AND ended_at IS NULL AND completed_at IS NULL) OR (status = 'LIVE' AND started_at IS NOT NULL AND ended_at IS NULL AND completed_at IS NULL) OR (status = 'PROCESSING' AND started_at IS NOT NULL AND ended_at IS NOT NULL AND completed_at IS NULL) OR (status = 'COMPLETED' AND started_at IS NOT NULL AND ended_at IS NOT NULL AND completed_at IS NOT NULL))`
- `CHECK (ended_at IS NULL OR ended_at >= started_at)`
- `CHECK (completed_at IS NULL OR completed_at >= ended_at)`
- `course_id ON DELETE CASCADE`
- `created_by_user_id ON DELETE RESTRICT`; 탈퇴 시 User 행 자체를 익명화한다.

같은 날짜의 class는 순차적으로 여러 개 허용한다. 완료 기록은 `lecture_date DESC, started_at DESC, id DESC`로 정렬하고 실제 `started_at`을 표시해 구분한다. `READY`, `LIVE`, `PROCESSING` 합계는 partial UNIQUE 인덱스가 Course당 최대 한 행으로 제한한다. class 생성 경쟁에서 난 충돌은 `409 ACTIVE_SESSION_EXISTS`, 허용되지 않은 상태 전이는 `409 SESSION_STATE_CONFLICT`로 변환한다. 제목은 모든 상태에서 바꿀 수 있고 빈 입력은 Course 제목·class 날짜·시각을 포함한 자동 제목으로 치환한 뒤 저장한다. 정확한 문자열 형식, `READY`에서 사용할 시각 원장과 timezone은 미정이다. `lecture_date`는 생성 후 변경하지 않으며, `started_at`, `ended_at`, `completed_at`은 각 상태 전이에서 최초 설정된 뒤 바꾸지 않는다. 이 불변성은 상태 전이용 DB trigger가 기존 non-NULL 시각의 덮어쓰기를 거부해 이중 보장한다.

## 7. 자료·Transcript

### 7.1 `lecture_materials`

class에 업로드한 PDF 원본 메타데이터, 사용자에게 노출할 안정적인 이름, 전처리 상태와 연결 해제 tombstone을 저장한다. `detached_at IS NULL`인 행만 현재 class에 연결된 Material이다.

| 컬럼                       | 타입          | NULL | 기본값              | 키·제약                    | 설명                      |
| -------------------------- | ------------- | ---: | ------------------- | -------------------------- | ------------------------- |
| `id`                       | `uuid`        |    N | `gen_random_uuid()` | PK                         | Material ID               |
| `session_id`               | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                |
| `uploaded_by_user_id`      | `uuid`        |    Y | `NULL`              | FK → `users.id`            | 업로드 교수자             |
| `original_filename`        | `text`        |    N | -                   | CHECK                      | 업로드 시 정규화한 원본명 |
| `display_name`             | `text`        |    N | -                   | CHECK, partial UNIQUE      | 안정적인 표시 이름        |
| `mime_type`                | `text`        |    N | `'application/pdf'` | CHECK                      | PDF MIME                  |
| `byte_size`                | `bigint`      |    N | -                   | CHECK                      | 파일 크기                 |
| `storage_key`              | `text`        |    N | -                   | UNIQUE                     | 내부 서버 생성 키         |
| `page_count`               | `integer`     |    Y | `NULL`              | CHECK `> 0`                | 전처리 후 페이지 수       |
| `processing_status`        | `text`        |    N | `'UPLOADED'`        | CHECK                      | 전처리 상태               |
| `processed_by_job_id`      | `uuid`        |    Y | `NULL`              | 복합 FK                    | 성공한 Material 처리 Job  |
| `processed_by_job_attempt` | `integer`     |    Y | `NULL`              | CHECK `> 0`                | 처리 당시 Job attempt     |
| `detached_at`              | `timestamptz` |    Y | `NULL`              | -                          | 연결 해제 시각            |
| `version`                  | `bigint`      |    N | `1`                 | CHECK `> 0`                | 상태 버전                 |
| `created_at`               | `timestamptz` |    N | `now()`             | -                          | 업로드 시각               |
| `updated_at`               | `timestamptz` |    N | `now()`             | -                          | 갱신 시각                 |

제약·인덱스:

- `UNIQUE (id, session_id)`; KnowledgeChunk의 동일 Session FK에 사용한다.
- `UNIQUE INDEX lecture_materials_active_display_name_uq (session_id, display_name) WHERE detached_at IS NULL`; 연결된 Material의 표시 이름만 Session 안에서 유일하다.
- `UNIQUE INDEX lecture_materials_processed_by_job_uq (processed_by_job_id) WHERE processed_by_job_id IS NOT NULL`; Material 처리 Job 하나는 Material 하나만 확정한다.
- `CHECK (mime_type = 'application/pdf')`
- `CHECK (length(btrim(original_filename)) > 0)`
- `CHECK (length(btrim(display_name)) > 0)`
- `CHECK (byte_size BETWEEN 1 AND 100000000)`
- `CHECK ((processed_by_job_id IS NULL) = (processed_by_job_attempt IS NULL))`
- `CHECK (processing_status <> 'READY' OR processed_by_job_id IS NOT NULL)`
- `CHECK (processing_status <> 'READY' OR page_count IS NOT NULL)`
- `INDEX lecture_materials_session_idx (session_id, created_at, id) WHERE detached_at IS NULL`
- `INDEX lecture_materials_processing_idx (processing_status, updated_at) WHERE detached_at IS NULL AND processing_status IN ('UPLOADED', 'PROCESSING', 'FAILED')`
- `session_id ON DELETE CASCADE`
- `uploaded_by_user_id ON DELETE SET NULL`
- `(processed_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

연결된 Material 수는 Session당 최대 10개다. 서비스는 Material 삽입 전에 Session 행을 잠그고 `detached_at IS NULL` 행을 세며, `lecture_materials_active_count_guard` trigger도 `INSERT` 또는 `session_id`·`detached_at` 변경 전에 같은 Session 행을 잠근 뒤 변경 후 개수가 10 이하인지 검증한다. 따라서 동시 업로드가 선조회를 모두 통과해도 DB가 최종 차단한다. 이 위반은 `409 MATERIAL_LIMIT_EXCEEDED`로 변환한다.

`original_filename`은 업로드 당시 정규화한 basename이고 `display_name`은 생성 뒤 바꾸거나 재번호를 매기지 않는 공개 이름이다. 연결된 이름이 충돌하면 확장자 앞에 ` (1)`, ` (2)` 순의 사용 가능한 suffix를 붙이고, Session 잠금 아래에서 할당한 뒤 partial UNIQUE로 최종 검증한다. tombstone 행은 현재 이름 충돌과 10개 계산에서 제외하지만 그 행의 `display_name` 값 자체는 유지한다. content hash UNIQUE는 두지 않아 같은 내용과 같은 `original_filename`의 업로드를 허용한다.

`storage_key`는 서버가 생성하는 내부 식별자다. API 응답, 공유 event와 애플리케이션 로그에 노출하지 않으며 object 삭제용 내부 outbox payload에서만 사용한다. 원본 object와 파생 Knowledge 삭제는 DB tombstone commit 뒤 별도의 멱등 정리 작업으로 실행한다.

### 7.2 `session_recordings`

첫 `audio.start`가 성공했을 때 만드는 Session당 하나의 논리 녹음 aggregate다.
publisher claim, resumable upload의 최종 결과, HQ STT input과 playback metadata의
최종 진실을 저장한다. `storage_key`는 논리 storage locator이며 물리 파일
하나를 의미하지 않는다. Session당 단일 파일인지 fragment·manifest 집합인지는
미정이며 해당 물리 매핑은 이 스키마에 굳히지 않는다.

| 컬럼                              | 타입          | NULL | 기본값              | 키·제약      | 설명                                |
| --------------------------------- | ------------- | ---: | ------------------- | ------------ | ----------------------------------- |
| `id`                              | `uuid`        |    N | `gen_random_uuid()` | PK           | Recording ID                        |
| `session_id`                      | `uuid`        |    N | -                   | FK, UNIQUE   | 소속 class                          |
| `publisher_user_id`               | `uuid`        |    Y | `NULL`              | FK           | 첫 publisher 교수자, 탈퇴 시 익명화 |
| `publisher_client_stream_id_hash` | `bytea`       |    N | -                   | CHECK        | `client_stream_id` 목적별 HMAC      |
| `status`                          | `text`        |    N | `'CAPTURING'`       | CHECK        | 공개 Recording 상태                 |
| `content_type`                    | `text`        |    Y | `NULL`              | CHECK        | finalize 후 검증한 media type       |
| `byte_size`                       | `bigint`      |    Y | `NULL`              | CHECK `> 0`  | finalize 후 전체 byte               |
| `duration_ms`                     | `bigint`      |    Y | `NULL`              | CHECK `>= 0` | finalize 후 녹음 길이               |
| `storage_key`                     | `text`        |    Y | `NULL`              | UNIQUE       | 내부 논리 storage locator           |
| `capture_started_at`              | `timestamptz` |    N | `now()`             | -            | 첫 claim·capture 시작               |
| `capture_ended_at`                | `timestamptz` |    Y | `NULL`              | -            | Session 종료로 local capture 마감   |
| `uploaded_at`                     | `timestamptz` |    Y | `NULL`              | -            | upload finalize 시각                |
| `failed_at`                       | `timestamptz` |    Y | `NULL`              | -            | terminal 실패 시각                  |
| `version`                         | `bigint`      |    N | `1`                 | CHECK `> 0`  | `recording.updated` 리소스 버전     |
| `created_at`                      | `timestamptz` |    N | `now()`             | -            | 생성 시각                           |
| `updated_at`                      | `timestamptz` |    N | `now()`             | -            | 갱신 시각                           |

제약·인덱스:

- `UNIQUE (session_id)`; Session당 논리 Recording aggregate는 최대 하나다.
- `UNIQUE (id, session_id)`; PR4가 HQ STT typed FK를 선택할 경우에만 같은
  Session 복합 FK의 대상으로 사용하며 이번 변경에 target 컬럼은 추가하지 않는다.
- `CHECK (octet_length(publisher_client_stream_id_hash) = 32)`
- `CHECK (status IN ('CAPTURING', 'UPLOAD_PENDING', 'UPLOADING', 'UPLOADED', 'FAILED'))`
- `CHECK (byte_size IS NULL OR byte_size > 0)`
- `CHECK (duration_ms IS NULL OR duration_ms >= 0)`
- `CHECK (content_type IS NULL OR length(btrim(content_type)) > 0)`
- `CHECK (num_nonnulls(content_type, byte_size, duration_ms, storage_key, uploaded_at) IN (0, 5))`
- `CHECK ((status = 'UPLOADED') = (storage_key IS NOT NULL))`
- `CHECK ((status = 'FAILED') = (failed_at IS NOT NULL))`
- `CHECK (status NOT IN ('UPLOAD_PENDING', 'UPLOADING', 'UPLOADED') OR capture_ended_at IS NOT NULL)`
- `CHECK (capture_ended_at IS NULL OR capture_ended_at >= capture_started_at)`
- `CHECK (uploaded_at IS NULL OR uploaded_at >= capture_ended_at)`
- `INDEX session_recordings_status_idx (status, updated_at, id)`
- `INDEX session_recordings_publisher_idx (publisher_user_id, created_at DESC) WHERE publisher_user_id IS NOT NULL`
- `session_id ON DELETE CASCADE`
- `publisher_user_id ON DELETE SET NULL`

`publisher_client_stream_id_hash`는 원문을 저장하지 않고 목적별 HMAC key로
계산한다. 첫 `audio.start`는 Session을 잠그고 `LIVE`·Course `PROFESSOR`를 확인한
뒤 Recording insert와 `CAPTURING` 전이를 하나의 transaction으로 commit한다.
`session_id` UNIQUE 충돌 시 기존 행을 잠그고 같은 User와 같은 HMAC이면 재연결로
취급하며, 다르면 `AUDIO_PUBLISHER_CONFLICT`로 변환한다. WebSocket 소켓, PCM
ring buffer, ack sequence는 low-latency 실행 상태이며 이 테이블에 매 chunk마다
쓰지 않는다. lease 만료·서버 재시작 후 재획득·다른 탭 takeover는 미정이다.

정상 전이는 `CAPTURING → UPLOAD_PENDING → UPLOADING → UPLOADED`이며
`UPLOADED`가 영구 저장·playback 가능 상태다. upload finalize commit 후에만
HQ STT 후속 처리를 시작할 수 있다. `FAILED`는 capture·upload 실패를 하나의
공개 상태로 표현하지만, 실패 단계별 재시도, Session 완료 허용과
`DEGRADED`·stop·replay 정책은 미정이다. HQ STT의 상태와 결과는 이
Recording storage lifecycle에 혼합하지 않고 PR4에서 별도로 설계한다.

### 7.3 `recording_uploads`

브라우저 로컬 녹음을 Session 종료 후 재개 가능하게 전송하는 논리 upload
resource와 서버가 확인한 byte offset을 영구 저장한다. exact HTTP method·header,
chunk 크기, checksum algorithm과 expiry 기간은 미정이지만, process 재시작 후에도
동일 upload ID와 offset을 복구할 수 있어야 한다.

| 컬럼                    | 타입          | NULL | 기본값              | 키·제약      | 설명                                |
| ----------------------- | ------------- | ---: | ------------------- | ------------ | ----------------------------------- |
| `id`                    | `uuid`        |    N | `gen_random_uuid()` | PK           | 불투명 upload ID                    |
| `recording_id`          | `uuid`        |    N | -                   | FK           | 대상 Recording                      |
| `initiated_by_user_id`  | `uuid`        |    Y | `NULL`              | FK           | upload를 시작한 교수자              |
| `status`                | `text`        |    N | `'ACTIVE'`          | CHECK        | upload 상태                         |
| `offset_bytes`          | `bigint`      |    N | `0`                 | CHECK        | 서버가 commit한 연속 byte offset    |
| `total_bytes`           | `bigint`      |    N | -                   | CHECK `> 0`  | client가 선언한 전체 크기           |
| `declared_content_type` | `text`        |    N | -                   | CHECK        | client 선언 media type              |
| `declared_duration_ms`  | `bigint`      |    N | -                   | CHECK `>= 0` | client 선언 녹음 길이               |
| `temporary_storage_key` | `text`        |    N | -                   | UNIQUE       | 내부 temp namespace·provider handle |
| `expires_at`            | `timestamptz` |    N | -                   | CHECK        | upload 만료 시각                    |
| `terminal_at`           | `timestamptz` |    Y | `NULL`              | CHECK        | 완료·만료·실패 확정 시각            |
| `version`               | `bigint`      |    N | `1`                 | CHECK `> 0`  | 동시 update·finalize fence          |
| `created_at`            | `timestamptz` |    N | `now()`             | -            | 생성 시각                           |
| `updated_at`            | `timestamptz` |    N | `now()`             | -            | 갱신 시각                           |

제약·인덱스:

- `CHECK (status IN ('ACTIVE', 'COMPLETED', 'EXPIRED', 'FAILED'))`
- `CHECK (offset_bytes BETWEEN 0 AND total_bytes)`
- `CHECK (length(btrim(declared_content_type)) > 0)`
- `CHECK (declared_duration_ms >= 0)`
- `CHECK (expires_at > created_at)`
- `CHECK ((status = 'ACTIVE') = (terminal_at IS NULL))`
- `CHECK (status <> 'COMPLETED' OR offset_bytes = total_bytes)`
- `UNIQUE INDEX recording_uploads_one_active_uq (recording_id) WHERE status = 'ACTIVE'`
- `INDEX recording_uploads_expiry_idx (expires_at, id) WHERE status = 'ACTIVE'`
- `INDEX recording_uploads_recording_idx (recording_id, created_at DESC, id DESC)`
- `recording_id ON DELETE CASCADE`
- `initiated_by_user_id ON DELETE SET NULL`

`temporary_storage_key`는 하나의 물리 파일을 의미하지 않는 서버 생성 논리
handle이다. 임시 파일 하나, 여러 part, provider multipart upload와 fragment
manifest 중 어느 형태로 매핑할지는 protocol·storage backend 결정 뒤
확정한다. 따라서 이번 변경에 checksum 컬럼, part·fragment child table이나
Session당 물리 object 개수 제약을 추가하지 않는다.

chunk 처리는 `status = 'ACTIVE' AND offset_bytes = :expected_offset` 조건으로
연속 append만 허용하고 저장 backend에 남은 byte와 DB offset을 재조정할 수
있어야 한다. finalize는 `Session → Recording → Upload` 순서로
잠그고 `PROCESSING`, `UPLOAD_PENDING|UPLOADING`, `ACTIVE`, `offset_bytes = total_bytes`를
검증한다. 검증된 final storage locator와 metadata, Upload `COMPLETED`, Recording
`UPLOADED`, 안전한 `recording.updated`·HQ STT 후속 wakeup outbox를 하나의 DB
transaction에 commit한다. 이 outbox는 PR4에서 확정할 구체 Job type이나
Transcript 결과 계약을 이번 스키마에 미리 추가하지 않는 내부 gate다. object
publish 후 DB commit이 실패하면 내부 cleanup outbox 또는 동기 보상으로 orphan을
제거한다. 정확한 checksum·expiry·quota·orphan reconciliation 규칙은 미정이다.

### 7.4 `transcript_segments`

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

### 7.5 `transcript_gaps`

재연결 실패나 audio resume 거부로 live PCM 경로가 받지 못한 구간을
표시한다. 브라우저 로컬 녹음과 HQ STT가 이 gap을 canonical Transcript에서
어떻게 보정하고 실시간 gap metadata를 유지·표시할지는 PR4 계약으로 남긴다.

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
| `title`                  | `text`        |    N | -                   | CHECK                      | AI 대표 질문의 정확한 text       |
| `summary`                | `text`        |    Y | `NULL`              | -                          | 대표 설명                        |
| `generation`             | `bigint`      |    N | -                   | CHECK `> 0`                | 같은 클러스터링 결과 세트 식별자 |
| `ordinal`                | `integer`     |    N | -                   | CHECK `>= 0`               | 같은 generation 안의 안정적 순서 |
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
- `UNIQUE (session_id, generation, ordinal)`
- `UNIQUE (created_by_job_id, created_by_job_attempt, ordinal)`
- deferrable constraint trigger는 한 `(created_by_job_id, created_by_job_attempt)` 결과의 모든 행이 같은 `session_id`, `generation`, `is_final`을 사용하고, 한 `(session_id, generation)`이 하나의 Job attempt에만 귀속되는지 검증한다.
- `INDEX question_clusters_session_idx (session_id, is_final DESC, generation DESC, ordinal, id)`
- `INDEX question_clusters_job_idx (created_by_job_id)`
- `session_id ON DELETE CASCADE`
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`; 결과가 남아 있는 Job만 독립 삭제할 수 없고 Session 전체 삭제 transaction은 허용한다.

`generation`은 같은 Session 안에서 새 결과 세트마다 증가하고 재사용하지 않는 공개 식별자다. 정확한 원자 할당 방식과 최신 generation watermark·late-result fence는 전체 재클러스터링 계약을 다루는 후속 변경에서 확정한다. 재클러스터링은 새 Cluster 행을 만든 뒤 `questions.cluster_id`를 새 현재 값으로 갱신한다. 교체된 Cluster는 Answer가 선택했던 행이어도 삭제한다. 선택 당시 Cluster ID·AI 대표 질문의 정확한 text와 질문 membership은 Answer snapshot에 남는다. 수업 종료 후 새 final Cluster만 `is_final = true`로 표시하고 그 시점의 `questions.cluster_id`를 최종 배치로 보존한다. 이후 final 결과를 다시 확정하면 대체된 final Cluster도 삭제해 일반 변경 이력을 만들지 않는다.

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

| 컬럼                             | 타입          | NULL | 기본값              | 키·제약                    | 설명                              |
| -------------------------------- | ------------- | ---: | ------------------- | -------------------------- | --------------------------------- |
| `id`                             | `uuid`        |    N | `gen_random_uuid()` | PK                         | Answer ID                         |
| `session_id`                     | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                        |
| `professor_user_id`              | `uuid`        |    Y | `NULL`              | FK → `users.id`            | 답변 교수자                       |
| `status`                         | `text`        |    N | `'CAPTURING'`       | CHECK                      | 상태                              |
| `source_cluster_id_snapshot`     | `uuid`        |    Y | `NULL`              | 의도적으로 FK 없음         | 선택 당시 Cluster ID snapshot     |
| `source_cluster_title_snapshot`  | `text`        |    Y | `NULL`              | -                          | 선택 당시 AI 대표 질문 exact text |
| `capture_started_after_sequence` | `bigint`      |    N | -                   | CHECK `>= 0`               | 선택 시점 마지막 final sequence   |
| `start_segment_id`               | `uuid`        |    Y | `NULL`              | 복합 FK                    | 확정 범위 첫 Segment              |
| `end_segment_id`                 | `uuid`        |    Y | `NULL`              | 복합 FK                    | 확정 범위 마지막 Segment          |
| `version`                        | `bigint`      |    N | `1`                 | CHECK `> 0`                | 실시간 리소스 버전                |
| `started_at`                     | `timestamptz` |    N | `now()`             | -                          | 캡처 시작 시각                    |
| `completed_at`                   | `timestamptz` |    Y | `NULL`              | -                          | 완료 시각                         |
| `cancelled_at`                   | `timestamptz` |    Y | `NULL`              | -                          | 취소 시각                         |
| `created_at`                     | `timestamptz` |    N | `now()`             | -                          | 생성 시각                         |
| `updated_at`                     | `timestamptz` |    N | `now()`             | -                          | 갱신 시각                         |

제약·인덱스:

- `UNIQUE (id, session_id)`
- `UNIQUE INDEX answers_one_capturing_per_session_uq (session_id) WHERE status = 'CAPTURING'`
- `(start_segment_id, session_id) FK → transcript_segments(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(end_segment_id, session_id) FK → transcript_segments(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `CHECK ((start_segment_id IS NULL) = (end_segment_id IS NULL))`
- `CHECK ((source_cluster_id_snapshot IS NULL) = (source_cluster_title_snapshot IS NULL))`
- `CHECK (source_cluster_title_snapshot IS NULL OR length(btrim(source_cluster_title_snapshot)) > 0)`
- `CHECK ((status = 'CAPTURING' AND completed_at IS NULL AND cancelled_at IS NULL AND start_segment_id IS NULL) OR (status = 'COMPLETED' AND completed_at IS NOT NULL AND cancelled_at IS NULL AND start_segment_id IS NOT NULL) OR (status = 'CANCELLED' AND cancelled_at IS NOT NULL AND completed_at IS NULL AND start_segment_id IS NULL))`
- `CHECK (completed_at IS NULL OR completed_at >= started_at)`
- `CHECK (cancelled_at IS NULL OR cancelled_at >= started_at)`
- `INDEX answers_session_started_idx (session_id, started_at, id)`
- `session_id ON DELETE CASCADE`
- `professor_user_id ON DELETE SET NULL`

API의 `start_sequence`, `end_sequence`는 두 Segment를 join해 계산한다. 범위 순서와 같은 Session 여부는 완료 트랜잭션에서 검증한다.

`source_cluster_id_snapshot`은 더 이상 존재하지 않을 수 있는 과거 Cluster의 식별값이므로 FK를 걸지 않는다. 현재 계약에서 `question_clusters.title`은 AI가 만든 대표 질문 문장의 정확한 text다. Answer 시작 transaction은 Cluster가 같은 Session의 현재 행인지 검증한 뒤 ID와 그 `title`을 `source_cluster_title_snapshot`에 그대로 기록하고 이후 수정하지 않는다. 대표 질문을 안정적인 독립 리소스로 관리하거나 별도 provenance를 보존하는 전체 설계는 후속 계약으로 분리한다. 실제 원본 질문 대상의 원장은 `answer_questions`다.

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
retryable = false
```

worker는 실행 시작 시 새 `run_token`과 lease를 기록한다. 결과 저장과 성공 전이는 `WHERE id = :id AND status = 'RUNNING' AND attempt = :attempt AND run_token = :run_token` 조건으로 수행해 이전 attempt의 늦은 응답이 최신 결과를 덮어쓰지 못하게 한다.
성공·실패 terminal 전이에서는 `run_token`, `lease_expires_at`을 `NULL`로 정리한다.

### 9.2 Job 결과 역참조 규칙

| Job 결과                     | 결과 테이블         | 규칙                                              |
| ---------------------------- | ------------------- | ------------------------------------------------- |
| PDF 처리 상태                | `lecture_materials` | `processed_by_job_id`, `processed_by_job_attempt` |
| PDF·Transcript·Q&A 검색 조각 | `knowledge_chunks`  | `created_by_job_id`, `created_by_job_attempt`     |
| 질문 클러스터                | `question_clusters` | 같은 Job에서 여러 행 가능                         |
| LIVE/FINAL 요약              | `lecture_summaries` | Job당 한 결과                                     |
| Assistant 답변               | `chat_messages`     | Job당 한 Assistant Message                        |

Job 결과 행 삽입 또는 Material 상태 확정과 `ai_jobs.status = 'SUCCEEDED'` 전이는 같은 DB 트랜잭션에서 수행한다. 실패한 attempt가 만든 중간 결과는 commit하지 않는다. `chat_message_evidence`처럼 결과 aggregate의 종속 행은 상위 `chat_messages.created_by_job_id`를 통해 같은 Job에 귀속된다.

녹음 upload 완료는 HQ STT 후속 시작 gate지만, 구체 AIJob type·typed target·
Transcript 결과 역참조는 PR4 범위이므로 이 표와 `ai_jobs`에 추가하지 않는다.

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
| `completed_at`             | `timestamptz` |    Y | `NULL`              | -               | 완료·실패 terminal 전이 시각        |
| `expires_at`               | `timestamptz` |    Y | `NULL`              | CHECK           | terminal 전이 후 정확히 24시간      |
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
- `CHECK ((state = 'PROCESSING' AND completed_at IS NULL AND expires_at IS NULL) OR (state IN ('COMPLETED', 'FAILED') AND completed_at IS NOT NULL AND expires_at = completed_at + interval '24 hours'))`
- `CHECK (completed_at IS NULL OR completed_at >= created_at)`
- `CHECK (state = 'PROCESSING' OR response_status IS NOT NULL)`
- `INDEX idempotency_records_expiry_idx (expires_at) WHERE expires_at IS NOT NULL`
- `user_id ON DELETE CASCADE`

같은 key로 다른 `request_hash`가 오면 `409 IDEMPOTENCY_KEY_REUSED`를 반환한다. `PROCESSING` record의 lease가 유효하면 중복 처리를 시작하지 않는다. `COMPLETED` 또는 `FAILED`로 terminal 전이할 때 `completed_at`과 `expires_at = completed_at + interval '24 hours'`를 함께 기록하고 같은 응답을 정확히 24시간 재사용한다. cleanup은 terminal이면서 `expires_at <= now()`인 행만 삭제하고, lease가 만료된 `PROCESSING` 행은 별도 복구 절차로 재처리하거나 실패 전이한다.

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
| `Course.current_session`                | 해당 Course의 유일한 `READY`, `LIVE`, `PROCESSING` Session; 없으면 `NULL`                                    |
| `LectureSessionSummary.started_at`      | 같은 날짜의 완료 class를 실제 시작 시각으로 구분하는 `lecture_sessions.started_at`                           |
| `LectureSession.completed_at`           | 후처리 완료 시각인 `lecture_sessions.completed_at`                                                           |
| `Question.cluster`                      | `questions.cluster_id`로 현재 `question_clusters` join                                                       |
| `Question.cluster` 공개 lifecycle       | Cluster의 `generation`, `ordinal`, `is_final`, `finalized_at`, `created_by_job_id`, `created_by_job_attempt` |
| `Question.reacted_by_me`                | 현재 사용자의 `question_reactions` 존재 여부                                                                 |
| `Question.reaction_count`               | `questions.reaction_count`; 원장은 `question_reactions`                                                      |
| `Answer.question_ids`                   | 해당 Answer의 모든 `answer_questions`를 `position` 순으로 반환; `released_at`은 현재 유효 연결 판정에만 사용 |
| `Answer` 선택 출처 snapshot             | Cluster ID와 AI 대표 질문 exact text snapshot을 현재 Cluster 재조회 없이 반환                                |
| `Answer.start_sequence`, `end_sequence` | `start_segment_id`, `end_segment_id`의 `transcript_segments.sequence`                                        |
| `SessionRecording`                      | `session_recordings`의 공개 상태·media metadata; 내부 key와 publisher hash는 제외                            |
| `RecordingUpload`                       | `recording_uploads`의 ID·공개 상태·offset·total·expiry; temp key는 제외                                      |
| `AIJob.target`                          | `session_id`와 세 개의 typed target FK 중 값이 있는 FK                                                       |
| `AIJob.result`                          | 결과 테이블의 `created_by_job_id`; generic result FK는 없음                                                  |
| `AIJob.progress`                        | `progress_stage`, `progress_percent`를 안전한 공개 객체로 조립                                               |
| `AIJob` 공개 lifecycle                  | `visibility`, `attempt`, `version`, `blocks_session_completion`, `retryable`, `updated_at`                   |
| `SessionRecord`                         | Session, 권한이 허용한 Recording, 자료, final Transcript, Answer, FINAL Summary를 조립                       |
| `ChatEvidence.source_kind`              | `knowledge_chunks`에서 값이 있는 typed source FK로 안전하게 파생                                             |

목록 조회는 동일 정렬 값에서 `id`를 마지막 tie-breaker로 사용하고 cursor에도 포함한다. 같은 `lecture_date`의 완료 class 목록은 `started_at DESC, id DESC`를 추가한다. Material 목록·상세·content 조회는 `detached_at IS NULL`을 강제한다. Chat vector 검색은 반드시 SQL 안에서 `course_id`와 `session_id`를 제한하고, Material source에는 `lecture_materials.detached_at IS NULL AND processing_status = 'READY'`를 추가한다. 검색 후 애플리케이션에서 다른 Session이나 연결 해제 Material 결과를 제거하는 방식을 사용하지 않는다.

## 14. 주요 트랜잭션·동시성 규칙

멱등성 record를 쓰는 transaction은 도메인 변경과 terminal 응답을 같은 commit에 넣는다. terminal 전이 시 `completed_at = now()`, `expires_at = completed_at + interval '24 hours'`를 함께 기록한다.

### 14.1 Course 생성·참여·코드 회전·삭제

Course 생성은 다음 항목을 한 트랜잭션으로 처리한다.

1. `idempotency_records`를 선점하고 동일 요청인지 확인한다.
2. 서버가 참여 코드를 생성하고 정규화한다.
3. HMAC lookup hash와 AES-256-GCM 암호문을 만든다.
4. `courses`와 생성자의 `course_members(PROFESSOR)`를 함께 삽입한다.
5. 암호화한 응답과 멱등성 terminal 상태·`completed_at`·`expires_at`을 기록한다.

참여 시 정규화한 `[A-Z]{6}` 코드의 HMAC으로 Course를 찾은 뒤 Course 또는 멤버 행을 잠근다. 코드는 자동 만료하지 않으므로 만료 시각을 검사하지 않는다. `(course_id, user_id)`를 멱등 upsert하되 기존 `PROFESSOR` 역할을 `STUDENT`로 변경하지 않는다. HMAC UNIQUE 충돌이 난 코드 생성은 새 코드를 만들어 제한 횟수만큼 재시도한다.

제품 참여 코드 회전은 owner 권한과 멱등성 record를 확인하고 Course 행을 잠근 뒤 새 코드의 hash·ciphertext·nonce·key version, Course `version`, 멱등성 terminal 응답을 한 transaction에서 교체한다. commit 전에는 기존 코드가 유효하고 commit 뒤에는 새 코드만 유효하다. 이전 코드나 회전 이력 행은 만들지 않는다.

Course 삭제 권한은 불변 owner에게만 있다. Course에는 별도 종료 상태를 만들지 않는다. active class가 있을 때 삭제를 허용할지와 삭제 후 복구 유예 정책은 미정이므로 구현에서 임의로 hard delete·soft delete 중 하나를 확정하지 않는다. 삭제가 허용되는 조건이 충족된 뒤에는 `Course → Session → Material → Recording → Upload → AIJob` 순서로 잠그고 PDF·Recording final object key와 active Upload temp key를 수집해 storage cleanup outbox와 멱등성 `204` terminal 응답을 남긴 다음 Course aggregate를 한 transaction에서 cascade 삭제한다. outbox의 `session_id`는 부모 삭제 시 `NULL`이 되어도 내부 cleanup payload와 event ID로 처리할 수 있어야 한다.

### 14.2 class 생성·제목 수정·시작·삭제

- class 생성은 Course 행을 잠근 뒤 active class가 없는지 확인한다. 동일 날짜의 완료 이력과는 충돌하지 않으므로 순차적으로 여러 행을 허용한다. partial UNIQUE가 동시 생성 경쟁의 최종 방어선이며 충돌은 `409 ACTIVE_SESSION_EXISTS`로 변환한다.
- 제목 수정은 Session 행을 잠그고 모든 상태에서 허용한다. trim 후 빈 값이면 Course 제목·class 날짜·시각을 포함한 자동 제목으로 치환하고 `version`, `updated_at`, 공유 outbox event를 함께 갱신한다. 정확한 문자열 형식, `READY`에서 사용할 시각 원장과 timezone은 미정이며 `lecture_date`와 이미 기록된 lifecycle 시각은 수정하지 않는다.
- 시작은 Session을 잠근 뒤 `detached_at IS NULL`인 Material을 ID 순서로 잠근다. 연결된 Material 중 `processing_status = 'PROCESSING'`이 하나라도 있으면 `409 MATERIAL_PROCESSING_ACTIVE`로 거부한다. PDF가 0개이거나 연결된 행이 `READY`, `UPLOADED`, `FAILED`뿐이면 시작을 허용하고 `status = 'READY'` 조건으로 `LIVE`, `started_at`, `version`을 함께 갱신한다.
- 시작을 포함한 active 상태 경쟁의 최종 방어선은 `lecture_sessions_one_active_per_course_uq`다. 충돌은 `409 SESSION_STATE_CONFLICT`로 변환한다.
- 실시간 audio ticket은 시작 권한과 `LIVE` 상태를 확인한 뒤 별도 짧은 트랜잭션에서 발급한다.
- class 삭제는 owner가 `READY`, `COMPLETED`에서만 실행하고 `LIVE`, `PROCESSING`에서는 `409 SESSION_STATE_CONFLICT`로 거부한다. 삭제 transaction은 멱등성 record를 선점한 뒤 `Session → Material → Recording → Upload → AIJob` 순서로 대상 aggregate를 잠그고 PDF·Recording final object key와 Upload temp key를 수집한다. storage cleanup outbox와 멱등성 `204` terminal 응답을 남긴 다음 Session aggregate를 cascade 삭제한다. 삭제된 Job의 이전 attempt worker는 Job ID·attempt·run token·`RUNNING` 조건을 만족하지 못해 늦은 결과를 commit할 수 없다.

### 14.3 PDF 업로드·전처리·연결 해제

Material 관련 transaction의 잠금 순서는 `Session → Material → AIJob`이다. 업로드는 새 Material·Job을 만들기 전에 Session을 잠그고, Material worker claim은 잠금 없는 후보 탐색 뒤 이 순서로 행을 잠근 다음 Job의 `PENDING` 조건을 다시 검증한다. Material을 `UPLOADED`에서 `PROCESSING`으로 바꾸는 worker와 class 시작이 같은 Session 잠금에서 직렬화되므로, worker가 먼저 전이하면 시작은 `MATERIAL_PROCESSING_ACTIVE`로 실패하고 시작이 먼저 commit되면 이후 `LIVE`에서 전처리를 계속할 수 있다.

업로드는 다음 규칙을 따른다.

1. 해당 Course의 `PROFESSOR` 권한을 확인하고 파일을 임시 영역에서 검증한다. `byte_size > 100000000`은 `413 FILE_TOO_LARGE`, PDF MIME·parsing 검증 실패는 `415 UNSUPPORTED_MEDIA_TYPE`으로 변환한다.
2. 서버 생성 `storage_key`로 object를 저장한 뒤 Session을 잠그고 상태를 다시 확인한다. `READY`, `LIVE`, `COMPLETED`에서는 허용하고 `PROCESSING`에서는 `409 SESSION_STATE_CONFLICT`로 거부하며, 거부·DB 실패 시 저장 object를 보상 삭제한다.
3. `detached_at IS NULL`인 Material이 10개 미만인지 확인한다. 10개면 `409 MATERIAL_LIMIT_EXCEEDED`로 거부하고, 동시 삽입은 active-count trigger가 최종 차단한다.
4. 정규화한 `original_filename`과 별도 `display_name`을 만든다. 연결된 이름과 충돌하면 확장자 앞에 ` (1)`, ` (2)` 순 suffix를 붙여 partial UNIQUE를 만족시키며 기존 행의 이름은 바꾸거나 재번호를 매기지 않는다.
5. `lecture_materials`, `MATERIAL_PROCESSING` Job, queue outbox event와 제공된 멱등성 키의 terminal `202` 응답을 같은 DB transaction에서 만들고 commit한다. 같은 키·요청은 기존 결과를 재사용하지만 키가 없거나 서로 다른 키인 별도 요청은 파일 내용과 `original_filename`이 같아도 새 Material을 만들며 content hash UNIQUE를 두지 않는다.

Worker claim과 결과 transaction은 `detached_at IS NULL`인 대상만 처리한다. 처리 성공은 Job의 `target_material_id`, 현재 attempt, run token, `RUNNING`, Material의 현재 `version`, `detached_at IS NULL`을 모두 확인하고 KnowledgeChunk 삽입, Material `READY`·`processed_by_job_id` 갱신, Job `SUCCEEDED` 전환을 함께 commit한다. 조건이 달라진 늦은 결과는 저장하지 않는다.

Material 연결 해제는 해당 Course의 `PROFESSOR`가 요청할 수 있고 Session이 `READY`, `LIVE`, `COMPLETED`일 때 허용한다. `PROCESSING`에서는 `409 SESSION_STATE_CONFLICT`로 거부한다. transaction은 `Session → Material → AIJob` 순서로 잠근 뒤 다음을 수행한다.

1. `detached_at IS NULL`인 Material을 찾지 못하면 `404 MATERIAL_NOT_FOUND`를 반환한다. 조회 뒤 드문 동시 요청으로 version 조건 갱신이 실패하면 `409 MATERIAL_DELETE_CONFLICT`로 구분한다.
2. `detached_at = now()`, `version + 1`, `updated_at`을 한 번에 기록한다. `processing_status`에는 새 `DETACHED` 값을 추가하지 않는다.
3. 아직 결과를 만들지 않은 대상 `MATERIAL_PROCESSING` Job이 `PENDING`, `RUNNING`, `FAILED`이면 같은 transaction에서 삭제한다. Worker는 Job 행과 Material version·tombstone을 모두 확인하므로 실행 중 Job을 삭제해도 늦은 결과를 저장할 수 없다. 성공 결과의 provenance로 참조되는 `SUCCEEDED` Job은 Evidence·Chunk 보관 정책이 확정될 때까지 유지한다.
4. object 삭제와 Material source KnowledgeChunk 정리를 위한 내부 outbox task, 필수 멱등성 키의 terminal `204` 응답을 같은 transaction에 기록하고 commit한다. `storage_key`는 내부 object 정리 payload에서만 사용한다. 같은 키·요청의 재실행은 tombstone 뒤에도 기존 `204`를 반환한다.
5. commit 직후부터 목록·상세·content 조회와 RAG 검색은 `detached_at IS NULL` 조건으로 해당 Material을 제외한다. 정리 작업 실패가 tombstone을 되돌리지는 않는다.

Outbox consumer는 object가 이미 없어도 성공으로 처리하고 실패 시 멱등 재시도한다. Knowledge 정리는 참조되지 않은 Material source Chunk를 background에서 삭제한다. 연결 해제 Material의 원문 content link는 제공하지 않는다. 기존 `chat_message_evidence`가 참조하는 Chunk의 보관, Evidence snapshot 또는 FK 변경, 과거 Evidence label·source 표시 방식과 Material·Chunk 최종 hard delete 시점은 미정이므로 현재 deferred `NO ACTION` FK를 유지하고 참조 중인 행을 임의로 삭제하지 않는다.

### 14.4 Recording publisher claim·upload

- 첫 `audio.start`는 `Session → Recording` 순서로 잠그고 권한·`LIVE`를
  재확인한 뒤 Recording과 publisher HMAC claim을 원자적으로 만든다. 같은
  publisher는 기존 행을 재사용하고 다른 publisher는 거부한다.
- 종료 transaction은 Session을 즉시 `PROCESSING`으로 바꾸고 Recording을
  `UPLOAD_PENDING`으로 전이한다. audio stop·drain 성공 여부로 Session 전이를
  클라이언트가 추정하지 않는다.
- upload 초기화는 `Session → Recording → Upload` 순서로 잠그고
  `PROCESSING`·`UPLOAD_PENDING`을 확인한다. active upload partial UNIQUE가 동시
  초기화를 막고 Recording을 `UPLOADING`으로 바꾼다.
- chunk는 조건부 offset update로 중복·역순 쓰기를 막고, finalize는 7.3절의
  한 transaction으로 final metadata·outbox를 확정한다.
- upload 만료 worker는 잠금 없는 후보 탐색 뒤 `Session → Recording → Upload`를
  잠그고 여전히 `ACTIVE` 이며 `expires_at <= now()`인지 재확인한다.
  `EXPIRED`·`terminal_at`와 temp cleanup outbox를 같이 commit하지만 exact expiry와
  Recording·Session 전이는 미정이다.

### 14.5 Transcript 저장

- streaming STT의 partial 결과는 메모리·WebSocket 전송에만 사용하고 DB에 넣지 않는다.
- final 결과는 `(session_id, utterance_id)` upsert 또는 insert-on-conflict로 중복 저장을 막는다.
- 새 `sequence`는 `UPDATE lecture_sessions SET last_final_sequence = last_final_sequence + 1 ... RETURNING last_final_sequence`로 원자 할당하고 Segment insert를 같은 짧은 트랜잭션에서 처리한다.
- 끊김으로 복구할 수 없는 구간은 텍스트를 추측해 채우지 않고 `transcript_gaps`에 남긴다.

### 14.6 질문·반응·클러스터링

- 질문 생성과 `QUESTION_CLUSTERING` Job/outbox 등록을 같은 트랜잭션으로 처리한다.
- 반응 추가·삭제는 `(question_id, user_id)` 실제 삽입·삭제 성공 여부에 따라 `questions.reaction_count`를 같은 트랜잭션에서 `+1/-1` 한다.
- 자기 질문 반응 금지는 Question을 읽어 작성자를 비교하는 조건부 DML 또는 constraint trigger로 보장한다.
- 재클러스터링 worker는 Session과 대상 Question들을 잠그고 같은 Job attempt가 만든 모든 Cluster에 Session 안에서 증가하는 같은 `generation`과 서로 다른 `ordinal`을 넣은 뒤 `questions.cluster_id`를 한 번에 교체한다. generation 원자 할당과 최신 결과 fence의 구체 방식은 후속 계약으로 남긴다. 교체가 끝난 뒤 대체된 non-final Cluster를 모두 삭제한다. Answer의 Cluster ID·AI 대표 질문 exact text와 AnswerQuestion membership snapshot은 유지된다.
- 수업 종료 후 final clustering 결과는 새 Cluster 행에 `is_final = true`, `finalized_at`을 기록하고 질문 FK를 원자적으로 교체한다. 현재 final Cluster는 Session 삭제 전까지 보관한다. 나중에 final 결과를 다시 확정하면 새 세트를 commit한 뒤 대체된 final 세트를 삭제한다.
- 클러스터 membership 변경 이력이나 과거 질문→Cluster 매핑은 저장하지 않는다.

### 14.7 Answer 시작·완료·취소

Answer 시작은 다음 순서로 처리한다.

1. Session을 잠그고 `LIVE`인지, 요청자가 해당 Course의 `PROFESSOR`인지 확인한다.
2. `CAPTURING` Answer가 없는지 확인한다. 경쟁 요청은 partial UNIQUE가 최종 차단한다.
3. 직접 선택된 질문 또는 선택 Cluster의 현재 질문을 잠근다. Cluster 선택이면 현재 Cluster ID와 AI 대표 질문 exact text인 `title`도 함께 읽는다.
4. `answers`를 만들고 Cluster ID·`title` snapshot과 선택 시점 마지막 final Transcript `sequence`를 저장한다. 직접 질문 선택이면 두 Cluster snapshot 컬럼은 모두 `NULL`이다.
5. 질문 ID와 표시 순서를 `answer_questions`에 snapshot하고 Question 상태를 `SELECTED`로 바꾼다.
6. Answer와 질문 event를 outbox에 기록하고 commit한다.

완료 시 첫·마지막 Segment를 잠그고 둘이 Answer와 같은 Session인지, `start.sequence <= end.sequence`, `start.sequence > capture_started_after_sequence`인지 검증한다. 이를 deferrable constraint trigger로도 이중 검증한다. Answer를 `COMPLETED`, 대상 질문을 `ANSWERED`로 바꾸고 outbox event를 함께 기록한다.

취소 시 Answer를 `CANCELLED`로 바꾸고 해당 `answer_questions.released_at`을 채운 뒤 질문을 `OPEN`으로 되돌린다. 따라서 “질문당 Answer 1개”는 취소되지 않은 활성·완료 연결이 최대 하나라는 뜻이며, 취소 snapshot은 감사용으로 남는다.

### 14.8 class 종료와 후처리 완료

종료 요청은 Session 행을 `FOR UPDATE`로 잠근 뒤 다음을 한 트랜잭션에서 수행한다.

1. `LIVE` 상태이고 `CAPTURING` Answer가 없는지 확인한다.
2. `PROCESSING`, `ended_at`, 새 `version`으로 바꿔 추가 audio를 즉시 차단한다.
3. Recording이 있으면 `CAPTURING → UPLOAD_PENDING`, `capture_ended_at`을 같이
   기록한다. Recording이 없어도 Session 종료 자체는 허용하며 HQ source·
   fallback과 후처리 완료 predicate는 PR4로 넘긴다.
4. `SESSION_POSTPROCESSING`, final clustering, FINAL Summary, 공통 KnowledgeChunk 등
   필수 후처리 Job을 `blocks_session_completion = true`로 생성한다.
5. 공유 상태 event와 idempotency 응답을 기록한다.

Recording 저장 gate는 blocking Job 개수와 별도로 평가한다. Recording이
`UPLOAD_PENDING`이나 `UPLOADING`인 동안은 다른 blocking Job이 모두 terminal이어도
Session을 `COMPLETED`로 바꾸지 않는다. `SESSION_POSTPROCESSING`은 live drain·child
Job 상태 수집 책임을 독립적으로 마칠 수 있고, upload finalize outbox가
`UPLOADED`를 commit한 뒤에만 HQ STT 후속 처리를 시작할 수 있다.
HQ STT Job·Transcript 결과·최종 Session 완료 predicate, Recording `FAILED`, upload
만료·timeout 전이는 PR4에서 확정한다. Recording 없이 종료된 Session은 기존
공유 blocking Job 완료 규칙을 유지하며 HQ source·fallback만 PR4로 넘긴다.

각 blocking Job이 terminal 상태가 될 때 worker는 먼저 같은 Session 행을 잠근다. Recording이 없고 미완료 blocking Job이 없으면 기존처럼 Session을 `COMPLETED`로 바꾸고 `completed_at`을 기록한다. Recording이 있으면 위 저장 gate와 PR4 완료 predicate를 함께 확인한다. 일부 기존 Job이 최종 실패해도 Session은 완료될 수 있지만 실패 Job과 마지막 성공 결과를 그대로 노출해 재시도할 수 있게 한다. 동시에 끝나는 worker 경쟁을 보정하는 reconciliation 작업도 둔다. 완료 후 Job을 다시 시도해도 Session을 `PROCESSING`으로 되돌리지 않는다.

### 14.9 AIJob claim·재시도·결과 commit

- worker claim은 `status = 'PENDING' AND available_at <= now()`를 `FOR UPDATE SKIP LOCKED`로 선택한다.
- claim 시 `RUNNING`, `run_token`, `lease_expires_at`, `started_at`을 함께 기록한다.
- heartbeat는 현재 `run_token`이 일치할 때만 lease를 연장한다.
- 결과 테이블 삽입과 Job `SUCCEEDED` 전이는 같은 트랜잭션이다.
- 결과 commit 조건에는 `id`, `attempt`, `run_token`, `RUNNING` 상태를 모두 포함한다.
- 실패는 안전한 code/message만 저장하며 원문 PDF, 질문, prompt, provider 응답을 오류 칼럼이나 로그에 넣지 않는다.
- 재시도는 멱등성 record와 같은 Job 행을 잠그고 `FAILED`이며 `retryable = true`인지 확인한 뒤에만 허용한다. 새 Job을 만들지 않고 같은 행에서 `attempt + 1`, `version + 1`, `PENDING`으로 전환하며 `run_token`, lease, progress, error, `started_at`, `finished_at`을 초기화한다. 재시도 queue outbox와 멱등성 `202` terminal 응답도 같은 transaction에 기록한다.
- 실패 attempt의 부분 결과는 commit하지 않으므로 retry가 기존 성공 결과를 덮어쓰지 않는다. 이전 attempt의 늦은 worker 결과는 현재 `attempt`, `run_token`, `RUNNING` 조건을 만족하지 못해 폐기한다. 성공 결과 재생성 기능은 MVP retry와 분리된 명시적 후속 정책으로 다룬다.

### 14.10 Chat 메시지와 근거

사용자 Message 생성 시 `chat_sessions` 행을 잠가 다음 sequence를 발급하고 `CHAT_RESPONSE` Job을 함께 만든다. Assistant 결과 transaction은 Message, `chat_message_evidence`, Job 성공을 함께 commit한다. Evidence는 검색 시점 Chunk ID와 순위의 snapshot이며, 근거 source의 변경 여부와 무관하게 해당 답변이 사용한 Chunk를 가리킨다.

### 14.11 Outbox 발행

도메인 행과 outbox 행을 같은 transaction에 저장하고 commit 후 publisher가 발행한다. 발행 완료 전 장애가 나면 같은 event를 재발행할 수 있으므로 client와 내부 consumer는 event ID와 resource version으로 중복·역순을 처리한다.

## 15. 보안·보관·삭제 정책

### 15.1 민감정보

- 참여 코드, OAuth PKCE verifier, 멱등성 응답은 AES-256-GCM으로 암호화한다.
- 검색이 필요한 token·code는 원문 대신 목적별로 분리된 HMAC을 저장한다.
- 참여 코드, 인증 token, ticket, prompt 원문은 애플리케이션 로그와 outbox payload에 남기지 않는다. 질문 원문은 로그에 남기지 않고, 멤버용 실시간 event 계약에 필요한 경우에만 최소 payload로 24시간 이내 보관한다.
- Recording final·Upload temp storage key, 서버 경로, fragment key·manifest,
  `client_stream_id` 원문과 provider 원문 오류는 외부 응답·공유 event·로그에
  남기지 않는다. storage key는 내부 worker 조회와 cleanup outbox에만 사용한다.
- Course 상세에서 참여 코드를 복호화하는 경로는 `PROFESSOR` 권한을 다시 확인하고 접근 audit을 남긴다.
- DB 계정은 API·worker·migration 역할을 분리하고 최소 권한을 부여한다.

### 15.2 권장 보관 기간

| 데이터                                          | MVP 권장값                                | 처리                               |
| ----------------------------------------------- | ----------------------------------------- | ---------------------------------- |
| `oauth_transactions`                            | 생성 후 10분                              | 사용 완료·만료 후 정기 삭제        |
| `realtime_tickets`                              | 생성 후 60초                              | 사용 완료·만료 후 정기 삭제        |
| `auth_sessions`                                 | 발급 후 7일                               | 만료·폐기 후 정기 삭제             |
| `idempotency_records`                           | terminal `completed_at`부터 정확히 24시간 | 암호문 포함 만료 직후 정기 삭제    |
| 발행 완료 `outbox_events`                       | 24시간                                    | replay window 후 정기 삭제         |
| `session_recordings`·녹음 object                | 미정                                      | 동의·접근·보관·삭제 정책 확정 후   |
| terminal `recording_uploads`·temp object        | exact expiry 미정                         | 만료 후 outbox 멱등 정리           |
| 연결된 PDF·Transcript·질문·Answer·FINAL Summary | Course 수명                               | Course 관리 삭제·정책 만료 시 삭제 |
| 연결 해제 Material metadata·source Chunk        | Evidence 정책 확정 전 tombstone 유지      | object는 즉시 비노출·비동기 삭제   |
| 개인 LIVE Summary·Chat                          | 계정 또는 Course 수명 중 먼저 도달한 시점 | 사용자 탈퇴·Course 삭제 시 삭제    |
| 실패 `ai_jobs`                                  | Course 수명                               | 진단 가능한 안전한 metadata만 보관 |

멱등성 record의 24시간은 외부 요청 계약으로 확정된 값이다. 나머지 보관 기간은 제품의 개인정보 정책 확정 전 운영 기본값이며, 외부 공개 전 법무·운영 검토로 확정한다. 녹음은 동의·접근·보관·삭제가 모두 미정이므로 임시 운영 기본값도 가정하지 않는다.

### 15.3 삭제 순서와 `ON DELETE`

- owner의 Course 삭제는 허용 조건이 확정된 뒤 `course_members`, `lecture_sessions`와 Session 하위 데이터를 aggregate 단위로 cascade한다. active class가 있을 때의 삭제와 복구 유예 정책은 아직 미정이다.
- owner의 class 삭제는 `READY`, `COMPLETED`에서만 허용한다. Session 삭제는 Material, Recording, Upload, Transcript, Gap, Cluster, Question, Answer, Summary, Chat, KnowledgeChunk와 Job을 함께 정리하며 `LIVE`, `PROCESSING`에서는 거부한다.
- Question 삭제는 Reaction을 cascade한다. 공유 질문 보존을 위해 User 탈퇴가 Question 삭제로 이어지지는 않는다.
- Chat 삭제는 Message와 Evidence를 cascade한다.
- 독립적인 `ai_jobs` 삭제는 결과 행의 deferred `NO ACTION` FK 때문에 commit되지 않는다. Session 전체 삭제에서는 Job과 결과가 같은 transaction에서 함께 제거된다.
- KnowledgeChunk 단독 삭제는 Evidence가 참조하면 deferred `NO ACTION` FK가 막는다. 재색인 시 기존 Chunk를 즉시 삭제하지 말고 새 Chunk·Evidence 처리 정책을 먼저 적용한다.
- Material 연결 해제는 `detached_at` tombstone을 먼저 commit한다. 그 즉시 목록·content·RAG에서 제외하고 object와 참조되지 않은 Material source Chunk는 outbox 기반 background 정리로 삭제한다. Evidence가 참조하는 Chunk와 Material tombstone의 hard delete 시점은 미정이다.
- 삭제 transaction은 `Course → Session → Material → Recording → Upload → AIJob` 순서로 잠근다. Session 단독 삭제도 `Session → Material → Recording → Upload → AIJob`, Material lifecycle은 기존 `Session → Material → AIJob`, Recording lifecycle은 `Session → Recording → Upload → AIJob` 순서를 사용한다. 삭제·연결 해제된 Material을 처리하던 Job의 늦은 결과는 Job attempt·run token·상태와 Material version·`detached_at IS NULL` fencing에서 폐기한다.
- PDF·Recording final object와 Upload temp object는 DB cascade로 삭제되지 않는다. aggregate 삭제는 DB 행을 지우기 전에 모든 key를 수집하고 내부 storage cleanup outbox를 남겨 멱등 삭제한다. storage key와 물리 구성은 외부 응답·공유 event·로그에 노출하지 않는다.
- User 탈퇴는 우선 `users.deleted_at`을 기록하고 이름·이메일·avatar를 익명값으로 교체한다. 인증 identity/session과 개인 Chat·LIVE Summary·REQUESTER_ONLY Job은 같은 deferred transaction에서 제거하고, 공유 질문·Answer 작성자 FK는 익명화된 동일 User 행을 가리키게 유지한다.
- `courses.created_by_user_id`, `course_members.user_id`, `lecture_sessions.created_by_user_id`, `questions.author_user_id` 등 공유 `RESTRICT` 참조가 하나라도 있으면 User 행은 영구 tombstone으로 유지하고 hard delete하지 않는다. hard delete는 모든 공유·Reaction·개인 참조가 전혀 없는 계정만 허용한다. Course owner 탈퇴 시 Course와 멤버십을 어떻게 처리할지는 별도 미정 사항이다.

MVP의 질문 일반 hard delete API는 제공하지 않는다. Course·class 삭제는 위 owner 권한, 상태, cascade와 object storage 보상 규칙을 따르는 하나의 관리 workflow로 구현한다.

## 16. 인덱스 운영 원칙

- B-tree 복합 인덱스의 선두 컬럼은 권한·범위 조건인 `course_id`, `session_id`, `owner_user_id`를 우선한다.
- partial UNIQUE와 trigger를 애플리케이션 선조회로 대체하지 않는다. Course당 `READY`·`LIVE`·`PROCESSING` 합계 하나, Session당 연결된 Material 최대 10개와 표시 이름 유일성, Session당 논리 Recording 하나, Recording당 active Upload 하나, Session당 `CAPTURING` Answer 하나, 질문당 미해제 Answer 하나는 DB가 최종 보장한다.
- `questions.reaction_count`와 최신 cursor는 실시간 hot path를 위해 저장하되 원장과 reconciliation한다.
- HNSW는 embedding model과 차원이 확정된 뒤 생성한다. Session 범위 B-tree를 함께 두고 실제 데이터 분포로 `ef_search`, `m`, `ef_construction`을 조정한다.
- production index 추가·교체는 가능한 경우 `CREATE INDEX CONCURRENTLY`를 사용하고 migration transaction 제약을 별도로 처리한다.
- `EXPLAIN (ANALYZE, BUFFERS)`로 최근 질문, 인기 질문, final Transcript cursor, Job claim, Chat vector 검색을 우선 검증한다.

## 17. 모델·migration 생성 순서

이 문서 승인 후 SQLAlchemy 모델과 Alembic migration은 다음 순서로 나눈다.

1. `pgcrypto`, `vector` 확장과 공통 `updated_at` trigger
2. User, Course, CourseMember, LectureSession
3. 인증 Session·OAuth·RealtimeTicket, Material, SessionRecording, RecordingUpload, Transcript, Gap, ChatSession
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

| 항목                                      | 현재 문서 표현                                             | 확정 시점                           |
| ----------------------------------------- | ---------------------------------------------------------- | ----------------------------------- |
| class 자동 제목 형식·시각 원장·timezone   | Course 제목·날짜·시각 포함은 확정, 나머지는 미정           | class 생성·수정 구현 전             |
| active class가 있는 Course 삭제           | owner 권한만 확정, 허용 여부·응답 미정                     | Course 삭제 구현 전                 |
| Course 삭제 후 복구 유예                  | hard delete·soft delete·유예 기간 미정                     | Course 삭제 구현 전                 |
| Course owner 탈퇴 처리                    | owner 이전은 없고 User tombstone 원칙만 확정               | 탈퇴 workflow 구현 전               |
| Cluster generation 할당·최신 결과 fence   | Session별 증가·미재사용과 공개 필드만 확정                 | 전체 재클러스터링 계약 변경 시      |
| embedding model·차원                      | `vector(EMBEDDING_DIM)` placeholder                        | 모델 선택 후 첫 vector migration 전 |
| vector index parameter                    | HNSW 사용 방향만 확정                                      | staging 데이터 부하 시험 후         |
| 개인 LIVE Summary·Chat 정확한 보관 기간   | 계정/Course 수명 이내 권장                                 | 개인정보 정책 확정 전               |
| outbox replay 보관 기간                   | 발행 완료 후 24시간 권장                                   | 운영 SLO 확정 전                    |
| 연결 해제 후 Evidence·Chunk 보관·FK       | 즉시 RAG 제외만 확정, snapshot·FK·기간 미정                | Material hard delete 구현 전        |
| Material·Chunk 최종 hard delete 시점      | object 비동기 삭제와 tombstone만 확정                      | Evidence 정책 확정 후               |
| 녹음 codec·container·browser 저장         | live PCM 규격과 별개임만 확정                              | 클라이언 녹음 구현 전               |
| resumable upload protocol·checksum·expiry | offset 원장과 만료 필드만 확정                             | upload handler·migration 전         |
| Recording 물리 object cardinality         | Session당 논리 aggregate 1개, file·fragment·manifest 미정  | storage adapter 확정 전             |
| publisher lease·재획득·takeover           | 첫 HMAC claim·같은 publisher resume만 확정                 | realtime 다중 process 구현 전       |
| Recording 실패·Session 완료               | upload 완결 gate만 확정, 미생성·만료·`FAILED` 전이 미정    | PR4 후처리 계약                     |
| `DEGRADED`·audio stop·replay              | 현재 임계·상태 전이·복구 방식 미정                         | realtime 장애 계약 확정 전          |
| 녹음 동의·접근·보관·삭제                  | 녹음 저장·권한 재확인만 확정, 정책 미정                    | 외부 공개·개인정보 검토 전          |
| 녹음 quota·backup·RPO·RTO                 | PDF 제한과 분리 필요, 수치·backend 미정                    | KCloud 저장소 운영 설계 전          |
| HQ STT·Transcript·Answer 연결             | upload complete가 시작 gate, Job·version·offset·remap 미정 | PR4 계약 변경                       |

위 항목을 확정하기 전에는 placeholder를 실제 SQLAlchemy 타입이나 irreversible migration으로 굳히지 않는다.

### 18.1 외부 계약 동기화 확인

API 명세와 OpenAPI는 다음 DB 규칙을 같은 변경 묶음에서 반영해야 한다.

- Course 생성자는 유일한 교수자 owner이며 owner 이전은 없다.
- 참여 코드는 `[A-Z]{6}`, 무기한이고 owner 회전 시 이전 코드가 즉시 무효다.
- Course당 `READY`, `LIVE`, `PROCESSING` 합계는 최대 1개이며 `current_session`으로 노출한다.
- 같은 날짜 class는 허용하고 완료 목록은 실제 `started_at`으로 구분한다.
- 제목은 모든 상태에서 수정하고 날짜·lifecycle 시각은 수정하지 않는다.
- `READY`, `COMPLETED` class 삭제만 허용하며 Course 삭제의 active·복구 정책은 미정으로 유지한다.
- 멱등성 terminal 응답은 `completed_at`부터 정확히 24시간 재사용한다.
- class당 연결된 PDF는 최대 10개이고 파일당 최대 `100000000` bytes다. PDF 0개와 `READY`·`UPLOADED`·`FAILED`는 시작을 허용하며 연결된 `PROCESSING`만 시작을 막는다.
- Material 업로드·연결 해제 허용 Session 상태, 안정적인 `display_name`, `detached_at` 즉시 비노출과 비동기 정리 계약을 동일하게 노출한다.
- 첫 `audio.start`가 Session당 논리 Recording과 publisher claim을 만들고, 다른
  `client_stream_id`는 거부하며 같은 ID만 reconnect·resume한다.
- Recording 상태는 `CAPTURING`, `UPLOAD_PENDING`, `UPLOADING`, `UPLOADED`,
  `FAILED`로 동기화하고 `UPLOADED`에서만 playback한다.
- Upload 상태는 `ACTIVE`, `COMPLETED`, `EXPIRED`, `FAILED`이며 서버 확인
  offset을 최종 진실로 사용한다.
- 모든 Recording·Upload 응답에서 storage key, 서버 경로, fragment·manifest
  구성을 제외하고, upload complete를 HQ STT 후속 시작 gate로 사용한다.
- 질문당 취소되지 않은 활성·완료 Answer는 최대 1개다.
- AIJob retry는 같은 Job ID에서 `attempt`를 증가시킨다.
- Cluster 공개 필드는 `generation`, `ordinal`, `is_final`, `finalized_at`, `created_by_job_id`, `created_by_job_attempt`다.
- `source_cluster_title_snapshot`은 선택 당시 `question_clusters.title`, 즉 AI 대표 질문의 정확한 text다.
- Chat Evidence의 저장 식별자는 `knowledge_chunk_id`다. API에 source 표시가 필요하면 KnowledgeChunk의 typed FK에서 `source_kind`, label, 안전한 link를 파생한다.
- AIJob `result` link는 결과 테이블의 `created_by_job_id` 역조회로 조립한다.

## 19. 구현 전 검토 체크리스트

- [ ] API 상태값과 DB `CHECK` 값이 일치하는가?
- [ ] 참여 코드 암호화 키와 lookup HMAC key가 분리되어 있는가?
- [ ] Course 생성자와 정확히 한 명인 `PROFESSOR` membership을 deferred invariant로 검증하는가?
- [ ] Course당 `READY`·`LIVE`·`PROCESSING` 합계 하나를 partial UNIQUE로 검증하는가?
- [ ] 같은 날짜 완료 class 목록이 `started_at`과 `id`를 tie-breaker로 사용하는가?
- [ ] 참여 코드가 `[A-Z]{6}`로 정규화되고 회전 뒤 이전 코드·이력이 남지 않는가?
- [ ] Session당 연결된 PDF 최대 10개를 Session 잠금과 DB trigger가 함께 검증하는가?
- [ ] 연결된 Material의 `display_name` partial UNIQUE와 안정적인 suffix를 검증하는가?
- [ ] 파일 크기 `1..100000000`, MIME·parsing과 같은 내용 재업로드 허용이 일치하는가?
- [ ] class 시작이 연결된 `PROCESSING`만 차단하고 PDF 0개·`READY`·`UPLOADED`·`FAILED`는 허용하는가?
- [ ] Material 연결 해제가 tombstone commit 즉시 목록·content·RAG에서 제외되고 object·Knowledge 정리를 outbox로 예약하는가?
- [ ] 클러스터 generation·ordinal·final 상태와 Job attempt provenance를 검증하는가?
- [ ] 클러스터 이력 테이블 없이 Answer 시작 시 AI 대표 질문 exact text snapshot만 보관하는가?
- [ ] 취소되지 않은 질문–Answer 연결이 질문당 하나인가?
- [ ] 모든 AI 생성 root 결과 행에 `created_by_job_id`, `created_by_job_attempt`가 있는가? (입력 Material 상태는 `processed_by_*`, Evidence는 상위 Assistant Message를 통해 귀속)
- [ ] Job 재시도가 같은 행의 `attempt` 증가와 run token 검증을 사용하는가?
- [ ] 멱등성 terminal 응답 만료가 `completed_at + 24 hours`인가?
- [ ] Chat Evidence가 공통 KnowledgeChunk만 참조하는가?
- [ ] DB에 generic `source_type + source_id` FK가 없는가?
- [ ] vector 검색이 SQL 단계에서 Course·Session 범위를 제한하는가?
- [ ] partial Transcript는 저장하지 않고 browser 로컬 녹음만 upload 후 영구 저장하는가?
- [ ] Session당 Recording 하나와 Recording당 active Upload 하나를 DB가 보장하는가?
- [ ] publisher HMAC claim이 첫 탭과 같은 ID resume을 구분하고 원문을 로그에 남기지 않는가?
- [ ] upload offset·finalize·expiry가 조건부 전이와 outbox cleanup으로 일관되는가?
- [ ] 삭제 transaction이 PDF·Recording final·Upload temp object 정리 outbox를 남기는가?
- [ ] class 삭제가 `READY`, `COMPLETED`에서만 가능하고 늦은 worker 결과를 fence하는가?
- [ ] Material transaction 잠금 순서가 `Session → Material → AIJob`이고 늦은 결과가 `detached_at`·version을 확인하는가?
