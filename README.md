# GOAL: God Of All Lectures

> 실시간 강의 기록부터 질문, 답변, AI 복습까지 하나로 연결하는 오프라인 수업 보조 서비스

GOAL은 수업 중 교수자의 음성을 실시간 Transcript로 제공하고, 학생이 익명으로 질문하며 놓친 내용을 AI에게 바로 물어볼 수 있도록 돕습니다. 수업이 끝난 뒤에는 전체 녹음을 다시 처리한 고품질 Transcript와 질문·답변, 강의 자료, AI 요약을 한곳에 모아 복습할 수 있습니다.

## 프로젝트 소개

오프라인 강의에서는 학생이 설명을 놓치거나 공개적으로 질문하기 어려운 경우가 많고, 교수자는 여러 학생이 공통으로 어려워하는 지점을 수업 중 파악하기 어렵습니다. 수업이 끝난 뒤에도 실제 강의 내용과 질문·답변이 서로 다른 곳에 흩어져 있어 체계적인 복습이 어렵습니다.

GOAL은 다음과 같은 방식으로 이 문제를 해결합니다.

- 교수자의 음성을 스트리밍 STT로 변환하여 실시간 Transcript 제공
- 익명 질문과 `나도 궁금해요` 반응을 통한 참여 부담 완화
- 유사 질문을 AI가 묶어 대표 질문과 포함 질문을 목록으로 제공
- 현재 Transcript와 강의 자료를 활용한 개인 AI 요약 및 질의응답
- 수업 녹음 전체를 HQ STT로 재처리하여 복습용 Transcript 생성
- Transcript 문장을 선택하면 해당 녹음 시점으로 이동
- 수업별 Transcript, 질문·답변, AI 요약과 자료를 Course 단위로 축적

## 선택 옵션

- [x] 실시간 인터랙션
- [x] LLM Wrapper
- [ ] Cross-Platform

### 실시간 인터랙션

교수자 브라우저에서 전달되는 음성과 강의 상태를 WebSocket으로 처리합니다. Transcript, 질문, 반응, 답변, 클러스터링과 작업 상태 변경을 실시간 이벤트로 전달하며, 연결이 끊어졌을 때는 cursor와 REST API를 이용해 상태를 복원합니다.

### LLM Wrapper

로컬 Ollama 기반 LLM을 provider-neutral wrapper로 연결했습니다. 질문 초안 생성, 실시간 요약, 복습 채팅, 질문 클러스터링, 교수자 답변 정리와 최종 수업 요약을 비동기 Job으로 실행합니다. 요청은 즉시 Job ID를 반환하고 Worker가 백그라운드에서 처리한 결과를 polling하여 보여줍니다.

## 팀원

