# 26s-w2-c2-08

## 공통과제 II : 협업형 실전 산출물 제작 (2인 1팀)

**목적:** 실시간 인터랙션, LLM Wrapper, Cross-Platform 중 하나의 옵션을 선택해 구현하며, 선택한 기술을 실제로 동작하는 형태의 산출물로 완성한다.

**선택 옵션:**

| 옵션 | 설명 |
|---|---|
| 실시간 인터랙션 | 사용자 간 상태 변화, 실시간 데이터 흐름, 스트리밍 응답 등 실시간성이 드러나는 기능을 구현 |
| LLM Wrapper | LLM API를 활용하여 AI 기능이 포함된 산출물을 구현 |
| Cross-Platform | 하나의 산출물을 여러 실행 환경에서 사용할 수 있도록 구현* |

> *데스크톱 앱 ↔ 모바일 앱; 혹은 다른 폼팩터에서의 앱; 웹만/웹 기반 프레임워크(Electron, Tauri 등) 대신 다른 프레임워크를 시도해보는 것을 적극 권장

**결과물:** 선택한 옵션이 적용된 작동 가능한 산출물, 실행 가능한 코드, 시연 자료 및 관련 문서

---

## 팀원

| 이름 | 학교 | GitHub | 역할 |
|---|---|---|---|
| 박정준 |  |  |  |
| 김도현 |  |  |  |

---

## 선택 옵션

- [ ] 실시간 인터랙션
- [ ] LLM Wrapper
- [ ] Cross-Platform

---

## 기획안

- **산출물 주제:**
- **제작 목적:**
- **선택 옵션:**
- **핵심 구현 요소:**
  -
  -
  -
- **사용 / 시연 시나리오:**
- **팀원별 역할:**

### 개발 일정

| 날짜 | 목표 |
|---|---|
| Day 1 |  |
| Day 2 |  |
| Day 3 |  |
| Day 4 |  |
| Day 5 |  |
| Day 6 |  |
| Day 7 |  |

---

## 구현 명세서

| 구현 요소 | 설명 | 우선순위 |
|---|---|---|
|  |  | 필수 |
|  |  | 필수 |
|  |  | 선택 |
|  |  | 선택 |

---

## 아키텍처

현재 저장소에는 로컬 개발에 필요한 최소 구성만 포함한다.

```text
React + Vite (:5173)
        │ /api proxy
        ▼
FastAPI (:8000)
        │ SQLAlchemy + psycopg
        ▼
PostgreSQL 17 + pgvector (:5432, Docker)
```

Ollama, STT, Nginx, Cloudflare와 운영 배포 환경은 관련 기능을 구현할 때 추가한다.

---

## 설계 문서

> 프로젝트 성격에 따라 필요한 항목만 작성

### 화면 / 인터페이스 설계

<!-- Figma 링크, 화면 이미지, CLI 사용 예시, 앱 화면 등 -->

### 데이터 구조

<!-- DB 스키마, JSON 구조, 파일 저장 방식 등 -->

### API / 외부 서비스 연동

| Method / 방식 | Endpoint / 서비스 | 설명 | 요청 | 응답 | 비고 |
|---|---|---|---|---|---|
| GET | `/api/health` | API 프로세스 상태 확인 | 없음 | `{"status":"ok"}` | DB 비의존 |
| GET | `/api/health/db` | PostgreSQL 연결 확인 | 없음 | DB 연결 상태 | 장애 시 503 |

---

## 산출물 및 실행 방법

- **산출물 설명:** React와 FastAPI로 개발하는 실시간 AI 강의 보조 서비스
- **실행 환경:** Node.js 22, pnpm 11, Python 3.12, uv, Docker Compose
- **실행 방법:** 아래 로컬 개발환경 실행 절차 참고
- **시연 영상 / 이미지:** (선택)

### 사전 요구사항

- Node.js 22.13 이상 23 미만
- Corepack과 pnpm 11.11.0
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker Engine과 Docker Compose

### 최초 설정

