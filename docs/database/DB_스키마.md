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

이 계약의 관계형 골격은 2026-07-14에 SQLAlchemy 모델과 Alembic migration으로 생성했다. `pgcrypto`, 공통 `updated_at` trigger, 32개 domain table, 확정된 CHECK·partial UNIQUE·조회 index·복합 FK와 Course owner·Material 수량 guard를 포함한다. API·service·worker는 아직 별도 기능 PR에서 구현한다. embedding 차원과 HNSW index는 18절의 미정 사항대로 PR-18에서 추가한다.

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
- `purge_on_session_end=false`인 일반 멱등성 완료·실패 응답은 terminal 전이 시각부터 정확히 24시간 재사용한다. 개인 LIVE AI purge 범위의 조기 삭제·재응답은 별도 미정 정책을 따른다.
- 한 class에는 연결 상태인 PDF를 최대 10개까지 둘 수 있고, PDF가 0개여도 class를 시작할 수 있다.
- 연결된 Material 중 `PROCESSING`이 하나라도 있으면 class 시작을 거부한다. `READY`, `UPLOADED`, `FAILED`와 PDF 0개는 시작을 막지 않는다.
- PDF 한 파일의 최대 크기는 decimal `100000000` bytes다. 같은 내용과 같은 원본 파일명 재업로드는 허용한다.
- 학생 질문은 Session별 `clustering_sequence`를 생성 순서대로 한 번만 부여받고, 클러스터링 수요·적용 범위·revision은 Session 1:1 `question_clustering_states`가 관리한다.
- AI 대표 질문은 `ai_representative_questions` 독립 리소스로 저장하며 생성 뒤 text와 Job provenance를 수정하지 않는다.
- LIVE 클러스터링은 새 학생 질문만 기존 클러스터에 배치하고 기존 질문을 이동시키지 않는다. PROCESSING의 FINAL 클러스터링은 대상 전체를 처음부터 다시 배치한다.
- 클러스터 교체 이력은 보관하지 않되, 답변 중이거나 답변 완료된 과거 대표 질문은 일반 child 노드로 보존한다. 답변이 없는 과거 대표 질문은 공개·RAG에서 즉시 폐기하며, 관련 KnowledgeChunk를 참조하는 Evidence가 없을 때만 hard delete하고 있으면 내부 `DISCARDED` tombstone으로 남긴다.
- Answer는 학생 질문 또는 AI 대표 질문 중 정확히 하나만 대상으로 가지며, 대상별 Answer는 최대 하나다. `CAPTURING` 취소는 Answer를 hard delete하고 감사 이력을 남기지 않는다.
- 수업 중 Answer는 LIVE Transcript 범위를 캡처한다. 수업 후 새 text-only Answer는 미답변 학생 질문에만 만들고, 학생 질문 또는 답변 때문에 보존된 AI 대표 질문의 기존 완료 Answer에는 교수자 text를 보충할 수 있다.
- 완료된 voice Answer는 `ANSWER_ORGANIZATION` Job이 교수의 음성 답변을 별도 `answer_organizations`에 정리한다. 성공한 정리 결과는 재생성하지 않고 교수가 작성한 `answers.text_content`를 덮어쓰지 않는다.
- 수업 종료 후 모든 학생 질문과 `COMPLETED` Answer가 있는 AI 대표 질문을 대상으로 FINAL 클러스터를 확정한다. 성공 결과는 대상 각각을 정확히 한 Cluster에 포함하고 분류할 수 없는 입력도 `기타` Cluster에 포함한다.
- AIJob 재시도는 같은 행의 `attempt`를 증가시킨다.
- PDF·Transcript·학생 Question·AI 대표 질문·Answer 검색 단위는 공통 `knowledge_chunks` 테이블로 통합한다.
- Chat 근거는 `chat_message_evidence`가 `knowledge_chunks`를 참조한다.
- `/api/v1/sessions/{session_id}/record`는 대형 하위 배열을 포함하지 않는 manifest다. Session·처리 상태·리소스별 개수와 전용 조회 경로만 계산해 반환하고, Material·Transcript·Question·Answer·Cluster·공용 AIJob은 각 cursor API에서 조회한다.
- Transcript 한 page는 version과 `(start_ms, item kind, id)`를 고정한 하나의 cursor로 Segment·Gap을 함께 자른 뒤 공개 응답의 `segments[]`, `gaps[]`로 분리한다.
- Chat Evidence는 내부에 `knowledge_chunk_id`와 안전한 `label_snapshot`만 저장한다. 내부 typed source를 공개 `source_kind=MATERIAL|TRANSCRIPT|QUESTION|ANSWER`, `label`, `link`로 계산하고 내부 Chunk ID·storage key·cursor·배열 위치를 노출하지 않는다.
- Course의 `PROFESSOR`, `STUDENT`는 역할 구분 없이 개인 AI를 사용한다. `LIVE` Summary·Chat은 Session `LIVE`에서만, `REVIEW` Chat은 `COMPLETED`에서만 생성·사용한다.
- 개인 AI는 `202 + REQUESTER_ONLY AIJob` 뒤 polling과 저장된 최종 결과 조회만 사용한다. Chat `USER` Message는 Worker 실행 전에 영구 저장하지만 생성 중 Assistant delta는 저장·공유하지 않고, 성공한 최종 Summary 또는 Assistant Message·Evidence만 결과 원장에 저장한다.
- LIVE Session 종료 transaction은 모든 LIVE Summary·Chat·Message·Evidence와 관련 `REQUESTER_ONLY` Job을 삭제한다. FINAL Summary와 `REVIEW` Chat은 삭제하지 않는다. purge 뒤 기존 polling·단건 조회와 멱등 재요청에 어떤 응답을 반환할지는 미정이므로 멱등성 행의 조기 삭제나 stale 응답 재사용을 DB 계약으로 확정하지 않는다.
- 실제 질문·질문 작성 도움 초안·Chat `USER` Message는 앞뒤 공백 trim 뒤 Unicode NFC로 정규화하고 정규화된 값의 Unicode code point 길이를 각각 1~300, 1~500, 1~2,000자로 검증한다. 초과 입력을 자르지 않으며 Assistant Message에는 2,000자 상한을 적용하지 않는다.
- AIJob 결과는 각 결과 행의 `created_by_job_id`로 역참조한다.
- `source_type + source_id` 형태의 직접적인 다형 FK는 사용하지 않는다.
- partial Transcript는 영구 저장하지 않지만, 첫 `audio.start`가 만든 논리
  Recording과 종료 후 resumable upload로 확정한 강의 음성은 MVP 영구
  원장에 남긴다.
- 한 Session에는 논리 `session_recordings` 행을 최대 하나만 두고, 첫
  publisher의 `client_stream_id` HMAC claim과 Recording `CAPTURING` 전이를 같은
  transaction에서 확정한다.
- 다른 `client_stream_id`는 거부하고 같은 ID의 재연결·resume만 허용한다.
  수락 frame마다 45초 liveness를 갱신하지만 만료가 다른 ID의 takeover를 허용하지 않는다.
- Recording upload 완결 전에는 HQ STT 후속 처리를 시작하지 않는다. 완료
  transaction은 `RECORDING_TRANSCRIPTION` Job과 RECORDING TranscriptVersion을 만들고,
  검증된 결과만 canonical 전환한다.
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

| 구분                                           | 허용 값                                                          |
| ---------------------------------------------- | ---------------------------------------------------------------- |
| `course_members.role`                          | `PROFESSOR`, `STUDENT`                                           |
| `lecture_sessions.status`                      | `READY`, `LIVE`, `PROCESSING`, `COMPLETED`                       |
| `lecture_materials.processing_status`          | `UPLOADED`, `PROCESSING`, `READY`, `FAILED`                      |
| `session_recordings.status`                    | `CAPTURING`, `UPLOAD_PENDING`, `UPLOADING`, `UPLOADED`, `FAILED` |
| `recording_uploads.status`                     | `ACTIVE`, `COMPLETED`, `EXPIRED`, `FAILED`                       |
| `transcript_versions.source`                   | `LIVE`, `RECORDING`                                              |
| `transcript_versions.status`                   | `FINALIZING`, `FINALIZED`, `FAILED`, `EMPTY`                     |
| `questions.status`                             | `OPEN`, `SELECTED`, `ANSWERED`                                   |
| `ai_representative_questions.status`           | `OPEN`, `SELECTED`, `ANSWERED`                                   |
| `ai_representative_questions.lifecycle_status` | `ACTIVE`, `PRESERVED`, `DISCARDED`                               |
| `answers.status`                               | `CAPTURING`, `COMPLETED`                                         |
| `answer_transcript_mappings.status`            | `PENDING`, `SUCCEEDED`, `FAILED`                                 |
| `lecture_summaries.summary_type`               | `LIVE`, `FINAL`                                                  |
| `lecture_summaries.visibility`                 | `REQUESTER_ONLY`, `COURSE_MEMBERS`                               |
| `chat_sessions.mode`                           | `LIVE`, `REVIEW`                                                 |
| `chat_messages.role`                           | `USER`, `ASSISTANT`                                              |
| `ai_jobs.status`                               | `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`                      |
| `ai_jobs.visibility`                           | `SHARED`, `REQUESTER_ONLY`                                       |
| `ai_jobs.clustering_mode`                      | `LIVE_INCREMENTAL`, `FINAL`                                      |
| `realtime_tickets.scope`                       | `SESSION_EVENTS_READ`, `SESSION_AUDIO_WRITE`                     |
| `user_auth_identities.provider`                | `GOOGLE`                                                         |

AIJob 유형은 다음 값을 사용한다.

- `MATERIAL_PROCESSING`
- `QUESTION_CLUSTERING`
- `LIVE_SUMMARY`
- `FINAL_SUMMARY`
- `CHAT_RESPONSE`
- `SESSION_POSTPROCESSING`
- `RECORDING_TRANSCRIPTION`
- `ANSWER_ORGANIZATION`

## 4. 테이블 구성 요약

| 영역          | 테이블                                                                                                                                                                                                           |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 사용자·인증   | `users`, `user_auth_identities`, `user_password_credentials`, `auth_sessions`, `oauth_transactions`, `realtime_tickets`                                                                                          |
| Course·class  | `courses`, `course_members`, `lecture_sessions`                                                                                                                                                                  |
| 자료·기록     | `lecture_materials`, `session_recordings`, `recording_uploads`, `transcript_versions`, `transcript_segments`, `transcript_gaps`, `knowledge_chunks`                                                              |
| 질문·답변     | `question_clustering_states`, `ai_representative_questions`, `question_clusters`, `question_cluster_members`, `questions`, `question_reactions`, `answers`, `answer_transcript_mappings`, `answer_organizations` |
| AI 요약·채팅  | `lecture_summaries`, `chat_sessions`, `chat_messages`, `chat_message_evidence`                                                                                                                                   |
| 비동기·일관성 | `ai_jobs`, `idempotency_records`, `outbox_events`                                                                                                                                                                |

## 5. 사용자·인증

### 5.1 `users`

서비스 사용자 본체다. 전역 교수자·학생 역할을 저장하지 않는다.

| 컬럼            | 타입          | NULL | 기본값              | 키·제약 | 설명              |
| --------------- | ------------- | ---: | ------------------- | ------- | ----------------- |
| `id`            | `uuid`        |    N | `gen_random_uuid()` | PK      | 사용자 ID         |
| `display_name`  | `text`        |    N | -                   | -       | 표시 이름         |
| `primary_email` | `text`        |    Y | `NULL`              | partial UNIQUE | 현재 대표·이메일 로그인 식별자 |
| `avatar_url`    | `text`        |    Y | `NULL`              | -       | 프로필 이미지 URL |
| `deleted_at`    | `timestamptz` |    Y | `NULL`              | -       | 탈퇴·익명화 시각  |
| `created_at`    | `timestamptz` |    N | `now()`             | -       | 생성 시각         |
| `updated_at`    | `timestamptz` |    N | `now()`             | -       | 갱신 시각         |

인덱스:

- `INDEX users_active_idx (id) WHERE deleted_at IS NULL`
- 활성 User의 `primary_email`은 trim·NFKC·casefold로 정규화하고 `UNIQUE (primary_email) WHERE primary_email IS NOT NULL AND deleted_at IS NULL`로 보호한다. Google의 안정적인 identity 식별자는 계속 `user_auth_identities.provider_subject`다.
- 같은 이메일의 Google identity와 이메일·비밀번호 credential은 자동으로 연결하지 않는다. 먼저 만들어진 활성 User만 그 이메일을 소유하며, 연결은 별도 인증된 account-linking workflow가 확정될 때까지 제공하지 않는다.

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

### 5.3 `user_password_credentials`

이메일·비밀번호 로그인 User당 정확히 하나의 one-way password verifier다. 이메일은 이
테이블에 중복 저장하지 않고 `users.primary_email`을 유일한 로그인 식별자로 사용한다.

| 컬럼           | 타입          | NULL | 기본값  | 키·제약               | 설명 |
| -------------- | ------------- | ---: | ------- | --------------------- | ---- |
| `user_id`      | `uuid`        | N | - | PK, FK → `users.id` | credential 소유 User |
| `password_hash`| `text`        | N | - | - | versioned scrypt salt hash; 원문·복호화 키 없음 |
| `created_at`   | `timestamptz` | N | `now()` | - | 가입 또는 credential 생성 시각 |
| `updated_at`   | `timestamptz` | N | `now()` | trigger | 마지막 비밀번호 변경 시각 |

제약·보안 규칙:

- `user_id`는 PK이므로 User당 credential은 최대 하나다. `user_id ON DELETE CASCADE`다.
- `password_hash`는 `scrypt$v1$N$r$p$salt$derived-key` 형식이며, 16-byte random salt와
  32-byte derived key를 사용한다. 비밀번호 원문, salt 이외의 복구 정보와 비밀번호 reset token은 저장하지 않는다.
- 로그인 조회는 active User의 정규화 `primary_email`과 credential을 함께 읽는다. 미등록 이메일과
  password 불일치는 같은 `INVALID_CREDENTIALS` 외부 오류로 처리한다.
- 이메일 소유 확인, 비밀번호 reset, password 변경과 Google/email credential linking은 미구현이다.

### 5.4 `auth_sessions`

`goal_session` Cookie의 원문을 저장하지 않고 hash만 저장한다.

세션 만료는 Google callback 또는 이메일 가입·로그인 발급 시점부터 7일인 절대 만료다. 인증
요청은 `last_seen_at`을 최대 5분 간격으로 갱신하지만 `expires_at`을 연장하지 않는다. 같은
브라우저가 어느 로그인 방식을 다시 완료해도 기존 활성 token을 폐기하고 새 token hash를 발급해
session fixation을 막는다.

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

### 5.5 `oauth_transactions`

Google callback의 state·nonce·PKCE를 10분 동안 보관한다. PKCE verifier는 callback에서 필요하므로 암호화한다.

callback은 `browser_binding_hash`, `state_hash`, 만료와 `consumed_at IS NULL`을 한 transaction에서
잠금·검증하고 provider token 교환 전에 `consumed_at`을 commit한다. 따라서 동일 state나 임시
Cookie의 동시·반복 callback은 provider 호출 전에 하나만 성공한다. provider 장애가 발생해도
소비한 transaction을 되살리지 않고 사용자는 새 로그인 흐름을 시작한다.

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

| 컬럼                              | 타입          | NULL | 기본값              | 키·제약           | 설명                                  |
| --------------------------------- | ------------- | ---: | ------------------- | ----------------- | ------------------------------------- |
| `id`                              | `uuid`        |    N | `gen_random_uuid()` | PK                | class ID                              |
| `course_id`                       | `uuid`        |    N | -                   | FK → `courses.id` | 소속 Course                           |
| `created_by_user_id`              | `uuid`        |    N | -                   | FK → `users.id`   | 생성 교수자                           |
| `title`                           | `text`        |    N | -                   | CHECK             | class 제목                            |
| `lecture_date`                    | `date`        |    N | -                   | -                 | class 날짜                            |
| `status`                          | `text`        |    N | `'READY'`           | CHECK             | 상태                                  |
| `canonical_transcript_version_id` | `uuid`        |    Y | `NULL`              | 복합 FK           | 기본 조회에 선택된 Transcript version |
| `version`                         | `bigint`      |    N | `1`                 | CHECK `> 0`       | 실시간 리소스 버전                    |
| `started_at`                      | `timestamptz` |    Y | `NULL`              | -                 | 시작 시각                             |
| `ended_at`                        | `timestamptz` |    Y | `NULL`              | -                 | 종료 요청 시각                        |
| `completed_at`                    | `timestamptz` |    Y | `NULL`              | -                 | 후처리 완료 시각                      |
| `created_at`                      | `timestamptz` |    N | `now()`             | -                 | 생성 시각                             |
| `updated_at`                      | `timestamptz` |    N | `now()`             | -                 | 갱신 시각                             |

제약·인덱스:

- `UNIQUE (id, course_id)`; KnowledgeChunk의 범위 검증에 사용한다.
- `(canonical_transcript_version_id, id) FK → transcript_versions(id, session_id) ON DELETE SET NULL (canonical_transcript_version_id) DEFERRABLE INITIALLY DEFERRED`
- `UNIQUE INDEX lecture_sessions_one_active_per_course_uq (course_id) WHERE status IN ('READY', 'LIVE', 'PROCESSING')`
- `INDEX lecture_sessions_course_history_idx (course_id, lecture_date DESC, started_at DESC, id DESC)`
- `INDEX lecture_sessions_course_status_idx (course_id, status, updated_at DESC)`
- `CHECK (length(btrim(title)) > 0)`
- `CHECK ((status = 'READY' AND started_at IS NULL AND ended_at IS NULL AND completed_at IS NULL) OR (status = 'LIVE' AND started_at IS NOT NULL AND ended_at IS NULL AND completed_at IS NULL) OR (status = 'PROCESSING' AND started_at IS NOT NULL AND ended_at IS NOT NULL AND completed_at IS NULL) OR (status = 'COMPLETED' AND started_at IS NOT NULL AND ended_at IS NOT NULL AND completed_at IS NOT NULL))`
- `CHECK (ended_at IS NULL OR ended_at >= started_at)`
- `CHECK (completed_at IS NULL OR completed_at >= ended_at)`
- `course_id ON DELETE CASCADE`
- `created_by_user_id ON DELETE RESTRICT`; 탈퇴 시 User 행 자체를 익명화한다.

같은 날짜의 class는 순차적으로 여러 개 허용한다. 완료 기록은 `lecture_date DESC, started_at DESC, id DESC`로 정렬하고 실제 `started_at`을 표시해 구분한다. `READY`, `LIVE`, `PROCESSING` 합계는 partial UNIQUE 인덱스가 Course당 최대 한 행으로 제한한다. class 생성 경쟁에서 난 충돌은 `409 ACTIVE_SESSION_EXISTS`, 허용되지 않은 상태 전이는 `409 SESSION_STATE_CONFLICT`로 변환한다. 제목은 모든 상태에서 바꿀 수 있고 빈 입력은 `Course 제목 · YYYY.MM.DD HH:mm` 자동 제목으로 치환한 뒤 저장한다. 날짜는 `lecture_date`, 시각은 생성 시 저장한 `created_at`의 기본 timezone `Asia/Seoul` 표시값이며 상태 전이 뒤에도 고정한다. `lecture_date`는 생성 후 변경하지 않으며, `started_at`, `ended_at`, `completed_at`은 각 상태 전이에서 최초 설정된 뒤 바꾸지 않는다. 이 불변성은 상태 전이용 DB trigger가 기존 non-NULL 시각의 덮어쓰기를 거부해 이중 보장한다. `canonical_transcript_version_id`는 해당 Session의 현재 기본 Transcript를 가리키며 API의 `is_canonical`은 이 포인터로 계산한다. class 시작 때 LIVE version으로 설정하고 정상 RECORDING `FINALIZED` 또는 `EMPTY` 결과가 이를 교체한다. HQ 실패 또는 HQ 결과 없이 10분 deadline에 도달하면 LIVE 포인터를 보존하되, 이를 완료 기록의 final source로 인정할지는 미정이다.

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
| `last_received_sequence`          | `bigint`      |    N | `-1`                | CHECK `>= -1`| 영속 ACK 기준 마지막 PCM sequence    |
| `last_processed_sequence`         | `bigint`      |    N | `-1`                | CHECK        | STT로 넘긴 마지막 PCM sequence       |
| `last_captured_offset_ms`         | `bigint`      |    N | `0`                 | CHECK `>= 0` | 마지막 수락 frame의 capture offset   |
| `live_audio_lease_expires_at`     | `timestamptz` |    Y | `NULL`              | -            | 45초 liveness 관측 시각              |
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
- `UNIQUE (id, session_id)`; HQ STT typed target과 같은 Session 복합 FK의 대상이다.
- `CHECK (octet_length(publisher_client_stream_id_hash) = 32)`
- `CHECK (last_received_sequence >= -1)`
- `CHECK (last_processed_sequence BETWEEN -1 AND last_received_sequence)`
- `CHECK (last_captured_offset_ms >= 0)`
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
공개 상태로 표현한다. Session deadline 뒤에는 실패도 terminal로 간주해 다음
class를 막지 않지만, 실패 단계별 새 upload 재시작 정책과
`DEGRADED`·stop·replay 정책은 미정이다. HQ STT 상태는 이 Recording storage
lifecycle에 혼합하지 않고 TranscriptVersion과 AIJob으로 분리한다.

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
`UPLOADED`, 안전한 `recording.updated`, `RECORDING_TRANSCRIPTION` blocking Job,
해당 attempt의 `FINALIZING` TranscriptVersion과 queue outbox를 하나의 DB
transaction에 commit한다. object
publish 후 DB commit이 실패하면 내부 cleanup outbox 또는 동기 보상으로 orphan을
제거한다. 정확한 checksum·expiry·quota·orphan reconciliation 규칙은 미정이다.

### 7.4 `transcript_versions`

LIVE STT와 녹음 전체 재처리 결과를 섞지 않는 영구 Transcript 원장이다. 한
Session의 version 번호는 증가만 하고 재사용하지 않는다. `LIVE` version은 실시간
확정 발화를, `RECORDING` version은 업로드된 전체 녹음 기반 고품질 STT 결과를
담는다. `FINALIZED`는 전체 입력 재처리, Segment 저장, 문장 시간 정렬과 녹음 위치
매핑 검증이 모두 성공했다는 기술 상태이며 Transcript 문구가 100% 정확하다는
보장은 아니다.

| 컬럼                     | 타입          | NULL | 기본값              | 키·제약                    | 설명                                 |
| ------------------------ | ------------- | ---: | ------------------- | -------------------------- | ------------------------------------ |
| `id`                     | `uuid`        |    N | `gen_random_uuid()` | PK                         | Transcript version ID                |
| `session_id`             | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                           |
| `version`                | `bigint`      |    N | -                   | CHECK `> 0`                | Session 안에서 증가하는 version 번호 |
| `source`                 | `text`        |    N | -                   | CHECK                      | `LIVE`, `RECORDING`                  |
| `status`                 | `text`        |    N | `'FINALIZING'`      | CHECK                      | 영구 처리 상태                       |
| `recording_id`           | `uuid`        |    Y | `NULL`              | 복합 FK                    | `RECORDING` 입력 녹음                |
| `created_by_job_id`      | `uuid`        |    Y | `NULL`              | 복합 FK                    | HQ STT Job                           |
| `created_by_job_attempt` | `integer`     |    Y | `NULL`              | CHECK `> 0`                | 생성 attempt                         |
| `last_sequence`          | `bigint`      |    N | `0`                 | CHECK `>= 0`               | 이 version의 마지막 Segment 순번     |
| `finalized_at`           | `timestamptz` |    Y | `NULL`              | -                          | `FINALIZED`·`EMPTY` 확정 시각        |
| `failed_at`              | `timestamptz` |    Y | `NULL`              | -                          | `FAILED` 확정 시각                   |
| `created_at`             | `timestamptz` |    N | `now()`             | -                          | 생성 시각                            |
| `updated_at`             | `timestamptz` |    N | `now()`             | -                          | 상태 갱신 시각                       |

제약·인덱스:

- `UNIQUE (session_id, version)`; version 번호는 Session 안에서 재사용하지 않는다.
- `UNIQUE (id, session_id)`; Session canonical 포인터와 하위 복합 FK 대상이다.
- `UNIQUE INDEX transcript_versions_created_by_job_attempt_uq (created_by_job_id, created_by_job_attempt) WHERE created_by_job_id IS NOT NULL`; 같은 Job attempt는 결과 version 하나만 만든다.
- `UNIQUE INDEX transcript_versions_one_finalizing_per_source_uq (session_id, source) WHERE status = 'FINALIZING'`; Session·source별 조립 중 version은 최대 하나다. 종료 직후 LIVE drain과 upload 완료 뒤 RECORDING staging은 서로 다른 version에서 잠시 겹칠 수 있다.
- `CHECK (source IN ('LIVE', 'RECORDING'))`
- `CHECK (status IN ('FINALIZING', 'FINALIZED', 'FAILED', 'EMPTY'))`
- `CHECK ((created_by_job_id IS NULL) = (created_by_job_attempt IS NULL))`
- `CHECK ((source = 'LIVE' AND recording_id IS NULL AND created_by_job_id IS NULL) OR (source = 'RECORDING' AND recording_id IS NOT NULL AND created_by_job_id IS NOT NULL))`
- `CHECK ((status = 'FINALIZING' AND finalized_at IS NULL AND failed_at IS NULL) OR (status IN ('FINALIZED', 'EMPTY') AND finalized_at IS NOT NULL AND failed_at IS NULL) OR (status = 'FAILED' AND finalized_at IS NULL AND failed_at IS NOT NULL))`
- `CHECK (status NOT IN ('EMPTY', 'FAILED') OR last_sequence = 0)`
- `INDEX transcript_versions_session_idx (session_id, version DESC, id DESC)`
- `INDEX transcript_versions_status_idx (status, updated_at, id)`
- `session_id ON DELETE CASCADE`
- `(recording_id, session_id) FK → session_recordings(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

Session row와 현재 최대 version row를 잠근 뒤 새 version 번호를 할당한다. LIVE
version은 class 시작 후 실시간 final Segment의 원장이며 종료 drain이 끝나면
Segment가 있으면 `FINALIZED`, 없으면 `EMPTY`가 된다. Recording upload complete
transaction은 같은 Recording을 target으로 하는 `RECORDING_TRANSCRIPTION` Job과
`FINALIZING` version을 만든다. 같은 Job 재시도는 Job 행의 `attempt + 1`을 사용하되
실패한 version을 덮어쓰지 않고 attempt마다 새 version을 만든다.

HQ worker는 비canonical version 아래 Segment·Gap을 준비하고 현재 Job
ID·attempt·run token, version `FINALIZING`과 Session 상태를 다시 검증한다. 전체
녹음 재처리, Segment 저장과 class·recording 시간축 정렬 검증이 모두 성공한 짧은
transaction에서만 `FINALIZED` 또는 `EMPTY`와 Session canonical 포인터를 함께
전환한다. 정상 처리 결과가 0 Segment이면 `EMPTY`로 확정한다. Answer mapping과 canonical
KnowledgeChunk 재연결은 이 전환 뒤 `SESSION_POSTPROCESSING`이 수행한다.
실패·timeout terminal transaction은 Session·Job·version을 잠그고 해당 attempt가
비canonical version 아래 staging한 Segment·Gap을 모두 삭제하거나 같은 transaction의
미commit 결과로 폐기한다. 그 뒤 `last_sequence = 0`, version `FAILED`, Job `FAILED`와
안전한 invalidation·coordinator wakeup outbox를 함께 commit한다. deferred constraint
trigger는 `FINALIZED`의 Segment가 1개 이상, `EMPTY`의 Segment가 0개, `FAILED`의
Segment·Gap이 모두 0개인지 검사한다. timeout된 이전 worker는 Job fence와 version status를
통과할 수 없어 canonical 포인터를 바꾸지 못한다. HQ 실패 또는 HQ 결과 없이 10분
timeout에 도달했을 때 보존된 LIVE 포인터를 완료 기록의 final source로 인정할지는 미정이다.

### 7.5 `transcript_segments`

version 안에서 확정된 Transcript 문장을 저장한다. partial STT는 저장하지 않는다.

| 컬럼                     | 타입          | NULL | 기본값              | 키·제약                    | 설명                           |
| ------------------------ | ------------- | ---: | ------------------- | -------------------------- | ------------------------------ |
| `id`                     | `uuid`        |    N | `gen_random_uuid()` | PK                         | Segment ID                     |
| `session_id`             | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                     |
| `transcript_version_id`  | `uuid`        |    N | -                   | 복합 FK                    | 소속 Transcript version        |
| `sequence`               | `bigint`      |    N | -                   | CHECK `> 0`                | version 내 확정 순번           |
| `utterance_id`           | `text`        |    Y | `NULL`              | -                          | LIVE partial/final 치환용 ID   |
| `start_ms`               | `bigint`      |    N | -                   | CHECK `>= 0`               | class 시작 기준 시각           |
| `end_ms`                 | `bigint`      |    N | -                   | CHECK                      | 종료 시각                      |
| `recording_start_ms`     | `bigint`      |    Y | `NULL`              | CHECK `>= 0`               | 녹음 재생 기준 시작 위치       |
| `recording_end_ms`       | `bigint`      |    Y | `NULL`              | CHECK                      | 녹음 재생 기준 종료 위치       |
| `text`                   | `text`        |    N | -                   | CHECK                      | 확정 텍스트                    |
| `created_by_job_id`      | `uuid`        |    Y | `NULL`              | 복합 FK                    | Job 결과인 경우 원인 Job       |
| `created_by_job_attempt` | `integer`     |    Y | `NULL`              | CHECK `> 0`                | 생성 당시 Job attempt snapshot |
| `created_at`             | `timestamptz` |    N | `now()`             | -                          | 저장 시각                      |

제약·인덱스:

- `UNIQUE (transcript_version_id, sequence)`
- `UNIQUE INDEX transcript_segments_version_utterance_uq (transcript_version_id, utterance_id) WHERE utterance_id IS NOT NULL`
- `UNIQUE (id, transcript_version_id, session_id)`; Answer·Summary·KnowledgeChunk의 version·Session FK에 사용한다.
- `CHECK (end_ms >= start_ms)`
- `CHECK (utterance_id IS NULL OR length(btrim(utterance_id)) > 0)`
- `CHECK ((recording_start_ms IS NULL) = (recording_end_ms IS NULL))`
- `CHECK (recording_end_ms IS NULL OR recording_end_ms >= recording_start_ms)`
- `CHECK (length(btrim(text)) > 0)`
- `CHECK ((created_by_job_id IS NULL) = (created_by_job_attempt IS NULL))`
- `INDEX transcript_segments_time_idx (transcript_version_id, start_ms, id)`
- `(transcript_version_id, session_id) FK → transcript_versions(id, session_id) ON DELETE CASCADE`
- `session_id ON DELETE CASCADE`
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

LIVE version은 `utterance_id`가 필수이고 HQ `RECORDING` version은 녹음 기반 문장이라
`recording_start_ms`, `recording_end_ms`가 필수다. 이 source별 조건과 Segment의
producer Job·attempt가 부모 version과 일치하는지는 deferred constraint trigger가
검증한다. `start_ms`·`end_ms`는 class 시간축, `recording_*_ms`는 playback seek
시간축이며 HTTP byte Range와 혼용하지 않는다. 각 version row를 잠그고
`last_sequence + 1`을 할당하므로 LIVE와 HQ sequence는 서로 독립적이다.

### 7.6 `transcript_gaps`

Transcript를 만들 수 없는 시간 구간을 version별로 표시한다. LIVE gap은 실시간
연결 문제로 생긴 복구 가능한 관찰값이고, HQ에도 남은 gap만 final gap이다.

| 컬럼                    | 타입          | NULL | 기본값              | 키·제약                    | 설명                                                                            |
| ----------------------- | ------------- | ---: | ------------------- | -------------------------- | ------------------------------------------------------------------------------- |
| `id`                    | `uuid`        |    N | `gen_random_uuid()` | PK                         | Gap ID                                                                          |
| `session_id`            | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                                                                      |
| `transcript_version_id` | `uuid`        |    N | -                   | 복합 FK                    | 소속 Transcript version                                                         |
| `start_ms`              | `bigint`      |    N | -                   | CHECK `>= 0`               | 추정 누락 시작                                                                  |
| `end_ms`                | `bigint`      |    Y | `NULL`              | CHECK                      | 추정 누락 종료                                                                  |
| `is_final`              | `boolean`     |    N | `false`             | -                          | canonical 후보에 남은 최종 gap 여부                                             |
| `reason`                | `text`        |    N | -                   | CHECK                      | `SERVER_STATE_LOST`, `SEQUENCE_GAP`, `CLIENT_DISCONNECTED`, `BACKPRESSURE_DROP` |
| `details`               | `jsonb`       |    N | `'{}'::jsonb`       | -                          | 민감정보 없는 진단 정보                                                         |
| `created_at`            | `timestamptz` |    N | `now()`             | -                          | 감지 시각                                                                       |

제약·인덱스:

- `CHECK (end_ms IS NULL OR end_ms >= start_ms)`
- `CHECK (NOT is_final OR end_ms IS NOT NULL)`
- `UNIQUE (id, transcript_version_id, session_id)`
- `INDEX transcript_gaps_version_time_idx (transcript_version_id, start_ms, id)`
- `(transcript_version_id, session_id) FK → transcript_versions(id, session_id) ON DELETE CASCADE`
- `session_id ON DELETE CASCADE`

LIVE version의 gap은 `is_final=false`, `RECORDING` version에서 재처리 후에도 복구하지
못한 gap은 `is_final=true`인지 constraint trigger로 검증한다. 복구된 live gap은
LIVE version provenance에 남을 수 있지만 HQ version에는 복사하지 않는다. Segment가
0개이고 gap만 있는 version도 시간순 조회할 수 있으므로 gap을 Segment sequence에
종속시키지 않는다.

Transcript REST page는 Segment와 Gap에 독립 cursor를 발급하지 않는다. 먼저 선택한
`transcript_version_id`에 고정한 두 index range를 `UNION ALL`하고
`(start_ms ASC, item_kind ASC, id ASC)` keyset으로 `limit`개를 선택한다.
`item_kind`는 `SEGMENT`가 `GAP`보다 먼저 오도록 고정한다. API는 같은 page의 행을
`segments[]`와 `gaps[]`로만 분리하므로 두 배열 길이의 합은 `limit` 이하다. cursor는
version ID와 마지막 정렬 tuple을 포함하는 불투명 값이며 canonical 포인터가 뒤에서
바뀌어도 최초 선택 version을 유지한다. `transcript_segments_time_idx`와
`transcript_gaps_version_time_idx`가 두 range를 각각 지원한다.

## 8. 질문·클러스터·답변

### 8.1 `question_clustering_states`

Session별 클러스터링 요청 watermark, 적용 watermark와 최신 결과 fence를 저장하는 1:1 원장이다. 질문 생성과 결과 commit은 이 행을 잠가 순서를 직렬화한다.

| 컬럼                 | 타입          | NULL | 기본값  | 키·제약                        | 설명                                              |
| -------------------- | ------------- | ---: | ------- | ------------------------------ | ------------------------------------------------- |
| `session_id`         | `uuid`        |    N | -       | PK, FK → `lecture_sessions.id` | 소속 class                                        |
| `requested_sequence` | `bigint`      |    N | `0`     | CHECK `>= 0`                   | 등록되어 클러스터링이 필요한 마지막 질문 sequence |
| `applied_sequence`   | `bigint`      |    N | `0`     | CHECK `>= 0`                   | 현재 결과에 적용된 마지막 질문 sequence           |
| `current_revision`   | `bigint`      |    N | `0`     | CHECK `>= 0`                   | 결과 commit마다 증가하는 late-result fence        |
| `current_generation` | `bigint`      |    Y | `NULL`  | CHECK `> 0`                    | 현재 노출하는 generation                          |
| `final_generation`   | `bigint`      |    Y | `NULL`  | CHECK `> 0`                    | PROCESSING에서 확정한 FINAL generation            |
| `last_job_id`        | `uuid`        |    Y | `NULL`  | 복합 FK                        | 마지막으로 생성·종료한 클러스터링 Job             |
| `last_job_attempt`   | `integer`     |    Y | `NULL`  | CHECK `> 0`                    | 마지막 Job attempt snapshot                       |
| `last_job_status`    | `text`        |    Y | `NULL`  | CHECK                          | `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`       |
| `retry_job_id`       | `uuid`        |    Y | `NULL`  | 복합 FK                        | retry 예약된 실패 LIVE 클러스터링 Job             |
| `created_at`         | `timestamptz` |    N | `now()` | -                              | 생성 시각                                         |
| `updated_at`         | `timestamptz` |    N | `now()` | -                              | 갱신 시각                                         |

제약·인덱스:

- `CHECK (applied_sequence <= requested_sequence)`
- `CHECK ((last_job_id IS NULL) = (last_job_attempt IS NULL))`
- `CHECK ((last_job_id IS NULL) = (last_job_status IS NULL))`
- `CHECK (last_job_status IS NULL OR last_job_status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'SUPERSEDED'))`
- `CHECK (final_generation IS NULL OR final_generation = current_generation)`
- `(last_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `UNIQUE (retry_job_id)`
- `(retry_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `session_id ON DELETE CASCADE`

`last_job_attempt`와 `last_job_status`는 변경되는 Job 행의 현재값을 FK로 묶지 않고 마지막 상태 전이 때 snapshot한다. 서비스와 deferred trigger는 `last_job_id`가 같은 Session의 `QUESTION_CLUSTERING`인지 검증한다. `retry_job_id`는 같은 Session의 `LIVE_INCREMENTAL`, `FAILED`, `retryable=true` Job만 가리킬 수 있고 그 Job의 `input_through_sequence`와 `base_revision`은 예약 중 바꾸지 않는다. retry 예약이 있을 때 같은 Session에 active clustering Job이 없는지도 deferred trigger가 검증한다. 질문 insert는 state 행을 잠근 뒤 `requested_sequence + 1`을 Question에 부여하고 `requested_sequence`를 같은 값으로 올린다. 결과 commit은 Job의 `base_revision = current_revision`일 때만 허용하고 성공 시 `current_revision + 1`로 갱신한다.

`requested_sequence`, `applied_sequence`, revision·generation, last/retry Job snapshot 중 하나라도 공개 값이 바뀌는 transaction은 `clustering.updated` outbox를 반드시 함께 기록한다. 여기에는 질문 commit, failure의 `retry_job_id` 예약, scheduler requeue와 예약 해제, 성공·다음 Job 생성, PRESERVED 대표 질문 취소, Session 종료 fence가 모두 포함된다.

### 8.2 `ai_representative_questions`

AI가 생성한 대표 질문을 Cluster title과 분리된 독립 리소스로 저장한다. Answer target이 된 대표 질문은 클러스터가 바뀌어도 안정적인 ID와 text를 유지한다.

| 컬럼                     | 타입          | NULL | 기본값              | 키·제약                    | 설명                              |
| ------------------------ | ------------- | ---: | ------------------- | -------------------------- | --------------------------------- |
| `id`                     | `uuid`        |    N | `gen_random_uuid()` | PK                         | AI 대표 질문 ID                   |
| `session_id`             | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                        |
| `text`                   | `text`        |    N | -                   | CHECK                      | AI가 생성한 대표 질문 exact text  |
| `status`                 | `text`        |    N | `'OPEN'`            | CHECK                      | Answer 상태                       |
| `lifecycle_status`       | `text`        |    N | `'ACTIVE'`          | CHECK                      | 중앙·보존·내부 폐기 lifecycle     |
| `version`                | `bigint`      |    N | `1`                 | CHECK `> 0`                | 상태 변경용 공개 리소스 버전      |
| `created_by_job_id`      | `uuid`        |    N | -                   | 복합 FK                    | 생성한 클러스터링 Job             |
| `created_by_job_attempt` | `integer`     |    N | -                   | CHECK `> 0`                | 생성 당시 attempt                 |
| `created_in_generation`  | `bigint`      |    N | -                   | CHECK `> 0`                | 생성 당시 Cluster generation      |
| `preserved_at`           | `timestamptz` |    Y | `NULL`              | CHECK                      | Answer 때문에 child로 보존한 시각 |
| `discarded_at`           | `timestamptz` |    Y | `NULL`              | CHECK                      | 공개·RAG에서 폐기한 시각          |
| `created_at`             | `timestamptz` |    N | `now()`             | -                          | 생성 시각                         |

제약·인덱스:

- `UNIQUE (id, session_id)`
- `CHECK (char_length(btrim(text)) BETWEEN 1 AND 300)`
- `CHECK (status IN ('OPEN', 'SELECTED', 'ANSWERED'))`
- `CHECK (lifecycle_status IN ('ACTIVE', 'PRESERVED', 'DISCARDED'))`
- `CHECK (version > 0)`
- `CHECK (created_in_generation > 0)`
- `CHECK ((lifecycle_status = 'ACTIVE' AND preserved_at IS NULL AND discarded_at IS NULL) OR (lifecycle_status = 'PRESERVED' AND preserved_at IS NOT NULL AND discarded_at IS NULL) OR (lifecycle_status = 'DISCARDED' AND discarded_at IS NOT NULL AND status = 'OPEN'))`
- `INDEX ai_representative_questions_session_idx (session_id, lifecycle_status, status, created_at, id)`
- `INDEX ai_representative_questions_discarded_cleanup_idx (discarded_at, id) WHERE lifecycle_status = 'DISCARDED'`
- `INDEX ai_representative_questions_job_idx (created_by_job_id, created_by_job_attempt)`
- `session_id ON DELETE CASCADE`
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- deferrable constraint trigger는 `lifecycle_status=ACTIVE`가 current generation의 중앙 대표 질문으로 정확히 한 번 쓰이고, `lifecycle_status=PRESERVED`가 Answer target이면서 current generation의 child로 정확히 한 번 쓰이는지 검증한다. `DISCARDED`는 Answer target·Cluster 중앙·membership이 모두 0건이고 `status=OPEN`이며, 그 대표 질문 source KnowledgeChunk 중 하나 이상을 참조하는 Evidence가 최소 1건인지 검증한다. 마지막 Evidence를 삭제하는 transaction은 commit 전에 tombstone 대표 질문을 함께 hard delete해야 하므로 Evidence 없는 orphan `DISCARDED` 행은 남을 수 없다.
- deferrable constraint trigger는 `status=OPEN`이면 Answer가 없고, `SELECTED`이면 `CAPTURING`, `ANSWERED`이면 `COMPLETED` Answer가 정확히 하나인지 검증한다.

`text`, `created_by_job_id`, `created_by_job_attempt`, `created_in_generation`, `created_at`은 생성 뒤 immutable이다. `created_in_generation`은 이 리소스를 처음 만든 완결된 Cluster generation이며 이후 `PRESERVED` child로 이동해도 바뀌지 않는다. `lifecycle_status`는 대표 질문 교체에서 `ACTIVE → PRESERVED` 또는 `ACTIVE → DISCARDED`, 보존 Answer 취소에서 `PRESERVED → DISCARDED`로만 전이하며 되돌리지 않는다. `PRESERVED`는 현재 대표가 아니라 Answer target 보존을 위해 일반 질문과 같은 child 노드로 남았다는 뜻이다. `DISCARDED`는 Evidence provenance 때문에만 유지하는 내부 tombstone이며 공개 대표질문 조회·Cluster·RAG에서 제외한다. `preserved_at`은 `PRESERVED → DISCARDED` 뒤에도 과거 보존 시각으로 유지할 수 있다. Answer transaction은 `status`를 `OPEN → SELECTED → ANSWERED`, 취소는 `SELECTED → OPEN`, 수업 후 학생 질문 text-only 생성은 `OPEN → ANSWERED`로 전이한다. `status` 또는 `lifecycle_status`가 바뀌는 transaction은 `version + 1`도 함께 적용해 REST와 WebSocket의 stale event를 구분한다.

### 8.3 `question_clusters`

Session의 현재 또는 FINAL 클러스터를 저장한다. 대표 질문 text를 중복 저장하지 않고 독립 대표 질문 FK를 사용한다.

| 컬럼                         | 타입          | NULL | 기본값              | 키·제약                    | 설명                             |
| ---------------------------- | ------------- | ---: | ------------------- | -------------------------- | -------------------------------- |
| `id`                         | `uuid`        |    N | `gen_random_uuid()` | PK                         | generation별 물리 Cluster row ID |
| `logical_cluster_id`         | `uuid`        |    N | -                   | -                          | 공개·semantic Cluster ID         |
| `session_id`                 | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                       |
| `representative_question_id` | `uuid`        |    N | -                   | 복합 FK                    | 중앙 AI 대표 질문                |
| `generation`                 | `bigint`      |    N | -                   | CHECK `> 0`                | 같은 클러스터링 결과 세트 식별자 |
| `ordinal`                    | `integer`     |    N | -                   | CHECK `>= 0`               | 같은 generation 안의 안정적 순서 |
| `is_final`                   | `boolean`     |    N | `false`             | -                          | 종료 후 확정 여부                |
| `finalized_at`               | `timestamptz` |    Y | `NULL`              | CHECK                      | 최종 확정 시각                   |
| `created_by_job_id`          | `uuid`        |    N | -                   | 복합 FK                    | 생성한 클러스터링 Job            |
| `created_by_job_attempt`     | `integer`     |    N | -                   | CHECK `> 0`                | 생성 당시 attempt                |
| `created_at`                 | `timestamptz` |    N | `now()`             | -                          | 생성 시각                        |

제약·인덱스:

- `UNIQUE (id, session_id)`
- `UNIQUE (session_id, generation, logical_cluster_id)`
- `(representative_question_id, session_id) FK → ai_representative_questions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `CHECK ((is_final AND finalized_at IS NOT NULL) OR (NOT is_final AND finalized_at IS NULL))`
- `UNIQUE (session_id, generation, ordinal)`
- `UNIQUE (session_id, generation, representative_question_id)`
- `UNIQUE (created_by_job_id, created_by_job_attempt, ordinal)`
- deferrable constraint trigger는 한 `(created_by_job_id, created_by_job_attempt)` 결과의 모든 행이 같은 `session_id`, `generation`, `is_final`을 사용하고, 한 `(session_id, generation)`이 하나의 Job attempt에만 귀속되는지 검증한다.
- deferrable constraint trigger는 중앙 `representative_question_id`의 `lifecycle_status = 'ACTIVE'`인지 검증한다.
- Job을 `SUCCEEDED`로 전이하는 deferred trigger는 새 generation의 Cluster·membership이 해당 mode의 정확한 입력 집합과 일치하고 LIVE 계승 Cluster의 `logical_cluster_id`가 유지되는지 검증한다. 한 행이라도 누락·초과·중복·오배치되면 Job 성공과 `applied_sequence` 전진을 거부한다.
- `INDEX question_clusters_session_idx (session_id, is_final DESC, generation DESC, ordinal, logical_cluster_id)`
- `INDEX question_clusters_job_idx (created_by_job_id, created_by_job_attempt)`
- `session_id ON DELETE CASCADE`
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

같은 Session의 `generation`은 state 행을 잠근 상태에서 `coalesce(current_generation, 0) + 1`로 할당하고 재사용하지 않는다. `id`는 staging·membership FK에만 쓰는 generation별 물리 식별자다. LIVE 새 generation은 기존 semantic Cluster를 복사하거나 대표 질문을 교체해도 `logical_cluster_id`를 계승하고, 새로 생긴 Cluster에만 새 UUID를 할당한다. FINAL full rebuild는 과거 LIVE identity를 계승하지 않고 모든 결과 Cluster에 새 logical ID를 할당한다. commit한 결과만 state의 `current_generation`에 연결한다. 일반 변경 이력은 보관하지 않으므로 새 generation과 membership을 완성하고 state를 교체한 뒤 이전 generation을 삭제한다. FINAL 결과는 `current_generation = final_generation`으로 남긴다.

API `QuestionCluster.id`와 Cluster child URL의 `cluster_id`는 `logical_cluster_id`를 사용한다. 현재 generation의 Question 응답 `cluster_id`도 해당 Question membership의 부모 `logical_cluster_id`에서 계산한다. 물리 `question_clusters.id`는 API·event에 노출하지 않는다.

### 8.4 `question_cluster_members`

Cluster child 노드를 학생 질문 또는 과거 AI 대표 질문 중 정확히 한 종류로 저장한다. 중앙 대표 질문은 `question_clusters.representative_question_id`이므로 자신의 membership에 다시 넣지 않는다.

| 컬럼                         | 타입          | NULL | 기본값  | 키·제약          | 설명                        |
| ---------------------------- | ------------- | ---: | ------- | ---------------- | --------------------------- |
| `cluster_id`                 | `uuid`        |    N | -       | PK, 복합 FK      | 소속 Cluster                |
| `session_id`                 | `uuid`        |    N | -       | 복합 FK          | 동일 Session 검증           |
| `generation`                 | `bigint`      |    N | -       | CHECK `> 0`      | 동일 generation 검증        |
| `position`                   | `integer`     |    N | -       | PK, CHECK `>= 0` | child 표시 순서             |
| `question_id`                | `uuid`        |    Y | `NULL`  | 복합 FK          | 학생 질문 child             |
| `representative_question_id` | `uuid`        |    Y | `NULL`  | 복합 FK          | 보존된 과거 대표 질문 child |
| `created_at`                 | `timestamptz` |    N | `now()` | -                | membership 생성 시각        |

제약·인덱스:

- PK `(cluster_id, position)`
- `CHECK (num_nonnulls(question_id, representative_question_id) = 1)`
- `(cluster_id, session_id) FK → question_clusters(id, session_id) ON DELETE CASCADE`
- `(question_id, session_id) FK → questions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(representative_question_id, session_id) FK → ai_representative_questions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `UNIQUE INDEX question_cluster_members_question_uq (session_id, generation, question_id) WHERE question_id IS NOT NULL`
- `UNIQUE INDEX question_cluster_members_representative_uq (session_id, generation, representative_question_id) WHERE representative_question_id IS NOT NULL`
- deferrable constraint trigger는 membership의 `generation`이 부모 Cluster와 같고, child 대표 질문이 부모의 중앙 대표 질문과 다르며 `lifecycle_status = 'PRESERVED'`인지 검증한다.
- `INDEX question_cluster_members_cluster_idx (cluster_id, position)`

API child `ordinal`은 DB `position`을 그대로 projection한다.

### 8.5 `questions`

익명으로 공개되는 학생 질문과 내부 작성자, Session별 클러스터링 입력 순서를 저장한다. AI 도움을 받기 위해 입력한 질문 초안은 이 테이블을 포함한 DB에 저장하지 않고 200 응답이 끝나면 폐기한다.

서비스는 학생 질문과 작성 도움 초안을 `trim → Unicode NFC` 순서로 정규화한 뒤 Unicode code point를 센다. 질문은 1~300자, 초안은 1~500자이며 위반은 저장·절단 없이 `422 VALIDATION_ERROR`로 거부한다. `questions.content`에는 trim·NFC가 끝난 값만 저장한다.

| 컬럼                  | 타입          | NULL | 기본값              | 키·제약                    | 설명                |
| --------------------- | ------------- | ---: | ------------------- | -------------------------- | ------------------- |
| `id`                  | `uuid`        |    N | `gen_random_uuid()` | PK                         | Question ID         |
| `session_id`          | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class          |
| `author_user_id`      | `uuid`        |    N | -                   | FK → `users.id`            | 외부 비공개 작성자  |
| `clustering_sequence` | `bigint`      |    N | -                   | CHECK `> 0`                | Session별 등록 순서 |
| `content`             | `text`        |    N | -                   | CHECK                      | 질문 내용           |
| `status`              | `text`        |    N | `'OPEN'`            | CHECK                      | 상태                |
| `reaction_count`      | `integer`     |    N | `0`                 | CHECK `>= 0`               | 반응 집계 cache     |
| `version`             | `bigint`      |    N | `1`                 | CHECK `> 0`                | 실시간 리소스 버전  |
| `created_at`          | `timestamptz` |    N | `now()`             | -                          | 생성 시각           |
| `updated_at`          | `timestamptz` |    N | `now()`             | -                          | 갱신 시각           |

제약·인덱스:

- `UNIQUE (id, session_id)`
- `UNIQUE (session_id, clustering_sequence)`
- `CHECK (content = btrim(content) AND content IS NFC NORMALIZED AND char_length(content) BETWEEN 1 AND 300)`; 서비스 우회 insert도 NFD 값을 저장하지 못하도록 trim·NFC·code point 길이를 DB가 함께 방어한다. `IS NFC NORMALIZED`는 UTF-8 PostgreSQL의 Unicode 정규화 판정식을 사용한다.
- `INDEX questions_session_recent_idx (session_id, created_at DESC, id DESC)`
- `INDEX questions_session_popular_idx (session_id, reaction_count DESC, created_at DESC, id DESC)`
- `INDEX questions_recent_idx (session_id, status, created_at DESC, id DESC)`
- `INDEX questions_popular_idx (session_id, status, reaction_count DESC, created_at DESC, id DESC)`
- `INDEX questions_clustering_input_idx (session_id, clustering_sequence, id)`
- `session_id ON DELETE CASCADE`
- `author_user_id ON DELETE RESTRICT`; 탈퇴 사용자는 익명화한다.
- deferrable constraint trigger는 `status=OPEN`이면 direct Answer가 없고, `SELECTED`이면 `CAPTURING`, `ANSWERED`이면 `COMPLETED` Answer가 정확히 하나인지 검증한다.

`reaction_count`는 인기순 저지연 조회를 위해 저장한다. 반응 행 변경과 같은 트랜잭션에서 원자적으로 증감하고, 운영 점검에서 실제 `COUNT(*)`와 불일치를 복구한다.

질문 생성 transaction은 `question_clustering_states`를 잠가 `clustering_sequence`와 `requested_sequence`를 함께 증가시킨다. 같은 transaction에서 active 클러스터링 Job과 `retry_job_id`가 모두 없을 때만 새 `LIVE_INCREMENTAL` Job과 queue outbox를 만든다. active Job 또는 retry 예약 Job이 있으면 watermark만 갱신하고 기존 Job의 captured input은 바꾸지 않는다. 어느 경우든 공개 state invalidation인 `clustering.updated` outbox를 같은 transaction에 기록한다.

### 8.6 `question_reactions`

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

### 8.7 `answers`

교수자의 Answer를 학생 질문 또는 AI 대표 질문 중 정확히 하나에 연결한다. LIVE 중에는 음성 Transcript 범위를 캡처하고, 수업 후에는 text-only Answer를 만들거나 기존 완료 Answer에 text를 보충할 수 있다.

| 컬럼                                | 타입          | NULL | 기본값              | 키·제약                    | 설명                                  |
| ----------------------------------- | ------------- | ---: | ------------------- | -------------------------- | ------------------------------------- |
| `id`                                | `uuid`        |    N | `gen_random_uuid()` | PK                         | Answer ID                             |
| `session_id`                        | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class                            |
| `professor_user_id`                 | `uuid`        |    Y | `NULL`              | FK → `users.id`            | 답변 교수자                           |
| `target_question_id`                | `uuid`        |    Y | `NULL`              | 복합 FK                    | 학생 질문 target                      |
| `target_representative_question_id` | `uuid`        |    Y | `NULL`              | 복합 FK                    | AI 대표 질문 target                   |
| `target_text_snapshot`              | `text`        |    N | -                   | CHECK                      | 답변 선택 당시 target exact text      |
| `status`                            | `text`        |    N | `'CAPTURING'`       | CHECK                      | `CAPTURING`, `COMPLETED`              |
| `source_transcript_version_id`      | `uuid`        |    Y | `NULL`              | 복합 FK                    | 음성 답변 캡처 원본 LIVE version      |
| `capture_started_after_sequence`    | `bigint`      |    Y | `NULL`              | CHECK `>= 0`               | 선택 시점 마지막 final sequence       |
| `start_segment_id`                  | `uuid`        |    Y | `NULL`              | 복합 FK                    | 확정 음성 범위 첫 Segment             |
| `end_segment_id`                    | `uuid`        |    Y | `NULL`              | 복합 FK                    | 확정 음성 범위 마지막 Segment         |
| `text_content`                      | `text`        |    Y | `NULL`              | CHECK                      | 수업 후 text 답변 또는 음성 답변 보충 |
| `version`                           | `bigint`      |    N | `1`                 | CHECK `> 0`                | 실시간 리소스 버전                    |
| `started_at`                        | `timestamptz` |    N | `now()`             | -                          | 답변 시작·작성 시각                   |
| `completed_at`                      | `timestamptz` |    Y | `NULL`              | -                          | 완료 시각                             |
| `created_at`                        | `timestamptz` |    N | `now()`             | -                          | 생성 시각                             |
| `updated_at`                        | `timestamptz` |    N | `now()`             | -                          | 갱신 시각                             |

제약·인덱스:

- `UNIQUE (id, session_id)`
- `CHECK (num_nonnulls(target_question_id, target_representative_question_id) = 1)`
- `(target_question_id, session_id) FK → questions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(target_representative_question_id, session_id) FK → ai_representative_questions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `UNIQUE INDEX answers_one_per_question_uq (target_question_id) WHERE target_question_id IS NOT NULL`
- `UNIQUE INDEX answers_one_per_representative_question_uq (target_representative_question_id) WHERE target_representative_question_id IS NOT NULL`
- `UNIQUE INDEX answers_one_capturing_per_session_uq (session_id) WHERE status = 'CAPTURING'`
- `(source_transcript_version_id, session_id) FK → transcript_versions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(start_segment_id, source_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(end_segment_id, source_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `CHECK (status IN ('CAPTURING', 'COMPLETED'))`
- `CHECK (char_length(btrim(target_text_snapshot)) BETWEEN 1 AND 300)`
- `CHECK (text_content IS NULL OR char_length(btrim(text_content)) > 0)`; 정확한 최대 길이는 미정이다.
- `CHECK ((start_segment_id IS NULL) = (end_segment_id IS NULL))`
- `CHECK ((source_transcript_version_id IS NULL) = (capture_started_after_sequence IS NULL))`
- `CHECK ((status = 'CAPTURING' AND source_transcript_version_id IS NOT NULL AND capture_started_after_sequence IS NOT NULL AND start_segment_id IS NULL AND text_content IS NULL AND completed_at IS NULL) OR (status = 'COMPLETED' AND completed_at IS NOT NULL AND ((source_transcript_version_id IS NOT NULL AND capture_started_after_sequence IS NOT NULL AND start_segment_id IS NOT NULL) OR (source_transcript_version_id IS NULL AND capture_started_after_sequence IS NULL AND start_segment_id IS NULL AND text_content IS NOT NULL))))`
- `CHECK (completed_at IS NULL OR completed_at >= started_at)`
- `INDEX answers_session_started_idx (session_id, started_at, id)`
- `session_id ON DELETE CASCADE`
- `professor_user_id ON DELETE SET NULL`

`target_text_snapshot`은 두 target 모두에 적용한다. 학생 질문이면 `questions.content`, 대표 질문이면 `ai_representative_questions.text`의 선택 당시 값을 같은 transaction에서 정확히 복사하고 이후 수정하지 않는다. 따라서 대표 질문이 교체되어도 교수자가 실제 답변한 문구와 Answer 쌍은 보존된다. target별 partial UNIQUE 때문에 `CAPTURING`과 `COMPLETED`를 합쳐 Answer는 최대 하나다.

LIVE 음성 Answer의 `source_transcript_version_id`, `capture_started_after_sequence`, 완료된 Segment 범위는 이후 HQ canonical 전환과 관계없이 바꾸지 않는다. API의 원본 `start_sequence`, `end_sequence`는 두 LIVE Segment를 join해 계산한다. 완료된 음성 Answer에는 수업 후 `text_content`를 추가·수정할 수 있으나 target과 음성 범위는 유지한다. 수업 후 새 text-only Answer는 즉시 `COMPLETED`로 만들고 모든 Transcript 관련 컬럼을 `NULL`로 둔다.

별도 `answer_type` 컬럼은 두지 않는다. CHECK가 `source_transcript_version_id IS NOT NULL`인 Answer를 voice-backed로, source가 `NULL`이고 `text_content`가 필수인 완료 Answer를 text-only로 상호 배타적으로 만들므로 API는 각각 `VOICE`, `TEXT`로 안전하게 계산한다.

`CAPTURING` 취소는 Answer 행을 hard delete하고 target `status`를 `OPEN`으로 되돌린다. target 대표 질문의 `lifecycle_status`가 이미 `PRESERVED`라면 membership을 제거한 뒤 관련 Evidence가 없을 때만 대표 질문을 hard delete하고, Evidence가 있으면 `DISCARDED` tombstone으로 전이한다. 아직 중앙 `lifecycle_status=ACTIVE` 대표 질문이면 유지하되 다음 교체 때 같은 Evidence-aware 폐기 분기를 적용한다. `CANCELLED`, `cancelled_at`, `released_at`과 별도 취소 감사 행은 만들지 않는다. `COMPLETED` Answer의 삭제·text 최대 길이·검색 Chunk 재생성 세부 정책은 미정이다.

### 8.8 `answer_transcript_mappings`

LIVE Transcript에서 캡처한 Answer 원본 범위를 덮어쓰지 않고 각 HQ Transcript
version에 재매핑한 결과를 저장한다. 별도 `ANSWER_LINKING` Job은 만들지 않고
`SESSION_POSTPROCESSING`이 현재 canonical 후보에 대한 mapping과 검색 데이터
재연결을 담당한다.

| 컬럼                           | 타입          | NULL | 기본값      | 키·제약     | 설명                   |
| ------------------------------ | ------------- | ---: | ----------- | ----------- | ---------------------- |
| `answer_id`                    | `uuid`        |    N | -           | PK, 복합 FK | 원본 Answer            |
| `target_transcript_version_id` | `uuid`        |    N | -           | PK, 복합 FK | 재매핑 대상 HQ version |
| `session_id`                   | `uuid`        |    N | -           | 복합 FK     | 동일 Session 검증      |
| `status`                       | `text`        |    N | `'PENDING'` | CHECK       | mapping 상태           |
| `mapped_start_segment_id`      | `uuid`        |    Y | `NULL`      | 복합 FK     | HQ 범위 첫 Segment     |
| `mapped_end_segment_id`        | `uuid`        |    Y | `NULL`      | 복합 FK     | HQ 범위 마지막 Segment |
| `processed_by_job_id`          | `uuid`        |    Y | `NULL`      | 복합 FK     | 재매핑한 후처리 Job    |
| `processed_by_job_attempt`     | `integer`     |    Y | `NULL`      | CHECK `> 0` | 처리 attempt           |
| `mapped_at`                    | `timestamptz` |    Y | `NULL`      | -           | 성공 확정 시각         |
| `failed_at`                    | `timestamptz` |    Y | `NULL`      | -           | 실패 확정 시각         |
| `created_at`                   | `timestamptz` |    N | `now()`     | -           | 생성 시각              |
| `updated_at`                   | `timestamptz` |    N | `now()`     | -           | 갱신 시각              |

제약·인덱스:

- PK `(answer_id, target_transcript_version_id)`
- `(answer_id, session_id) FK → answers(id, session_id) ON DELETE CASCADE`
- `(target_transcript_version_id, session_id) FK → transcript_versions(id, session_id) ON DELETE CASCADE`
- `(mapped_start_segment_id, target_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(mapped_end_segment_id, target_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(processed_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `CHECK (status IN ('PENDING', 'SUCCEEDED', 'FAILED'))`
- `CHECK ((mapped_start_segment_id IS NULL) = (mapped_end_segment_id IS NULL))`
- `CHECK ((processed_by_job_id IS NULL) = (processed_by_job_attempt IS NULL))`
- `CHECK ((status = 'PENDING' AND mapped_start_segment_id IS NULL AND processed_by_job_id IS NULL AND mapped_at IS NULL AND failed_at IS NULL) OR (status = 'SUCCEEDED' AND mapped_start_segment_id IS NOT NULL AND processed_by_job_id IS NOT NULL AND mapped_at IS NOT NULL AND failed_at IS NULL) OR (status = 'FAILED' AND mapped_start_segment_id IS NULL AND processed_by_job_id IS NOT NULL AND mapped_at IS NULL AND failed_at IS NOT NULL))`
- `INDEX answer_transcript_mappings_target_idx (target_transcript_version_id, status, answer_id)`

voice-backed `COMPLETED` Answer에만 mapping을 만들며 text-only Answer에는 만들지 않는다. 성공 mapping은 target version이 `RECORDING`이고 현재 후처리 Job attempt와 같은지,
시작 sequence가 끝 sequence 이하인지 deferred trigger로 검증한다. Answer 시간 범위의
매칭 tolerance, 겹침률과 동률 해소 알고리즘은 미정이다. 일부 Answer mapping 실패는
이미 확정된 HQ Transcript를 되돌리지 않고 해당 mapping과 후처리 Job 실패로
격리한다. 원본 LIVE 범위는 계속 열람할 수 있고 canonical version 조회에서는 성공
mapping을 우선한다.

### 8.9 `answer_organizations`

수업 중 교수가 말로 완료한 voice-backed Answer를 AI가 독립적인 결과로 정리한다. 교수가 수업 후 직접 작성하는 `answers.text_content`와 분리하며, Answer당 성공 결과를 최대 하나만 보관한다.

| 컬럼                           | 타입          | NULL | 기본값              | 키·제약         | 설명                             |
| ------------------------------ | ------------- | ---: | ------------------- | --------------- | -------------------------------- |
| `id`                           | `uuid`        |    N | `gen_random_uuid()` | PK              | Answer organization ID           |
| `answer_id`                    | `uuid`        |    N | -                   | UNIQUE, 복합 FK | 정리 대상 voice Answer           |
| `session_id`                   | `uuid`        |    N | -                   | 복합 FK         | 동일 Session 검증                |
| `content`                      | `text`        |    N | -                   | CHECK           | AI가 정리한 답변 본문            |
| `source_transcript_version_id` | `uuid`        |    N | -                   | 복합 FK         | Job이 고정한 Transcript version  |
| `source_start_segment_id`      | `uuid`        |    N | -                   | 복합 FK         | 고정 입력 범위 시작 Segment      |
| `source_end_segment_id`        | `uuid`        |    N | -                   | 복합 FK         | 고정 입력 범위 종료 Segment      |
| `created_by_job_id`            | `uuid`        |    N | -                   | UNIQUE, 복합 FK | 생성한 `ANSWER_ORGANIZATION` Job |
| `created_by_job_attempt`       | `integer`     |    N | -                   | CHECK `> 0`     | 성공 생성 attempt                |
| `model_name`                   | `text`        |    Y | `NULL`              | -               | 모델 식별자                      |
| `prompt_version`               | `text`        |    Y | `NULL`              | -               | 프롬프트 버전                    |
| `created_at`                   | `timestamptz` |    N | `now()`             | -               | 성공 결과 생성 시각              |

제약·인덱스:

- `UNIQUE (id, session_id)`
- `UNIQUE (answer_id)`
- `UNIQUE (created_by_job_id)`
- `CHECK (char_length(btrim(content)) > 0)`; 정확한 최대 길이는 미정이다.
- `(answer_id, session_id) FK → answers(id, session_id) ON DELETE CASCADE`
- `(source_transcript_version_id, session_id) FK → transcript_versions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(source_start_segment_id, source_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(source_end_segment_id, source_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `INDEX answer_organizations_session_created_idx (session_id, created_at, id)`
- `INDEX answer_organizations_source_idx (source_transcript_version_id, source_start_segment_id, source_end_segment_id)`

결과 commit과 deferred constraint trigger는 다음을 검증한다.

- `answer_id`가 `COMPLETED` voice-backed Answer이고 `source_transcript_version_id IS NOT NULL`인지 확인한다.
- source 시작·종료 Segment가 같은 version·Session이며 시작 `sequence <=` 종료 `sequence`인지 확인한다.
- 생성 Job이 같은 Session의 `ANSWER_ORGANIZATION`, `target_answer_id = answer_id`, `SHARED`, `blocks_session_completion=true`이고 `created_by_job_attempt = ai_jobs.attempt`인지 확인한다.
- 결과 source version·시작·종료 Segment가 Job의 immutable `input_transcript_version_id`, `input_start_segment_id`, `input_end_segment_id`와 정확히 같은지 확인한다.

Organization 행 삽입과 Job `SUCCEEDED` 전이는 한 transaction으로 commit한다. 실패 attempt의 부분 content는 저장하지 않고, 재시도는 같은 Job 행에서 source snapshot을 유지한 채 `attempt + 1`로 실행한다. 성공 행은 수정·재생성하지 않으며 `id`, `answer_id`, `content`, source 범위, Job provenance, 모델·prompt, `created_at`은 생성 후 immutable이다. 형식, 모델, prompt, content 최대 길이와 정리 품질 기준은 미정이다.

Organization 모델 입력은 immutable `answers.target_text_snapshot`과 Job에 고정한 Transcript version·시작·종료 Segment 범위의 텍스트만 사용한다. 교수자가 작성한 `answers.text_content`는 모델 입력에서 항상 제외하고 Worker가 읽거나 쓰거나 덮어쓰지 않는다. 교수의 수동 text와 AI organization은 각각 독립 원본으로 조회한다. 성공한 organization을 KnowledgeChunk로 재색인할지와 그 생성·교체 시점은 미정이다.

API `organization_state`는 별도 저장 컬럼 없이 Answer 형태, Session·coordinator와 Job·결과 원장에서 다음 순서로 계산한다.

- text-only Answer는 Session 상태와 무관하게 `NOT_APPLICABLE`이다.
- Session이 `LIVE`인 voice Answer는 `CAPTURING`, `COMPLETED` 모두 아직 후처리 전이므로 정상적으로 Job 없이 `NOT_STARTED`다. LIVE에서는 organization Job을 만들지 않는다.
- Session이 `PROCESSING`인 `COMPLETED` voice Answer에 Job이 없고 `SESSION_POSTPROCESSING` coordinator가 source terminal을 기다리는 `PENDING` 또는 source 선택을 수행하는 `RUNNING`인 동안에만 `WAITING_SOURCE`다.
- Job이 있으면 PROCESSING에서 정상 active/terminal 상태는 `PENDING`, `RUNNING`, `FAILED`, `SUCCEEDED`다. COMPLETED에서는 terminal `FAILED`, `SUCCEEDED`뿐 아니라 명시적 실패 재시도로 `attempt > 1`인 `PENDING`, `RUNNING`도 정상 공개 상태다. `PENDING`·`RUNNING`·`FAILED`에는 organization 결과가 없어야 하고, `SUCCEEDED`에는 같은 Job의 현재 attempt로 생성된 `answer_organizations`가 정확히 한 행 있어야 한다.
- 공개 `DATA_INTEGRITY_ERROR`는 정상 처리 상태가 아니라 원장 누락·모순을 뜻한다. PROCESSING coordinator가 terminal인데 적용 대상 Job이 없을 때, Session이 `COMPLETED`인데 Job이 없을 때, COMPLETED에서 최초 `attempt = 1` Job이 `PENDING`·`RUNNING`으로 남을 때, non-SUCCEEDED Job에 결과가 있을 때, SUCCEEDED Job의 현재 attempt 결과가 없거나 하나를 초과할 때 사용한다. READY에 voice Answer가 있거나 PROCESSING에 `CAPTURING` Answer가 남은 경우, LIVE에 organization Job이 있는 경우도 상태 전이 무결성 오류다.
- 완료 뒤 실패 Job retry는 이 projection만 갱신하고 Session을 `PROCESSING`으로 되돌리지 않는다.

## 9. 비동기 작업

### 9.1 `ai_jobs`

PDF 처리, 클러스터링, Answer organization, 요약, Chat 응답과 Session 후처리 상태를 저장한다. 재시도는 같은 행을 사용한다.

| 컬럼                          | 타입          | NULL | 기본값              | 키·제약                    | 설명                                   |
| ----------------------------- | ------------- | ---: | ------------------- | -------------------------- | -------------------------------------- |
| `id`                          | `uuid`        |    N | `gen_random_uuid()` | PK                         | AIJob ID                               |
| `session_id`                  | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 작업 범위 class                        |
| `requester_user_id`           | `uuid`        |    Y | `NULL`              | FK → `users.id`            | 개인 작업 요청자                       |
| `job_type`                    | `text`        |    N | -                   | CHECK                      | 작업 유형                              |
| `visibility`                  | `text`        |    N | -                   | CHECK                      | `SHARED`, `REQUESTER_ONLY`             |
| `status`                      | `text`        |    N | `'PENDING'`         | CHECK                      | 작업 상태                              |
| `attempt`                     | `integer`     |    N | `1`                 | CHECK `> 0`                | 현재 시도 번호                         |
| `version`                     | `bigint`      |    N | `1`                 | CHECK `> 0`                | 상태 이벤트 버전                       |
| `target_material_id`          | `uuid`        |    Y | `NULL`              | 복합 FK                    | 자료 처리 대상                         |
| `target_recording_id`         | `uuid`        |    Y | `NULL`              | 복합 FK                    | 고품질 STT 대상 녹음                   |
| `target_chat_id`              | `uuid`        |    Y | `NULL`              | 복합 FK                    | Chat 응답 대상                         |
| `target_user_message_id`      | `uuid`        |    Y | `NULL`              | 복합 FK                    | Chat 응답의 immutable USER 입력        |
| `target_answer_id`            | `uuid`        |    Y | `NULL`              | 복합 FK                    | AI 정리 대상 voice Answer              |
| `input_transcript_version_id` | `uuid`        |    Y | `NULL`              | 복합 FK                    | Answer 정리 immutable source version   |
| `input_start_segment_id`      | `uuid`        |    Y | `NULL`              | 복합 FK                    | Answer 정리 immutable 시작 Segment     |
| `input_end_segment_id`        | `uuid`        |    Y | `NULL`              | 복합 FK                    | Answer 정리 immutable 종료 Segment     |
| `clustering_mode`             | `text`        |    Y | `NULL`              | CHECK                      | `LIVE_INCREMENTAL`, `FINAL`            |
| `input_through_sequence`      | `bigint`      |    Y | `NULL`              | CHECK `>= 0`               | Job 입력에 포함한 마지막 질문 sequence |
| `base_revision`               | `bigint`      |    Y | `NULL`              | CHECK `>= 0`               | 생성 시 state 결과 revision            |
| `final_answered_through_at`   | `timestamptz` |    Y | `NULL`              | CHECK                      | FINAL 대표질문 Answer snapshot 상한    |
| `dedupe_key_hash`             | `bytea`       |    Y | `NULL`              | -                          | 논리 작업 중복 방지 키                 |
| `available_at`                | `timestamptz` |    N | `now()`             | -                          | worker가 실행할 수 있는 시각           |
| `blocks_session_completion`   | `boolean`     |    N | `false`             | -                          | Session 완료 판정 대상 여부            |
| `run_token`                   | `uuid`        |    Y | `NULL`              | -                          | 현재 worker lease token                |
| `lease_expires_at`            | `timestamptz` |    Y | `NULL`              | -                          | worker lease 만료                      |
| `progress_stage`              | `text`        |    Y | `NULL`              | -                          | 작업별 단계 코드                       |
| `progress_percent`            | `smallint`    |    Y | `NULL`              | CHECK `0..100`             | 계산 가능한 경우 진행률                |
| `retryable`                   | `boolean`     |    N | `false`             | -                          | 재시도 가능 여부                       |
| `error_code`                  | `text`        |    Y | `NULL`              | -                          | 안전한 오류 코드                       |
| `error_message`               | `text`        |    Y | `NULL`              | -                          | 민감정보 없는 오류 메시지              |
| `created_at`                  | `timestamptz` |    N | `now()`             | -                          | 생성 시각                              |
| `updated_at`                  | `timestamptz` |    N | `now()`             | -                          | 갱신 시각                              |
| `started_at`                  | `timestamptz` |    Y | `NULL`              | -                          | 현재/마지막 시도 시작                  |
| `finished_at`                 | `timestamptz` |    Y | `NULL`              | -                          | 현재/마지막 시도 종료                  |

다형 관계 회피:

- 공통 `target_type + target_id`를 두지 않는다.
- Job 범위는 `session_id`, 구체 대상은 `target_material_id`, `target_recording_id`, `target_chat_id`, `target_user_message_id`, `target_answer_id`라는 실제 FK로 표현한다. `CHAT_RESPONSE`는 대화 aggregate와 해당 turn의 immutable USER Message를 둘 다 가리킨다.
- QUESTION_CLUSTERING, Summary와 Session 후처리는 `session_id` 자체가 target이다. 클러스터링 mode·질문 watermark·revision fence·FINAL Answer 시각 상한은 별도 typed 컬럼 네 개로 표현한다.
- `ANSWER_ORGANIZATION`은 `target_answer_id`와 coordinator가 생성 시 고정한 Transcript version·시작·종료 Segment typed 입력을 모두 가진다. 이 네 값은 Job 행 생성 뒤 수정하지 않는다.
- 결과는 Job에 generic result ID를 저장하지 않고 결과 테이블의 `created_by_job_id`, `created_by_job_attempt = ai_jobs.attempt`로 현재 attempt 결과를 조회한다.

제약·인덱스:

- `UNIQUE (id, session_id)`; 모든 결과가 원인 Job과 같은 Session인지 검증할 때 사용한다.
- `CHECK (num_nonnulls(target_material_id, target_recording_id, target_chat_id, target_answer_id) <= 1)`
- `CHECK (target_material_id IS NULL OR job_type = 'MATERIAL_PROCESSING')`
- `CHECK (target_recording_id IS NULL OR job_type = 'RECORDING_TRANSCRIPTION')`
- `CHECK ((job_type = 'CHAT_RESPONSE' AND target_chat_id IS NOT NULL AND target_user_message_id IS NOT NULL) OR (job_type <> 'CHAT_RESPONSE' AND target_chat_id IS NULL AND target_user_message_id IS NULL))`
- `CHECK (target_answer_id IS NULL OR job_type = 'ANSWER_ORGANIZATION')`
- `CHECK (job_type <> 'MATERIAL_PROCESSING' OR target_material_id IS NOT NULL)`
- `CHECK (job_type <> 'RECORDING_TRANSCRIPTION' OR target_recording_id IS NOT NULL)`
- `CHECK (job_type <> 'ANSWER_ORGANIZATION' OR target_answer_id IS NOT NULL)`
- `CHECK ((job_type = 'ANSWER_ORGANIZATION' AND input_transcript_version_id IS NOT NULL AND input_start_segment_id IS NOT NULL AND input_end_segment_id IS NOT NULL) OR (job_type <> 'ANSWER_ORGANIZATION' AND input_transcript_version_id IS NULL AND input_start_segment_id IS NULL AND input_end_segment_id IS NULL))`
- `CHECK ((input_start_segment_id IS NULL) = (input_end_segment_id IS NULL))`
- `CHECK ((input_transcript_version_id IS NULL) = (input_start_segment_id IS NULL))`
- `CHECK ((job_type = 'QUESTION_CLUSTERING' AND clustering_mode IS NOT NULL AND input_through_sequence IS NOT NULL AND base_revision IS NOT NULL) OR (job_type <> 'QUESTION_CLUSTERING' AND clustering_mode IS NULL AND input_through_sequence IS NULL AND base_revision IS NULL))`
- `CHECK (job_type <> 'QUESTION_CLUSTERING' OR requester_user_id IS NULL)`; 자동 공유 Job에는 요청자를 귀속하지 않는다.
- `CHECK (clustering_mode IS NULL OR clustering_mode IN ('LIVE_INCREMENTAL', 'FINAL'))`
- `CHECK ((clustering_mode = 'FINAL' AND final_answered_through_at IS NOT NULL) OR (clustering_mode IS DISTINCT FROM 'FINAL' AND final_answered_through_at IS NULL))`
- `CHECK (clustering_mode <> 'LIVE_INCREMENTAL' OR (visibility = 'SHARED' AND NOT blocks_session_completion))`
- `CHECK (clustering_mode <> 'FINAL' OR (visibility = 'SHARED' AND blocks_session_completion))`
- `CHECK ((visibility = 'REQUESTER_ONLY' AND requester_user_id IS NOT NULL) OR visibility = 'SHARED')`
- `CHECK (NOT blocks_session_completion OR visibility = 'SHARED')`
- `CHECK (job_type NOT IN ('LIVE_SUMMARY', 'CHAT_RESPONSE') OR (visibility = 'REQUESTER_ONLY' AND requester_user_id IS NOT NULL AND NOT blocks_session_completion))`
- `CHECK (job_type <> 'FINAL_SUMMARY' OR (visibility = 'SHARED' AND requester_user_id IS NULL AND blocks_session_completion))`
- `CHECK (job_type NOT IN ('SESSION_POSTPROCESSING', 'RECORDING_TRANSCRIPTION', 'ANSWER_ORGANIZATION') OR (visibility = 'SHARED' AND requester_user_id IS NULL AND blocks_session_completion))`
- `CHECK (progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100)`
- `CHECK ((run_token IS NOT NULL) = (status = 'RUNNING'))`
- `CHECK ((lease_expires_at IS NOT NULL) = (status = 'RUNNING'))`
- `CHECK ((status = 'PENDING' AND started_at IS NULL AND finished_at IS NULL AND error_code IS NULL AND error_message IS NULL) OR (status = 'RUNNING' AND started_at IS NOT NULL AND finished_at IS NULL AND error_code IS NULL AND error_message IS NULL) OR (status = 'SUCCEEDED' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND error_code IS NULL AND error_message IS NULL) OR (status IN ('FAILED', 'CANCELLED', 'SUPERSEDED') AND finished_at IS NOT NULL AND error_code IS NOT NULL))`; Session 10분 watchdog이 실행 전 `PENDING` Job도 실패시킬 수 있으므로 FAILED의 `started_at`은 nullable이다. `CANCELLED`와 `SUPERSEDED`는 `retryable=false` terminal이다.
- `CHECK (finished_at IS NULL OR finished_at >= started_at)`
- `CHECK (dedupe_key_hash IS NULL OR octet_length(dedupe_key_hash) = 32)`
- `UNIQUE INDEX ai_jobs_dedupe_uq (session_id, job_type, dedupe_key_hash) WHERE dedupe_key_hash IS NOT NULL`
- `UNIQUE INDEX ai_jobs_one_active_chat_response_uq (target_chat_id) WHERE job_type = 'CHAT_RESPONSE' AND status IN ('PENDING', 'RUNNING')`
- `UNIQUE INDEX ai_jobs_one_chat_response_per_user_message_uq (target_user_message_id) WHERE job_type = 'CHAT_RESPONSE'`; USER Message당 논리 응답 Job은 하나이고 retry는 같은 행을 쓴다.
- `UNIQUE INDEX ai_jobs_one_active_material_processing_uq (target_material_id) WHERE job_type = 'MATERIAL_PROCESSING' AND status IN ('PENDING', 'RUNNING')`
- `UNIQUE INDEX ai_jobs_one_active_question_clustering_uq (session_id) WHERE job_type = 'QUESTION_CLUSTERING' AND status IN ('PENDING', 'RUNNING')`
- `UNIQUE INDEX ai_jobs_one_final_question_clustering_uq (session_id) WHERE job_type = 'QUESTION_CLUSTERING' AND clustering_mode = 'FINAL'`; Session당 논리 FINAL Job은 terminal 상태까지 합쳐 하나이고 실패 retry는 같은 행을 쓴다.
- `UNIQUE INDEX ai_jobs_one_recording_transcription_uq (target_recording_id) WHERE job_type = 'RECORDING_TRANSCRIPTION'`; Recording당 논리 HQ STT Job은 하나이고 retry는 같은 행을 쓴다.
- `UNIQUE INDEX ai_jobs_one_answer_organization_uq (target_answer_id) WHERE job_type = 'ANSWER_ORGANIZATION'`; voice Answer당 논리 AI 정리 Job은 상태와 관계없이 하나다.
- `UNIQUE INDEX ai_jobs_one_session_postprocessing_uq (session_id) WHERE job_type = 'SESSION_POSTPROCESSING'`; Session당 후처리 coordinator는 하나이고 retry는 같은 행을 쓴다.
- `UNIQUE INDEX ai_jobs_one_final_summary_uq (session_id) WHERE job_type = 'FINAL_SUMMARY'`; Session당 논리 FINAL Summary Job은 하나이고 실패 retry는 같은 행을 쓴다.
- `INDEX ai_jobs_session_shared_idx (session_id, status, job_type, created_at DESC, id DESC) WHERE visibility = 'SHARED'`
- `INDEX ai_jobs_session_shared_created_idx (session_id, created_at DESC, id DESC) WHERE visibility = 'SHARED'`
- `INDEX ai_jobs_requester_idx (requester_user_id, status, created_at DESC) WHERE requester_user_id IS NOT NULL`
- `INDEX ai_jobs_claim_idx (available_at, created_at, id) WHERE status = 'PENDING'`
- `INDEX ai_jobs_lease_idx (lease_expires_at) WHERE status = 'RUNNING'`
- `session_id ON DELETE CASCADE`
- `requester_user_id ON DELETE RESTRICT`; User 행은 기본적으로 익명화하며 hard delete workflow는 개인 Job을 삭제하고 공유 Job의 requester를 명시적으로 `NULL` 처리한 뒤 진행한다.
- `(target_material_id, session_id) FK → lecture_materials(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(target_recording_id, session_id) FK → session_recordings(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(target_chat_id, session_id) FK → chat_sessions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(target_user_message_id, target_chat_id, session_id) FK → chat_messages(id, chat_id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(target_answer_id, session_id) FK → answers(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(input_transcript_version_id, session_id) FK → transcript_versions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(input_start_segment_id, input_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(input_end_segment_id, input_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

typed target FK는 target만 독립 삭제하는 것은 막고 Session aggregate 전체 삭제는 한 transaction에서 허용한다.

deferred integrity trigger는 `LIVE_SUMMARY` Job의 Session이 생성 시점에 `LIVE`이고 requester가 그 Course의 현재 멤버인지 검증한다. `CHAT_RESPONSE`는 target Chat의 owner와 requester가 같고 `target_user_message_id`가 같은 Chat·Session의 `role=USER`이며 아직 다른 응답 Job에 귀속되지 않았는지 검증한다. Chat mode가 `LIVE`이면 Session `LIVE`, `REVIEW`이면 Session `COMPLETED`여야 한다. 두 경로 모두 `PROFESSOR`, `STUDENT`를 구분하지 않는다. mode 또는 Session 상태가 맞지 않는 개인 Job은 만들거나 claim하지 않는다. `CHAT_RESPONSE`의 `target_chat_id`, `target_user_message_id` update는 생성 뒤 항상 거부해 모든 retry가 같은 turn을 사용하게 한다.

`ANSWER_ORGANIZATION` 생성 transaction은 선택한 source 시작 Segment의 `sequence <=` 종료 Segment의 `sequence`인지, 대상이 `COMPLETED` voice-backed Answer인지를 검증한다. DB trigger는 target·source 네 컬럼의 update를 언제나 거부해 재시도가 동일 입력을 사용하게 한다. 실패 Job만 같은 행에서 `attempt + 1`로 retry할 수 있고, `SUCCEEDED` Job이나 이미 `answer_organizations`가 있는 Answer는 재생성하지 않는다.

PROCESSING coordinator는 Answer를 잠그고 Job을 만들 때 source를 한 번만 선택한다. 현재 HQ RECORDING version으로의 `SUCCEEDED` `answer_transcript_mappings`가 있으면 그 version과 `mapped_start_segment_id`·`mapped_end_segment_id`를 우선한다. 성공 mapping이 없으면 Answer의 원본 LIVE `source_transcript_version_id`·`start_segment_id`·`end_segment_id`를 사용한다. 선택한 값은 Job의 `input_*` 컬럼에 즉시 복사하며, 후속 HQ mapping 변경이나 retry로 다시 선택하지 않는다. 따라서 mapping 실패는 개별 Answer 정리를 막지 않고 LIVE 원본 범위로 fallback한다.

클러스터링 Job 생성·claim·결과 commit은 `Session → question_clustering_states → AIJob` 순서로 잠근 뒤 다음 조건을 검증한다.

- `LIVE_INCREMENTAL`: Session이 `LIVE`, `input_through_sequence > applied_sequence`, `input_through_sequence <= requested_sequence`, `base_revision = current_revision`, `blocks_session_completion=false`여야 한다.
- `FINAL`: 최초 생성은 Session이 `PROCESSING`, `input_through_sequence = requested_sequence`, `base_revision = current_revision`, `final_answered_through_at = lecture_sessions.ended_at`, `blocks_session_completion=true`여야 한다. 학생 질문 입력은 `clustering_sequence <= input_through_sequence`, AI 대표질문 입력은 direct Answer가 `COMPLETED`이고 `completed_at <= final_answered_through_at`인 행으로 선택한다. 현재 중앙인지 과거 child인지와 무관하다. 실패 뒤 교수자가 명시적으로 retry하면 같은 Job 행의 `input_through_sequence`는 유지하되, transaction에서 state를 잠그고 `base_revision = current_revision`, `final_answered_through_at = now()`로 재캡처한 뒤 `attempt + 1`로 전이한다. 따라서 이전 실패 뒤 완료된 대표질문 text Answer도 retry 입력에 포함될 수 있으며, Session이 이미 `COMPLETED`여도 상태를 되돌리지 않는다. 이 재캡처는 실패 FINAL retry에만 허용하고 성공한 FINAL은 자동 재생성하지 않는다.
- active partial UNIQUE는 질문이 연속 등록되어도 Session당 `PENDING` 또는 `RUNNING` 클러스터링 Job을 하나만 허용한다. 실행 중이거나 retry 예약 중 증가한 `requested_sequence`는 해당 Job의 captured watermark를 바꾸지 않고 성공 뒤 다음 fresh Job 입력으로 합친다.
- 결과 commit은 Job의 현재 `attempt`, `run_token`, `RUNNING` 상태뿐 아니라 state의 `current_revision = base_revision`과 Session 상태·mode를 다시 확인한다. `LIVE_INCREMENTAL`은 반드시 `LIVE`, `FINAL`은 최초 실행의 `PROCESSING` 또는 실패 Job의 명시적 retry인 `COMPLETED`만 허용한다. 하나라도 다르면 생성한 Cluster·대표 질문·membership을 commit하지 않는다.
- retry 가능한 `LIVE_INCREMENTAL` 실패는 state의 `retry_job_id`에 같은 Job을 예약한다. scheduler는 Session·state·Job을 같은 순서로 잠그고 새 Job을 만들지 않은 채 그 행을 원래 `input_through_sequence`·`base_revision` 그대로 `attempt + 1`, `PENDING`으로 전환하며 retry 예약을 해제한다. backoff와 최대 횟수는 미정이다.

`dedupe_key_hash`는 목적별 HMAC으로 계산한다. 입력에는 `session_id`, `job_type`, `visibility`, `REQUESTER_ONLY`이면 `requester_user_id`, typed target을 넣고 `CHAT_RESPONSE`이면 `target_chat_id`와 immutable `target_user_message_id`를 모두 포함한다. 클러스터링이면 `clustering_mode`·`input_through_sequence`·`base_revision`·`final_answered_through_at`, Answer 정리면 immutable Transcript version·시작·종료 Segment, 그 밖에는 정규화된 논리 입력 digest를 포함한다. 따라서 다른 사용자·Session·Chat turn의 개인 작업이 같은 Job으로 합쳐지지 않는다. FINAL retry에서 재캡처한 `base_revision`·`final_answered_through_at`은 동일 Job 행의 새 attempt 입력이며 새 논리 Job을 만들기 위한 dedupe 키로 사용하지 않는다.

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

모든 Worker는 RUNNING Job의 lease를 15초마다 갱신하고 갱신 시
`lease_expires_at = now() + interval '60 seconds'`로 둔다. watchdog은 60초 동안
갱신되지 않은 Job을 `FAILED`로 terminal 처리한다. 또한
`RECORDING_TRANSCRIPTION`을 제외한 일반 후처리 Job이
`started_at + interval '5 minutes'`를 넘으면 같은 실패 전이를 적용한다. HQ STT
개별 Job timeout은 미정이며, 추후 상한이 확정되면 초과
`RECORDING_TRANSCRIPTION`은 7.4절의 원자 실패 transaction으로 staging 하위
행을 비운다. Session 전체 deadline은
`lecture_sessions.ended_at + interval '10 minutes'`다. 이 시점에는 Session과
coordinator를 먼저 잠그고, `FINAL_SUMMARY`를 제외한 아직 생성되지 않은 적용 가능한 downstream blocking Job을
`FAILED`, `retryable=true`, `started_at=NULL`, `finished_at=now()`,
`error_code=SESSION_PROCESSING_TIMEOUT`으로 원자 생성한다. HQ source가 없거나 실패한
Summary는 `SUMMARY_SOURCE_UNAVAILABLE`, RECORDING `EMPTY`는 `NO_FINAL_TRANSCRIPT`로
확정한다. RECORDING `FINALIZED` Segment가 1건 이상인데 coordinator가 만들었어야 할 `FINAL_SUMMARY` Job이 없으면 synthetic 실패 Job을 만들지 않고 `DATA_INTEGRITY_ERROR`로 projection·관측한다. 이때 FINAL 대상이 1건 이상인데 누락된 clustering 원장은 `clustering_mode=FINAL`, `input_through_sequence = requested_sequence`, `base_revision = current_revision`, `final_answered_through_at = lecture_sessions.ended_at`, `SHARED`, `blocks_session_completion=true`를
채운다. 대상 0건에서는 미정인 Job·빈 generation 표현을 watchdog이 임의로 선택하지 않는다. 또한 Job이 없는 모든 `COMPLETED` voice-backed Answer를 잠그고, 성공 HQ mapping을 우선하되 없으면 원본 LIVE 범위로 source를 고정한 `ANSWER_ORGANIZATION`, `SHARED`, blocking Job을 Answer당 하나씩 즉시 `FAILED`, `retryable=true`, `error_code=SESSION_PROCESSING_TIMEOUT`으로 생성한다. 그 뒤 coordinator, 남은 blocking Job과 비terminal Recording·Upload gate를
같은 timeout code로 `FAILED` 처리하고 완료 판정을 실행한다. timeout된 RUNNING Job의
run token과 lease는 지우므로 늦게 도착한 결과는 commit할 수 없다.

### 9.2 Job 결과 역참조 규칙

| Job 결과                     | 결과 테이블                                        | 규칙                                              |
| ---------------------------- | -------------------------------------------------- | ------------------------------------------------- |
| PDF 처리 상태                | `lecture_materials`                                | `processed_by_job_id`, `processed_by_job_attempt` |
| 고품질 Transcript version    | `transcript_versions`                              | `created_by_job_id`, `created_by_job_attempt`     |
| PDF·Transcript·Q&A 검색 조각 | `knowledge_chunks`                                 | `created_by_job_id`, `created_by_job_attempt`     |
| 질문 클러스터 generation     | `question_clusters`, `ai_representative_questions` | 같은 Job attempt의 generation/list aggregate      |
| 음성 Answer AI 정리          | `answer_organizations`                             | Answer당·Job당 한 immutable 결과                  |
| LIVE/FINAL 요약              | `lecture_summaries`                                | Job당 한 결과                                     |
| Assistant 답변               | `chat_messages`                                    | Job당 한 Assistant Message                        |

Job 결과 행 삽입 또는 Material 상태 확정과 `ai_jobs.status = 'SUCCEEDED'` 전이는 같은 DB 트랜잭션에서 수행한다. 실패한 attempt가 만든 중간 결과는 commit하지 않는다. `chat_message_evidence`처럼 결과 aggregate의 종속 행은 상위 `chat_messages.created_by_job_id`를 통해 같은 Job에 귀속된다.

`QUESTION_CLUSTERING` 성공 결과는 단일 Cluster가 아니라 한 Job attempt가 만든 generation 전체다. 현재 generation이 그 Job 결과이면 API `result.resource_type = QUESTION_CLUSTER_GENERATION`, `resource_id = generation::text`, `resource_url = /api/v1/sessions/{session_id}/question-clusters`로 projection한다. 일반 과거 generation은 정책상 새 generation 공개 transaction에서 즉시 삭제하므로 이전 `SUCCEEDED` Job은 결과 행을 더 이상 역조회할 수 없다. 이 경우에만 `result = null`, 파생 `result_unavailable_reason = SUPERSEDED`를 반환한다.

generation 삭제 guard는 state가 같은 transaction에서 더 새 `current_generation`·revision으로 전환되고 삭제 대상 generation의 producer가 현재 producer와 다를 때만 위 SUPERSEDED 예외를 허용한다. 현재 generation producer Job의 행이 없거나 다른 `SUCCEEDED` Job 결과가 누락된 경우는 SUPERSEDED가 아니라 데이터 무결성 오류다. 따라서 `SUPERSEDED`는 QUESTION_CLUSTERING의 정책적 과거 generation 삭제에만 쓰며 Summary, Chat, Answer organization, Transcript 등 다른 성공 Job의 결과 누락을 정상화하지 않는다.

녹음 upload 완료 transaction은 Recording `UPLOADED`와 함께 동일 Recording을 target으로
하는 `RECORDING_TRANSCRIPTION`, `SHARED`, `blocks_session_completion=true` Job을 만든다.
Job 성공 결과는 현재 attempt와 같은 `transcript_versions` 행 하나이며 Job 성공과
version `FINALIZED` 또는 `EMPTY`, canonical 전환 outbox를 같은 transaction에서
확정한다. `FAILED` version은 Job 실패 provenance로 보존하되 실패 transaction에서
해당 version의 Segment·Gap을 비우고 `last_sequence = 0`으로 되돌린다.

결과 commit은 복합 FK의 같은 Session 조건에 더해 Job의 현재 `attempt`, `run_token`, `job_type`, `visibility`, requester와 정확한 typed target을 대조한다. 서비스 검증과 deferred constraint trigger의 공통 규칙은 다음과 같다.

- Material 상태와 Material source Chunk: `MATERIAL_PROCESSING`, `target_material_id = material_id`
- HQ TranscriptVersion·Segment·final Gap: `RECORDING_TRANSCRIPTION`, `target_recording_id = transcript_versions.recording_id`
- Cluster generation·AI 대표 질문: `QUESTION_CLUSTERING`; `clustering_mode`, `input_through_sequence`, `base_revision`, FINAL이면 `final_answered_through_at`, 현재 state fence와 final 여부, 같은 attempt의 단일 generation과 membership set equality가 일치
- Answer organization: `ANSWER_ORGANIZATION`, `SHARED`, blocking, `target_answer_id = answer_id`; 결과의 source version·시작·종료 Segment가 Job immutable input과 일치하고 결과 삽입·Job 성공을 원자 commit
- LIVE Summary: `LIVE_SUMMARY`, `REQUESTER_ONLY`, Job requester와 Summary requester가 동일
- FINAL Summary: `FINAL_SUMMARY`, `SHARED`, Summary requester는 `NULL`
- Assistant Message·Evidence: `CHAT_RESPONSE`, `target_chat_id = chat_id`, `target_user_message_id`가 같은 Chat의 immutable USER Message, Job requester와 Chat owner가 동일. Assistant는 해당 입력 다음 응답 turn이며 결과 commit은 이 target을 다시 대조한다.
- Transcript·Question·AI 대표 질문·Answer source Chunk: 허용된 producer Job 유형과 실제 source가 현재 처리 입력 범위에 포함. `answer_id` source는 교수 수동 `text_content`만 사용

## 10. 공통 검색 지식

### 10.1 `knowledge_chunks`

PDF, final Transcript, 학생 Question, AI 대표 질문과 교수 수동 Answer text를 같은 RAG 검색 단위로 통합한다. `source_type + source_id` 대신 실제 nullable FK를 사용하며 정확히 한 source 계열만 값이 있어야 한다. Answer organization 재색인은 별도 미정 사항이며 현재 source 종류에 포함하지 않는다.

| 컬럼                           | 타입                    | NULL | 기본값              | 키·제약      | 설명                         |
| ------------------------------ | ----------------------- | ---: | ------------------- | ------------ | ---------------------------- |
| `id`                           | `uuid`                  |    N | `gen_random_uuid()` | PK           | KnowledgeChunk ID            |
| `course_id`                    | `uuid`                  |    N | -                   | 복합 FK      | 검색 Course 범위             |
| `session_id`                   | `uuid`                  |    N | -                   | 복합 FK      | 검색 class 범위              |
| `material_id`                  | `uuid`                  |    Y | `NULL`              | 복합 FK      | PDF source                   |
| `source_transcript_version_id` | `uuid`                  |    Y | `NULL`              | 복합 FK      | Transcript source version    |
| `transcript_start_segment_id`  | `uuid`                  |    Y | `NULL`              | 복합 FK      | Transcript source 범위 시작  |
| `transcript_end_segment_id`    | `uuid`                  |    Y | `NULL`              | 복합 FK      | Transcript source 범위 끝    |
| `question_id`                  | `uuid`                  |    Y | `NULL`              | 복합 FK      | Question source              |
| `representative_question_id`   | `uuid`                  |    Y | `NULL`              | 복합 FK      | AI 대표 질문 source          |
| `answer_id`                    | `uuid`                  |    Y | `NULL`              | 복합 FK      | 교수 수동 Answer text source |
| `chunk_index`                  | `integer`               |    N | -                   | CHECK `>= 0` | source 내 순번               |
| `page_number`                  | `integer`               |    Y | `NULL`              | CHECK `> 0`  | Material source 페이지       |
| `content`                      | `text`                  |    N | -                   | CHECK        | 검색 텍스트                  |
| `token_count`                  | `integer`               |    Y | `NULL`              | CHECK `>= 0` | 모델 tokenizer 기준          |
| `embedding`                    | `vector(EMBEDDING_DIM)` |    N | -                   | -            | 임베딩                       |
| `embedding_model`              | `text`                  |    N | -                   | -            | 모델·버전 식별자             |
| `created_by_job_id`            | `uuid`                  |    N | -                   | 복합 FK      | 생성 Job                     |
| `created_by_job_attempt`       | `integer`               |    N | -                   | CHECK `> 0`  | 생성 attempt                 |
| `created_at`                   | `timestamptz`           |    N | `now()`             | -            | 생성 시각                    |

범위·source 제약:

- `CHECK ((transcript_start_segment_id IS NULL) = (transcript_end_segment_id IS NULL))`
- `CHECK ((source_transcript_version_id IS NULL) = (transcript_start_segment_id IS NULL))`
- `CHECK (num_nonnulls(material_id, source_transcript_version_id, question_id, representative_question_id, answer_id) = 1)`
- `CHECK (page_number IS NULL OR material_id IS NOT NULL)`
- `(session_id, course_id) FK → lecture_sessions(id, course_id) ON DELETE CASCADE`
- `(material_id, session_id) FK → lecture_materials(id, session_id) ON DELETE CASCADE`
- `(source_transcript_version_id, session_id) FK → transcript_versions(id, session_id) ON DELETE CASCADE`
- `(transcript_start_segment_id, source_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE CASCADE`
- `(transcript_end_segment_id, source_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE CASCADE`
- `(question_id, session_id) FK → questions(id, session_id) ON DELETE CASCADE`
- `(representative_question_id, session_id) FK → ai_representative_questions(id, session_id) ON DELETE CASCADE`
- `(answer_id, session_id) FK → answers(id, session_id) ON DELETE CASCADE`
- source가 `NULL`인 복합 FK는 PostgreSQL 기본 `MATCH SIMPLE`에 따라 검사하지 않는다.
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

고유·조회 인덱스:

- `UNIQUE (id, session_id)`
- `UNIQUE INDEX knowledge_chunks_material_ordinal_uq (material_id, chunk_index) WHERE material_id IS NOT NULL`
- `UNIQUE INDEX knowledge_chunks_transcript_ordinal_uq (source_transcript_version_id, transcript_start_segment_id, transcript_end_segment_id, chunk_index) WHERE source_transcript_version_id IS NOT NULL`
- `UNIQUE INDEX knowledge_chunks_question_ordinal_uq (question_id, chunk_index) WHERE question_id IS NOT NULL`
- `UNIQUE INDEX knowledge_chunks_representative_question_ordinal_uq (representative_question_id, chunk_index) WHERE representative_question_id IS NOT NULL`
- `UNIQUE INDEX knowledge_chunks_answer_ordinal_uq (answer_id, chunk_index) WHERE answer_id IS NOT NULL`
- `INDEX knowledge_chunks_scope_idx (course_id, session_id)`
- `INDEX knowledge_chunks_job_idx (created_by_job_id, created_by_job_attempt)`
- embedding 모델과 차원을 확정한 뒤 `USING hnsw (embedding vector_cosine_ops)` 인덱스를 생성한다.

Transcript 범위의 시작·끝 순서와 같은 Session·version 여부는 복합 FK와 constraint trigger로 검증한다. 모든 vector 검색은 `course_id = :course_id AND session_id = :session_id`를 먼저 강제한다. Transcript source는 `source_transcript_version_id = lecture_sessions.canonical_transcript_version_id`, AI 대표 질문 source는 `ai_representative_questions.lifecycle_status IN ('ACTIVE', 'PRESERVED')`를 같은 SQL에서 적용해 HQ 전환 전 LIVE Chunk와 `DISCARDED` 대표질문 Chunk가 새 검색에 섞이지 않게 한다. 기존 Chat Evidence가 참조하는 과거 version 또는 `DISCARDED` 대표질문 Chunk는 provenance로 유지한다. `course_id`는 vector filter 성능을 위한 의도적 중복이며 `(session_id, course_id)` FK가 불일치를 막는다.

`answer_id` source Chunk는 `answers.text_content IS NOT NULL`인 교수 수동 본문만 색인한다. AI가 정리한 `answer_organizations.content`는 현재 KnowledgeChunk source가 아니며, 성공 결과 재색인 여부·producer Job·생성 및 교체 transaction은 후속 정책으로 남긴다.

## 11. 요약·AI Chat

### 11.1 `lecture_summaries`

성공한 LIVE/FINAL 요약을 보관한다. LIVE는 요청자 전용, FINAL은 Course 멤버 공유다.

| 컬럼                           | 타입          | NULL | 기본값              | 키·제약                    | 설명                    |
| ------------------------------ | ------------- | ---: | ------------------- | -------------------------- | ----------------------- |
| `id`                           | `uuid`        |    N | `gen_random_uuid()` | PK                         | Summary ID              |
| `session_id`                   | `uuid`        |    N | -                   | FK → `lecture_sessions.id` | 소속 class              |
| `requester_user_id`            | `uuid`        |    Y | `NULL`              | FK → `users.id`            | LIVE 요청자             |
| `created_by_job_id`            | `uuid`        |    N | -                   | 복합 FK                    | 생성 Job                |
| `created_by_job_attempt`       | `integer`     |    N | -                   | CHECK `> 0`                | 생성 attempt            |
| `summary_type`                 | `text`        |    N | -                   | CHECK                      | `LIVE`, `FINAL`         |
| `visibility`                   | `text`        |    N | -                   | CHECK                      | 공개 범위               |
| `content`                      | `text`        |    N | -                   | CHECK                      | 요약 본문               |
| `source_transcript_version_id` | `uuid`        |    N | -                   | 복합 FK                    | 근거 Transcript version |
| `source_start_segment_id`      | `uuid`        |    N | -                   | 복합 FK                    | 선택 범위 시작          |
| `source_end_segment_id`        | `uuid`        |    N | -                   | 복합 FK                    | 선택 범위 종료          |
| `model_name`                   | `text`        |    Y | `NULL`              | -                          | 모델 식별자             |
| `prompt_version`               | `text`        |    Y | `NULL`              | -                          | 프롬프트 버전           |
| `created_at`                   | `timestamptz` |    N | `now()`             | -                          | 생성 시각               |

제약·인덱스:

- `UNIQUE (created_by_job_id)`; 한 Summary Job은 결과 하나만 만든다.
- `CHECK ((summary_type = 'LIVE' AND visibility = 'REQUESTER_ONLY' AND requester_user_id IS NOT NULL) OR (summary_type = 'FINAL' AND visibility = 'COURSE_MEMBERS' AND requester_user_id IS NULL))`
- `CHECK (length(btrim(content)) > 0)`
- `(source_transcript_version_id, session_id) FK → transcript_versions(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(source_start_segment_id, source_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- `(source_end_segment_id, source_transcript_version_id, session_id) FK → transcript_segments(id, transcript_version_id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- 시작 Segment의 `sequence <=` 끝 Segment의 `sequence`를 결과 commit과 deferred constraint trigger로 검증한다.
- `INDEX lecture_summaries_session_type_idx (session_id, summary_type, created_at DESC, id DESC)`
- `INDEX lecture_summaries_requester_idx (requester_user_id, session_id, created_at DESC) WHERE requester_user_id IS NOT NULL`
- `session_id ON DELETE CASCADE`
- `requester_user_id ON DELETE CASCADE`; 개인 LIVE Summary를 함께 삭제한다.
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

같은 FINAL Summary Job의 retry는 동일 Job 행을 쓰므로 성공 결과도 최대 한 행이다. MVP는 Session별 하나의 논리 FINAL Summary Job을 dedupe한다. 향후 명시적 재생성 기능이 추가되어 새 Job을 허용할 때만 여러 결과 행을 보관하고 `(created_at DESC, id DESC)`로 최신 결과를 선택한다.

LIVE Summary는 요청을 수락한 시점의 LIVE version과 마지막 Segment 범위를 snapshot한다.
LIVE Session에서 Segment가 0개면 Job을 만들지 않고
`409 SUMMARY_TRANSCRIPT_NOT_READY`를 반환한다. FINAL Summary는 최신 HQ source가
`RECORDING`, `FINALIZED`이고 Segment가 1개 이상일 때만 Job과 결과를 만든다.
RECORDING source가 정상 `EMPTY`이면 Summary row와 Job 없이 API에서
`NOT_APPLICABLE / NO_FINAL_TRANSCRIPT`, Recording source 자체가 없으면 coordinator가
즉시 `SUMMARY_SOURCE_UNAVAILABLE`로 확정한다. Recording은 있지만 HQ source가
`FAILED`이거나 10분 deadline까지 결과가 없을 때도 `SUMMARY_SOURCE_UNAVAILABLE`다. 보존된 LIVE
포인터를 완료 기록의 final source로 인정하는 정책이 확정되기 전에는 이를 자동
FINAL Summary source로 사용하지 않는다. `FINAL_SUMMARY` Job이 `SUCCEEDED`인데 같은
Job attempt의 Summary가 없으면 정상 null이 아니라 데이터 불일치다.

LIVE Summary 생성은 Course 멤버라면 역할과 무관하게 허용하고 Session `LIVE`에서만 수락한다. 결과 insert와 `LIVE_SUMMARY` Job 성공은 현재 Job ID·attempt·run token을 확인해 한 transaction으로 commit하며, 중간 token·부분 문장은 저장하지 않는다. Session이 `LIVE → PROCESSING`으로 전이할 때 결과와 원인 Job을 함께 삭제하므로 종료 뒤에는 이 행을 복구하거나 FINAL Summary로 승격하지 않는다.

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
- `INDEX chat_sessions_session_mode_idx (session_id, mode, id)`; Session 종료 시 LIVE Chat 잠금·삭제에 사용한다.
- `session_id ON DELETE CASCADE`
- `owner_user_id ON DELETE CASCADE`

`owner_user_id`는 Chat 생성 시 해당 Course의 현재 멤버여야 하며 역할은 구분하지 않는다. deferred trigger는 `mode=LIVE`이면 Session `LIVE`, `mode=REVIEW`이면 Session `COMPLETED`인지 검증하고 `mode` update를 금지한다. Message 추가·Job 생성 transaction도 같은 상태를 다시 확인한다. 따라서 `READY`, `PROCESSING`에서는 Chat을 생성하거나 계속 사용할 수 없고, Session 종료 transaction과 새 LIVE Message 요청은 Session 잠금에서 직렬화된다.

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
- `UNIQUE (id, chat_id, session_id)`; `CHAT_RESPONSE`의 immutable USER Message 복합 FK target이다.
- `UNIQUE INDEX chat_messages_created_by_job_uq (created_by_job_id) WHERE created_by_job_id IS NOT NULL`
- `(chat_id, session_id) FK → chat_sessions(id, session_id) ON DELETE CASCADE`
- `CHECK ((role = 'USER' AND content = btrim(content) AND content IS NFC NORMALIZED AND char_length(content) BETWEEN 1 AND 2000) OR (role = 'ASSISTANT' AND char_length(btrim(content)) > 0))`; 서비스 우회 insert도 NFD USER content를 저장하지 못하며 `char_length`는 byte가 아닌 Unicode code point를 센다. Assistant에는 NFC·2,000자 상한을 적용하지 않는다.
- `CHECK ((role = 'USER' AND created_by_job_id IS NULL AND created_by_job_attempt IS NULL AND model_name IS NULL AND prompt_version IS NULL) OR (role = 'ASSISTANT' AND created_by_job_id IS NOT NULL AND created_by_job_attempt IS NOT NULL))`
- `INDEX chat_messages_chat_sequence_idx (chat_id, sequence)`
- `(created_by_job_id, session_id) FK → ai_jobs(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`

Chat row를 `SELECT ... FOR UPDATE`로 잠근 뒤 다음 sequence를 할당한다. 서비스는 USER content를 `trim → Unicode NFC` 순서로 정규화한 뒤 Unicode code point 1~2,000자를 검증한다. 빈 값·초과 입력은 잘라 저장하지 않고 `422 VALIDATION_ERROR`로 거부한다. `USER` Message에는 producer Job·attempt와 model·prompt metadata를 기록하지 않는다. `ASSISTANT` Message는 producer Job·attempt가 필수이고 `model_name`, `prompt_version`은 현재 계약대로 nullable이다. `USER` Message, `CHAT_RESPONSE` Job, queue outbox와 terminal `202` 멱등성 응답을 같은 요청 transaction에 기록해 Worker claim 전에 새로고침 복구가 가능하게 한다. Assistant Message·Evidence 삽입과 Job 성공은 별도 결과 transaction에서 원자 commit하고, 실패·취소·생성 중 delta에는 Assistant Message를 만들지 않는다.

### 11.4 `chat_message_evidence`

Assistant Message가 실제로 사용한 공통 KnowledgeChunk를 순위와 함께 저장한다.

| 컬럼                 | 타입               | NULL | 기본값  | 키·제약         | 설명                                       |
| -------------------- | ------------------ | ---: | ------- | --------------- | ------------------------------------------ |
| `chat_message_id`    | `uuid`             |    N | -       | PK, 복합 FK     | Assistant Message                          |
| `knowledge_chunk_id` | `uuid`             |    N | -       | 복합 FK         | 사용한 Chunk                               |
| `session_id`         | `uuid`             |    N | -       | 복합 FK         | 동일 Session 검증                          |
| `rank`               | `integer`          |    N | -       | PK, CHECK `> 0` | 근거 순위                                  |
| `relevance_score`    | `double precision` |    Y | `NULL`  | -               | 검색 점수 snapshot                         |
| `label_snapshot`     | `text`             |    N | -       | CHECK           | 사용자 표시용 안전한 source label snapshot |
| `created_at`         | `timestamptz`      |    N | `now()` | -               | 저장 시각                                  |

제약·인덱스:

- PK `(chat_message_id, rank)`
- `UNIQUE (chat_message_id, knowledge_chunk_id)`; Chunk 전체에 대한 단독 UNIQUE는 두지 않는다.
- `INDEX chat_message_evidence_chunk_idx (knowledge_chunk_id, session_id)`
- `CHECK (length(btrim(label_snapshot)) > 0)`
- `(chat_message_id, session_id) FK → chat_messages(id, session_id) ON DELETE CASCADE`
- `(knowledge_chunk_id, session_id) FK → knowledge_chunks(id, session_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED`
- Evidence 생성 시 대상 Message가 `ASSISTANT`인지 서비스에서 확인한다.

`knowledge_chunk_id`는 검색 provenance를 위한 내부 식별자이며 API에 내보내지 않는다.
공개 `source_kind`는 Chunk의 유일한 typed source FK를 `MATERIAL`, `TRANSCRIPT`,
`QUESTION`, `ANSWER` 중 하나로 축약해 계산한다. Transcript Segment는 `TRANSCRIPT`,
학생 질문과 AI 대표 질문은 모두 `QUESTION`으로 projection한다. `label_snapshot`은 Evidence 생성 시 source의 사용자 표시 정보를
복사한 값이며 API의 `label`로 projection한다. Chunk 본문, 내부 UUID, storage key, 서버
경로와 provider 오류를 넣지 않는다.

공개 `link`는 DB에 저장하지 않고 현재 Course 접근 권한을 확인한 뒤 typed source의
공개 ID로 API root 기준 상대 경로를 계산한다. Material은 page가 있으면
`/api/v1/materials/{material_id}/content#page={page_number}`를 사용하고 page가 없으면
`/api/v1/materials/{material_id}/content`에서 fragment를 생략한다. Transcript는
`/api/v1/sessions/{session_id}/transcript?transcript_version_id={version_id}&start_sequence={start_sequence}&end_sequence={end_sequence}`처럼 Session·version과 stable sequence 범위를 사용한다. 학생 질문은
`/api/v1/questions/{question_id}`, AI 대표 질문은
`/api/v1/representative-questions/{representative_question_id}`, Answer는
`/api/v1/answers/{answer_id}`다. `/record` 배열 위치, pagination cursor, 내부 Chunk ID,
object storage key와 signed storage URL은 link 입력으로 사용하지 않는다. Material이 연결
해제되었거나 source가 삭제·비가시 상태라 안전한 공개 경로가 없으면 label은 유지하고
link만 `NULL`로 반환한다. 여기에는 내부 `DISCARDED` AI 대표질문도 포함되며,
`source_kind=QUESTION`과 `label_snapshot`은 그대로 유지한다. 그 밖의
접근 가능한 source는 link가 반드시 non-null이다.
연결 해제 source Chunk·Evidence의 보관, FK snapshot 전환과
최종 hard delete 시점은 18절의 미정 정책을 그대로 따른다.

## 12. 요청 멱등성·이벤트 발행

### 12.1 `idempotency_records`

`Idempotency-Key`가 필요한 쓰기 요청의 처리 상태와 재응답 데이터를 저장한다. Course 생성 응답처럼 참여 코드를 포함할 수 있으므로 응답 본문을 평문 `jsonb`로 보관하지 않는다.

| 컬럼                       | 타입          | NULL | 기본값              | 키·제약                    | 설명                                       |
| -------------------------- | ------------- | ---: | ------------------- | -------------------------- | ------------------------------------------ |
| `id`                       | `uuid`        |    N | `gen_random_uuid()` | PK                         | 멱등성 처리 ID                             |
| `user_id`                  | `uuid`        |    N | -                   | FK → `users.id`            | 요청 사용자                                |
| `session_id`               | `uuid`        |    Y | `NULL`              | FK → `lecture_sessions.id` | Session 종료 시 폐기할 개인 LIVE 요청 범위 |
| `purge_on_session_end`     | `boolean`     |    N | `false`             | CHECK                      | LIVE 종료 시 원 리소스 purge 대상 scope    |
| `http_method`              | `text`        |    N | -                   | CHECK                      | 대문자 HTTP method                         |
| `route_key`                | `text`        |    N | -                   | CHECK                      | path parameter를 정규화한 route ID         |
| `idempotency_key_hash`     | `bytea`       |    N | -                   | -                          | 원문 key의 HMAC                            |
| `request_hash`             | `bytea`       |    N | -                   | -                          | 정규화 요청 method·path·body hash          |
| `state`                    | `text`        |    N | `'PROCESSING'`      | CHECK                      | `PROCESSING`, `COMPLETED`, `FAILED`        |
| `locked_until`             | `timestamptz` |    Y | `NULL`              | -                          | 처리 주체 lease 만료                       |
| `response_status`          | `smallint`    |    Y | `NULL`              | CHECK                      | 완료된 HTTP status                         |
| `response_body_ciphertext` | `bytea`       |    Y | `NULL`              | -                          | AES-GCM 응답 본문                          |
| `response_body_nonce`      | `bytea`       |    Y | `NULL`              | -                          | 암호화 nonce                               |
| `response_key_version`     | `smallint`    |    Y | `NULL`              | CHECK `> 0`                | 응답 암호화 키 버전                        |
| `completed_at`             | `timestamptz` |    Y | `NULL`              | -                          | 완료·실패 terminal 전이 시각               |
| `expires_at`               | `timestamptz` |    Y | `NULL`              | CHECK                      | terminal 전이 후 정확히 24시간             |
| `created_at`               | `timestamptz` |    N | `now()`             | -                          | 최초 요청 시각                             |
| `updated_at`               | `timestamptz` |    N | `now()`             | -                          | 처리 상태 갱신 시각                        |

제약·인덱스:

- `UNIQUE (user_id, http_method, route_key, idempotency_key_hash)`
- `CHECK (NOT purge_on_session_end OR session_id IS NOT NULL)`
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
- `INDEX idempotency_records_session_purge_idx (session_id, id) WHERE purge_on_session_end`
- `user_id ON DELETE CASCADE`
- `session_id ON DELETE SET NULL`; `purge_on_session_end=true`는 LIVE 종료 시 원 리소스가 제거되는 요청임을 표시할 뿐, 그 멱등성 행을 조기 삭제할지와 종료 뒤 어떤 응답을 재사용할지는 아직 확정하지 않는다. 일반 terminal 재응답은 Session 삭제 뒤에도 `session_id=NULL`로 24시간 유지할 수 있다.

같은 key로 다른 `request_hash`가 오면 `409 IDEMPOTENCY_KEY_REUSED`를 반환한다. `PROCESSING` record의 lease는 60초이며 유효하면 중복 처리를 시작하지 않고 `409 IDEMPOTENCY_REQUEST_IN_PROGRESS`를 반환한다. lease가 만료된 행은 다음 동일 요청이 소유해 복구한다. `COMPLETED` 또는 `FAILED`로 terminal 전이할 때 `completed_at`과 nominal `expires_at = completed_at + interval '24 hours'`를 함께 기록한다. `purge_on_session_end=false`이면 같은 응답을 정확히 24시간 재사용하고, true인 개인 LIVE AI 행의 조기 삭제·재응답은 아래 미정 정책을 따른다. 일반 cleanup은 terminal이면서 `expires_at <= now()`인 행만 삭제한다.

LIVE Summary 요청, `mode=LIVE` Chat 생성·Message 요청과 해당 `LIVE_SUMMARY`·LIVE-mode `CHAT_RESPONSE` Job 재시도처럼 Session 종료 때 원 리소스가 제거되는 개인 AI write는 `session_id`를 기록하고 `purge_on_session_end=true`로 표시한다. FINAL Summary, `REVIEW` Chat·Job 재시도와 일반 요청은 `purge_on_session_end=false`다. 이 표시는 purge와 늦은 Worker commit을 fence하기 위한 내부 scope이며, 종료 뒤 in-flight polling·단건 조회·동일 멱등 키 요청에 `404`, 상태 충돌 또는 별도 terminal 응답 중 무엇을 반환할지와 행을 조기 삭제할지는 미정이다. 따라서 현재 스키마 설명은 stale `202`를 재생하거나 삭제한다고 어느 쪽도 확정하지 않는다.

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

| API 필드                                         | 계산 기준                                                                                                                                      |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `Course.role`                                    | 현재 사용자의 `course_members.role`                                                                                                            |
| `Course.current_session`                         | 해당 Course의 유일한 `READY`, `LIVE`, `PROCESSING` Session; 없으면 `NULL`                                                                      |
| `LectureSessionSummary.started_at`               | 같은 날짜의 완료 class를 실제 시작 시각으로 구분하는 `lecture_sessions.started_at`                                                             |
| `LectureSession.completed_at`                    | 후처리 완료 시각인 `lecture_sessions.completed_at`                                                                                             |
| `LectureSession.canonical_transcript_version_id` | `lecture_sessions.canonical_transcript_version_id`; 기본 Transcript가 없으면 `NULL`                                                            |
| `TranscriptVersion.is_canonical`                 | Session의 `canonical_transcript_version_id = transcript_versions.id` 여부                                                                      |
| `TranscriptVersion` 공개 상태                    | version row의 `source`, `status`, `last_sequence`, terminal 시각과 Job provenance                                                              |
| `Transcript aggregate.status`                    | Session lifecycle에 맞는 최신 LIVE 또는 RECORDING version 상태; canonical 포인터와 독립                                                        |
| `TranscriptSegment` 재생 위치                    | `recording_start_ms`, `recording_end_ms`; HTTP byte Range가 아닌 녹음 시간축                                                                   |
| `Question.cluster`                               | state의 `current_generation`과 `question_cluster_members.question_id`로 현재 `question_clusters` join                                          |
| `Question.cluster` 공개 lifecycle                | Cluster의 대표 질문, `generation`, `ordinal`, `is_final`, `finalized_at`, `created_by_job_id`, `created_by_job_attempt`                        |
| `AIRepresentativeQuestion`                       | `ACTIVE/PRESERVED` 독립 행의 ID·exact text·QuestionStatus·Job provenance·`created_in_generation`; `DISCARDED`는 공개 조회에서 제외             |
| `Question.reacted_by_me`                         | 현재 사용자의 `question_reactions` 존재 여부                                                                                                   |
| `Question.reaction_count`                        | `questions.reaction_count`; 원장은 `question_reactions`                                                                                        |
| `Answer.target`                                  | `target_question_id`, `target_representative_question_id` 중 값이 있는 하나와 `target_text_snapshot`                                           |
| `Answer.answer_type`                             | `source_transcript_version_id IS NOT NULL`이면 `VOICE`, `NULL`인 text-only 완료 Answer면 `TEXT`                                                |
| `Answer.start_sequence`, `end_sequence`          | `start_segment_id`, `end_segment_id`의 `transcript_segments.sequence`                                                                          |
| `Answer.canonical_transcript_mapping`            | canonical version 대상 `answer_transcript_mappings`; 없으면 `NULL`, 상태와 mapped Segment 범위 공개                                            |
| `SessionRecording`                               | `session_recordings`의 공개 상태·media metadata; 내부 key와 publisher hash는 제외                                                              |
| `RecordingUpload`                                | `recording_uploads`의 ID·공개 상태·offset·total·expiry; temp key는 제외                                                                        |
| `AIJob.target`                                   | `session_id`와 typed target FK; Chat 응답이면 Chat과 immutable USER Message, 클러스터링이면 mode·input sequence·base revision 포함             |
| `AIJob.result`                                   | 결과 테이블의 `created_by_job_id`와 현재 `created_by_job_attempt`; generic result FK는 없음                                                    |
| `AIJob.progress`                                 | `progress_stage`, `progress_percent`를 안전한 공개 객체로 조립                                                                                 |
| `AIJob` 공개 lifecycle                           | `visibility`, `attempt`, `version`, `blocks_session_completion`, `retryable`, `updated_at`                                                     |
| `FinalSummary.state`                             | latest HQ RECORDING source, 논리 `FINAL_SUMMARY` Job과 현재 attempt의 `lecture_summaries` 결과를 함께 대조해 계산                              |
| `ChatMessage.response_job_id`                    | `USER`이면 `ai_jobs.target_user_message_id = chat_messages.id`인 유일한 `CHAT_RESPONSE` Job ID, `ASSISTANT`이면 `NULL`                         |
| `SessionRecord`                                  | Session·Recording·Transcript·Summary·clustering·후처리 상태, 리소스별 count와 전용 REST path만 조립하는 manifest                               |
| `ChatEvidence.source_kind`                       | 내부 typed source FK를 `MATERIAL`, `TRANSCRIPT`, `QUESTION`, `ANSWER`로 축약. 학생·AI 대표 질문은 모두 공개 `QUESTION`                         |
| `ChatEvidence.label`                             | `chat_message_evidence.label_snapshot`의 생성 시점 안전한 source 표시 snapshot                                                                 |
| `ChatEvidence.link`                              | Material·질문·Answer 공개 ID 또는 Session·TranscriptVersion·stable sequence/time range로 만든 상대 경로; 공개 source가 없으면 `NULL`            |

FINAL Summary projection은 다음 조합만 정상으로 인정한다. `LIVE_SUMMARY` 결과·Job은 이 projection에 포함하지 않는다.

| Source·Job·결과 원장                                                                                                                                                   | 공개 상태·이유                                       |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `READY`, 또는 `LIVE`에서 FINAL source 평가 전이며 FINAL Job·결과 없음                                                                                                  | `summary=NULL`, Job 없음은 정상                      |
| `PROCESSING`에서 Recording upload·HQ source gate가 아직 비terminal이고 FINAL Job·결과 없음                                                                             | `PENDING`, reason·summary·Job 없음                   |
| latest HQ RECORDING이 `FINALIZED`, Segment 1건 이상이고 Session `PROCESSING`의 `FINAL_SUMMARY` Job이 `PENDING` 또는 `RUNNING`                                          | `PENDING`, reason·summary 없음, Job 있음             |
| Session `COMPLETED`에서 명시적 Summary retry, 또는 HQ retry 성공 뒤 `SESSION_POSTPROCESSING attempt > 1` 복구가 만든 `FINAL_SUMMARY` Job이 `PENDING` 또는 `RUNNING` | `PENDING`, reason·summary 없음, Job 있음             |
| 같은 source의 `FINAL_SUMMARY` Job이 `SUCCEEDED`이고 현재 attempt의 호환되는 FINAL Summary가 정확히 1건                                                                 | `AVAILABLE`, reason 없음, Summary·Job 있음           |
| latest HQ RECORDING이 정상 `EMPTY`이고 FINAL Job·Summary가 없음                                                                                                        | `NOT_APPLICABLE`, `NO_FINAL_TRANSCRIPT`              |
| Recording source가 없거나 latest HQ RECORDING이 `FAILED`, 또는 10분 deadline까지 HQ 결과가 없고 FINAL Job·Summary가 없음                                               | `FAILED`, `SUMMARY_SOURCE_UNAVAILABLE`               |
| 유효한 source의 `FINAL_SUMMARY` Job이 `FAILED`이고 결과가 없음                                                                                                         | `FAILED`, reason은 `NULL`, Job의 안전한 error로 설명 |
| RECORDING `FINALIZED`·Segment 1건 이상인데 FINAL Job이 없거나, `SUCCEEDED` Job의 현재 attempt Summary가 없거나 source 범위가 불일치                                    | `DATA_INTEGRITY_ERROR`                               |
| 복구 coordinator와 무관한 `COMPLETED` 최초 FINAL Job이 active, `EMPTY`·source unavailable에 Job·Summary 존재, non-`SUCCEEDED` Job에 Summary 존재 등 위 조합 외 모든 경우 | `DATA_INTEGRITY_ERROR`                               |

coordinator는 latest HQ RECORDING `FINALIZED`와 Segment 1건 이상을 확정한 source handoff에서 Session당 하나인 `FINAL_SUMMARY` Job을 downstream outbox와 함께 원자 생성한다. `EMPTY`와 source unavailable은 Job을 만들지 않는다. HQ retry가 `COMPLETED` 뒤 성공하면 같은 `SESSION_POSTPROCESSING` 행을 `attempt + 1`로 자동 requeue하고, 그 복구 attempt가 새 source의 Answer mapping·canonical KnowledgeChunk 연결을 멱등 재조정한 뒤 아직 없는 FINAL Summary Job을 생성한다. 이 경우 Session을 `PROCESSING`으로 되돌리지 않으며 새 FINAL Summary의 최초 attempt가 active여도 coordinator recovery가 끝날 때까지 정상 `PENDING`이다. 기존 `ANSWER_ORGANIZATION` Job·결과의 immutable source는 바꾸거나 자동 재생성하지 않는다. deferred integrity·reconciliation은 FINAL Summary의 `session_id`, `summary_type=FINAL`, `visibility=COURSE_MEMBERS`, `requester_user_id=NULL`, source version·Segment 범위와 producer Job의 `job_type=FINAL_SUMMARY`, `visibility=SHARED`, 현재 attempt가 모두 일치하는지 검증한다. recovery coordinator가 terminal인데도 eligible source의 Job이 없으면 `DATA_INTEGRITY_ERROR`로 projection한다.

`SessionRecord`는 Material, Transcript Segment·Gap, Question, Cluster·member, Answer,
AIJob 본문 배열과 Summary 본문을 embed하지 않는다. Session과 권한이 허용한 nullable
Recording metadata만 직접 조립한다. 하나의 SQL statement 또는 동일 snapshot을 유지하는
read transaction에서 현재 권한과
각 전용 조회 API의 visibility 조건을 똑같이 적용해 상태와 count를 계산한다. attached
Material과 `SHARED` Job만 count하고 개인 Summary·Chat·`REQUESTER_ONLY` Job은 manifest로
누출하지 않는다. 질문 `list_url`은 복습 cursor 정렬을 불변 `created_at DESC, id DESC`로
고정하는 `sort=RECENT`를 포함한다. 각 path는 API root 기준 상대 경로이며 cursor나 배열
위치를 포함하지 않는다. manifest를 읽은 뒤 리소스가 바뀔 수 있으므로 count는 그 응답 시점 snapshot이고,
실제 page의 `items`와 이후 항상 같다는 보장은 하지 않는다. 영구 데이터와 최신 상태의
최종 진실은 각 전용 REST 조회다.

cursor 조회의 DB 정렬·고정 범위는 다음과 같다.

| 리소스             | 고정 범위와 keyset 정렬                                                                                                     | 지원 인덱스·제약                                                                                                                                                        |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Material           | `session_id`, `detached_at IS NULL`, `(created_at ASC, id ASC)`                                                             | `lecture_materials_session_idx`                                                                                                                                         |
| Transcript         | cursor의 `transcript_version_id`, `(start_ms ASC, SEGMENT 우선, id ASC)` union page; 응답에서 `segments[]`, `gaps[]`로 분리 | `transcript_segments_time_idx`, `transcript_gaps_version_time_idx`                                                                                                      |
| Question `RECENT`  | `session_id`, nullable status, `(created_at DESC, id DESC)`                                                                 | `questions_session_recent_idx`; status filter가 있으면 `questions_recent_idx`                                                                                           |
| Question `POPULAR` | `session_id`, nullable status, `(reaction_count DESC, created_at DESC, id DESC)`                                            | `questions_session_popular_idx`; status filter가 있으면 `questions_popular_idx`. 반응 변경으로 정렬값이 바뀔 수 있으므로 cursor snapshot 보장 범위는 API 계약을 따른다. |
| Answer             | `session_id`, `(started_at ASC, id ASC)`                                                                                    | `answers_session_started_idx`                                                                                                                                           |
| Cluster            | state가 선택한 고정 generation, `(ordinal ASC, logical_cluster_id ASC)`                                                     | `question_clusters_session_idx`, generation별 ordinal·logical ID UNIQUE                                                                                                 |
| Cluster member     | cursor가 고정한 물리 generation Cluster, `(position ASC)`                                                                   | `question_cluster_members` PK, `question_cluster_members_cluster_idx`                                                                                                   |
| Shared AIJob       | `session_id`, `(created_at DESC, id DESC)`                                                                                  | `ai_jobs_session_shared_created_idx`                                                                                                                                    |

모든 cursor는 scope·filter와 정렬 tuple을 포함하는 서버 생성 불투명 값이고, 동일 정렬
값에서는 `id` 또는 generation 안의 unique ordinal을 마지막 tie-breaker로 사용한다.
Transcript cursor는 첫 page의 version에 고정된다. Cluster generation 교체 중 이전
cursor의 만료·재시작 계약은 별도 미정 사항이며 generation을 가로질러 안정적이라고
과장하지 않는다. 같은 `lecture_date`의 완료 class 목록은 `started_at DESC, id DESC`를
추가한다. Material 목록·상세 조회는 `detached_at IS NULL`을 강제한다. content 조회는
이에 더해 `processing_status IN ('UPLOADED', 'PROCESSING', 'READY')`를 강제하고 `FAILED`는
`404 MATERIAL_NOT_FOUND`로 숨긴다. Chat
vector 검색은 반드시 SQL 안에서 `course_id`와 `session_id`를 제한하고, Material
source에는 `lecture_materials.detached_at IS NULL AND processing_status = 'READY'`를
추가한다. 검색 후 애플리케이션에서 다른 Session이나 연결 해제 Material 결과를 제거하는
방식을 사용하지 않는다.

## 14. 주요 트랜잭션·동시성 규칙

멱등성 record를 쓰는 transaction은 도메인 변경과 terminal 응답을 같은 commit에 넣는다. terminal 전이 시 `completed_at = now()`, `expires_at = completed_at + interval '24 hours'`를 함께 기록한다. `purge_on_session_end=true`인 개인 LIVE 요청의 결과 리소스·Job은 14.8절에서 삭제하지만 멱등성 행 자체의 조기 삭제와 종료 뒤 재응답 의미는 18절의 미정 정책으로 남긴다.

### 14.1 Course 생성·참여·코드 회전·삭제

Course 생성은 다음 항목을 한 트랜잭션으로 처리한다. `Idempotency-Key`는 선택 사항이며,
1·5항의 멱등성 처리는 헤더가 제공된 요청에만 적용한다.

1. 헤더가 제공됐으면 `idempotency_records`를 선점하고 동일 요청인지 확인한다.
2. 서버가 참여 코드를 생성하고 정규화한다.
3. HMAC lookup hash와 AES-256-GCM 암호문을 만든다.
4. `courses`와 생성자의 `course_members(PROFESSOR)`를 함께 삽입한다.
5. 헤더가 제공됐으면 암호화한 응답과 멱등성 terminal 상태·`completed_at`·`expires_at`을 기록한다.

참여 시 정규화한 `[A-Z]{6}` 코드의 HMAC으로 Course를 찾은 뒤 Course 또는 멤버 행을 잠근다. 코드는 자동 만료하지 않으므로 만료 시각을 검사하지 않는다. `(course_id, user_id)`를 멱등 upsert하되 기존 `PROFESSOR` 역할을 `STUDENT`로 변경하지 않는다. 선택적인 `Idempotency-Key`가 제공되면 같은 transaction에서 멱등성 원장도 처리한다. HMAC UNIQUE 충돌이 난 코드 생성은 새 코드를 만들어 제한 횟수만큼 재시도한다.

제품 참여 코드 회전은 owner 권한과 멱등성 record를 확인하고 Course 행을 잠근 뒤 새 코드의 hash·ciphertext·nonce·key version, Course `version`, 멱등성 terminal 응답을 한 transaction에서 교체한다. commit 전에는 기존 코드가 유효하고 commit 뒤에는 새 코드만 유효하다. 이전 코드나 회전 이력 행은 만들지 않는다.

Course 삭제 권한은 불변 owner에게만 있다. Course에는 별도 종료 상태를 만들지 않는다. active class가 있을 때 삭제를 허용할지와 삭제 후 복구 유예 정책은 미정이므로 구현에서 임의로 hard delete·soft delete 중 하나를 확정하지 않는다. 삭제가 허용되는 조건이 충족된 뒤에는 `Course → Session → Material → Recording → Upload → TranscriptVersion → ClusteringState → Answer → AIJob` 순서로 잠그고 PDF·Recording final object key와 active Upload temp key를 수집해 storage cleanup outbox와 멱등성 `204` terminal 응답을 남긴 다음 Course aggregate를 한 transaction에서 cascade 삭제한다. outbox의 `session_id`는 부모 삭제 시 `NULL`이 되어도 내부 cleanup payload와 event ID로 처리할 수 있어야 한다.

### 14.2 class 생성·제목 수정·시작·삭제

- class 생성은 Course 행을 잠근 뒤 active class가 없는지 확인한다. 동일 날짜의 완료 이력과는 충돌하지 않으므로 순차적으로 여러 행을 허용한다. partial UNIQUE가 동시 생성 경쟁의 최종 방어선이며 충돌은 `409 ACTIVE_SESSION_EXISTS`로 변환한다. 새 `lecture_sessions`와 requested/applied/revision이 모두 0인 `question_clustering_states` 1:1 행을 같은 transaction에서 만든다.
- 제목 수정은 Session 행을 잠그고 모든 상태에서 허용한다. trim 후 빈 값이면 `Course 제목 · YYYY.MM.DD HH:mm` 자동 제목으로 치환하고 `version`, `updated_at`, 공유 outbox event를 함께 갱신한다. 날짜는 `lecture_date`, 시각은 최초 `created_at`의 `Asia/Seoul` 표시값이며 `lecture_date`와 이미 기록된 lifecycle 시각은 수정하지 않는다.
- 시작은 Session을 잠근 뒤 `detached_at IS NULL`인 Material을 ID 순서로 잠근다. 연결된 Material 중 `processing_status = 'PROCESSING'`이 하나라도 있으면 `409 MATERIAL_PROCESSING_ACTIVE`로 거부한다. PDF가 0개이거나 연결된 행이 `READY`, `UPLOADED`, `FAILED`뿐이면 시작을 허용하고 `status = 'READY'` 조건으로 `LIVE`, `started_at`, Session `version`과 `FINALIZING` LIVE TranscriptVersion을 함께 만든다. LIVE 중 기본 Transcript 조회가 사용할 canonical 포인터도 이 version으로 설정한다.
- 시작을 포함한 active 상태 경쟁의 최종 방어선은 `lecture_sessions_one_active_per_course_uq`다. 충돌은 `409 SESSION_STATE_CONFLICT`로 변환한다.
- 실시간 audio ticket은 시작 권한과 `LIVE` 상태를 확인한 뒤 별도 짧은 트랜잭션에서 발급한다.
- class 삭제는 owner가 `READY`, `COMPLETED`에서만 실행하고 `LIVE`, `PROCESSING`에서는 `409 SESSION_STATE_CONFLICT`로 거부한다. 삭제 transaction은 멱등성 record를 선점한 뒤 `Session → Material → Recording → Upload → TranscriptVersion → AIJob` 순서로 대상 aggregate를 잠그고 PDF·Recording final object key와 Upload temp key를 수집한다. storage cleanup outbox와 멱등성 `204` terminal 응답을 남긴 다음 Session aggregate를 cascade 삭제한다. 삭제된 Job의 이전 attempt worker는 Job ID·attempt·run token·`RUNNING` 조건을 만족하지 못해 늦은 결과를 commit할 수 없다.

### 14.3 PDF 업로드·전처리·연결 해제

Material 관련 transaction의 잠금 순서는 `Session → Material → AIJob`이다. 업로드는 새 Material·Job을 만들기 전에 Session을 잠그고, Material worker claim은 잠금 없는 후보 탐색 뒤 이 순서로 행을 잠근 다음 Job의 `PENDING` 조건을 다시 검증한다. Material을 `UPLOADED`에서 `PROCESSING`으로 바꾸는 worker와 class 시작이 같은 Session 잠금에서 직렬화되므로, worker가 먼저 전이하면 시작은 `MATERIAL_PROCESSING_ACTIVE`로 실패하고 시작이 먼저 commit되면 이후 `LIVE`에서 전처리를 계속할 수 있다.

업로드는 다음 규칙을 따른다.

1. 해당 Course의 `PROFESSOR` 권한을 확인하고 파일을 임시 영역에서 검증한다. `byte_size > 100000000`은 `413 FILE_TOO_LARGE`, PDF MIME·parsing 검증 실패는 `415 UNSUPPORTED_MEDIA_TYPE`으로 변환한다.
2. 서버 생성 `storage_key`로 object를 저장한 뒤 Session을 잠그고 상태를 다시 확인한다. `READY`, `LIVE`, `COMPLETED`에서는 허용하고 `PROCESSING`에서는 `409 SESSION_STATE_CONFLICT`로 거부하며, 거부·DB 실패 시 저장 object를 보상 삭제한다.
3. `detached_at IS NULL`인 Material이 10개 미만인지 확인한다. 10개면 `409 MATERIAL_LIMIT_EXCEEDED`로 거부하고, 동시 삽입은 active-count trigger가 최종 차단한다.
4. 정규화한 `original_filename`과 별도 `display_name`을 만든다. 연결된 이름과 충돌하면 확장자 앞에 ` (1)`, ` (2)` 순 suffix를 붙여 partial UNIQUE를 만족시키며 기존 행의 이름은 바꾸거나 재번호를 매기지 않는다.
5. `lecture_materials`, `MATERIAL_PROCESSING` Job, queue outbox event와 제공된 멱등성 키의 terminal `202` 응답을 같은 DB transaction에서 만들고 commit한다. 같은 키·요청은 기존 결과를 재사용하지만 키가 없거나 서로 다른 키인 별도 요청은 파일 내용과 `original_filename`이 같아도 새 Material을 만들며 content hash UNIQUE를 두지 않는다.

Worker claim과 결과 transaction은 `detached_at IS NULL`인 대상만 처리한다. 처리 성공은 Job의 `target_material_id`, 현재 attempt, run token, `RUNNING`, Material의 현재 `version`, `detached_at IS NULL`을 모두 확인하고 Material `READY`·`processed_by_job_id` 갱신과 Job `SUCCEEDED` 전환을 함께 commit한다. KnowledgeChunk 삽입은 PR-18 RAG Worker의 별도 범위다. 조건이 달라진 늦은 결과는 저장하지 않는다.

Material 연결 해제는 해당 Course의 `PROFESSOR`가 요청할 수 있고 Session이 `READY`, `LIVE`, `COMPLETED`일 때 허용한다. `PROCESSING`에서는 `409 SESSION_STATE_CONFLICT`로 거부한다. transaction은 `Session → Material → AIJob` 순서로 잠근 뒤 다음을 수행한다.

1. `detached_at IS NULL`인 Material을 찾지 못하면 `404 MATERIAL_NOT_FOUND`를 반환한다. 조회 뒤 드문 동시 요청으로 version 조건 갱신이 실패하면 `409 MATERIAL_DELETE_CONFLICT`로 구분한다.
2. `detached_at = now()`, `version + 1`, `updated_at`을 한 번에 기록한다. `processing_status`에는 새 `DETACHED` 값을 추가하지 않는다.
3. 아직 결과를 만들지 않은 대상 `MATERIAL_PROCESSING` Job이 `PENDING`, `RUNNING`이면 같은 transaction에서 `CANCELLED`로 전이하고, `FAILED`이면 `retryable=false`로 바꾼다. Worker는 Job 행과 Material version·tombstone을 모두 확인하므로 늦은 결과를 저장할 수 없다. 성공 결과의 provenance로 참조되는 `SUCCEEDED` Job은 Evidence·Chunk 보관 정책이 확정될 때까지 유지한다.
4. object 삭제 요청과 필수 멱등성 키의 terminal `204` 응답을 같은 transaction에 기록하고 commit한다. 현재 outbox payload는 안전한 Material ID만 가지며 cleanup worker가 내부 tombstone에서 storage key를 조회한다. PR-18 이후에는 참조되지 않은 Material source KnowledgeChunk 정리를 같은 task에 추가한다. 같은 키·요청의 재실행은 tombstone 뒤에도 기존 `204`를 반환한다.
5. commit 직후부터 목록·상세·content 조회와 RAG 검색은 `detached_at IS NULL` 조건으로 해당 Material을 제외한다. 정리 작업 실패가 tombstone을 되돌리지는 않는다.

후속 object cleanup consumer는 object가 이미 없어도 성공으로 처리하고 실패 시 멱등 재시도한다. PR-18의 Knowledge 정리는 참조되지 않은 Material source Chunk를 background에서 삭제한다. 연결 해제 Material의 원문 content link는 제공하지 않는다. 기존 Evidence는 생성 시 저장한 안전한 label을 계속 표시하고 공개 link를 `NULL`로 반환한다. 참조 중인 Chunk의 보관 기간, FK를 별도 source snapshot으로 전환할지와 Material·Chunk 최종 hard delete 시점은 미정이므로 현재 deferred `NO ACTION` FK와 Material tombstone을 유지하고 참조 중인 행을 임의로 삭제하지 않는다.

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
  한 transaction으로 final metadata, `RECORDING_TRANSCRIPTION` blocking Job,
  해당 attempt의 `FINALIZING` RECORDING TranscriptVersion과 outbox를 확정한다.
- upload 만료 worker는 잠금 없는 후보 탐색 뒤 `Session → Recording → Upload`를
  잠그고 여전히 `ACTIVE` 이며 `expires_at <= now()`인지 재확인한다.
  `EXPIRED`·`terminal_at`와 temp cleanup outbox를 같이 commit한다. exact expiry와
  새 upload 재시작 정책은 미정이지만 Session 10분 deadline에서는 남은 Recording과
  Upload을 `FAILED` terminal 처리해 다음 class를 막지 않는다.

### 14.5 Transcript 저장

- streaming STT의 partial 결과는 메모리·WebSocket 전송에만 사용하고 DB에 넣지 않는다.
- live final 결과는 `(transcript_version_id, utterance_id)` upsert 또는 insert-on-conflict로 중복 저장을 막는다.
- 새 `sequence`는 해당 `transcript_versions` row를 잠그고 `last_sequence + 1`을 원자 할당해 Segment insert와 같은 짧은 transaction에서 처리한다. LIVE·RECORDING version sequence는 서로 독립적이다.
- `transcript.final`은 LIVE version Segment commit 뒤에만 발행한다. HQ version status·canonical 전환은 `transcript.version.updated`로 invalidation만 보내고 클라이언트가 version-bound REST를 다시 읽는다.
- 끊김으로 복구할 수 없는 구간은 텍스트를 추측해 채우지 않고 같은 version의 `transcript_gaps`에 남긴다. 조회 cursor는 version ID와 `(start_ms, item kind, id)`를 결합해 Segment와 Gap의 union page를 안정적으로 자른다. API는 그 한 page를 `segments[]`, `gaps[]`로 분리하며 두 배열에 별도 cursor를 발급하지 않는다.
- HQ worker는 비canonical version에서 전체 Transcript 결과와 class·recording 시간축을 검증한 뒤 Session canonical 포인터를 먼저 교체한다. 그 뒤 `SESSION_POSTPROCESSING`이 Answer mapping과 KnowledgeChunk 재연결을 수행한다. 실패·timeout terminal transaction은 해당 version의 staged Segment·Gap을 비우고 `last_sequence = 0`, version·Job `FAILED`를 함께 commit하며 늦은 결과는 공개하거나 검색하지 않는다.

### 14.6 질문·반응·클러스터링

- 질문 생성은 Session과 `question_clustering_states`를 잠그고 `requested_sequence + 1`을 새 `questions.clustering_sequence`에 할당한다. `requested_sequence` 갱신, 필요할 때의 `LIVE_INCREMENTAL` Job·queue outbox와 공개 invalidation `clustering.updated` outbox를 같은 트랜잭션으로 처리한다.
- active 클러스터링 Job과 `retry_job_id`가 모두 없으면 `input_through_sequence = requested_sequence`, `base_revision = current_revision`인 fresh Job을 자동 생성한다. `PENDING`·`RUNNING` Job 또는 retry 예약된 `FAILED` LIVE Job이 있으면 새 Job을 만들지 않고 watermark만 올린다.
- Job 생성·claim·terminal·retry 전이마다 state의 `last_job_id`, `last_job_attempt`, `last_job_status`를 같은 transaction에서 현재 값으로 갱신하고 `clustering.updated` outbox를 기록한다.
- 반응 추가·삭제는 `(question_id, user_id)` 실제 삽입·삭제 성공 여부에 따라 `questions.reaction_count`를 같은 트랜잭션에서 `+1/-1` 한다.
- 자기 질문 반응 금지는 Question을 읽어 작성자를 비교하는 조건부 DML 또는 constraint trigger로 보장한다.
- `LIVE_INCREMENTAL` 입력은 `(applied_sequence, input_through_sequence]`의 새 학생 질문이다. 기존 generation의 학생 질문과 `PRESERVED` 대표 질문은 다른 semantic Cluster로 이동시키지 않는다. 기존 학생 membership의 부모 `logical_cluster_id`는 새 generation에서도 동일해야 한다. 새 질문을 받은 Cluster만 중앙 대표 질문을 재생성하고, 필요하면 새 logical Cluster를 만든다. unchanged Cluster도 새 generation snapshot으로 복사하되 기존 `logical_cluster_id`, 대표 질문 ID와 membership을 그대로 사용한다.
- 대표 질문이 교체될 때 old 대표 질문에 Answer가 없으면 이전 generation 참조를 제거하고 관련 `knowledge_chunks`와 `chat_message_evidence`를 확인한다. 관련 Chunk를 참조하는 Evidence가 0건이면 대표 질문을 hard delete하고 `ON DELETE CASCADE`로 Chunk도 제거한다. Evidence가 하나라도 있으면 대표 질문을 `status=OPEN`, `lifecycle_status=DISCARDED`, `discarded_at=now()`, `version + 1`인 내부 tombstone으로 바꾸고 Chunk를 유지한다. 두 경우 모두 새 generation 공개와 동시에 과거 대표질문을 Cluster·대표질문 공개 조회·UI·RAG에서 제외한다. `CAPTURING` 또는 `COMPLETED` Answer가 있으면 기존대로 `lifecycle_status`를 `ACTIVE → PRESERVED`로 바꾸고, 새 대표 질문이 중앙인 Cluster에 `question_cluster_members.representative_question_id` child로 넣는다. `status`는 Answer 상태인 `SELECTED` 또는 `ANSWERED`를 유지하며 같은 Cluster의 다른 질문 상태를 바꾸지 않는다.
- worker 결과 transaction은 Session, state, Job을 잠그고 `RUNNING`, 현재 attempt·run token, `base_revision = current_revision`, mode에 맞는 Session 상태를 다시 검증한다. 성공 deferred trigger는 LIVE이면 기존 generation의 학생·PRESERVED membership을 정확히 한 번씩 새 generation에 보존하고 기존 학생의 `logical_cluster_id`가 같은지, `(applied_sequence, input_through_sequence]`의 새 학생 질문이 각각 정확히 한 번만 포함됐는지 검증한다. FINAL이면 `clustering_sequence <= input_through_sequence`인 모든 학생 질문과 `completed_at <= final_answered_through_at`인 `COMPLETED` Answer target 대표 질문이 각각 정확히 한 번, 미답변 대표 질문은 0번 포함됐는지 검증하고 모든 logical ID가 새 값인지 확인한다. 모델이 어느 주제에도 확정적으로 배치하지 못한 입력도 누락하지 않고 하나의 `기타` Cluster에 포함한다. 예상 집합과 membership의 set equality가 성립한 뒤에만 새 generation의 대표 질문·Cluster·typed membership, `applied_sequence = input_through_sequence`, `current_revision + 1`, `current_generation`, Job `SUCCEEDED`, `clustering.updated` outbox를 한 번에 commit한다. 누락·중복 membership이 있으면 `기타` 표시 여부와 무관하게 성공할 수 없고, 검증 실패나 이전 attempt의 늦은 결과는 전부 폐기한다.
- 성공 직전 `requested_sequence > input_through_sequence`이면 현재 Job을 `SUCCEEDED`로 끝낸 같은 transaction에서 새 `LIVE_INCREMENTAL` Job 하나와 queue outbox를 자동 생성한다. 새 질문 여러 개는 이 다음 Job 하나에 합쳐지고 하나의 `clustering.updated`가 새 generation·다음 Job 상태를 함께 invalidate한다.
- retry 가능한 LIVE 실패 transaction은 부분 결과를 폐기하고 Job을 `FAILED`로 끝낸 뒤 `retry_job_id = job.id`와 `clustering.updated` outbox를 함께 기록한다. 그동안 새 질문은 `requested_sequence`만 증가시킨다. scheduler는 예약된 같은 행을 원래 captured watermark와 revision으로 `attempt + 1`, active `PENDING`으로 바꾸고 예약을 해제하면서 queue·`clustering.updated` outbox를 같은 transaction에 기록한다. 성공 뒤에만 `requested_sequence > applied_sequence`인 backlog 전체를 새 fresh Job으로 만든다.
- `FINAL` 입력은 `input_through_sequence` 이하의 모든 학생 질문과 `final_answered_through_at`까지 `COMPLETED` Answer가 연결된 AI 대표 질문이다. 현재 중앙인지 과거 child인지와 무관하며 답변하지 않은 AI 대표 질문은 포함하지 않는다. 최초 Job은 두 상한을 종료 시점에 캡처한다. 실패 FINAL의 교수자 명시적 retry에서는 학생 질문 상한은 유지하되 `base_revision`을 현재 revision으로, Answer 상한을 `now()`로 재캡처해 그 사이 완료된 대표질문 Answer를 포함한다. FINAL은 기존 배치를 유지하지 않고 입력 전체를 처음부터 다시 클러스터링하며 대표 질문 생성까지 한 Job에 포함한다.
- FINAL 대상 집합이 0건일 때 Job을 생략할지, 성공한 빈 Job 원장을 만들지와 `final_generation`을 `NULL` 또는 빈 generation 중 무엇으로 표현할지는 미정이다. 이 결정을 worker가 임의로 빈 Cluster 성공으로 굳히지 않는다.
- FINAL 결과는 set equality 검증 뒤 새 logical ID만 가진 generation의 Cluster에 `is_final=true`, 동일 `finalized_at`을 기록하고 `current_generation = final_generation`, `applied_sequence = input_through_sequence`, `current_revision + 1`과 `clustering.updated`를 원자 확정한다. 현재 final 세트는 Session 삭제 전까지 보관한다.
- 새 generation을 공개한 뒤 이전 generation의 Cluster·membership을 같은 transaction에서 삭제해 일반 변경 이력을 보관하지 않는다. 삭제된 generation의 과거 `SUCCEEDED` Job은 파생 `result_unavailable_reason=SUPERSEDED`로 조회한다. 다만 Answer target인 `PRESERVED` 대표 질문과 immutable text·provenance는 삭제하지 않는다.
- 클러스터 similarity 기준, 모델·prompt, LIVE 실패 retry backoff·최대 횟수는 미정이다. Cluster 목록은 `GET /api/v1/sessions/{session_id}/question-clusters`에서 고정 generation 안의 `ordinal ASC, logical_cluster_id ASC`, child는 `GET /api/v1/sessions/{session_id}/question-clusters/{logical_cluster_id}/members`에서 `position ASC` cursor pagination을 사용하고 공개 child `ordinal = position`이다. child 조회는 `(session_id, logical_cluster_id)`로 현재 generation row를 해석하여 다른 Session의 Cluster를 잘못 연결하지 않는다. 두 endpoint 모두 기본 `limit=20`, 최대 `100`이다. generation 교체 중 이전 cursor의 만료 오류·처음부터 재시작 계약과 클라이언트가 한 번에 preload할 page 수·점진 loading·layout만 미정이며, generation을 가로질러 cursor가 stable하다고 보장하지 않는다.

### 14.7 Answer 시작·완료·취소

LIVE 음성 Answer 시작은 다음 순서로 처리한다.

1. Session과 clustering state를 잠그고 `LIVE`인지, 요청자가 해당 Course의 `PROFESSOR`인지 확인한다.
2. `CAPTURING` Answer가 없는지 확인한다. 경쟁 요청은 partial UNIQUE가 최종 차단한다.
3. 학생 질문 또는 현재 AI 대표 질문 중 target 하나를 잠근다. target별 Answer가 이미 있으면 거부하고 partial UNIQUE가 경쟁 요청을 최종 차단한다.
4. target exact text를 `target_text_snapshot`에 복사하고 현재 LIVE `source_transcript_version_id`, 그 version의 마지막 final `sequence`를 저장해 `CAPTURING` Answer를 만든다.
5. 학생 질문과 대표 질문 모두 target `status`를 `SELECTED`로 바꾸고 Answer event를 outbox에 기록해 commit한다.

완료 시 첫·마지막 Segment를 잠그고 둘이 Answer와 같은 Session인지, `start.sequence <= end.sequence`, `start.sequence > capture_started_after_sequence`인지 검증한다. 이를 deferrable constraint trigger로도 이중 검증한다. Answer를 `COMPLETED`로 바꾸고 선택한 학생 질문 또는 대표 질문 target 하나의 `status`만 `ANSWERED`로 바꾼 뒤 outbox event를 함께 기록한다.

취소는 `CAPTURING`에서만 허용한다. Answer를 hard delete하고 선택한 학생 질문 또는 대표 질문 target 하나의 `status`를 `OPEN`으로 되돌리며 `answer.deleted` outbox만 취소 사실 동기화를 위해 기록한다. Answer 취소 원장·감사 snapshot은 남기지 않는다. 아직 중앙 `lifecycle_status=ACTIVE` 대표 질문은 유지하고 이후 교체 transaction에서 Answer 없는 old 대표 질문과 같은 Evidence-aware 폐기 분기를 적용한다.

target 대표 질문의 `lifecycle_status=PRESERVED`이면 현재 generation membership에서 제거하므로 clustering 결과의 공개 내용이 바뀐다. 이 취소는 `Session → question_clustering_states → active 또는 retry-reserved LIVE Job → Answer/target → representative KnowledgeChunk` 순서로 잠근 뒤 다음을 한 transaction에서 수행한다.

1. Answer와 PRESERVED membership을 삭제하고 target `status=OPEN`으로 Answer 상태를 해제한다. 관련 KnowledgeChunk를 참조하는 Evidence가 없으면 대표 질문을 hard delete하고 Chunk를 cascade한다. Evidence가 있으면 `lifecycle_status=PRESERVED → DISCARDED`, `discarded_at=now()`, `version + 1`로 전이해 대표 질문·Chunk를 내부 provenance tombstone으로 유지하되 공개 조회·UI·RAG에서는 즉시 제외한다.
2. state의 `current_revision + 1`로 late-result fence를 전진시킨다.
3. 기존 active `PENDING`·`RUNNING` LIVE Job이 있으면 `FAILED`, `retryable=false`, `error_code=CLUSTER_REVISION_CHANGED`, `finished_at=now()`로 끝내고 run token·lease를 지운다. `retry_job_id`가 가리키는 예약 Job도 같은 nonretryable 오류로 고정하고 예약을 해제한다.
4. `requested_sequence > applied_sequence`이면 현재 `requested_sequence`와 증가한 `current_revision`을 캡처한 fresh `LIVE_INCREMENTAL`, `SHARED`, nonblocking Job과 queue outbox를 만든다. backlog가 없으면 새 Job을 만들지 않는다.
5. state의 last Job snapshot과 `clustering.updated`, `answer.deleted` outbox를 최종 상태에 맞춰 함께 기록한다.

fence된 Worker의 늦은 결과는 Job 상태·run token과 `base_revision != current_revision` 조건으로 폐기된다.
이 revision fence와 outbox 순서는 hard delete·`DISCARDED` 분기와 무관하게 유지한다. 이후 마지막 Evidence를 삭제하는 cleanup transaction은 tombstone 대표 질문을 함께 hard delete하고 Chunk를 cascade해야 하며, 이미 공개 결과에서 제거된 내부 정리이므로 revision을 다시 올리지 않는다.

Session이 `COMPLETED`이면 교수자는 `status=OPEN`인 학생 질문에만 `text_content`가 있는 text-only `COMPLETED` Answer를 바로 만들고 target `status`를 `ANSWERED`로 바꿀 수 있다. 새 text-only Answer를 최종 복습용 대표질문이나 미답변 `ACTIVE` 대표질문에 만들 수는 없다. 학생 질문 또는 Answer 때문에 `PRESERVED`된 AI 대표질문을 target으로 하는 기존 `COMPLETED` Answer에는 target·snapshot·음성 범위를 바꾸지 않고 text를 보충·수정할 수 있다. 이때도 target당 Answer 최대 하나를 유지한다. 수업 후 text Answer의 최대 길이, 완료 Answer 삭제, 새 text Answer로 인해 FINAL 마인드맵을 다시 만드는 방식은 미정이다.

### 14.8 class 종료와 후처리 완료

종료 요청은 요청 자체의 멱등성 record를 선점한 뒤 `purge_on_session_end=true`인 해당 Session의 멱등성 행을 `id` 순서로 먼저 `FOR UPDATE` 잠근다. 그 다음 `Session → LIVE Summary → LIVE Chat·Message·Evidence → 관련 REQUESTER_ONLY AIJob → question_clustering_states → active/retry clustering AIJob` 순서로 잠근다. 개인 LIVE 요청도 자신의 멱등성 행을 먼저 잠그고 Session을 잠그므로 종료와 새 요청이 같은 순서를 사용한다. 종료 transaction은 READ COMMITTED에서 Session 잠금 직후 purge scope를 다시 조회해 첫 조회와 Session 잠금 사이 먼저 commit한 LIVE 요청의 결과·Job도 삭제 집합에 포함한다. Session을 기다리던 새 요청은 전이 후 상태 재검증에서 거부된다. 단, 이미 terminal인 멱등성 행 자체의 보존과 종료 뒤 재요청 응답은 별도 미정 정책을 따른다.

1. `LIVE` 상태이고 `CAPTURING` Answer가 없는지 확인한다.
2. 모든 `summary_type=LIVE` `lecture_summaries`, `mode=LIVE` `chat_sessions`와 cascade되는 Message·Evidence를 삭제한다. 해당 Session의 모든 `LIVE_SUMMARY`, 그리고 삭제 대상 Chat을 target으로 하는 `CHAT_RESPONSE` `REQUESTER_ONLY` Job을 결과 aggregate와 같은 deferred transaction에서 삭제한다. `purge_on_session_end=true` 멱등성 행은 잠가 race를 막되 조기 삭제·24시간 보존과 종료 뒤 응답 의미는 미정이므로 여기서 어느 한쪽으로 고정하지 않는다. FINAL Summary·`FINAL_SUMMARY` Job, `mode=REVIEW` Chat과 관련 Job·멱등성 행은 건드리지 않는다.
3. LIVE Chat Evidence cascade로 `DISCARDED` 대표질문의 마지막 Evidence가 사라지면 기존 deferred cleanup이 그 tombstone과 source Chunk를 같은 transaction에서 hard delete한다. Evidence가 남아 있으면 tombstone도 유지하며 이 정리는 공개 clustering revision을 바꾸지 않는다.
4. active `LIVE_INCREMENTAL` 클러스터링 Job과 `retry_job_id` 예약을 해제하고 Session 상태·revision·run token fence로 이후 결과와 재실행을 막는다. 이때 Job을 `CANCELLED`/`SUPERSEDED`로 확장할지, 기존 enum의 비재시도 `FAILED`로 표현할지는 미정이므로 `SESSION_ENDED` 오류와 terminal 상태를 migration에 고정하지 않는다. state의 마지막 Job snapshot과 공개 응답도 이 결정 뒤 함께 확정한다.
5. `PROCESSING`, `ended_at`, 새 `version`으로 바꿔 추가 audio, 개인 LIVE AI와 새 실시간 클러스터링을 즉시 차단한다.
6. Recording이 있으면 `CAPTURING → UPLOAD_PENDING`, `capture_ended_at`을 같이
   기록한다. Recording이 없어도 Session 종료 자체는 허용한다.
7. LIVE TranscriptVersion을 drain한 뒤 Segment가 있으면 `FINALIZED`, 없으면
   `EMPTY`로 terminal 처리한다. Session당 하나인 `SESSION_POSTPROCESSING`, `SHARED`,
   `blocks_session_completion=true` coordinator Job을 `PENDING`으로 만든다. Recording이
   있으면 source가 terminal이 될 때까지 claim할 수 없게 두고, 없으면 즉시 실행 가능하게 한다. 같은 종료 transaction은 FINAL 대상이 1건 이상이면 종료 시점의 `requested_sequence`, `current_revision`, `ended_at`을 각각 `input_through_sequence`, `base_revision`, `final_answered_through_at`으로 고정한 별도 `FINAL` clustering Job도 함께 만든다.
8. `clustering.updated`를 포함한 공유 상태 outbox와 종료 요청 자체의 idempotency 응답을 기록한다. 개인 Summary·Chat 삭제 본문이나 ID를 공용 event에 싣지 않는다.

삭제 대상 개인 Job이 `RUNNING`이어도 행 자체와 결과 target이 없어지고 run token도 더 이상 현재 Job에서 조회되지 않으므로 늦은 Worker 결과는 저장되지 않는다. 결과 commit은 Job ID·attempt·run token·`RUNNING`뿐 아니라 Summary 또는 Chat target과 Session mode/state가 모두 존재·일치해야 한다. 따라서 purge 뒤 도착한 성공 응답이 삭제된 결과를 되살릴 수 없다.

종료된 LIVE 클러스터링 Worker의 늦은 결과는 Session이 더 이상 `LIVE`가 아니고 revision·run token fence가 바뀌었으므로 commit되지 않는다. 이 Job의 공개·영구 terminal 상태 표현은 미정이지만 LIVE 재시도 예약은 해제한다. 같은 LIVE→PROCESSING 종료 transaction은 FINAL 대상이 1건 이상이면 별도의 `FINAL`, `input_through_sequence = requested_sequence`, `base_revision = current_revision`, `final_answered_through_at = ended_at`, `SHARED`, `blocks_session_completion=true` 클러스터링 Job과 queue·event outbox를 생성한다. 이 Job은 Recording upload·HQ source·coordinator와 무관하게 즉시 실행할 수 있다. 대상 0건의 Job·빈 generation 표현은 18절 미정 정책을 따른다. 이 Job이 실패한 뒤 교수자가 명시적으로 retry하면 학생 질문 `input_through_sequence`는 유지하고 `base_revision = current_revision`, `final_answered_through_at = now()`로 재캡처한다. 그 새 상한까지 완료된 AI 대표질문 Answer는 retry 입력에 포함한다. 성공한 FINAL은 자동으로 다시 만들지 않으며, 성공 후 text Answer에 따른 FINAL 마인드맵 재생성은 별도 미정이다.

Recording 저장 gate는 blocking Job 개수와 별도로 평가한다. Recording이
`UPLOAD_PENDING`이나 `UPLOADING`인 동안은 다른 blocking Job이 모두 terminal이어도
Session을 `COMPLETED`로 바꾸지 않는다. upload finalize outbox가 `UPLOADED`를
commit한 뒤에만 `RECORDING_TRANSCRIPTION`, `SHARED`,
`blocks_session_completion=true` Job과 해당 attempt의 `FINALIZING`
TranscriptVersion을 만든다. HQ worker는 비canonical version에 Segment·final Gap을
준비하고 전체 녹음 재처리·시간 매핑을 검증한 뒤 짧은 transaction에서
`FINALIZED` 또는 `EMPTY`, canonical 포인터와 Job terminal을 함께 확정한다. HQ
`FAILED`를 포함해 source가 terminal이 되는 transaction은 PENDING coordinator의
`available_at`과 queue outbox도 함께 갱신한다.

`SESSION_POSTPROCESSING`은 source가 terminal이 된 뒤에만 claim한다. 최신 HQ source가
`RECORDING FINALIZED`이면 Answer mapping·KnowledgeChunk 재연결과 FINAL Summary를
준비한다. 그런 다음 모든 `COMPLETED` voice-backed Answer에 대해 현재 HQ version의 `SUCCEEDED` mapping이 있으면 그 범위를 우선하고, 없으면 Answer의 원본 LIVE 범위를 사용해 `ANSWER_ORGANIZATION`, `SHARED`, `blocks_session_completion=true` Job을 Answer당 하나씩 생성한다. Job에 복사한 source typed 컬럼은 이후 mapping 변경·retry에도 고정한다. RECORDING `EMPTY`는 `NO_FINAL_TRANSCRIPT`, Recording source 자체가 없으면
즉시 `SUMMARY_SOURCE_UNAVAILABLE`로 확정한다. Recording은 있지만 HQ `FAILED` 또는 HQ 결과 없는
deadline이어도 `SUMMARY_SOURCE_UNAVAILABLE`이며, 보존된 LIVE 포인터는 final source
정책이 정해질 때까지 자동 FINAL Summary에 사용하지 않는다. Transcript와 독립적인
LIVE→PROCESSING transaction에서 이미 생성한 final clustering은 독립 실행을 계속한다. HQ mapping이 없거나 실패해도 Answer organization은 원본 LIVE 범위로 계속 예약한다. coordinator의 terminal 전이 transaction은 실행 가능한
FINAL Summary·Answer organization 등 source 의존 downstream blocking Job과 queue outbox를
먼저 생성한 뒤 coordinator를 `SUCCEEDED` 또는 `FAILED`로 끝낸다. 따라서 HQ Job이
terminal이 된 순간과 downstream Job 생성 사이에 Session이 먼저 `COMPLETED`가 되는
구간이 없다. HQ 실패는 기존 PDF·질문·Answer·LIVE version 조회를 유지하고, 재연결
일부 실패도 해당 후처리 결과로 격리한다. `COMPLETED` 뒤 같은 `RECORDING_TRANSCRIPTION`
행의 retry가 성공하면 그 success transaction은 Session과 기존 coordinator를 잠가
`SESSION_POSTPROCESSING`을 같은 행의 `attempt + 1`로 자동 requeue한다. Session 상태와
`completed_at`은 유지한다. 복구 coordinator는 새 canonical version의 Answer mapping과
KnowledgeChunk 연결을 멱등 재조정하고 새 HQ source에 적합한 FINAL Summary Job이 없으면
생성한다. 이미 존재하는 `ANSWER_ORGANIZATION` Job·결과의 고정 source를 바꾸거나 성공
결과를 자동 재생성하지 않는다.

각 blocking Job 또는 Recording gate가 terminal이 될 때 worker·watchdog는 같은 Session
행을 먼저 잠근다. 미완료 blocking Job과 비terminal Recording·Upload가 모두 없으면
성공·실패 여부와 관계없이 Session을 `COMPLETED`로 바꾸고 `completed_at`을 기록한다.
실패 Job과 Transcript 상태는 완료 기록에 그대로 노출해 나중에 retry할 수 있게 한다. Answer organization 실패는 다른 Answer 정리·Transcript·Summary·clustering 결과를 되돌리거나 열람을 막지 않는다.
동시에 끝나는 worker 경쟁은 reconciliation이 같은 predicate로 보정한다. 완료 후
retry는 같은 Job 행의 attempt를 늘리지만 Session을 `PROCESSING`으로 되돌리지 않는다. 실패한 Answer organization도 고정된 source snapshot으로 같은 Job 행을 retry하며, 성공한 organization은 재생성하지 않는다.
HQ 실패 또는 HQ 결과 없이 deadline에 도달했을 때 보존된 LIVE 포인터를 완료 기록의
final source로 인정할지는 미정이며 완료 여부와 분리한다.

### 14.9 AIJob claim·재시도·결과 commit

- worker claim은 `status = 'PENDING' AND available_at <= now()`를 `FOR UPDATE SKIP LOCKED`로 선택한다. `SESSION_POSTPROCESSING`은 여기에 Recording이 없거나 Recording/HQ source가 terminal이라는 조건을 추가해 조기 claim을 막는다.
- 단, 개인 AI Job은 Job을 먼저 잠그는 위 generic claim에서 제외한다. 후보 ID는 잠금 없이 읽고 `LIVE_SUMMARY`는 해당 Session의 purge-scoped idempotency 행을 `id` 순서로 잠근 뒤 `Session → AIJob`, `CHAT_RESPONSE`는 `purge-scoped IdempotencyRecord → Session → Chat → target USER Message → AIJob` 순서로 잠근다. REVIEW Chat에는 purge 행이 없지만 `Session → Chat → target USER Message → AIJob` suffix는 동일하다. claim·result commit·retry가 모두 이 순서를 사용하고 마지막 Job 잠금 뒤 `PENDING`/`RUNNING`, available time, requester·visibility, immutable target, attempt·run token과 Session mode를 재검증한다.
- claim 시 `RUNNING`, `run_token`, `lease_expires_at`, `started_at`을 함께 기록한다.
- Worker는 15초마다 현재 `run_token`이 일치하는 Job의 lease를 `now() + 60 seconds`로 연장한다.
- watchdog은 60초간 lease 갱신이 없거나 `started_at + 5 minutes`를 넘긴 일반 후처리 Job을 `FAILED`로 terminal 처리한다. `RECORDING_TRANSCRIPTION`에 이 5분 기본값을 적용할지 별도 상한을 둘지는 미정이며, 어떤 경우에도 Session 전체 `ended_at + 10 minutes` deadline은 적용한다.
- Session `ended_at + 10 minutes`가 되면 Session·coordinator를 먼저 잠근다. `FINAL_SUMMARY`를 제외한 아직 없는 적용 가능한 downstream blocking Job을 `FAILED`, `retryable=true`, `started_at=NULL`, `finished_at=now()`, `error_code=SESSION_PROCESSING_TIMEOUT`으로 만들고 Summary 상태를 확정한다. 유효한 RECORDING `FINALIZED` source에 FINAL Summary Job이 없으면 합성하지 않고 `DATA_INTEGRITY_ERROR`로 표시한다. 이때 Job이 없는 모든 `COMPLETED` voice-backed Answer에는 HQ 성공 mapping 우선·LIVE 원본 fallback source를 고정한 `ANSWER_ORGANIZATION` 실패 Job을 하나씩 합성한다. 그 뒤 coordinator, 남은 blocking `PENDING`·`RUNNING` Job과 nonterminal Recording·Upload를 `FAILED`로 만들고 완료 predicate를 다시 평가한다.
- 결과 테이블 삽입과 Job `SUCCEEDED` 전이는 같은 트랜잭션이다.
- 결과 commit 조건에는 `id`, `attempt`, `run_token`, `RUNNING` 상태를 모두 포함한다.
- 실패는 안전한 code/message만 저장하며 원문 PDF, 질문, prompt, provider 응답을 오류 칼럼이나 로그에 넣지 않는다.
- worker lease 만료와 일반 Job timeout은 `FAILED` terminal과 안전한 오류 code로 기록한다. `CANCELLED`는 대체 작업 없는 명시 중단, `SUPERSEDED`는 새 logical Job 또는 generation이 기존 작업을 대체한 terminal 상태이며 둘 다 `retryable=false`다. 종료 transaction에서 FINAL clustering Job이 LIVE clustering 입력을 대체하면 LIVE Job은 `SUPERSEDED`로 끝낸다.
- 재시도는 멱등성 record와 같은 Job 행을 잠그고 `FAILED`이며 `retryable = true`인지 확인한 뒤에만 허용한다. 새 Job을 만들지 않고 같은 행에서 `attempt + 1`, `version + 1`, `PENDING`으로 전환하며 `run_token`, lease, progress, error, `started_at`, `finished_at`을 초기화한다. 재시도 queue outbox와 멱등성 `202` terminal 응답도 같은 transaction에 기록한다.
- 실패 `FINAL` clustering의 교수자 명시적 retry는 state와 Job을 잠그고 `input_through_sequence`는 유지하되, `base_revision = current_revision`, `final_answered_through_at = now()`로 재캡처한 뒤 `attempt + 1`로 전환한다. 새 시각 상한까지 완료된 AI 대표질문 Answer를 포함하며 stale revision commit을 막는다. 성공한 FINAL은 이 경로로 재생성하지 않는다.
- 실패 `ANSWER_ORGANIZATION` retry는 target Answer와 `input_transcript_version_id`·`input_start_segment_id`·`input_end_segment_id`를 수정하지 않고 같은 행의 `attempt + 1`만 사용한다. Session이 `COMPLETED`면 상태를 되돌리지 않는다.
- 실패 `RECORDING_TRANSCRIPTION` retry는 같은 Job 행의 `attempt + 1`과 새 RECORDING TranscriptVersion을 사용한다. `COMPLETED` 뒤 성공하면 같은 coordinator 행을 `attempt + 1`로 자동 requeue해 Answer mapping·canonical KnowledgeChunk·새롭게 생성 자격을 얻은 FINAL Summary를 재조정한다. 기존 `ANSWER_ORGANIZATION` source와 성공 결과는 그대로 두며 Session을 `PROCESSING`으로 되돌리지 않는다.
- 자동 `LIVE_INCREMENTAL` retry는 외부 API 멱등성 record 대신 `Session → clustering state → retry_job_id Job` 순서로 잠근 scheduler transaction으로 수행한다. 원래 `input_through_sequence`·`base_revision`을 유지하고 `attempt + 1`, queue·`clustering.updated` outbox를 기록한 뒤 `retry_job_id`를 `NULL`로 바꾼다. 새 질문 backlog를 이 retry 입력에 합치지 않는다.
- 실패 attempt의 부분 결과는 commit하지 않으므로 retry가 기존 성공 결과를 덮어쓰지 않는다. `RECORDING_TRANSCRIPTION`이 staging Segment·Gap을 이미 저장했다면 실패·timeout transaction에서 모두 삭제하고 `last_sequence = 0`, version·Job `FAILED`를 함께 확정한다. 이전 attempt의 늦은 worker 결과는 현재 `attempt`, `run_token`, `RUNNING` 조건을 만족하지 못해 폐기한다. 성공 결과 재생성 기능은 MVP retry와 분리된 명시적 후속 정책으로 다룬다.

### 14.10 Chat 메시지와 근거

Chat 생성·Message 요청은 Course 멤버라면 역할과 무관하게 허용하되 `LIVE` mode는 Session `LIVE`, `REVIEW` mode는 Session `COMPLETED`에서만 처리한다. 멱등성 행을 먼저 잠그고 Session과 `chat_sessions`를 잠가 mode·owner·상태를 재검증한다. 사용자 Message는 trim·Unicode NFC 정규화 뒤 code point 길이가 1~2,000이 아니면 저장하거나 자르지 않고 `422 VALIDATION_ERROR`로 거부한다.

LIVE Message 생성·Job retry는 해당 Session의 purge-scoped 멱등성 행 전체를 `id` 순서로 잠근 뒤 `Session → Chat → target USER Message → AIJob` 순서를 사용한다. Worker claim·결과도 후보를 무잠금 조회한 뒤 같은 순서로 잠근다. 이 순서는 종료 purge의 `purge-scoped IdempotencyRecord → Session → LIVE Summary → Chat·Message·Evidence → AIJob`과 공통 prefix를 가지므로 purge가 Chat을 가진 채 Job을 기다리고 Worker가 Job을 가진 채 Chat을 기다리는 역순을 금지한다.

유효한 Message 요청은 Chat의 다음 sequence인 `USER` Message를 먼저 insert한 뒤 같은 transaction에서 이 행을 `target_user_message_id`로 고정한 `CHAT_RESPONSE`, `REQUESTER_ONLY`, non-blocking Job, 내부 queue outbox와 terminal `202` 멱등성 응답을 만든다. Worker는 commit 뒤에만 claim한다. USER Message API의 `response_job_id`는 이 역참조로 계산하고 새로고침 뒤 같은 Job polling을 복구한다. Assistant Message는 producer `created_by_job_id`를 공개 `job_id`로 사용하고 `response_job_id=NULL`이다. 이 두 공개 필드를 `chat_messages` 중복 컬럼으로 저장하지 않는다. Assistant 결과 transaction은 immutable target USER Message·Chat owner·Session mode를 다시 검증하고 최종 Message, `chat_message_evidence`, Job 성공을 함께 commit한다. 생성 중 delta와 실패 attempt의 Assistant 본문은 저장하거나 공용 event로 보내지 않는다. retry는 같은 Job과 `target_user_message_id`를 재사용하므로 이후 turn의 Chat history를 실패 turn 입력으로 바꾸지 않는다. 클라이언트는 요청자 전용 Job을 polling하고 성공 뒤 저장 Message를 REST로 조회한다.

Evidence는 검색 시점 Chunk ID·순위와 안전한 `label_snapshot`이며, 근거 source의 변경 여부와 무관하게 해당 답변이 사용한 Chunk를 가리킨다. 공개 source kind는 내부 Material·Transcript Segment·학생 질문·AI 대표 질문·Answer FK를 각각 `MATERIAL|TRANSCRIPT|QUESTION|ANSWER`로 축약한다. Transcript link는 Segment ID 단건이 아니라 Session·TranscriptVersion과 stable sequence 또는 time range를 사용한다. label·상대 link는 조회 시 현재 접근 가능성을 확인해 계산하고 내부 Chunk ID는 반환하지 않는다. LIVE Message 요청은 `idempotency_records.session_id`와 `purge_on_session_end=true`를 기록하고 REVIEW 요청은 false다.

### 14.11 Outbox 발행

도메인 행과 outbox 행을 같은 transaction에 저장하고 commit 후 publisher가 발행한다. 발행 완료 전 장애가 나면 같은 event를 재발행할 수 있으므로 client와 내부 consumer는 event ID와 resource version으로 중복·역순을 처리한다.

현재 PR-11 publisher는 FastAPI process 안에서 `published_at IS NULL`인 행을
`FOR UPDATE SKIP LOCKED`로 작은 batch 단위 claim한 뒤 `published_at`·`publish_attempt`를
commit하고, 그 뒤 process-local WebSocket hub로 전달한다. live 전달 직전 장애는 cursor
replay 또는 REST resync로 복구한다. `outbox_events`는 공용 event와 내부 cleanup/queue hint를
함께 담으므로 Session WebSocket에는 `session.updated`, `job.updated`처럼 공개 계약에 허용된
event만 projection한다. 요청자 전용 AI Job, ticket·session token·storage key와 provider 오류는
outbox payload 또는 공용 event에 넣지 않는다.

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

| 데이터                                                                                                                  | MVP 권장값                                | 처리                                              |
| ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- | ------------------------------------------------- |
| `oauth_transactions`                                                                                                    | 생성 후 10분                              | 사용 완료·만료 후 정기 삭제                       |
| `realtime_tickets`                                                                                                      | 생성 후 60초                              | 사용 완료·만료 후 정기 삭제                       |
| `auth_sessions`                                                                                                         | 발급 후 7일                               | 만료·폐기 후 정기 삭제                            |
| 일반 `idempotency_records`                                                                                              | terminal `completed_at`부터 정확히 24시간 | 암호문 포함 만료 직후 정기 삭제                   |
| `purge_on_session_end=true` 멱등성 행                                                                                   | nominal `expires_at = completed_at + 24 hours` | LIVE purge 뒤 재응답 의미·조기 삭제 여부 미정      |
| 발행 완료 `outbox_events`                                                                                               | 24시간                                    | replay window 후 정기 삭제                        |
| `session_recordings`·녹음 object                                                                                        | 미정                                      | 동의·접근·보관·삭제 정책 확정 후                  |
| terminal `recording_uploads`·temp object                                                                                | exact expiry 미정                         | 만료 후 outbox 멱등 정리                          |
| 연결된 PDF·TranscriptVersion·Segment·Gap·Answer mapping·질문·대표 질문·Cluster·Answer·Answer organization·FINAL Summary | Course 수명                               | Course 관리 삭제·정책 만료 시 삭제                |
| 연결 해제 Material metadata·source Chunk                                                                                | Evidence 정책 확정 전 tombstone 유지      | object는 즉시 비노출·비동기 삭제                  |
| `DISCARDED` AI 대표 질문·source Chunk                                                                                   | 관련 Evidence 정책과 동일                 | 마지막 Evidence 삭제 transaction에서 함께 cleanup |
| 개인 LIVE Summary·Chat·Message·Evidence·관련 REQUESTER_ONLY Job                                                         | 해당 Session의 LIVE 종료까지              | `LIVE → PROCESSING` transaction에서 hard delete   |
| 개인 REVIEW Chat·Message·Evidence·관련 REQUESTER_ONLY Job                                                               | 계정 또는 Course 수명 중 먼저 도달한 시점 | 사용자 탈퇴·Course·Session 삭제 시 삭제           |
| 실패 `ai_jobs`                                                                                                          | Course 수명                               | 진단 가능한 안전한 metadata만 보관                |

일반 멱등성 record의 24시간은 확정됐다. LIVE 개인 AI의 원 리소스·Job은 Session 종료 시 삭제하지만, 관련 멱등성 행의 조기 삭제와 purge 뒤 polling·재요청 응답 의미는 미정이다. 나머지 보관 기간은 제품의 개인정보 정책 확정 전 운영 기본값이며, 외부 공개 전 법무·운영 검토로 확정한다. 녹음은 동의·접근·보관·삭제가 모두 미정이므로 임시 운영 기본값도 가정하지 않는다.

### 15.3 삭제 순서와 `ON DELETE`

- owner의 Course 삭제는 허용 조건이 확정된 뒤 `course_members`, `lecture_sessions`와 Session 하위 데이터를 aggregate 단위로 cascade한다. active class가 있을 때의 삭제와 복구 유예 정책은 아직 미정이다.
- owner의 class 삭제는 `READY`, `COMPLETED`에서만 허용한다. Session 삭제는 purge-scoped 멱등성 행을 먼저 잠가 race를 막은 뒤 Material, Recording, Upload, TranscriptVersion, Segment, Gap, Answer mapping, Answer organization, clustering state, 대표 질문, Cluster membership, Cluster, Question, Answer, Summary, Chat, KnowledgeChunk와 Job을 함께 정리하며 `LIVE`, `PROCESSING`에서는 거부한다. 멱등성 행은 `session_id=NULL`로 24시간 보존할 수 있으나 LIVE purge 뒤 재응답 의미는 미정 정책을 따른다.
- Question 삭제는 Reaction을 cascade한다. 공유 질문 보존을 위해 User 탈퇴가 Question 삭제로 이어지지는 않는다.
- 교체된 AI 대표 질문은 Answer target이 아니고 관련 source Chunk를 참조하는 Evidence도 없을 때만 Cluster·membership 교체 transaction에서 hard delete한다. Evidence가 있으면 `status=OPEN`, `lifecycle_status=DISCARDED`, `discarded_at` tombstone과 Chunk를 유지하되 공개·UI·RAG에서는 즉시 제외하고 Evidence에는 공개 `source_kind=QUESTION`·저장 label·`link=NULL`을 반환한다. `CAPTURING` 또는 `COMPLETED` Answer target이면 `lifecycle_status=PRESERVED` child로 유지하고 독립 삭제를 막는다.
- Answer organization은 Answer 삭제에 cascade하지만 target Answer→Job과 결과→Job의 deferred `NO ACTION`이 독립 삭제를 막는다. Session aggregate 삭제에서는 Answer, organization과 Job을 같은 transaction에서 제거한다.
- Chat 삭제는 Message와 Evidence를 cascade한다. LIVE 종료 purge도 같은 삭제 경로를 사용한다. Evidence 삭제로 `DISCARDED` 대표 질문에 연결된 모든 Chunk의 Evidence가 0건이 되면 같은 deferred transaction의 cleanup이 대표 질문을 hard delete해 해당 Chunk를 cascade한다. cleanup은 마지막 Evidence 삭제와 원자적이므로 orphan tombstone을 남기지 않으며, LIVE Evidence는 종료 시 삭제하고 REVIEW Evidence의 보관은 Course·계정 수명을 따른다.
- 독립적인 `ai_jobs` 삭제는 결과 행의 deferred `NO ACTION` FK 때문에 commit되지 않는다. Session 전체 삭제에서는 Job과 결과가 같은 transaction에서 함께 제거된다.
- KnowledgeChunk 단독 삭제는 Evidence가 참조하면 deferred `NO ACTION` FK가 막는다. 대표 질문 FK의 `ON DELETE CASCADE`와 Evidence FK의 deferred `NO ACTION` 조합은 참조 중 대표 질문의 잘못된 hard delete도 commit 시 막는다. 재색인 시 기존 Chunk를 즉시 삭제하지 말고 새 Chunk·Evidence 처리 정책을 먼저 적용한다.
- Material 연결 해제는 `detached_at` tombstone을 먼저 commit한다. 그 즉시 목록·content·RAG에서 제외하고 object와 참조되지 않은 Material source Chunk는 outbox 기반 background 정리로 삭제한다. 기존 Evidence의 안전한 label은 유지하고 공개 link는 `NULL`이다. Evidence가 참조하는 Chunk의 보관·FK 전환과 Material tombstone의 hard delete 시점은 미정이다.
- 일반 삭제 transaction은 `Course → purge-scoped IdempotencyRecord → Session → Material → Recording → Upload → TranscriptVersion → ClusteringState → Answer → AIJob` 순서로 잠근다. Session 단독 삭제와 LIVE 종료는 교착 방지를 위해 해당 Session의 purge-scoped idempotency 행을 Session보다 먼저 잠그는 명시적 예외를 사용한다. Material lifecycle은 기존 `Session → Material → AIJob`, Recording·HQ lifecycle은 `Session → Recording → Upload → TranscriptVersion → AIJob`, 질문 lifecycle은 `Session → ClusteringState → AIJob → Question/RepresentativeQuestion → KnowledgeChunk`, Answer organization lifecycle은 `Session → Answer → AnswerMapping → AIJob` 순서를 사용한다. 삭제·연결 해제된 Material과 종료된 LIVE clustering·Answer organization, purge된 개인 LIVE Job의 늦은 결과는 각 version·revision·attempt·run token·상태·target 존재 fence에서 폐기한다. Course·Session aggregate 삭제와 LIVE Chat purge는 Chat·Evidence·대표 질문·Chunk를 같은 deferred transaction에서 함께 처리하므로 `DISCARDED` tombstone 때문에 삭제를 막지 않는다.
- PDF·Recording final object와 Upload temp object는 DB cascade로 삭제되지 않는다. aggregate 삭제는 DB 행을 지우기 전에 모든 key를 수집하고 내부 storage cleanup outbox를 남겨 멱등 삭제한다. storage key와 물리 구성은 외부 응답·공유 event·로그에 노출하지 않는다.
- User 탈퇴는 우선 `users.deleted_at`을 기록하고 이름·이메일·avatar를 익명값으로 교체한다. 인증 identity/session과 개인 Chat·LIVE Summary·REQUESTER_ONLY Job은 같은 deferred transaction에서 제거하고, 공유 질문·Answer 작성자 FK는 익명화된 동일 User 행을 가리키게 유지한다.
- `courses.created_by_user_id`, `course_members.user_id`, `lecture_sessions.created_by_user_id`, `questions.author_user_id` 등 공유 `RESTRICT` 참조가 하나라도 있으면 User 행은 영구 tombstone으로 유지하고 hard delete하지 않는다. hard delete는 모든 공유·Reaction·개인 참조가 전혀 없는 계정만 허용한다. Course owner 탈퇴 시 Course와 멤버십을 어떻게 처리할지는 별도 미정 사항이다.

MVP의 질문 일반 hard delete API는 제공하지 않는다. Course·class 삭제는 위 owner 권한, 상태, cascade와 object storage 보상 규칙을 따르는 하나의 관리 workflow로 구현한다.

## 16. 인덱스 운영 원칙

- B-tree 복합 인덱스의 선두 컬럼은 권한·범위 조건인 `course_id`, `session_id`, `owner_user_id`를 우선한다.
- partial UNIQUE와 trigger를 애플리케이션 선조회로 대체하지 않는다. Course당 `READY`·`LIVE`·`PROCESSING` 합계 하나, Session당 연결된 Material 최대 10개와 표시 이름 유일성, Session당 논리 Recording 하나, Recording당 active Upload 하나, Session당 active clustering Job 하나와 FINAL Job 하나, Session당 논리 FINAL Summary Job 하나, generation별 logical Cluster ID 하나, Session당 `CAPTURING` Answer 하나, 학생 질문·대표 질문 target별 Answer 하나, voice Answer당 논리 organization Job·성공 결과 하나는 DB가 최종 보장한다.
- `questions.reaction_count`와 최신 cursor는 실시간 hot path를 위해 저장하되 원장과 reconciliation한다.
- HNSW는 embedding model과 차원이 확정된 뒤 생성한다. Session 범위 B-tree를 함께 두고 실제 데이터 분포로 `ef_search`, `m`, `ef_construction`을 조정한다.
- production index 추가·교체는 가능한 경우 `CREATE INDEX CONCURRENTLY`를 사용하고 migration transaction 제약을 별도로 처리한다.
- `EXPLAIN (ANALYZE, BUFFERS)`로 최근 질문, 인기 질문, final Transcript cursor, Job claim, Chat vector 검색을 우선 검증한다.

## 17. 모델·migration 생성 순서

관계형 골격은 다음 순서로 SQLAlchemy 모델과 Alembic migration에 반영했다.

1. `pgcrypto`, `vector` 확장과 공통 `updated_at` trigger
2. User, Course, CourseMember, LectureSession
3. 인증 Session·OAuth·RealtimeTicket, Material, SessionRecording, RecordingUpload, TranscriptVersion, TranscriptSegment, TranscriptGap, ChatSession
4. Question과 QuestionClusteringState를 Job FK 없이 우선 생성
5. clustering mode·input watermark·base revision을 포함한 AIJob을 생성하되 Material·Transcript·ClusteringState의 Job 순환 FK는 보류
6. AIRepresentativeQuestion, QuestionCluster, QuestionClusterMember, Answer, AnswerTranscriptMapping, AnswerOrganization과 보류한 복합·순환 FK 추가
7. KnowledgeChunk, LectureSummary, ChatMessage, ChatMessageEvidence
8. IdempotencyRecord, OutboxEvent
9. CHECK, partial UNIQUE, 조회 인덱스와 constraint trigger 추가
10. embedding 차원 확정 후 pgvector 타입과 HNSW 인덱스 추가

하나의 거대한 migration 대신 스키마 생성, 순환 FK, 비동기 인덱스를 분리했다. downgrade에서도 외부 object를 자동 복구할 수 없으므로 storage 변화는 별도 runbook으로 다룬다.

## 18. 미정 사항

문서와 사용자 결정만으로 확정할 수 없는 항목은 다음과 같다.

| 항목                                      | 현재 문서 표현                                                                                                                   | 확정 시점                           |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| active class가 있는 Course 삭제           | owner 권한만 확정, 허용 여부·응답 미정                                                                                           | Course 삭제 구현 전                 |
| Course 삭제 후 복구 유예                  | hard delete·soft delete·유예 기간 미정                                                                                           | Course 삭제 구현 전                 |
| Course owner 탈퇴 처리                    | owner 이전은 없고 User tombstone 원칙만 확정                                                                                     | 탈퇴 workflow 구현 전               |
| 클러스터 similarity·모델·prompt           | LIVE incremental·FINAL 입력과 결과 fence만 확정                                                                                  | 모델 평가·운영 비용 확정 후         |
| LIVE clustering 실패 retry                | 같은 Job 행 attempt 증가 원칙만 확정, backoff·최대 횟수 미정                                                                     | worker retry 운영 정책 확정 후      |
| 수업 후 text Answer 후속 처리             | text-only·보충 허용, 최대 길이·삭제·FINAL map rebuild 미정                                                                       | REVIEW 답변 UX·API 확정 전          |
| Answer organization 생성·재색인           | 별도 immutable 결과·고정 source·실패 retry는 확정, 형식·모델·prompt·content 최대 길이·품질·KnowledgeChunk 재색인 정책 미정       | 모델 평가·화면/RAG 계약 확정 전     |
| 마인드맵 generation cursor·UI loading     | cursor 정렬과 limit 20/max 100은 확정, generation 교체 시 이전 cursor 만료 오류·재시작, preload page 수·점진 loading·layout 미정 | 조회 API·UI 시험 후                 |
| FINAL clustering 입력 0건                 | Job 생략 vs 성공 빈 Job 원장, `final_generation=NULL` vs 빈 generation 표현 미정                                                 | 완료 기록·빈 마인드맵 API 확정 전   |
| embedding model·차원                      | `vector(EMBEDDING_DIM)` placeholder                                                                                              | 모델 선택 후 첫 vector migration 전 |
| vector index parameter                    | HNSW 사용 방향만 확정                                                                                                            | staging 데이터 부하 시험 후         |
| outbox replay 보관 기간                   | 발행 완료 후 24시간 권장                                                                                                         | 운영 SLO 확정 전                    |
| 연결 해제 후 Evidence·Chunk 보관·FK       | 안전한 label 유지·공개 link `NULL`은 확정, Chunk 보관 기간·별도 source snapshot/FK 전환은 미정                                   | Material hard delete 구현 전        |
| Material·Chunk 최종 hard delete 시점      | object 비동기 삭제와 tombstone만 확정                                                                                            | Evidence 정책 확정 후               |
| `DISCARDED` 대표질문 보관 기간            | 관련 Evidence가 존재하는 동안만 유지하고 마지막 Evidence 삭제와 원자 cleanup은 확정, Evidence 자체 보관 기간을 따름              | Evidence 보관 정책 확정 시          |
| 녹음 codec·container·browser 저장         | live PCM 규격과 별개임만 확정                                                                                                    | 클라이언 녹음 구현 전               |
| resumable upload protocol·checksum·expiry | offset 원장과 만료 필드만 확정                                                                                                   | upload handler·migration 전         |
| Recording 물리 object cardinality         | Session당 논리 aggregate 1개, file·fragment·manifest 미정                                                                        | storage adapter 확정 전             |
| publisher lease·재획득·takeover           | 첫 HMAC claim·같은 publisher resume만 확정                                                                                       | realtime 다중 process 구현 전       |
| Recording 실패 뒤 재업로드                | 10분 deadline terminal 완료는 확정, 새 upload 재시작 정책 미정                                                                   | upload 복구 UX·API 확정 전          |
| `DEGRADED`·audio stop·replay              | 현재 임계·상태 전이·복구 방식 미정                                                                                               | realtime 장애 계약 확정 전          |
| 녹음 동의·접근·보관·삭제                  | 녹음 저장·권한 재확인만 확정, 정책 미정                                                                                          | 외부 공개·개인정보 검토 전          |
| 녹음 quota·backup·RPO·RTO                 | PDF 제한과 분리 필요, 수치·backend 미정                                                                                          | KCloud 저장소 운영 설계 전          |
| HQ 실패·deadline final source             | LIVE 포인터 보존은 확정, 완료 기록의 final source 인정 여부 미정                                                                 | 완료 기록 fallback 정책 확정 전     |
| HQ STT 개별 Job timeout                   | 일반 후처리 5분·Session 전체 10분은 확정, HQ에도 5분을 적용할지 별도 상한을 둘지 미정                                             | STT 모델·녹음 길이 부하 시험 후     |
| Answer HQ 범위 재매핑                     | 원본·mapping 상태는 확정, tolerance·동률 해소 미정                                                                               | STT 평가 데이터 확정 후             |
| 비canonical Transcript 보관               | 실패 version provenance는 보존, 정리·공개 기간 미정                                                                              | 보관 정책 확정 후                   |
| LIVE AI purge 후 재응답                    | LIVE 결과·Message·관련 Job 삭제와 late-result fence는 확정, 기존 polling·단건 조회·멱등 재요청 응답과 행 조기 삭제 여부 미정       | 개인 AI 종료 경쟁 테스트 전         |

위 항목을 확정하기 전에는 placeholder를 실제 SQLAlchemy 타입이나 irreversible migration으로 굳히지 않는다.

### 18.1 외부 계약 동기화 확인

API 명세와 OpenAPI는 다음 DB 규칙을 같은 변경 묶음에서 반영해야 한다.

- Course 생성자는 유일한 교수자 owner이며 owner 이전은 없다.
- 참여 코드는 `[A-Z]{6}`, 무기한이고 owner 회전 시 이전 코드가 즉시 무효다.
- Course당 `READY`, `LIVE`, `PROCESSING` 합계는 최대 1개이며 `current_session`으로 노출한다.
- 같은 날짜 class는 허용하고 완료 목록은 실제 `started_at`으로 구분한다.
- 제목은 모든 상태에서 수정하고 날짜·lifecycle 시각은 수정하지 않는다.
- `READY`, `COMPLETED` class 삭제만 허용하며 Course 삭제의 active·복구 정책은 미정으로 유지한다.
- 일반 멱등성 terminal 응답은 `completed_at`부터 정확히 24시간 재사용한다. 개인 LIVE AI 원 리소스·Job은 종료 transaction에서 삭제하지만 purge-scoped record의 조기 삭제와 종료 뒤 재응답은 미정이다.
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
- TranscriptVersion source·상태, Session canonical version, version별 Segment·Gap과
  `recording_start_ms`·`recording_end_ms`를 공개 계약과 동일하게 유지한다.
- Transcript page는 version에 고정한 `(start_ms, SEGMENT 우선, id)` union cursor 하나를 사용하고 같은 page를 `segments[]`, `gaps[]`로 분리한다.
- `/record`는 하위 본문 배열 없이 Session·처리 상태·리소스 count·전용 조회 path만 반환하는 manifest이며, Material·Transcript·Question·Answer·Cluster·공용 AIJob은 각각 cursor API로 조회한다.
- `RECORDING_TRANSCRIPTION`은 Recording typed target, TranscriptVersion result,
  `SHARED`, `blocks_session_completion=true`이고 retry는 같은 Job 행을 사용한다.
- LIVE Summary 무근거 409, FINAL `EMPTY`의 `NOT_APPLICABLE / NO_FINAL_TRANSCRIPT`,
  source `FAILED`의 `SUMMARY_SOURCE_UNAVAILABLE`를 Job 없음과 구분한다.
- `PROFESSOR`, `STUDENT`는 같은 권한으로 `LIVE` Session의 개인 Summary·Chat과 `COMPLETED` Session의 `REVIEW` Chat을 사용하며 `READY`, `PROCESSING`에서는 개인 Chat을 만들거나 계속 사용하지 않는다.
- 개인 AI는 `REQUESTER_ONLY` Job polling과 성공한 최종 저장 결과 조회만 제공한다. Chat USER Message는 Worker 전에 trim·Unicode NFC 정규화해 저장하고 1~2,000 Unicode code point를 강제하며 생성 중 Assistant delta·개인 공용 event는 저장·전송하지 않는다. 검증 실패는 `422 VALIDATION_ERROR`다.
- Chat USER Message의 `response_job_id`는 자신을 immutable `target_user_message_id`로 가진 유일한 `CHAT_RESPONSE` Job이고, Assistant는 producer `job_id`만 가지며 `response_job_id=null`이다. Message 본문 row에 이 projection을 중복 저장하지 않는다.
- `LIVE → PROCESSING`은 LIVE Summary·Chat·Message·Evidence와 관련 requester-only Job을 원자 삭제하고 늦은 결과를 차단한다. 이전 ID polling·단건 조회와 purge-scoped 멱등 재요청 응답은 미정이며 FINAL Summary와 REVIEW Chat은 유지한다.
- Final Summary projection은 source gate 미해결의 Job 없는 `PENDING`, RECORDING `EMPTY`의 Job 없는 `NOT_APPLICABLE/NO_FINAL_TRANSCRIPT`, source unavailable의 Job 없는 `FAILED/SUMMARY_SOURCE_UNAVAILABLE`, 유효 source의 Job 상태·결과를 구분한다. RECORDING `FINALIZED` Segment가 있는데 Job이 없거나 성공 Job과 결과 원장이 불일치하면 `DATA_INTEGRITY_ERROR`다.
- Worker 15초 heartbeat, 60초 lease, 일반 후처리 Job 5분, Session 10분 deadline과 실패 포함 Session 완료 predicate를 API·운영 문서와 동일하게 유지한다. HQ STT의 개별 상한은 미정이다.
- 학생 질문 또는 AI 대표 질문 target당 `CAPTURING`·`COMPLETED` Answer는 최대 1개다.
- AI 대표 질문은 독립 ID·immutable exact text·Job provenance·`created_in_generation`을 가지며 Cluster는 `representative_question_id`로 참조한다.
- AI 대표 질문의 Answer 상태는 `OPEN/SELECTED/ANSWERED`, lifecycle은 `ACTIVE/PRESERVED/DISCARDED`로 구분하되 `DISCARDED`는 Evidence provenance용 내부 tombstone이라 공개 대표질문 조회와 RAG에서 제외한다.
- 질문은 Session별 `clustering_sequence`, 클러스터링 Job은 mode·input watermark·base revision을 공개 계약과 맞춘다.
- `QUESTION_CLUSTERING`은 requester 없는 자동 공유 Job이며 Session당 active 하나, FINAL 논리 Job 하나를 유지하고 실패 FINAL은 같은 행에서 retry한다.
- retryable FAILED LIVE Job은 state에 예약해 같은 행·captured input으로 재시도하고, 예약 중 새 질문은 새 Job 없이 requested watermark만 높인다.
- LIVE는 새 질문만 배치하고 기존 질문을 이동시키지 않으며 FINAL은 모든 학생 질문과 답변 완료 대표 질문을 전체 재배치한다. FINAL 성공은 입력별 membership 정확히 하나를 보장하고 분류 불가 입력도 `기타` Cluster에 넣는다.
- Cluster member 공개 discriminator는 내부 typed FK 이름과 분리해 `source_kind=STUDENT_QUESTION|AI_REPRESENTATIVE`를 사용한다.
- LIVE의 기존 Question `cluster_id`는 계승한 `logical_cluster_id`, FINAL의 Cluster ID는 새 logical ID를 사용한다. 물리 Cluster row ID는 공개하지 않는다.
- clustering 성공 전 mode별 기대 입력과 membership set equality를 검증해 누락 상태의 `applied_sequence` 전진을 금지한다.
- 질문 commit, retry 예약·requeue, 성공·다음 Job, PRESERVED 취소와 Session 종료의 state 변경은 `clustering.updated` outbox와 원자 commit한다.
- `CAPTURING` 취소는 Answer를 hard delete하고 `CANCELLED` 기록을 남기지 않는다.
- AIJob retry는 같은 Job ID에서 `attempt`를 증가시킨다.
- Cluster 공개 필드는 `generation`, `ordinal`, `is_final`, `finalized_at`, `created_by_job_id`, `created_by_job_attempt`다.
- Cluster·child cursor limit는 기본 20, 최대 100이고 child 공개 `ordinal`은 DB `position`이다. generation 교체 cursor 만료·재시작은 미정으로 노출한다.
- API `QuestionCluster.revision`은 선택한 current/final `generation`을 가리키는 `question_clustering_states.current_revision`에서 계산한다. Cluster 행에 중복 revision 컬럼을 두지 않는다.
- Answer는 target 한 개와 선택 당시 exact text인 `target_text_snapshot`을 보관한다.
- Answer `answer_type`은 source Transcript FK 유무로 `VOICE/TEXT`를 계산한다.
- 완료 voice Answer당 `ANSWER_ORGANIZATION` 공유 blocking Job은 하나이며 source는 생성 시 HQ 성공 mapping 우선, 없으면 원본 LIVE 범위로 고정한다.
- Answer organization 결과는 수동 `answers.text_content`와 분리하고 이를 덮어쓰지 않으며, 실패 retry는 같은 Job의 `attempt + 1`, 성공 결과는 재생성 없음으로 노출한다.
- Answer `organization_state`는 TEXT=`NOT_APPLICABLE`, LIVE voice=`NOT_STARTED`, PROCESSING coordinator source 대기 중 Job 없음=`WAITING_SOURCE`, Job 존재 시 active/terminal 상태로 계산한다. COMPLETED의 `attempt>1` active retry는 정상이고 최초 attempt active·Job/성공 결과 누락·상태 모순만 `DATA_INTEGRITY_ERROR`다.
- Chat Evidence의 저장 식별자는 `knowledge_chunk_id`다. API는 내부 ID를 제외하고 `MATERIAL|TRANSCRIPT|QUESTION|ANSWER` source kind, 저장한 안전한 `label_snapshot`의 공개 `label`, cursor·배열 위치와 무관한 상대 link만 파생한다. Transcript는 Session·version·stable sequence/time range link를 쓰고 `DISCARDED` 대표질문 Evidence는 `QUESTION`·label을 유지하며 link만 `NULL`이다.
- AIJob `result` link는 결과 테이블의 `created_by_job_id`와 현재 `created_by_job_attempt = ai_jobs.attempt` 역조회로 조립한다. 현재 clustering 결과는 `QUESTION_CLUSTER_GENERATION` aggregate이고 정책적으로 삭제된 과거 generation만 `result=null / result_unavailable_reason=SUPERSEDED`를 허용한다.

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
- [ ] 질문 생성이 state 행을 잠가 `clustering_sequence`와 `requested_sequence`를 함께 증가시키는가?
- [ ] 모든 clustering state 공개 변경이 `clustering.updated` outbox와 같은 transaction인가?
- [ ] retryable FAILED LIVE Job이 `retry_job_id`에 예약되고 fresh Job 생성과 backlog 합류를 막는가?
- [ ] 자동 `QUESTION_CLUSTERING` requester가 NULL이고 Session당 FINAL Job 전체가 하나인가?
- [ ] 클러스터 generation·ordinal·final 상태, requested/applied sequence, revision과 Job attempt provenance를 검증하는가?
- [ ] 물리 Cluster row ID와 공개 `logical_cluster_id`를 분리하고 LIVE 기존 질문의 logical ID를 유지하며 FINAL은 새 ID를 쓰는가?
- [ ] mode별 기대 Question·대표 질문 집합과 membership set equality가 성립하기 전 Job 성공·applied 전진을 거부하는가?
- [ ] LIVE에서 기존 질문을 이동시키지 않고 FINAL에서 대상 전체를 재배치하는가?
- [ ] old 대표 질문은 Answer target이면 `PRESERVED` child로 남기고, 미답변이면 Evidence 부재 시 hard delete·Evidence 존재 시 `DISCARDED` tombstone으로 분기하는가?
- [ ] 대표 질문의 `status`가 `OPEN/SELECTED/ANSWERED` Answer 상태이고 `ACTIVE/PRESERVED/DISCARDED` lifecycle과 분리되는가?
- [ ] 학생 질문 또는 AI 대표 질문 중 target이 정확히 하나이고 target별 Answer가 하나인가?
- [ ] `CAPTURING` 취소가 Answer를 hard delete하며 `CANCELLED` audit을 만들지 않는가?
- [ ] PRESERVED 대표 질문 취소가 revision을 올리고 active/retry Job을 `CLUSTER_REVISION_CHANGED`로 fence한 뒤 backlog fresh Job을 만드는가?
- [ ] PRESERVED 취소의 hard delete·`DISCARDED` 분기 모두 같은 revision fence를 유지하고 마지막 Evidence 삭제 transaction이 tombstone·Chunk를 함께 cleanup하되 revision을 다시 바꾸지 않는가?
- [ ] voice-backed·text-only `COMPLETED` Answer CHECK와 immutable `target_text_snapshot`을 검증하는가?
- [ ] 완료 voice Answer마다 `ANSWER_ORGANIZATION` Job이 정확히 하나이고 `SHARED`·blocking이며 source typed 입력이 생성 뒤 immutable인가?
- [ ] 성공 HQ mapping 우선·원본 LIVE fallback source 선택과 watchdog의 누락 Answer organization Job `FAILED` 합성이 Session 완료 전에 실행되며, eligible FINAL Summary Job 누락은 합성하지 않고 `DATA_INTEGRITY_ERROR`로 분리하는가?
- [ ] `answer_organizations`가 Answer·Job당 최대 하나이고 결과·Job 성공이 원자적이며 `answers.text_content`를 절대 덮어쓰지 않는가?
- [ ] organization 모델 입력이 `target_text_snapshot`과 고정 Transcript 범위뿐이고 교수 `text_content`를 포함하지 않는가?
- [ ] Answer organization 재색인 정책이 확정되기 전 `knowledge_chunks`에 전용 source FK나 자동 Chunk 생성을 추가하지 않는가?
- [ ] `organization_state`가 Answer 형태·Session/coordinator·Job·결과 조합에서 WAITING_SOURCE와 DATA_INTEGRITY_ERROR를 정확히 구분하는가?
- [ ] 실패 organization retry가 같은 Job의 `attempt + 1`을 사용하고 완료 Session을 `PROCESSING`으로 되돌리지 않는가?
- [ ] 모든 AI 생성 root 결과 행에 `created_by_job_id`, `created_by_job_attempt`가 있는가? (입력 Material 상태는 `processed_by_*`, Evidence는 상위 Assistant Message를 통해 귀속)
- [ ] 현재 clustering Job 결과를 generation aggregate로 projection하고 과거 삭제 generation에만 `SUPERSEDED`를 사용하는가?
- [ ] Job 재시도가 같은 행의 `attempt` 증가와 run token 검증을 사용하는가?
- [ ] 멱등성 terminal 응답 만료가 `completed_at + 24 hours`인가?
- [ ] `/record`가 하위 배열 없이 같은 snapshot의 상태·count·전용 path만 반환하는가?
- [ ] Transcript union cursor의 한 page를 `segments[]`, `gaps[]`로 분리하고 두 배열 합계가 limit 이하인가?
- [ ] Question·Answer·Cluster·member·shared Job cursor가 고정 scope와 마지막 tie-breaker를 포함하는가?
- [ ] Chat Evidence가 공통 KnowledgeChunk와 non-null 안전 `label_snapshot`만 저장하고 내부 Chunk ID를 공개하지 않는가?
- [ ] Evidence 공개 link가 상대 API 경로이고 cursor·배열 위치·storage key·signed URL에 의존하지 않는가?
- [ ] `DISCARDED` 대표질문 Chunk가 RAG·공개 조회에서 제외되고 Evidence에는 kind·label과 `link=NULL`만 남는가?
- [ ] deferred invariant가 `DISCARDED` 대표질문마다 관련 Evidence 최소 1건을 강제해 orphan tombstone을 막는가?
- [ ] DB에 generic `source_type + source_id` FK가 없는가?
- [ ] vector 검색이 SQL 단계에서 Course·Session 범위를 제한하는가?
- [ ] partial Transcript는 저장하지 않고 browser 로컬 녹음만 upload 후 영구 저장하는가?
- [ ] Session당 Recording 하나와 Recording당 active Upload 하나를 DB가 보장하는가?
- [ ] publisher HMAC claim이 첫 탭과 같은 ID resume을 구분하고 원문을 로그에 남기지 않는가?
- [ ] upload offset·finalize·expiry가 조건부 전이와 outbox cleanup으로 일관되는가?
- [ ] LIVE·RECORDING TranscriptVersion의 sequence·Segment·Gap이 version 범위로 격리되는가?
- [ ] HQ Segment의 class 시간축과 recording playback 시간축을 혼용하지 않는가?
- [ ] Answer 원본 LIVE 범위를 보존하고 canonical mapping을 별도 원장으로 제공하는가?
- [ ] canonical 전환 전에 Segment·Gap·시간축과 Job fence를 검증하고, 전환 뒤 mapping·Knowledge 재연결 실패를 별도로 격리하는가?
- [ ] Summary가 FINALIZED·EMPTY·FAILED source를 서로 다른 결과와 오류로 해석하는가?
- [ ] Worker 15/60초, HQ STT 제외 일반 Job 5분, Session 10분 timeout 뒤 늦은 결과와 PROCESSING 정체를 막고 HQ 개별 timeout은 미정으로 남겼는가?
- [ ] 삭제 transaction이 PDF·Recording final·Upload temp object 정리 outbox를 남기는가?
- [ ] class 삭제가 `READY`, `COMPLETED`에서만 가능하고 늦은 worker 결과를 fence하는가?
- [ ] Material transaction 잠금 순서가 `Session → Material → AIJob`이고 늦은 결과가 `detached_at`·version을 확인하는가?