| 이름 | 소속 | 담당 | GitHub |
| --- | --- | --- | --- |
| 박정준 | 성균관대학교 | 기획, 프론트엔드, UI/UX, 서버 자동 배포 및 관리 | [jungjun0708](https://github.com/jungjun0708) |
| 김도현 | KAIST | 기획, 백엔드, Local LLM, STT | [KimDoDohyeon](https://github.com/KimDoDohyeon) |

## 주요 기능

### 수업 전

- Google 또는 이메일·비밀번호 로그인
- 한 학기 단위 Course 생성 및 참여 코드 기반 학생 등록
- 날짜별 강의 세션 생성
- 강의 자료 PDF 업로드와 백그라운드 전처리
- 교수자와 학생 권한에 따른 Course 화면 제공

### 수업 중

- 교수자 마이크 입력을 실시간 STT와 브라우저 로컬 녹음으로 동시 분기
- partial/final Transcript 실시간 표시
- 학생 익명 질문 작성 및 `나도 궁금해요` 반응
- 유사 질문의 AI 클러스터링과 질문 목록 제공
- 교수자의 질문별 음성 답변
- 현재까지의 Transcript와 자료를 활용한 개인 AI Summary·Chat
- 중복 교수자 탭의 오디오 송출을 차단하는 단일 publisher 제어

### 수업 후

- 재개 가능한 방식으로 원본 녹음 업로드
- Faster-Whisper 기반 전체 녹음 HQ STT 처리
- 문장별 시작·종료 시각과 녹음 재생 위치가 연결된 canonical Transcript 생성
- Transcript 문장을 선택하여 해당 녹음 위치로 이동 및 재생
- 질문과 교수자 답변의 최종 목록 및 AI 정리
- 실제 강의 내용 중심의 Final summary 생성
- 녹음이 누락되어도 확정된 LIVE Transcript를 이용한 Final summary 복구
- 강의 자료, Transcript, AI 요약, 질문·답변을 Course archive에서 통합 탐색
- 완료된 수업 기록을 근거로 한 개인 REVIEW AI 채팅

## 사용 흐름

```text
Course 생성 ── 참여 코드 공유 ── 학생 참여
     │
     ▼
강의 세션 생성 ── PDF 자료 등록 ── 수업 시작
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                    ▼
          실시간 Transcript       익명 질문·반응       개인 AI
                 │                    │                    │
                 └────────────────────┼────────────────────┘
                                      ▼
                                  수업 종료
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                    ▼
           녹음 업로드·HQ STT    질문·답변 후처리      Final summary
                 │                    │                    │
                 └────────────────────┼────────────────────┘
                                      ▼
                            수업 기록 조회 및 AI 복습
```

## 시스템 아키텍처

```text
┌────────────────────────────────────────────────────────────┐
│ React 19 + TypeScript + Vite                               │
│ 교수자/학생 UI · MediaRecorder · REST polling · WebSocket  │
└───────────────────────┬────────────────────────────────────┘
                        │ REST / WebSocket
                        ▼
┌────────────────────────────────────────────────────────────┐
│ FastAPI                                                    │
│ 인증 · Course/Session · Transcript · 질문/답변 · Recording │
│ AI Job · OpenAPI · 권한 및 멱등성 처리                      │
└──────────────┬─────────────────────────────┬───────────────┘
               │                             │
               ▼                             ▼
┌──────────────────────────┐    ┌────────────────────────────┐
│ PostgreSQL 17 + pgvector │    │ Background Workers         │
│ 영구 데이터 · Job 원장   │    │ STT · LLM · PDF · RAG      │
│ vector embedding         │    │ clustering · postprocessing│
└──────────────────────────┘    └──────────────┬─────────────┘
                                               │
                              ┌────────────────┴──────────────┐
                              ▼                               ▼
                    ┌──────────────────┐          ┌──────────────────┐
                    │ Ollama Local LLM │          │ Faster-Whisper   │
                    │ 생성·요약·Chat   │          │ Streaming/HQ STT │
                    └──────────────────┘          └──────────────────┘
```

실시간 Session 이벤트와 오디오 전송은 서로 다른 WebSocket 채널로 분리합니다. LLM·STT·PDF 처리처럼 시간이 오래 걸리는 작업은 API 요청 안에서 실행하지 않고 PostgreSQL 기반 Job 원장과 전용 Worker에서 처리합니다. Worker는 lease와 heartbeat를 이용해 중복 실행과 중단된 작업을 관리합니다.

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Frontend | React 19, TypeScript 6, Vite 8, TanStack Query, Vitest, Playwright |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, psycopg 3, Alembic |
| Realtime | WebSocket, PCM S16LE 16 kHz mono audio streaming, MediaRecorder |
| AI | Ollama Local LLM, provider-neutral LLM wrapper, EmbeddingGemma |
| STT | Faster-Whisper, streaming STT adapter, batch recording transcription |
| Data | PostgreSQL 17, pgvector 0.8.2, filesystem object storage |
| Document | PyMuPDF, PDF text extraction, vector indexing |
| DevOps | GitHub Actions, Docker Compose, systemd, Nginx, Cloudflare Tunnel |
| Quality | Ruff, pytest, ESLint, Prettier, TypeScript, OpenAPI contract test |

## 저장소 구조

```text
.
├── backend/                  # FastAPI API, Worker, DB model과 Alembic migration
├── frontend/                 # React 애플리케이션과 UI 테스트
├── deploy/                   # KCLOUD VM 자동 배포 스크립트와 systemd unit
├── docs/
│   ├── api/                  # API 명세와 OpenAPI 문서
│   ├── architecture/         # 시스템 구성도와 기술 명세
│   ├── database/             # DB 스키마와 ERD
│   ├── product/              # 기획안, 기능 명세, IA와 화면 설계
│   └── prototypes/           # 화면 프로토타입
├── docker-compose.yml        # 로컬 PostgreSQL/pgvector 환경
└── Makefile                  # 개발, 검사와 배포 명령
```

## 로컬 실행 방법

### 사전 요구사항

- Node.js 22.13 이상, 23 미만
- pnpm 11.11.0
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker Engine 및 Docker Compose

### 최초 설정

```bash
cp .env.example .env
corepack enable
make setup
make db-up
make migrate
```

### API와 Frontend 실행

서로 다른 터미널에서 실행합니다.

```bash
# FastAPI
make dev-api

# React/Vite
make dev-web
```

- Frontend: <http://localhost:5173>
- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>

### Background Worker 실행

사용할 기능에 맞는 Worker를 별도 터미널에서 실행합니다.

```bash
cd backend

uv run python -m tbd.jobs.material_worker
uv run python -m tbd.jobs.knowledge_worker
uv run python -m tbd.jobs.clustering_worker
uv run python -m tbd.jobs.personal_ai_worker
uv run python -m tbd.jobs.recording_transcription_worker
uv run python -m tbd.jobs.postprocessing_worker
uv run python -m tbd.jobs.lifecycle_worker
```

로컬 LLM과 STT provider를 사용하려면 `.env.example`을 참고해 Ollama 및 Faster-Whisper 설정을 추가해야 합니다. provider가 구성되지 않은 환경에서는 AI/STT 작업이 안전한 실패 상태로 기록되며, 저장된 Transcript·질문 등 다른 기능은 계속 사용할 수 있습니다.

## 테스트 및 품질 검사

```bash
# PostgreSQL 시작
make db-up

# 전체 검사
make check

# 영역별 검사
make frontend-lint
make frontend-typecheck
make frontend-test
make frontend-build
make backend-lint
make backend-unit
make backend-contract
make backend-integration
make migration-check
make docs-check
make deploy-check
```

GitHub Actions는 Configuration, Frontend, Backend Job을 병렬 실행합니다. Frontend에서는 lint·format·type check·OpenAPI 계약·테스트·빌드·3개 viewport 시각 검증을 수행하고, Backend에서는 lint·unit·contract·PostgreSQL integration·Alembic upgrade/downgrade를 검사합니다.

## 자동 배포

KCLOUD VM의 systemd timer가 2분마다 GitHub `main` 브랜치의 SHA를 확인합니다. 해당 SHA의 push 기반 CI가 모두 성공했을 때만 새로운 immutable release를 생성하고 활성화합니다.

```text
GitHub main 변경
      │
      ▼
GitHub Actions CI 성공 확인
      │
      ▼
의존성 설치 → Frontend build → DB backup → Alembic upgrade
      │
      ▼
/opt/goal/current symlink 원자적 교체
      │
      ▼
API·Worker 재시작 → DB health check
```

배포 실패 시 코드 symlink와 프로세스는 이전 release로 복구합니다. PostgreSQL, 녹음·PDF storage와 Ollama 데이터는 release 경로 밖에 보존하며 애플리케이션 배포 시 Ollama와 PostgreSQL 자체를 재시작하지 않습니다.

자세한 설치 및 운영 절차는 [systemd 자동 배포 문서](deploy/systemd/README.md)를 참고하세요.

## 설계 문서

- [기획안](docs/product/기획안.md)
- [기능 명세서](docs/product/기능명세서.md)
- [Information Architecture](docs/product/IA.md)
- [화면 설계서](docs/product/화면설계서.md)
- [시스템 구성도](docs/architecture/시스템구성도.md)
- [기술 명세서](docs/architecture/기술명세서.md)
- [API 명세서](docs/api/API_명세서.md)
- [OpenAPI](docs/api/openapi.yaml)
- [DB 스키마](docs/database/DB_스키마.md)
- [ERD](docs/database/ERD.md)

## 프로젝트 회고

### 김도현

#### 프로젝트를 진행하며 배운 점

LMS와 같은 서비스가 실제로 동작하려면 사용자에게 보이는 기능뿐 아니라 다양한 기술 스택과 수많은 백그라운드 프로세스가 필요하다는 것을 배웠습니다.

#### 가장 어려웠던 문제와 해결 과정

로컬 LLM을 웹 서비스와 연결하고, 모델 응답 생성을 백그라운드 Job으로 실행한 뒤 완료된 결과를 다시 조회하여 화면에 보여주는 전 과정에서 많은 문제가 발생했습니다. API 요청과 긴 AI 작업을 분리하고 작업 상태를 DB에 기록하는 구조를 적용하면서 문제를 해결했습니다. UI를 AI로 수정할 때는 의도한 방향이 정확히 전달되지 않아 반복 수정이 많았고, 요구사항과 디자인 기준을 더 구체적으로 전달하는 것이 중요하다는 점도 배웠습니다.

#### 협업 과정에서 느낀 점

분업 범위와 각자 담당 영역의 독립성을 명확히 정하는 것이 중요하다고 느꼈습니다. 영역 간 독립성이 부족하면 서로의 구현에 의존성이 생겨 conflict가 발생하거나 한쪽의 진행 상황이 다른 쪽의 구현을 막을 수 있습니다.

#### AI를 활용하며 느낀 점

AI의 구현 능력이 매우 뛰어나다는 것을 체감했습니다. 다만 일주일 동안 서비스 하나를 집중적으로 개발하기에는 3만 원대 요금제의 사용량이 매우 부족하다는 점도 절실히 느꼈습니다.

### 🙋🏻 박정준

#### 프로젝트를 진행하며 배운 점

서버를 자동으로 배포하고 운영하는 방법과 디자인 레퍼런스를 실제 UI에 적용하는 방법을 배웠습니다.
특히 CI 결과를 기준으로 안전하게 배포하고 장애 시 이전 버전으로 복구하는 흐름을 이해하면서, 기능 구현뿐 아니라 운영 안정성까지 고려하는 개발 관점을 익혔습니다.

#### 가장 어려웠던 문제와 해결 과정

DB 스키마와 API 명세를 작성할 때 결정해야 하는 정책이 예상보다 많았습니다. 명세를 구체적으로 작성할수록 서비스 기획 의도가 구현에 정확히 반영된다는 장점이 있지만, 모든 예외와 상태를 정의하는 데 많은 시간이 필요했습니다. 문서와 계약을 기준으로 구현과 테스트를 맞추는 방식으로 이 문제를 해결했습니다.
이 과정에서 요구사항을 데이터 상태와 API 계약으로 구체화하고, 구현 전에 팀원과 예외 상황을 합의하는 것이 재작업을 줄이는 데 중요하다는 점을 배웠습니다.

#### 협업 과정에서 느낀 점

도현이가 프로젝트 구조를 이해하기 쉽게 설명해 주어 전체 흐름을 파악하는 데 큰 도움이 됐습니다. 학교 교수님보다 수업을 더 잘할 것 같다고 느낄 정도였습니다.
서로의 담당 영역을 단순히 분리하는 데 그치지 않고 설계 의도와 인터페이스를 공유하면서, 문제가 생겼을 때 책임을 나누기보다 함께 원인을 찾는 협업 방식의 중요성을 느꼈습니다.

#### AI를 활용하며 느낀 점

세부 기능 명세를 자세하게 작성하면 AI가 기능 구현 의도를 비교적 정확하게 반영하지만, 디자인은 크기·간격·배치·반응형 동작을 구체적으로 지시하지 않으면 원하는 결과가 나오지 않는다는 것을 느꼈습니다.
AI가 만든 결과를 그대로 수용하기보다 요구사항과 실제 화면을 기준으로 검증하고 피드백을 반복하는 과정이 개발자의 핵심 역할이라는 점도 배웠습니다.

## License

본 프로젝트는 2026년 MadCamp 공통과제 II 결과물입니다.