```bash
cp .env.example .env
corepack enable
make setup

# PostgreSQL 실행 및 pgvector migration
make db-up
make migrate
```

### 개발 서버 실행

터미널 두 개에서 각각 실행한다.

```bash
# 터미널 1: FastAPI
make dev-api

# 터미널 2: React/Vite
make dev-web
```

접속 주소:

- Frontend: <http://127.0.0.1:5173>
- FastAPI: <http://127.0.0.1:8000>
- API 문서: <http://127.0.0.1:8000/docs>

### 검사 명령

```bash
# 공통 Skill 원본을 Codex·Claude 발견 경로에 복사한 뒤 동일성과 형식 검사
make skills-sync

# 파일을 수정하지 않고 공통 Skill 동기화 상태와 형식만 검사
make skills-check

# PostgreSQL을 포함한 로컬 검증 환경 준비
make db-up

# 공통 Skill, 문서·계약, lint, typecheck, test, migration, build 전체 실행
make check

# DB 없이 실행되는 Backend unit test
make backend-unit

# 현재 구현 endpoint와 canonical OpenAPI의 부분 계약 검사
make backend-contract

# 고유한 임시 DB를 생성·폐기하는 PostgreSQL integration test
make backend-integration

# 빈 임시 DB에서 Alembic upgrade → downgrade → upgrade 검사
make migration-check

# OpenAPI로 다시 생성한 Frontend 타입과 저장된 타입의 차이 검사
make frontend-contract-check

# Markdown UTF-8·code fence·상대 링크 대상 검사
make docs-check

# DB 종료
make db-down
```

`make check`는 사용자의 Docker 상태를 임의로 변경하지 않는다. 먼저 `make db-up`으로
PostgreSQL을 준비해야 하며, DB가 없거나 테스트 DB 생성 권한이 없으면 integration과
migration 검사가 skip되지 않고 명확하게 실패한다. CI도 위와 동일한 Make target을
사용한다.

### 기술 구성

| 분류 | 사용 기술 |
|---|---|
| Frontend | React 19, Vite 8, TypeScript 6, Vitest |
| Backend | FastAPI, SQLAlchemy 2, psycopg 3, Alembic, PyMuPDF |
| 실행 환경 | Node.js 22, pnpm 11, Python 3.12, uv, Docker Compose |
| 데이터 저장 | PostgreSQL 17, pgvector 0.8.2, 로컬 filesystem |
| 품질 관리 | ESLint, Prettier, Ruff, pytest, GitHub Actions |
| 외부 API / 서비스 | Google OAuth 2.0 / OpenID Connect (선택), 이메일·비밀번호 로그인 |

### Backend 공통 경계

- `tbd.app.create_app()`이 FastAPI app과 `/api`, `/api/v1` router 경계를 조립한다. Google 로그인 start·callback, 이메일 가입·로그인, 로그아웃, 현재 사용자 조회, Course 목록·생성·상세·참여·코드 회전과 AIJob polling·retry endpoint가 구현되어 있다.
- app별 SQLAlchemy engine·session factory는 lifespan 종료 시 dispose한다. router와 repository는 transaction을 commit하지 않고, 이후 service·job 계층이 명시적으로 transaction을 소유한다.
- 모든 HTTP 응답은 `X-Request-ID`를 반환한다. 오류는 `{ "error": { "code", "message", "request_id", "details" } }` 형식이며, provider·DB 예외 원문을 응답에 포함하지 않는다.
- 인증은 Google OAuth/OIDC 또는 이메일·비밀번호 로그인 뒤 7일 절대 만료 HttpOnly `goal_session` Cookie를 사용한다. OAuth state는 10분 만료·1회용이며 state·nonce·PKCE로 browser transaction을 검증한다. 이메일 비밀번호는 scrypt hash만 저장하며 reset·이메일 확인·Google 계정 연결은 아직 없다.
- 상태 변경 요청은 `AUTH_ALLOWED_ORIGINS`의 exact Origin 일치를 필수로 검증한다. 운영에서는 HTTPS origin, 고유한 `AUTH_SECRET_KEY`, Google credential과 `AUTH_COOKIE_SECURE=true`도 필수다.
- `APP_ENV=production`에서는 `DATABASE_URL`을 명시하고 repository의 `tbd/tbd_dev` 개발 자격 증명을 사용하지 않아야 한다. `IDEMPOTENCY_RESPONSE_ENCRYPTION_KEY`에는 base64-encoded 32-byte AES-256-GCM 키를 주입한다. Course 참여 코드에는 서로 다른 `COURSE_JOIN_CODE_ENCRYPTION_KEY`와 `COURSE_JOIN_CODE_LOOKUP_KEY`를 주입하고 원문과 key material을 문서·로그·fixture·커밋에 넣지 않는다.

