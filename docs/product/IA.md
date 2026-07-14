# GOAL 정보 구조(IA)

> 원본: [Notion · GOAL IA 화면 구조 및 상세 설계](https://app.notion.com/p/eaaa8589f50b4c87b0fa1bb6b756e5bc?v=dbcc96da28584639b86edc83210cdea7)
> 동기화 기준: 2026-07-11 · Default view · 레벨 오름차순

## 1. 문서 목적

GOAL 서비스의 페이지, 화면 영역, 사용자 기능과 백그라운드 작업을 계층적으로 정리한다. 사용자 계정은 고정된 역할을 갖지 않으며, Course별로 교수자 또는 학생 역할을 가진다.

### 용어

- **Course**: 한 학기 단위 수업방
- **class**: Course 안의 날짜별 강의 세션
- **active class**: `READY`, `LIVE`, `PROCESSING` 상태인 class. Course마다 최대 하나만 존재한다.
- **current_session**: Course의 단일 active class 또는 active class가 없을 때 `null`
- **attached Material**: Session과 연결되어 목록·열람·AI 근거 판단 대상이 되는 삭제 전 PDF Material
- **실시간 class**: 현재 진행 중인 강의 세션
- **끝난 class**: 강의 종료 후 기록 정리가 완료된 세션
- **live final Segment**: 수업 중 발화 단위로 확정해 저장한 실시간 Segment. 영구 Transcript의 `FINALIZED` 상태와는 다르다.
- **canonical Transcript**: 전체 녹음 HQ STT, Segment 저장, 문장 시간·녹음 위치 매핑과 canonical 전환을 마친 수업 후 기준 Transcript
- **Answer AI 정리**: LIVE에서 완료된 음성 Answer의 HQ 재매핑 범위 또는 immutable 원본 LIVE 범위를 바탕으로 후처리에서 자동 생성하고 교수자 text와 별도로 보관하는 결과
- **기록 manifest**: `/record`가 반환하는 완료 기록 초기화 정보. 기록 요약·상태·영역별 개수·공개 조회 경로만 포함하고 대형 목록 배열은 포함하지 않는다.
- **공개 Evidence**: AI 결과에서 표시하는 정확히 `MATERIAL|TRANSCRIPT|QUESTION|ANSWER`인 `source_kind`·사용자용 `label`·권한 검사 공개 `link`. `QUESTION`은 학생 질문과 AI 대표질문을 포괄하고, `TRANSCRIPT` link는 Segment ID 대신 Session·version·안정적인 sequence/시간 범위를 사용한다. 내부 KnowledgeChunk·storage key를 포함하지 않는다.
- `LIVE_CLASS_PAGE_*`: 학생·교수자 실시간 class 페이지에 공통으로 사용되는 영역
- `ENDED_CLASS_PAGE_*`: 학생·교수자 완료 class 페이지에 공통으로 사용되는 영역

### 기본 계층

```text
ROOT(0)
└── 메인 페이지(1)
    └── 대시보드 기능·페이지(2)
        └── Course 페이지(3)
            └── class 페이지(4)
                └── 화면 영역·주요 기능(5)
                    └── 세부 기능·백그라운드 작업(6~7)
```

## 2. IA 노드

### Level 0 · 서비스

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| GOAL | `ROOT` | 0 | 서비스 | — | 공통 | MVP 필수 | 실시간 AI 강의 보조 서비스 전체 | 해당 없음 |

### Level 1 · 메인 화면

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| GOAL 메인 화면 | `MAIN_PAGE` | 1 | 페이지 | `ROOT` | 비로그인 | MVP 필수 | 서비스 가치 소개와 Google·이메일 로그인 및 이메일 가입 진입을 제공하고, 로그인 후 대시보드로 전환 | GOAL URL에 비로그인 상태로 접속 |
| GOAL 메인 화면 로그인 후 | `MAIN_PAGE_AUTH` | 1 | 페이지 | `ROOT` | 공통 | MVP 필수 | 참여·관리 중인 Course 목록, Course 생성·참여와 내 정보 진입을 제공하는 대시보드 | 인증된 사용자가 로그인하거나 서비스에 재접속 |

### Level 2 · 대시보드 기능 및 페이지

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| 한 학기 Course 만들기 버튼 | `COURSE_CREATE_BUTTON` | 2 | 기능 | `MAIN_PAGE_AUTH` | 인증 사용자 공통 | MVP 필수 | 과목명과 학기를 입력하는 Course 생성 페이지로 이동 | 로그인 후 메인 화면에서 Course 만들기 선택 |
| 한 학기 Course 만들기 페이지 | `COURSE_CREATE_PAGE` | 2 | 페이지 | `MAIN_PAGE_AUTH` | 인증 사용자 공통 | MVP 필수 | 과목명과 학기를 입력해 Course를 만들고 해당 Course의 유일한 교수자 owner가 됨 | 로그인 후 메인 화면에서 Course 만들기 선택 |
| 한 학기 Course 참여하기 버튼 | `COURSE_JOIN_BUTTON` | 2 | 기능 | `MAIN_PAGE_AUTH` | 인증 사용자 공통 | MVP 필수 | 참여 코드를 입력하는 Course 참여 페이지로 이동 | 로그인 후 메인 화면에서 Course 참여하기 선택 |
| 한 학기 Course 참여하기 | `COURSE_JOIN_PAGE` | 2 | 페이지 | `MAIN_PAGE_AUTH` | 인증 사용자 공통 | MVP 필수 | 참여 코드를 검증해 해당 Course의 학생이 됨 | 로그인 후 메인 화면에서 Course 참여하기 선택 |
| 로그인 버튼 | `LOGIN_BUTTON_AREA` | 2 | 기능 | `MAIN_PAGE` | 비로그인 | MVP 필수 | Google 또는 이메일 로그인 페이지로 이동하고 성공 시 로그인 후 메인 화면으로 전환 | 비로그인 사용자가 로그인 버튼 선택 |
| 로그인 페이지 | `LOGIN_PAGE` | 2 | 페이지 | `MAIN_PAGE` | 비로그인 | MVP 필수 | Google 계정 또는 이메일·비밀번호로 인증하며 역할은 계정이 아니라 Course별로 결정 | 메인 화면에서 로그인 버튼 선택 |
| 이메일 가입 페이지 | `EMAIL_SIGNUP_PAGE` | 2 | 페이지 | `MAIN_PAGE` | 비로그인 | MVP 필수 | 표시 이름·이메일·비밀번호로 계정을 만들고 바로 서버 Session을 발급받는다. 기존 Google 계정과 자동 연결하지 않는다. | 로그인 페이지에서 이메일 가입 선택 |
| 내가 참여 중인 Course 목록 | `MY_COURSE_LIST` | 2 | 영역 | `MAIN_PAGE_AUTH` | 공통 | MVP 필수 | 학생으로 참여한 Course 카드와 진입 기능을 표시하고 빈 목록에서는 코드 참여를 안내 | 로그인 후 메인 화면에 항상 표시 |
| 내 정보 조회 버튼 | `MY_INFO_BUTTON` | 2 | 기능 | `MAIN_PAGE_AUTH` | 공통 | MVP 필수 | 내 정보 조회 페이지로 이동 | 로그인 후 프로필 또는 내 정보 버튼 선택 |
| 내 정보 조회 페이지 | `MY_INFO_PAGE` | 2 | 페이지 | `MAIN_PAGE_AUTH` | 공통 | MVP 필수 | 계정 기본 정보, 로그아웃, 관리·참여 중인 Course 요약을 표시 | 로그인 후 메인 화면에서 내 정보 버튼 선택 |
| 내가 관리 중인 Course 목록 | `MY_OWN_COURSE_LIST` | 2 | 영역 | `MAIN_PAGE_AUTH` | 공통 | MVP 필수 | 교수자로 생성한 Course 카드와 진입 기능을 표시하고 빈 목록에서는 Course 생성을 안내 | 로그인 후 메인 화면에 항상 표시 |

### Level 3 · Course 및 계정 기능

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| Course 페이지-교수자 | `COURSE_PAGE_PROF` | 3 | 페이지 | `MY_OWN_COURSE_LIST` | Course 교수자 | MVP 필수 | 유일한 owner에게 Course 정보·참여 코드 회전·Course 삭제, 단일 active class 관리와 `started_at` 기준 완료 기록 진입 제공 | 관리 중인 Course 선택 또는 Course 생성 직후 |
| Course 페이지-학생 | `COURSE_PAGE_STUD` | 3 | 페이지 | `MY_COURSE_LIST` | Course 학생 | MVP 필수 | Course 정보, 단일 active class 상태·입장, 실제 시작 시각으로 구분되는 완료 class 목록과 기록 진입 제공 | 참여 중인 Course 선택 또는 Course 참여 직후 |
| 내 정보 수정 버튼 | `MY_INFO_CHANGE_BUTTON` | 3 | 기능 | `MY_INFO_PAGE` | 공통 | MVP 선택 | 수정 가능한 계정 정보를 편집하는 흐름으로 이동 | 내 정보 페이지에서 수정 버튼 선택 |

### Level 4 · class 페이지

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| class 생성 및 준비 페이지 | `CLASS_CREATE_PAGE` | 4 | 페이지 | `COURSE_PAGE_PROF` | Course 교수자 | MVP 필수 | active class가 없을 때 선택 제목·필수 날짜로 `READY` class를 생성하고 선택적으로 PDF를 추가; PDF가 없어도 시작 가능하고 빈 제목은 `Course 제목 · YYYY.MM.DD HH:mm` 서버 자동 제목 사용 | owner가 Course 페이지에서 class 생성 선택 |
| Course 참여 코드 영역 | `COURSE_CODE_AREA` | 4 | 영역 | `COURSE_PAGE_PROF` | Course 교수자 | MVP 필수 | owner에게만 무기한 `[A-Z]{6}` 참여 코드의 표시·복사·회전을 제공하고 회전 즉시 이전 코드를 무효화하며 감사·이력은 남기지 않음 | owner가 자신이 관리하는 Course 페이지에 진입 |
| Course 삭제 | `COURSE_DELETE` | 4 | 기능 | `COURSE_PAGE_PROF` | Course 교수자 | MVP 필수 | 종료·보관 상태나 owner 이전 없이 유일한 owner가 Course 삭제를 요청; active class가 있을 때의 삭제와 삭제 후 복구 정책은 미정 | owner가 Course 삭제를 선택하고 확인 |
| class 제목 수정 | `CLASS_TITLE_EDIT` | 4 | 기능 | `COURSE_PAGE_PROF` | Course 교수자 | MVP 필수 | `READY`·`LIVE`·`PROCESSING`·`COMPLETED`에서 제목을 수정하며 빈 제목은 `Course 제목 · YYYY.MM.DD HH:mm` 서버 자동 제목 사용; 시각은 `created_at`의 `Asia/Seoul` 표시값으로 고정되고 날짜와 상태 시각은 수정 불가 | owner가 해당 class의 제목 수정 선택 |
| class 삭제 | `CLASS_DELETE` | 4 | 기능 | `COURSE_PAGE_PROF` | Course 교수자 | MVP 필수 | `READY`·`COMPLETED`에서 삭제; `LIVE`는 종료 후 `PROCESSING` 완료를 기다리고 `PROCESSING`은 완료까지 삭제 불가 | owner가 삭제 가능한 상태의 class에서 삭제 선택 |
| 끝난 class 메인 페이지-교수자 | `ENDED_CLASS_PAGE_PROF` | 4 | 페이지 | `COURSE_PAGE_PROF` | 교수자 | MVP 필수 | 학생과 같은 기록·개인 `REVIEW` Chat UI에서 compact manifest 후 강의자료·Transcript·질문·Answer·Cluster·Job을 영역별 점진 로딩하고, 녹음 playback·문장 seek·FINAL Summary·마인드맵·Answer를 제공하며 교수자 관리·실패한 공유 Job 재시도 control만 추가 | 완료 class 목록에서 특정 `COMPLETED` class 선택 |
| 끝난 class 메인 페이지-학생 | `ENDED_CLASS_PAGE_STUD` | 4 | 페이지 | `COURSE_PAGE_STUD` | 학생 | MVP 필수 | compact 기록 manifest 후 강의자료·Transcript·질문·Answer·Cluster·Job을 영역별 점진 로딩하고, canonical Transcript의 final·empty·failed·mixed gap, 녹음 playback·문장 seek, AI 요약, 질문·교수자 text 우선 Answer·별도 AI 정리·안전한 Evidence 이동과 복습 AI 제공 | 완료 class 목록에서 특정 class 선택 |
| 실시간 class 메인 페이지-교수자 | `LIVE_CLASS_PAGE_PROF` | 4 | 페이지 | `COURSE_PAGE_PROF` | 교수자 | MVP 필수 | 학생과 같은 Transcript·질문·개인 LIVE Summary·Chat UI에 단일 audio publisher, 녹음·강의자료·Answer·종료 control을 추가 | class 시작 또는 진행 중인 class에 재입장 |
| 실시간 class 메인 페이지-학생 | `LIVE_CLASS_PAGE_STUD` | 4 | 페이지 | `COURSE_PAGE_STUD` | 학생 | MVP 필수 | 실시간 Transcript, 익명 질문·반응, AI 요약과 현재 연결된 `READY` 강의자료 기반 AI 채팅 제공 | 진행 중인 class 입장 선택 |

### Level 5 · 화면 영역 및 주요 기능

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| class 강의자료 PDF 업로드 | `CLASS_MATERIAL_UPLOAD` | 5 | 기능 | `CLASS_CREATE_PAGE`·`LIVE_CLASS_PAGE_PROF`·`ENDED_CLASS_PAGE_PROF` | Course 교수자 | MVP 필수 | Session `READY`·`LIVE`·`COMPLETED`에서 active 10개·파일당 100,000,000 bytes 제한으로 PDF 추가, 안정적인 표시 이름과 처리 상태 제공; `PROCESSING`에서는 금지 | owner가 허용 상태의 class에서 PDF 선택 |
| class 강의자료 삭제 | `CLASS_MATERIAL_DETACH` | 5 | 기능 | `CLASS_CREATE_PAGE`·`LIVE_CLASS_PAGE_PROF`·`ENDED_CLASS_PAGE_PROF` | Course 교수자 | MVP 필수 | Session `READY`·`LIVE`·`COMPLETED`에서 Material 연결을 즉시 해제하고 목록·열람·새 AI 검색에서 제거; 물리 정리는 백그라운드 처리 | owner가 연결된 PDF의 삭제를 선택하고 확인 |
| 끝난 class 기록 manifest | `ENDED_RECORD_MANIFEST` | 5 | 영역 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 필수 | `/record`에서 기록 요약·상태·영역별 개수·공개 조회 경로만 받고 영역별 독립 로딩과 재시도를 조정 | `PROCESSING`·`COMPLETED` class 기록 진입 |
| 끝난 class AI 대화 영역 | `ENDED_AI_CHAT_AREA` | 5 | 영역 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 필수 | 교수자·학생에게 동일한 개인 `REVIEW` Chat UI를 제공하고, `COMPLETED` class의 `READY` PDF·final Transcript·Q&A를 근거로 polling한 성공 결과와 안전한 Evidence를 표시 | `COMPLETED` class 페이지에 표시하거나 접고 펼침; `PROCESSING`에서는 미제공 |
| 끝난 class 녹음 파일 다운로드 | `ENDED_AUDIO_DOWNLOAD` | 5 | 기능 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 이후 | 저장된 강의 음성 원본 다운로드 | 별도 다운로드 정책이 확정된 완료 class에서 다운로드 선택 |
| 끝난 class 강의 녹음 재생 | `ENDED_AUDIO_PLAY` | 5 | 기능 | `ENDED_CLASS_PAGE_*` | 교수자·학생(접근 정책 미정) | MVP 필수 | 교수자·학생 화면에 같은 player 구조와 접근 거부 상태를 두고 요청마다 권한을 재확인한 뒤 저장 녹음 playback 제공 | 완료 class에서 녹음 playback 권한 확인 |
| 끝난 class Transcript 다운로드 | `ENDED_CLASS_TRANSCRIPT_DOWNLOAD` | 5 | 기능 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 이후 | final Transcript를 텍스트 파일로 다운로드 | 완료 class에서 Transcript 다운로드 선택 |
| 끝난 class 강의자료 다시 보기 | `ENDED_MATERIAL_VIEW` | 5 | 기능 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 필수 | Course 참여 권한을 확인한 뒤 해당 class에 현재 연결된 열람 가능한 PDF를 표시; 삭제된 Material 원문은 제공하지 않음 | 완료 class에 연결된 열람 가능 PDF가 존재 |
| 끝난 class 질문 마인드맵 영역 | `ENDED_QUESTION_AREA` | 5 | 영역 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 필수 | member `source_kind=STUDENT_QUESTION\|AI_REPRESENTATIVE`인 FINAL Cluster·child, AI 대표질문의 `created_in_generation`, 원본 질문과 target별 Answer를 각 cursor로 점진 로딩하고 교수자 text 우선 Answer·별도 AI 정리·원본 음성 범위·마지막 FINAL Job 상태 제공 | 완료 class 페이지에 항상 표시 |
| 끝난 class AI 강의 요약 영역 | `ENDED_SUMMARY_AREA` | 5 | 영역 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 필수 | READY·요청 전 LIVE의 `NOT_STARTED`·`summary_reason=null`, source 대기 `PENDING`, 완료 뒤 명시적 재시도와 HQ retry coordinator가 만든 새 Summary·`NO_FINAL_TRANSCRIPT`·`SUMMARY_SOURCE_UNAVAILABLE`·성공·`DATA_INTEGRITY_ERROR`를 구분하며, 최초 종료 후처리 Job이 active로 남은 모순에는 안전한 무결성 오류만 표시 | class 기록 화면에 진입 |
| 끝난 class Transcript 영역 | `ENDED_TRANSCRIPT_AREA` | 5 | 영역 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 필수 | canonical Transcript의 `FINALIZED`·`EMPTY`·`FAILED`를 구분하고 cursor 페이지의 `segments[]`·`gaps[]`를 시간 순으로 merge해 점진 표시 | 완료 class 페이지에 항상 표시 |
| 실시간 class AI 대화 영역 | `LIVE_AI_CHAT_AREA` | 5 | 영역 | `LIVE_CLASS_PAGE_*` | 공통 | MVP 필수 | 교수자·학생에게 같은 요청자 전용 Summary·Chat UI와 `202 + AIJob` polling·저장 결과 조회를 제공; USER Message와 이를 입력으로 고정한 Job을 원자 저장하고, USER Chat은 trim·Unicode NFC 후 1~2,000자이며 부분 결과·shared WS 전송 없음 | Course 멤버의 `LIVE` class 페이지에 표시하거나 접고 펼침 |
| 실시간 class 음성 스트리밍(STT) | `LIVE_AUDIO_STREAM` | 5 | 백그라운드 작업 | `LIVE_CLASS_PAGE_PROF` | 교수자 | MVP 필수 | 같은 마이크 입력을 `PCM_S16LE` 16 kHz mono 500 ms chunk WebSocket과 브라우저 로컬 녹음으로 분기해 partial/final STT와 저장 원본 생성; 두 경로 실패 격리 | active publisher 탭에서 마이크 권한 허용 |
| 실시간 class audio publisher | `LIVE_AUDIO_PUBLISHER` | 5 | 기능 | `LIVE_CLASS_PAGE_PROF` | 교수자 | MVP 필수 | 첫 `audio.start` 성공 탭만 전송하고 두 번째 탭은 전송만 거부하며 조회 유지; active 탭 이탈 경고 제공 | Session `LIVE`에서 교수자 탭이 audio 시작 요청 |
| 브라우저 로컬 녹음 | `LIVE_LOCAL_RECORDING` | 5 | 백그라운드 작업 | `LIVE_CLASS_PAGE_PROF` | 교수자 | MVP 필수 | 실시간 Audio WS와 독립적으로 같은 마이크를 로컬 녹음하고 종료 후 resumable upload 준비 | active publisher 탭에서 audio 시작 성공 |
| 실시간 class 끝내기 | `LIVE_CLASS_QUIT` | 5 | 기능 | `LIVE_CLASS_PAGE_PROF` | 교수자 | MVP 필수 | 새 실시간 입력을 마감하고 class를 정리 중 상태로 전환해 후처리 시작 | 교수자가 종료 버튼을 선택하고 확인 |
| 실시간 class 시작하기 | `LIVE_CLASS_START` | 5 | 기능 | `CLASS_CREATE_PAGE` | 교수자 | MVP 필수 | attached Material 중 `PROCESSING`이 없으면 PDF 0개 또는 `READY`·`UPLOADED`·`FAILED` 상태로도 `READY` class를 시작; AI는 `READY`만 참고 | class 정보가 준비되고 attached `PROCESSING` Material이 없을 때 시작 선택 |
| 실시간 class 질문 마인드맵 영역 | `LIVE_QUESTION_AREA` | 5 | 영역 | `LIVE_CLASS_PAGE_*` | 공통 | MVP 필수 | `created_in_generation` provenance가 있는 AI 대표질문 중앙, `source_kind=STUDENT_QUESTION\|AI_REPRESENTATIVE`로 구분한 학생 질문과 Answer 보존 과거 대표질문 child, 익명 질문·반응·target별 답변 상태·자동 클러스터링과 마지막 Job 상태 표시; 교수자는 정렬·답변 target 하나 선택 | 실시간 class 페이지에 항상 표시 |
| 실시간 class Transcript 영역 | `LIVE_TRANSCRIPT_AREA` | 5 | 영역 | `LIVE_CLASS_PAGE_*` | 공통 | MVP 필수 | partial STT를 즉시 갱신하고 final Transcript를 누적 표시하며 연결·재연결 상태 구분 | 실시간 class 페이지에 항상 표시 |

### Level 6 · 세부 기능 및 후처리

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| 끝난 class에서 AI와 질의응답 | `ENDED_AI_CHATING` | 6 | 기능 | `ENDED_AI_CHAT_AREA` | 공통 | MVP 필수 | `COMPLETED` class에서 교수자·학생 USER 입력을 trim·Unicode NFC 후 1~2,000자로 검증하고, `202 + AIJob` polling 뒤 `READY` PDF·final Transcript·Q&A 기반의 저장된 최종 답변과 안전한 Evidence를 조회 | 교수자 또는 학생이 완료 class 개인 `REVIEW` Chat에 복습 질문 전송 |
| 끝난 class Evidence 이동 | `ENDED_EVIDENCE_NAVIGATE` | 6 | 기능 | `ENDED_AI_CHAT_AREA` | 공통 | MVP 필수 | 정확히 `MATERIAL\|TRANSCRIPT\|QUESTION\|ANSWER`인 `source_kind`와 사용자용 `label`로 근거를 구분하고 배열 index·cursor와 무관한 공개 `link`로 이동; `QUESTION`은 학생·AI 대표질문을 포괄하고 `TRANSCRIPT`는 Session·version·안정적인 sequence/시간 범위를 사용하며 Segment ID에 의존하지 않음; detached Material 또는 폐기된 AI 대표질문은 label snapshot만 유지하고 `link=null` | AI 답변에 공개 Evidence가 존재하고 사용자가 선택 |
| 끝난 class Transcript 위치 재생 | `ENDED_CLASS_TRANSCRIPT_PLAY` | 6 | 기능 | `ENDED_TRANSCRIPT_AREA` | 교수자·학생(접근 정책 미정) | MVP 필수 | 권한 재확인 후 Transcript 문장을 선택해 표시 시각 추정값이 아닌 서버 제공 녹음 위치로 seek | 저장 녹음과 문장 위치가 제공되고 playback 권한 확인 |
| 끝난 class 텍스트 Answer | `ENDED_QUESTION_ANSWER` | 6 | 기능 | `ENDED_QUESTION_AREA` | Course 교수자 | MVP 필수 | LIVE에서는 text를 작성하지 않고, `COMPLETED`에서 미답변 `STUDENT_QUESTION`에만 새 text-only Answer 등록; 학생 질문 또는 Answer 보존 AI 대표질문의 기존 `COMPLETED` Answer text는 추가·수정하되 FINAL·REVIEW 전용·미답변 ACTIVE 대표질문에는 새 Answer 금지; 최대 길이·삭제 정책은 미정 | 교수자가 `COMPLETED` class의 허용된 Answer target 선택 |
| 끝난 class Answer AI 정리 | `ENDED_ANSWER_ORGANIZATION` | 6 | 영역·기능 | `ENDED_QUESTION_AREA` | 공통·Course 교수자 | MVP 필수 | 교수자 text를 우선 표시하고 AI 정리 결과를 별도 label로 표시하며 원본 음성 범위를 항상 제공; Course 교수자에게만 실패한 같은 `ANSWER_ORGANIZATION` Job의 `attempt + 1` 재시도 제공 | 완료된 음성 Answer가 있거나 정리 Job이 실패 |
| 끝난 class 복습 질문 올리기 | `ENDED_QUESTION_UPLOAD` | 6 | 기능 | `ENDED_QUESTION_AREA` | 학생 | MVP 이후 | 종료 후 추가 질문을 남기는 확장 기능; MVP에서는 종료된 class에 새 질문·반응 등록 불가 | 완료 class에서 추가 복습 질문 등록 |
| 실시간 class에서 AI와 질의응답 | `LIVE_AI_CHATING` | 6 | 기능 | `LIVE_AI_CHAT_AREA` | 공통 | MVP 필수 | 교수자·학생 USER 입력을 trim·Unicode NFC 후 1~2,000자로 검증하고 현재 `READY` PDF·Transcript 기반 개인 답변을 polling해 조회; `PROCESSING` 전이 시 LIVE Message·Evidence·Job과 함께 사라지며 기존 polling/resource·멱등 replay 응답은 미정 | Course 멤버가 LIVE Chat에 질문 또는 설명 요청 전송 |
| class 종료 후 기록 정리 | `LIVE_CLASS_QUIT_PROCESS` | 6 | 백그라운드 작업 | `LIVE_CLASS_QUIT` | 공통 | MVP 필수 | `PROCESSING` 전이에서 실행·retry 예약 LIVE 클러스터링과 늦은 결과를 fence하고 개인 LIVE Summary·Chat·Message·Evidence·Job을 제거한 뒤 녹음 upload·HQ STT·canonical 전환·Answer 재매핑·공유 후처리 작업을 독립 처리; LIVE Job의 `CANCELLED\|SUPERSEDED` 대 nonretryable `FAILED` 공개 표현은 미정 | 교수자가 class 종료 확정 |
| 실시간 질문 답변 시작 | `LIVE_QUESTION_ANSWER` | 6 | 기능 | `LIVE_QUESTION_AREA` | 교수자 | MVP 필수 | 미답변 학생 질문 또는 AI 대표질문 하나를 target으로 선택해 `CAPTURING` Answer를 만들고 선택 시점 문구와 이후 final Transcript를 보존 | 미답변 target 하나 선택 |
| 실시간 질문 답변 완료·취소 | `LIVE_QUESTION_ANSWER_COMPLETE` | 6 | 기능 | `LIVE_QUESTION_AREA` | 교수자 | MVP 필수 | 완료 시 target 하나에만 final Transcript 범위를 확정하고, 취소 시 `CAPTURING` Answer를 hard delete해 취소 기록을 노출하지 않음 | Answer 캡처 중 완료 또는 취소 선택 |
| 실시간 유사 질문 클러스터링 | `LIVE_QUESTION_CLUSTER` | 6 | 백그라운드 작업 | `LIVE_QUESTION_AREA` | 공통 | MVP 필수 | 질문 commit마다 pending watermark를 갱신하고 `active_job_id`·`retry_job_id`가 모두 없을 때만 fresh Job 생성; retry 예약 중에는 같은 행의 `attempt + 1`을 기다리며 새 질문을 watermark에 합치고, 새 질문만 배치해 영향받은 Cluster의 immutable AI 대표질문만 재생성 | 새 질문 commit 후 시스템이 자동 예약 |
| AI 질문 문장 작성 도움 | `LIVE_QUESTION_DRAFT_HELP` | 6 | 기능 | `LIVE_QUESTION_AREA` | 학생 | MVP 필수 | trim·Unicode NFC 후 Unicode code point 500자 이하 초안을 AIJob 없는 동기 `200`으로 다듬어 300자 이하 후보 제안; 초과는 자르지 않고 `422`로 거부 | 학생이 질문 작성 도움 요청 |
| ‘나도 궁금해요’ 반응 | `LIVE_QUESTION_METOO` | 6 | 기능 | `LIVE_QUESTION_AREA` | 학생 | MVP 필수 | 학생별 한 번만 반응하고 추가·취소 결과와 최신 수를 실시간 반영 | 다른 질문의 반응을 선택 또는 취소 |
| 실시간 인기 질문 우선 정렬 | `LIVE_QUESTION_SORT` | 6 | 기능 | `LIVE_QUESTION_AREA` | 공통 | MVP 필수 | 미답변 질문을 반응 수 내림차순으로 정렬해 교수자의 답변 우선순위 판단 지원 | 교수자가 인기순 정렬 선택 |
| 실시간 class 질문 올리기 | `LIVE_QUESTION_UPLOAD` | 6 | 기능 | `LIVE_QUESTION_AREA` | 학생 | MVP 필수 | 작성자를 노출하지 않고 trim·Unicode NFC 후 Unicode code point 300자 이하 질문을 commit한 뒤 클러스터링 pending watermark를 자동 갱신; 초과는 자르지 않고 `422`로 거부 | 질문 내용을 입력하고 등록 |
| 실시간 class Transcript 요약 | `LIVE_TRANSCRIPT_SUMMARY` | 6 | 기능 | `LIVE_AI_CHAT_AREA` | 공통 | MVP 필수 | 교수자·학생이 현재까지 또는 선택한 live final Transcript와 현재 연결된 `READY` PDF 기반 개인 Summary를 `202 + AIJob` polling 후 조회; final 0건은 Job 없이 409 | Course 멤버가 현재까지 또는 선택 영역 요약 요청 |
| 동일 publisher 재연결 | `LIVE_AUDIO_PUBLISHER_RESUME` | 6 | 백그라운드 작업 | `LIVE_AUDIO_PUBLISHER` | 교수자 | MVP 필수 | active publisher가 같은 `client_stream_id`로 재연결하고 서버가 수락한 위치부터 resume; 다른 탭 takeover는 미정 | active publisher Audio 연결 단절 |

### Level 7 · 처리 상태

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| class 기록 정리 중 상태 | `CLASS_PROCESSING_STATE` | 7 | 영역 | `LIVE_CLASS_QUIT_PROCESS` | 공통 | MVP 필수 | 개인 LIVE AI 선택·cache를 비우고 REVIEW Chat 없이 녹음 upload·HQ STT·canonical 전환·Answer 재매핑·최종 AI 작업을 독립 표시; 15초 heartbeat·60초 lease, HQ 제외 일반 Job 기본 5분·Session 10분을 적용하고 HQ 개별 timeout은 미정; source gate 중 FINAL Summary는 Job 없는 `PENDING`, eligible source의 Job 누락은 무결성 오류로 구분 | class 종료 확정 직후 |
| 녹음 resumable upload 상태 | `CLASS_RECORDING_UPLOAD_STATE` | 7 | 영역 | `CLASS_PROCESSING_STATE` | 공통 | MVP 필수 | upload 준비·진행 중·중단·재개 중·완료·실패와 원본 저장을 표시하고 완료 뒤 HQ STT 시작; protocol 세부는 미정 | publisher 탭의 로컬 녹음 마감 뒤 |
| HQ STT·canonical Transcript 상태 | `CLASS_HQ_STT_START` | 7 | 영역 | `CLASS_PROCESSING_STATE` | 공통 | MVP 필수 | 녹음 upload 완료 뒤 전체 녹음 HQ STT와 영구 Transcript의 `FINALIZING`·`FINALIZED`·`FAILED`·`EMPTY`, Segment·시간/녹음 위치 mapping·canonical 전환을 표시; COMPLETED 재시도 성공은 같은 `SESSION_POSTPROCESSING` coordinator를 `attempt + 1`로 requeue해 Session을 COMPLETED로 유지한 채 Answer mapping·canonical Knowledge link·eligible `FINAL_SUMMARY`를 재구축하고 기존 `ANSWER_ORGANIZATION`은 재생성·rebound하지 않음 | 녹음 upload 완료 또는 완료 기록에서 실패 HQ 재시도 |
| Answer 시간 범위 재매핑 상태 | `CLASS_ANSWER_REMAP_STATE` | 7 | 영역 | `CLASS_PROCESSING_STATE` | 공통 | MVP 필수 | canonical 전환 뒤 기존 Answer 시간 범위를 HQ Segment에 다시 연결해 `PENDING`·`SUCCEEDED`·`FAILED`를 표시하고 일부 실패를 다른 기록과 분리; 허용 오차·부분 일치 상태는 미정 | canonical HQ Transcript 확정 뒤 |
| Answer AI 정리 상태 | `CLASS_ANSWER_ORGANIZATION_STATE` | 7 | 영역 | `CLASS_PROCESSING_STATE` | 공통 | MVP 필수 | LIVE 완료 음성 Answer를 Job 없는 `WAITING_SOURCE`로 표시하고 재매핑·source가 terminal이 되면 coordinator가 공유 완료 차단 `ANSWER_ORGANIZATION` Job을 자동 생성; HQ 성공 범위 우선·immutable LIVE 범위 fallback과 Answer별 terminal 성공·실패를 독립 표시 | Session `PROCESSING` 전환 뒤 source 선택 대기부터 시작 |
| FINAL 질문 클러스터링 상태 | `CLASS_FINAL_CLUSTER_STATE` | 7 | 영역 | `CLASS_PROCESSING_STATE` | 공통 | MVP 필수 | LIVE 결과를 fence하고 종료 시점 학생 실제 질문 전체·그때까지 `COMPLETED` Answer가 있는 AI 대표질문을 중앙 여부와 무관하게 처음부터 재배치; 성공 시 eligible 입력을 정확히 한 번 포함하고 미분류 입력을 `기타` Cluster에 두며 member `source_kind=STUDENT_QUESTION\|AI_REPRESENTATIVE`와 `created_in_generation` provenance 표시; FAILED 뒤 명시적 retry는 Answer 시각 상한 재캡처 | Session `PROCESSING` 전환 뒤 |

## 3. MVP 범위 요약

### 필수

- 인증 사용자의 Course 생성·참여, Course별 유일한 교수자 owner와 학생 역할
- 무기한 `[A-Z]{6}` 참여 코드의 owner 전용 회전과 이전 코드 즉시 무효화
- Course별 단일 active class 생성과 상태별 강의자료 PDF 추가·삭제
- 같은 날짜 class의 실제 시작 시각 구분과 `started_at` 기준 완료 목록
- 모든 상태의 class 제목 수정, 상태별 class 삭제와 owner의 Course 삭제
- 실시간 음성 스트리밍과 partial/final STT
- 브라우저 로컬 녹음, resumable upload·원본 저장과 HQ STT
- 전체 녹음 HQ STT, 문장 Segment의 시간·녹음 위치 정렬과 영구 Transcript `FINALIZING`·`FINALIZED`·`FAILED`·`EMPTY`
- canonical Transcript 전환과 기존 Answer 시간 범위·AI 검색 데이터 재연결
- 첫 audio publisher 탭·동일 publisher 재연결과 중복 publisher 전송 거부
- 300자 익명 질문, 500자 AI 작성 도움 초안, ‘나도 궁금해요’와 자동 LIVE 클러스터링·coalescing
- AI 대표질문 중앙·typed child 마인드맵, target별 교수자 음성 Answer와 취소 hard delete
- LIVE 완료 음성 Answer별 자동 AI 정리, HQ 재매핑 우선·원본 LIVE 범위 fallback, 교수자 text 우선·AI 결과 분리 표시와 실패 재시도
- 각 eligible 입력을 정확히 한 번 포함하고 미분류 입력을 `기타` Cluster에 두는 FINAL 전체 재클러스터링, `COMPLETED` class의 미답변 학생 질문 text-only Answer·학생 질문 또는 Answer 보존 대표질문의 기존 Answer text 추가·수정
- 교수자·학생 공통 UI의 요청자 전용 LIVE Summary·Chat과 `COMPLETED` REVIEW Chat
- 개인 AI의 `202 + AIJob` polling·성공 결과 REST 조회, shared WS 비전송과 LIVE→PROCESSING 전이 제거; 기존 polling/resource·멱등 replay 응답은 미정
- 질문·초안·LIVE·REVIEW Chat USER 입력의 앞뒤 공백 제거·Unicode NFC 정규화 후 Unicode code point 길이 검증과 구조화된 `422 VALIDATION_ERROR`
- class 종료 후 canonical Transcript의 Segment·gap, 요약·질문·답변 기록 생성과 부분 실패 표시
- compact `/record` manifest와 Material·Transcript·질문·Answer·Cluster·Job 영역별 점진 로딩·독립 재시도
- 정확히 `MATERIAL|TRANSCRIPT|QUESTION|ANSWER`인 `source_kind`·사용자용 `label`·안정적인 공개 `link`를 이용한 Evidence 표시·이동
- 해당 class 기록 기반 복습 AI
- 권한 재확인 기반 저장 녹음 playback과 Transcript 문장 seek

### MVP 이후

- 음성 원본 다운로드
- Transcript 파일 다운로드
- 종료 후 학생의 추가 복습 질문
- 교수자의 canonical Transcript 수정

## 4. 주요 미정 사항

- HQ STT `RECORDING_TRANSCRIPTION` 개별 Job timeout
- `LIVE → PROCESSING`에서 fence된 LIVE clustering의 공개 terminal 표현: `CANCELLED|SUPERSEDED` 또는 `retryable=false`인 `FAILED`
- 종료 때 사라진 LIVE Summary·Chat·Message·Evidence·Job의 기존 polling/resource 요청 응답과 같은 `Idempotency-Key` replay 의미
- FINAL clustering 대상이 0건일 때 Job을 생략할지, 모델 호출 없는 빈 성공 원장을 남길지와 `final_generation`·`finalized_at` 표현
