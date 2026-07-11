# GOAL 정보 구조(IA)

> 원본: [Notion · GOAL IA 화면 구조 및 상세 설계](https://app.notion.com/p/eaaa8589f50b4c87b0fa1bb6b756e5bc?v=dbcc96da28584639b86edc83210cdea7)
> 동기화 기준: 2026-07-11 · Default view · 레벨 오름차순

## 1. 문서 목적

GOAL 서비스의 페이지, 화면 영역, 사용자 기능과 백그라운드 작업을 계층적으로 정리한다. 사용자 계정은 고정된 역할을 갖지 않으며, Course별로 교수자 또는 학생 역할을 가진다.

### 용어

- **Course**: 한 학기 단위 수업방
- **class**: Course 안의 날짜별 강의 세션
- **실시간 class**: 현재 진행 중인 강의 세션
- **끝난 class**: 강의 종료 후 기록 정리가 완료된 세션
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
| GOAL 메인 화면 | `MAIN_PAGE` | 1 | 페이지 | `ROOT` | 비로그인 | MVP 필수 | 서비스 가치 소개와 Google 로그인 진입을 제공하고, 로그인 후 대시보드로 전환 | GOAL URL에 비로그인 상태로 접속 |
| GOAL 메인 화면 로그인 후 | `MAIN_PAGE_AUTH` | 1 | 페이지 | `ROOT` | 공통 | MVP 필수 | 참여·관리 중인 Course 목록, Course 생성·참여와 내 정보 진입을 제공하는 대시보드 | 인증된 사용자가 로그인하거나 서비스에 재접속 |

### Level 2 · 대시보드 기능 및 페이지

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| 한 학기 Course 만들기 버튼 | `COURSE_CREATE_BUTTON` | 2 | 기능 | `MAIN_PAGE_AUTH` | 교수자 | MVP 필수 | 과목명과 학기를 입력하는 Course 생성 페이지로 이동 | 로그인 후 메인 화면에서 Course 만들기 선택 |
| 한 학기 Course 만들기 페이지 | `COURSE_CREATE_PAGE` | 2 | 페이지 | `MAIN_PAGE_AUTH` | 교수자 | MVP 필수 | 과목명과 학기를 입력해 Course와 고유 참여 코드를 생성 | 로그인 후 메인 화면에서 Course 만들기 선택 |
| 한 학기 Course 참여하기 버튼 | `COURSE_JOIN_BUTTON` | 2 | 기능 | `MAIN_PAGE_AUTH` | 학생 | MVP 필수 | 참여 코드를 입력하는 Course 참여 페이지로 이동 | 로그인 후 메인 화면에서 Course 참여하기 선택 |
| 한 학기 Course 참여하기 | `COURSE_JOIN_PAGE` | 2 | 페이지 | `MAIN_PAGE_AUTH` | 학생 | MVP 필수 | 교수자에게 받은 참여 코드를 검증해 학생으로 Course에 참여 | 로그인 후 메인 화면에서 Course 참여하기 선택 |
| 로그인 버튼 | `LOGIN_BUTTON_AREA` | 2 | 기능 | `MAIN_PAGE` | 비로그인 | MVP 필수 | Google 로그인 페이지로 이동하고 성공 시 로그인 후 메인 화면으로 전환 | 비로그인 사용자가 로그인 버튼 선택 |
| 로그인 페이지 | `LOGIN_PAGE` | 2 | 페이지 | `MAIN_PAGE` | 비로그인 | MVP 필수 | Google 계정으로 인증하며 역할은 계정이 아니라 Course별로 결정 | 메인 화면에서 로그인 버튼 선택 |
| 내가 참여 중인 Course 목록 | `MY_COURSE_LIST` | 2 | 영역 | `MAIN_PAGE_AUTH` | 공통 | MVP 필수 | 학생으로 참여한 Course 카드와 진입 기능을 표시하고 빈 목록에서는 코드 참여를 안내 | 로그인 후 메인 화면에 항상 표시 |
| 내 정보 조회 버튼 | `MY_INFO_BUTTON` | 2 | 기능 | `MAIN_PAGE_AUTH` | 공통 | MVP 필수 | 내 정보 조회 페이지로 이동 | 로그인 후 프로필 또는 내 정보 버튼 선택 |
| 내 정보 조회 페이지 | `MY_INFO_PAGE` | 2 | 페이지 | `MAIN_PAGE_AUTH` | 공통 | MVP 필수 | 계정 기본 정보, 로그아웃, 관리·참여 중인 Course 요약을 표시 | 로그인 후 메인 화면에서 내 정보 버튼 선택 |
| 내가 관리 중인 Course 목록 | `MY_OWN_COURSE_LIST` | 2 | 영역 | `MAIN_PAGE_AUTH` | 공통 | MVP 필수 | 교수자로 생성한 Course 카드와 진입 기능을 표시하고 빈 목록에서는 Course 생성을 안내 | 로그인 후 메인 화면에 항상 표시 |

### Level 3 · Course 및 계정 기능

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| Course 페이지-교수자 | `COURSE_PAGE_PROF` | 3 | 페이지 | `MY_OWN_COURSE_LIST` | 교수자 | MVP 필수 | Course 정보·참여 코드, 현재 class 상태, class 생성·시작·입장과 완료 기록 진입 제공 | 관리 중인 Course 선택 또는 Course 생성 직후 |
| Course 페이지-학생 | `COURSE_PAGE_STUD` | 3 | 페이지 | `MY_COURSE_LIST` | 학생 | MVP 필수 | Course 정보, 현재 class 상태·입장, 날짜별 완료 class 목록과 강의 기록 진입 제공 | 참여 중인 Course 선택 또는 Course 참여 직후 |
| 내 정보 수정 버튼 | `MY_INFO_CHANGE_BUTTON` | 3 | 기능 | `MY_INFO_PAGE` | 공통 | MVP 선택 | 수정 가능한 계정 정보를 편집하는 흐름으로 이동 | 내 정보 페이지에서 수정 버튼 선택 |

### Level 4 · class 페이지

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| 오늘 class 생성 및 준비 페이지 | `CLASS_CREATE_PAGE` | 4 | 페이지 | `COURSE_PAGE_PROF` | 교수자 | MVP 필수 | class 제목·날짜를 입력하고 강의자료 PDF를 업로드해 시작 준비 상태로 생성 | 교수자가 Course 페이지에서 오늘 class 생성 선택 |
| Course 참여 코드 영역 | `COURSE_CODE_AREA` | 4 | 영역 | `COURSE_PAGE_PROF` | 교수자 | MVP 필수 | 학생 참여용 고유 코드를 표시·복사하며 권한 없는 사용자에게는 숨김 | 교수자가 자신이 관리하는 Course 페이지에 진입 |
| 끝난 class 메인 페이지-교수자 | `ENDED_CLASS_PAGE_PROF` | 4 | 페이지 | `COURSE_PAGE_PROF` | 교수자 | MVP 필수 | 강의자료, final Transcript, AI 요약, 질문·답변 정리와 실패한 후처리 작업 재시도 제공 | 완료 class 목록에서 특정 class 선택 |
| 끝난 class 메인 페이지-학생 | `ENDED_CLASS_PAGE_STUD` | 4 | 페이지 | `COURSE_PAGE_STUD` | 학생 | MVP 필수 | 강의자료, final Transcript, AI 요약, 질문·교수자 답변과 복습 AI 제공 | 완료 class 목록에서 특정 class 선택 |
| 실시간 class 메인 페이지-교수자 | `LIVE_CLASS_PAGE_PROF` | 4 | 페이지 | `COURSE_PAGE_PROF` | 교수자 | MVP 필수 | STT 상태, 실시간 Transcript, 질문 클러스터·반응 순위, 답변과 class 종료 기능 제공 | class 시작 또는 진행 중인 class에 재입장 |
| 실시간 class 메인 페이지-학생 | `LIVE_CLASS_PAGE_STUD` | 4 | 페이지 | `COURSE_PAGE_STUD` | 학생 | MVP 필수 | 실시간 Transcript, 익명 질문·반응, AI 요약과 강의자료 기반 AI 채팅 제공 | 진행 중인 class 입장 선택 |

### Level 5 · 화면 영역 및 주요 기능

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| class 강의자료 PDF 업로드 | `CLASS_MATERIAL_UPLOAD` | 5 | 기능 | `CLASS_CREATE_PAGE` | 교수자 | MVP 필수 | PDF 업로드와 AI 검색용 텍스트 추출·임베딩 처리 상태 표시 | class 생성 페이지에서 PDF 선택 |
| 끝난 class AI 대화 영역 | `ENDED_AI_CHAT_AREA` | 5 | 영역 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 필수 | 해당 class의 PDF, final Transcript와 Q&A를 근거로 복습 질의응답 제공 | 학생 완료 class 페이지에 표시하거나 접고 펼침 |
| 끝난 class 녹음 파일 다운로드 | `ENDED_AUDIO_DOWNLOAD` | 5 | 기능 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 이후 | 저장된 강의 음성 원본 다운로드 | 음성 원본 저장이 활성화된 완료 class에서 다운로드 선택 |
| 끝난 class 강의 녹음 재생 | `ENDED_AUDIO_PLAY` | 5 | 기능 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 이후 | 저장된 강의 음성 원본 재생 | 음성 원본 저장이 활성화된 완료 class에서 재생 선택 |
| 끝난 class Transcript 다운로드 | `ENDED_CLASS_TRANSCRIPT_DOWNLOAD` | 5 | 기능 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 이후 | final Transcript를 텍스트 파일로 다운로드 | 완료 class에서 Transcript 다운로드 선택 |
| 끝난 class 강의자료 다시 보기 | `ENDED_MATERIAL_VIEW` | 5 | 기능 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 필수 | Course 참여 권한을 확인한 뒤 해당 class의 강의자료 PDF 열람 | 완료 class에 PDF가 존재 |
| 끝난 class 질문 목록 영역 | `ENDED_QUESTION_AREA` | 5 | 영역 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 필수 | 질문을 클러스터별로 묶고 반응 수, 답변 상태와 연결된 교수자 답변 표시 | 완료 class 페이지에 항상 표시 |
| 끝난 class AI 강의 요약 영역 | `ENDED_SUMMARY_AREA` | 5 | 영역 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 필수 | 핵심 내용·주요 개념·후처리 상태를 표시하고 실패 시 재시도 또는 저장 기록 우선 열람 지원 | 완료 class 페이지에 진입 |
| 끝난 class Transcript 영역 | `ENDED_TRANSCRIPT_AREA` | 5 | 영역 | `ENDED_CLASS_PAGE_*` | 공통 | MVP 필수 | final Transcript를 시간 순으로 표시하고 로딩·빈 상태·후처리 실패를 구분 | 완료 class 페이지에 항상 표시 |
| 실시간 class AI 대화 영역 | `LIVE_AI_CHAT_AREA` | 5 | 영역 | `LIVE_CLASS_PAGE_*` | 공통 | MVP 필수 | PDF와 현재 Transcript 기반 요약·설명·질의응답 및 처리·실패·재시도 상태 제공 | 학생 실시간 class 페이지에 표시하거나 접고 펼침 |
| 실시간 class 음성 스트리밍(STT) | `LIVE_AUDIO_STREAM` | 5 | 백그라운드 작업 | `LIVE_CLASS_PAGE_PROF` | 교수자 | MVP 필수 | 마이크 음성을 조각 단위로 전송해 partial/final STT 생성; 음성 원본 저장은 후순위 | 교수자가 class를 시작하고 마이크 권한 허용 |
| 실시간 class 끝내기 | `LIVE_CLASS_QUIT` | 5 | 기능 | `LIVE_CLASS_PAGE_PROF` | 교수자 | MVP 필수 | 새 실시간 입력을 마감하고 class를 정리 중 상태로 전환해 후처리 시작 | 교수자가 종료 버튼을 선택하고 확인 |
| 실시간 class 시작하기 | `LIVE_CLASS_START` | 5 | 기능 | `CLASS_CREATE_PAGE` | 교수자 | MVP 필수 | class 상태를 진행 중으로 바꾸고 음성 스트리밍, Transcript, 질문과 AI 기능 활성화 | class 정보와 강의자료 준비 완료 후 시작 선택 |
| 실시간 class 질문 목록 영역 | `LIVE_QUESTION_AREA` | 5 | 영역 | `LIVE_CLASS_PAGE_*` | 공통 | MVP 필수 | 익명 질문, 반응 수, 답변 상태와 유사 질문 클러스터 표시; 교수자는 정렬·답변 대상 선택 | 실시간 class 페이지에 항상 표시 |
| 실시간 class Transcript 영역 | `LIVE_TRANSCRIPT_AREA` | 5 | 영역 | `LIVE_CLASS_PAGE_*` | 공통 | MVP 필수 | partial STT를 즉시 갱신하고 final Transcript를 누적 표시하며 연결·재연결 상태 구분 | 실시간 class 페이지에 항상 표시 |

### Level 6 · 세부 기능 및 후처리

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| 끝난 class에서 AI와 질의응답 | `ENDED_AI_CHATING` | 6 | 기능 | `ENDED_AI_CHAT_AREA` | 공통 | MVP 필수 | 해당 class의 PDF, final Transcript와 Q&A를 검색해 근거 기반 답변 생성 | 완료 class AI 채팅에 복습 질문 전송 |
| 끝난 class Transcript 위치 재생 | `ENDED_CLASS_TRANSCRIPT_PLAY` | 6 | 기능 | `ENDED_TRANSCRIPT_AREA` | 공통 | MVP 이후 | 선택한 Transcript 문장의 시작 시각으로 녹음 재생 위치 이동 | 음성 원본·시각 매핑이 있을 때 Transcript 문장 선택 |
| 끝난 class 복습 질문 답변 | `ENDED_QUESTION_ANSWER` | 6 | 기능 | `ENDED_QUESTION_AREA` | 교수자 | MVP 이후 | 종료 후 추가된 복습 질문에 텍스트 답변 등록 | 완료 class의 미답변 복습 질문 선택 |
| 끝난 class 복습 질문 올리기 | `ENDED_QUESTION_UPLOAD` | 6 | 기능 | `ENDED_QUESTION_AREA` | 학생 | MVP 이후 | 종료 후 추가 질문을 남기는 확장 기능; MVP에서는 종료된 class에 새 질문·반응 등록 불가 | 완료 class에서 추가 복습 질문 등록 |
| 실시간 class에서 AI와 질의응답 | `LIVE_AI_CHATING` | 6 | 기능 | `LIVE_AI_CHAT_AREA` | 공통 | MVP 필수 | 현재 class의 PDF와 Transcript를 우선 근거로 답변하고 근거가 없으면 확인 불가 안내 | AI 채팅창에 질문 또는 설명 요청 전송 |
| class 종료 후 기록 정리 | `LIVE_CLASS_QUIT_PROCESS` | 6 | 백그라운드 작업 | `LIVE_CLASS_QUIT` | 공통 | MVP 필수 | final Transcript, 강의 요약, 질문 클러스터와 답변 연결을 독립 처리하고 부분 성공·재시도 지원 | 교수자가 class 종료 확정 |
| 실시간 질문 답변 시작 | `LIVE_QUESTION_ANSWER` | 6 | 기능 | `LIVE_QUESTION_AREA` | 교수자 | MVP 필수 | 선택 시점부터 교수자 음성의 final Transcript를 답변 후보 구간으로 연결 | 미답변 질문 또는 질문 클러스터 선택 |
| 실시간 질문 답변 완료 | `LIVE_QUESTION_ANSWER_COMPLETE` | 6 | 기능 | `LIVE_QUESTION_AREA` | 교수자 | MVP 필수 | 답변 종료 시 해당 final Transcript 구간을 질문 답변으로 확정하고 상태 전파 | 답변 대상 선택 후 음성 답변 완료 |
| 실시간 유사 질문 클러스터링 | `LIVE_QUESTION_CLUSTER` | 6 | 백그라운드 작업 | `LIVE_QUESTION_AREA` | 공통 | MVP 필수 | 같은 class의 열린 질문을 의미 유사도로 묶고 대표 주제와 원본 질문 목록 갱신 | 새 질문 등록 후 클러스터링 실행 |
| AI 질문 문장 작성 도움 | `LIVE_QUESTION_DRAFT_HELP` | 6 | 기능 | `LIVE_AI_CHAT_AREA` | 학생 | MVP 필수 | 현재 강의 맥락에 맞는 익명 질문 문장 후보 제안 | 학생이 질문 작성 도움 요청 |
| ‘나도 궁금해요’ 반응 | `LIVE_QUESTION_METOO` | 6 | 기능 | `LIVE_QUESTION_AREA` | 학생 | MVP 필수 | 학생별 한 번만 반응하고 추가·취소 결과와 최신 수를 실시간 반영 | 다른 질문의 반응을 선택 또는 취소 |
| 실시간 인기 질문 우선 정렬 | `LIVE_QUESTION_SORT` | 6 | 기능 | `LIVE_QUESTION_AREA` | 공통 | MVP 필수 | 미답변 질문을 반응 수 내림차순으로 정렬해 교수자의 답변 우선순위 판단 지원 | 교수자가 인기순 정렬 선택 |
| 실시간 class 질문 올리기 | `LIVE_QUESTION_UPLOAD` | 6 | 기능 | `LIVE_QUESTION_AREA` | 학생 | MVP 필수 | 작성자 이름을 노출하지 않고 질문을 추가하며 빈 입력·중복 제출·전송 실패 처리 | 질문 내용을 입력하고 등록 |
| 실시간 class Transcript 요약 | `LIVE_TRANSCRIPT_SUMMARY` | 6 | 기능 | `LIVE_TRANSCRIPT_AREA` | 학생 | MVP 필수 | 현재까지 또는 선택한 Transcript와 관련 PDF를 바탕으로 놓친 맥락 요약 | 학생이 현재까지 또는 선택 영역 요약 요청 |

### Level 7 · 처리 상태

| 화면명 | 노드 ID | 레벨 | 유형 | 상위 노드 | 역할 | 범위 | 핵심 내용 | 진입 조건 |
|---|---|---:|---|---|---|---|---|---|
| class 기록 정리 중 상태 | `CLASS_PROCESSING_STATE` | 7 | 영역 | `LIVE_CLASS_QUIT_PROCESS` | 공통 | MVP 필수 | Transcript 확정·요약·질문 답변 정리의 진행·부분 성공·실패를 표시하고 완료 후 기록 페이지로 전환 | class 종료 후 백그라운드 정리 작업 진행 중 |

## 3. MVP 범위 요약

### 필수

- Course 생성·참여 및 참여 코드 관리
- 날짜별 class 생성과 강의자료 PDF 업로드
- 실시간 음성 스트리밍과 partial/final STT
- 익명 질문, ‘나도 궁금해요’, 유사 질문 클러스터링과 교수자 답변 연결
- 수업 중 Transcript 요약과 강의자료 기반 AI 질의응답
- class 종료 후 Transcript·요약·질문·답변 기록 생성
- 해당 class 기록 기반 복습 AI

### MVP 이후

- 음성 원본 저장·재생·다운로드
- Transcript 파일 다운로드와 녹음 시점 이동
- 종료 후 추가 복습 질문과 교수자 텍스트 답변