### Google 로그인 설정 (선택)

Google OAuth client의 승인된 redirect URI에 `GOOGLE_OIDC_REDIRECT_URI`를 등록한 뒤 `.env`에 client ID와 secret을 설정한다.

```bash
GOOGLE_OIDC_CLIENT_ID=...
GOOGLE_OIDC_CLIENT_SECRET=...
GOOGLE_OIDC_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
```

개발 로그인 시작 화면은 <http://localhost:5173/login>이다. 테스트는 네트워크를 사용하지 않는 fake provider를 사용하므로 Google credential이 필요하지 않다.

이메일로 가입하려면 Google credential 없이 `/login`에서 **이메일로 로그인** 또는 **이메일 계정 만들기**를 선택하면 된다. 같은 이메일의 Google 계정과 이메일 계정은 자동으로 합쳐지지 않는다.

---

## 회고 문서

> [KPT 방법론 참고](https://velog.io/@habwa/%EB%8B%A8%EA%B8%B0-%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-%ED%9A%8C%EA%B3%A0-KPT-%EB%B0%A9%EB%B2%95%EB%A1%A0)

### Keep — 잘 된 점, 다음에도 유지할 것

-
-
-

### Problem — 아쉬웠던 점, 개선이 필요한 것

-
-
-

### Try — 다음번에 시도해볼 것

-
-
-

### 팀원별 소감

**박정준:**

> 

**김도현:**

> 

---

## 참고 자료

### 실시간 인터랙션

**WebSocket**
- https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API
- https://techblog.woowahan.com/5268/
- https://tech.kakao.com/posts/391
- https://daleseo.com/websocket/
- https://kakaoentertainment-tech.tistory.com/110

**Socket.IO**
- https://socket.io/docs/v4/
- https://inpa.tistory.com/entry/SOCKET-%F0%9F%93%9A-Namespace-Room-%EA%B8%B0%EB%8A%A5
- https://adjh54.tistory.com/549
- https://fred16157.github.io/node.js/nodejs-socketio-communication-room-and-namespace/

**SSE (Server-Sent Events)**
- https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
- https://developer.mozilla.org/ko/docs/Web/API/Server-sent_events/Using_server-sent_events
- https://api7.ai/ko/blog/what-is-sse

**TCP / UDP Socket**
- https://docs.python.org/3/library/socket.html
- https://inpa.tistory.com/entry/NW-%F0%9F%8C%90-%EC%95%84%EC%A7%81%EB%8F%84-%EB%AA%A8%ED%98%B8%ED%95%9C-TCP-UDP-%EA%B0%9C%EB%85%90-%E2%9D%93-%EC%89%BD%EA%B2%8C-%EC%9D%B4%ED%95%B4%ED%95%98%EC%9E%90

**gRPC Streaming**
- https://grpc.io/docs/what-is-grpc/core-concepts/
- https://tech.ktcloud.com/entry/gRPC%EC%9D%98-%EB%82%B4%EB%B6%80-%EA%B5%AC%EC%A1%B0-%ED%8C%8C%ED%97%A4%EC%B9%98%EA%B8%B0-HTTP2-Protobuf-%EA%B7%B8%EB%A6%AC%EA%B3%A0-%EC%8A%A4%ED%8A%B8%EB%A6%AC%EB%B0%8D
- https://tech.ktcloud.com/entry/gRPC%EC%9D%98-%EB%82%B4%EB%B6%80-%EA%B5%AC%EC%A1%B0-%ED%8C%8C%ED%97%A4%EC%B9%98%EA%B8%B02-Channel-Stub
- https://inspirit941.tistory.com/371
- https://devocean.sk.com/blog/techBoardDetail.do?ID=167433

**WebRTC**
- https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API
- https://webrtc.org/getting-started/overview
- https://web.dev/articles/webrtc-basics?hl=ko
- https://devocean.sk.com/blog/techBoardDetail.do?ID=164885
- https://beomkey-nkb.github.io/%EA%B0%9C%EB%85%90%EC%A0%95%EB%A6%AC/webRTC%EC%A0%95%EB%A6%AC/
- https://gh402.tistory.com/45
- https://on.com2us.com/tech/webrtc-coturn-turn-stun-server-setup-guide/

**QUIC / WebTransport**
- https://developer.mozilla.org/en-US/docs/Web/API/WebTransport_API
- https://datatracker.ietf.org/doc/html/rfc9000
- https://news.hada.io/topic?id=13888

#### KCLOUD VM / Cloudflare Tunnel 환경별 주의사항

| 환경 | 사용 가능(권장) 기술 | 포트/조건 | 주의할 기술 |
|---|---|---|---|
| **로컬 / 일반 VM** | HTTP/REST, WebSocket, Socket.IO, SSE, TCP Socket, gRPC Streaming, WebRTC, QUIC/WebTransport 등 대부분 가능 | 직접 포트 개방 가능. 예: 3000, 5000, 8000, 8080, 9000 등. 외부 공개 시 방화벽/보안그룹/공인 IP 설정 필요 | WebRTC는 STUN/TURN 필요 가능. QUIC/WebTransport는 HTTP/3 · UDP 지원 필요 |
| **KCLOUD VM (VPN 내부)** | HTTP/REST, WebSocket, Socket.IO, SSE, WebRTC 시그널링 | 접속 기기 VPN 필요. 기본 허용 포트: **22, 80, 443**. 개발 포트(3000, 8000, 8080 등)는 직접 접근 제한 가능 | TCP Socket은 포트 제한 있음. gRPC는 HTTP/2 설정 필요. WebRTC 미디어·UDP·QUIC/WebTransport 비권장 |
| **KCLOUD VM + Tunnel** | HTTP/REST, WebSocket, Socket.IO, SSE, WebRTC 시그널링 | VM의 `localhost:<port>`를 도메인에 연결. `localPort`는 **1024~65535**. 예: 3000, 8000, 8080 가능 | 순수 TCP Socket, UDP, WebRTC 미디어/DataChannel, QUIC/WebTransport 불가. gRPC 보장 어려움 |
| **외부 서비스 + 우리 도메인** | HTTP/REST, WebSocket, Socket.IO, SSE, WebRTC 시그널링 | Vercel/Netlify/Railway/Render/AWS/GCP 등에 배포 후 CNAME/A 레코드 연결. 보통 외부는 **443** 사용 | WebSocket/gRPC/TCP/UDP는 플랫폼 지원 여부 확인 필요. 서버리스 플랫폼은 장시간 연결 제한 가능 |
| **서버 없이 외부 SaaS 사용** | Supabase Realtime, Firebase, Pusher/Ably, LLM API Streaming | 직접 포트 관리 불필요. 각 서비스 SDK/API 사용 | 커스텀 TCP/UDP 서버 구현 불가. WebRTC는 STUN/TURN 필요할 수 있음 |

### LLM Wrapper

- https://github.com/teddylee777/openai-api-kr
- https://github.com/teddylee777/langchain-kr
- https://devocean.sk.com/blog/techBoardDetail.do?ID=167407
- https://mastra.ai/docs

### Cross-Platform

- https://flutter.dev/
- https://reactnative.dev/
- https://docs.expo.dev/
- https://kotlinlang.org/multiplatform/
