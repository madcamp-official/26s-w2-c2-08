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
| 서비스 진입 | Google·이메일 로그인    | `LOGIN_PAGE`             | `login.html`                 | 확인 가능 |
| 서비스 진입 | 이메일 계정 가입        | `EMAIL_SIGNUP_PAGE`      | `signup.html`                | 확인 가능 |
| 서비스 진입 | 로그인 후 대시보드      | `MAIN_PAGE_AUTH`         | `dashboard.html`             | 확인 가능 |
| 서비스 진입 | 내 정보                 | `MY_INFO_PAGE`           | `my-info.html`               | 확인 가능 |
| Course      | Course 생성             | `COURSE_CREATE_PAGE`     | `course-create.html`         | 확인 가능 |
| Course      | Course 참여             | `COURSE_JOIN_PAGE`       | `course-join.html`           | 확인 가능 |
| Course      | 교수자 Course           | `COURSE_PAGE_PROF`       | `course-professor.html`      | 확인 가능 |
| Course      | 학생 Course             | `COURSE_PAGE_STUD`       | `course-student.html`        | 확인 가능 |
| Course      | Course 기록 workspace   | `COURSE_WORKSPACE_NAV`   | `course-workspace.html`      | 확인 가능 |
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
| 비로그인 Session 확인 상태        | [`main.html?session=checking`](main.html?session=checking), [`main.html?session=error`](main.html?session=error)                                                                                                             |
| 로그인 정보·요청 오류             | [`login.html?state=invalid-credentials`](login.html?state=invalid-credentials), [`login.html?state=request-error`](login.html?state=request-error)                                                                           |
| 로그인 독립 안내                  | [`취소`](login.html?notice=cancelled), [`로그아웃`](login.html?notice=logged-out), [`탈퇴`](login.html?notice=withdrawn)                                                                                                     |
| 가입 이메일 중복·입력 오류        | [`signup.html?state=email-exists`](signup.html?state=email-exists), [`signup.html?state=validation-error`](signup.html?state=validation-error)                                                                               |
| 가입 Session·요청 오류            | [`signup.html?state=session-error`](signup.html?state=session-error), [`signup.html?state=request-error`](signup.html?state=request-error)                                                                                   |
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

## Course workspace 정책 검토 경로

Course workspace Prototype은 실제 archive API를 호출하지 않는다. 좌측에는 정확히 `PDF 자료`, `Transcript`, `AI 요약`, `질의응답` 네 route만 제공하고, 그 오른쪽 class rail의 `LIVE CLASS` slot을 현재 class 유무와 관계없이 유지한다. 완료 class 목록과 archive 본문은 독립 상태이므로 한 영역 오류가 다른 영역을 가리지 않는다.

| 검토 항목                               | 대표 경로                                                                                                                                                                                                               |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 네 archive route                        | [`PDF 자료`](course-workspace.html?archive=materials), [`Transcript`](course-workspace.html?archive=transcripts), [`AI 요약`](course-workspace.html?archive=summaries), [`질의응답`](course-workspace.html?archive=qna) |
| LIVE CLASS 실제 상태                    | [`LIVE`](course-workspace.html?session=live), [`READY`](course-workspace.html?session=ready), [`PROCESSING`](course-workspace.html?session=processing), [`없음`](course-workspace.html?session=none)                    |
| 완료 class 목록 독립 상태               | [`로딩`](course-workspace.html?classes=loading), [`빈 상태`](course-workspace.html?classes=empty), [`오류`](course-workspace.html?classes=error)                                                                        |
| 선택 archive 본문 독립 상태             | [`로딩`](course-workspace.html?content=loading), [`빈 상태`](course-workspace.html?content=empty), [`오류`](course-workspace.html?content=error)                                                                        |
| class rail 오류 중 Transcript 본문 유지 | [`classes=error&archive=transcripts`](course-workspace.html?archive=transcripts&classes=error&content=normal)                                                                                                           |
| archive 오류 중 현재 class 없음 유지    | [`session=none&content=error`](course-workspace.html?archive=qna&session=none&classes=normal&content=error)                                                                                                             |

데스크톱 1440px에서는 archive navigation·class rail·본문을 세 열로, 768px에서는 상단 4열 navigation·접이식 class rail·본문으로 배치한다. 375px에서는 navigation을 2열로 바꾸고 rail과 본문을 한 열로 쌓는다. 모든 주요 동작은 최소 44px이며 기본 공통 focus와 reduced motion 규칙을 따른다.

## LIVE class 정책 검토 경로

상단 상태 도구는 제품 기능이 아니라 서버 상태와 독립 실패 조합을 검토하는 목 도구다. 질문 클러스터링은 사용자가 실행하지 않으며 질문 commit 뒤 시스템이 자동 예약한다.

| 검토 항목                        | 대표 경로                                                                                                                                                                                                                                                                        |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 두 번째 publisher의 Audio만 거부 | [`publisher=conflict&audio=error&recording=idle`](class-live-professor.html?publisher=conflict&audio=error&recording=idle)                                                                                                                                                       |
| Audio·로컬 녹음 독립 실패        | [`audio=error&recording=recording`](class-live-professor.html?audio=error&recording=recording), [`audio=listening&recording=failed`](class-live-professor.html?audio=listening&recording=failed)                                                                                 |
| LIVE Material 제한·독립 처리     | [`materials=full`](class-live-professor.html?materials=full), [`materials=processing`](class-live-professor.html?materials=processing), [`materials=all-ready`](class-live-professor.html?materials=all-ready), [`materials=failed`](class-live-professor.html?materials=failed) |
| 자동 클러스터링 재시도·실패      | [`questions=clustering-retry-reserved`](class-live-professor.html?questions=clustering-retry-reserved), [`questions=cluster-failed`](class-live-professor.html?questions=cluster-failed)                                                                                         |
| Answer final 후보·대기           | [`answer=candidate`](class-live-professor.html?answer=candidate), [`answer=not-ready`](class-live-professor.html?answer=not-ready)                                                                                                                                               |
| 개인 Summary·Chat polling        | [`summary=not-ready&chat=evidence`](class-live-professor.html?summary=not-ready&chat=evidence), [`chat=error`](class-live-professor.html?chat=error)                                                                                                                             |
| 종료 뒤 LIVE 재노출 금지         | [`view=processing`](class-live-professor.html?view=processing)                                                                                                                                                                                                                   |
| 학생 미배치 질문·재시도 예약     | [`questions=clustering-retry-reserved`](class-live-student.html?questions=clustering-retry-reserved), [`questions=cluster-failed`](class-live-student.html?questions=cluster-failed)                                                                                             |
| final 0건 Summary Job 없음       | [`transcript=empty&summary=complete`](class-live-student.html?transcript=empty&summary=complete)                                                                                                                                                                                 |
| 초안 원문 유지·안전한 Evidence   | [`draft=error&chat=evidence`](class-live-student.html?draft=error&chat=evidence)                                                                                                                                                                                                 |
| 학생 종료·권한·재동기화          | [`view=processing`](class-live-student.html?view=processing), [`view=completed`](class-live-student.html?view=completed), [`view=wrong-role`](class-live-student.html?view=wrong-role), [`transcript=resync`](class-live-student.html?transcript=resync)                         |

LIVE Prototype은 다음 불변식을 유지한다.

- 첫 성공 `audio.start`만 publisher를 선점하며 충돌 탭의 저장 조회는 유지한다.
- 모든 질문은 별도 `POPULAR|RECENT` 목록에 즉시 나타나고, 새 질문은 clustering 성공 뒤에만 대표질문의 branch로 들어간다. active Job 중 질문은 다음 실행에 합친다. retry 예약 중 질문은 watermark만 높이며 같은 행의 원래 captured 범위 재시도가 성공한 뒤 fresh Job에서 처리한다.
- 개인 Summary·Chat은 requester-only `AIJob` polling과 저장된 최종 결과만 사용한다. `PROCESSING`·`COMPLETED` 전환 시 Message·Evidence·Job 식별자를 포함해 LIVE 개인 데이터를 삭제한다.
- Evidence는 배열 위치나 cursor가 아닌 안정적인 공개 link를 사용하며 정적 Prototype에서는 실제 API로 이동하지 않고 권한 재검사 동작만 모의한다.
- `CAPTURING` Answer가 있으면 종료할 수 없다. 종료 수락 뒤에는 즉시 `PROCESSING`만 표시하고 과거 LIVE control을 다시 활성화하지 않는다.

## PROCESSING 정책 검토 경로

독립 query 상태를 임의로 섞지 않고 실제로 가능한 처리 순서와 부분 실패 조합을 scenario preset으로 검토한다. Final clustering은 LIVE→PROCESSING 종료 transaction에서 자동 생성되어 HQ Transcript와 독립 실행하며, Summary와 Answer organization은 source gate를 따른다.

| 검토 항목                                   | 대표 경로                                                                                                                                                                                                                                                                               |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| publisher 원본 녹음 upload                  | [`scenario=uploading`](class-processing.html?role=professor&scenario=uploading), [`scenario=upload-interrupted`](class-processing.html?role=professor&scenario=upload-interrupted), [`scenario=upload-failed`](class-processing.html?role=professor&scenario=upload-failed)             |
| RECORDING version HQ STT·canonical 전환     | [`scenario=transcribing`](class-processing.html?role=professor&scenario=transcribing), [`scenario=empty`](class-processing.html?role=professor&scenario=empty), [`scenario=hq-failed`](class-processing.html?role=professor&scenario=hq-failed)                                         |
| Answer mapping·AI 정리·FINAL Summary        | [`scenario=organizing`](class-processing.html?role=professor&scenario=organizing)                                                                                                                                                                                                       |
| Final clustering 실패·기존 기록 유지        | [`scenario=finishing-with-failure`](class-processing.html?role=professor&scenario=finishing-with-failure)                                                                                                                                                                               |
| eligible Summary 원장 불일치                | [`scenario=integrity-error`](class-processing.html?role=professor&scenario=integrity-error)                                                                                                                                                                                             |
| manifest 뒤 영역별 독립 로딩·오류 복구      | [`region=loading`](class-processing.html?role=professor&scenario=organizing&region=loading), [`region=error`](class-processing.html?role=professor&scenario=organizing&region=error), [`region=page-error`](class-processing.html?role=professor&scenario=organizing&region=page-error) |
| 전체 manifest·인증·권한 실패                | [`view=loading`](class-processing.html?role=professor&view=loading), [`view=error`](class-processing.html?role=professor&view=error), [`view=forbidden`](class-processing.html?role=professor&view=forbidden), [`view=expired`](class-processing.html?role=professor&view=expired)      |
| 학생 읽기 전용 상태                         | [`role=student&scenario=transcribing`](class-processing.html?role=student&scenario=transcribing)                                                                                                                                                                                        |
| 서버 COMPLETED·부분 실패 완료 기록으로 이동 | [`scenario=completed-with-failures`](class-processing.html?role=professor&scenario=completed-with-failures)                                                                                                                                                                             |

PROCESSING Prototype은 `/record` 본문에 큰 배열을 embed하지 않고 count·상태·공개 조회 경로만 받은 뒤 자료·Transcript timeline·질문·Cluster·Answer·공유 Job을 독립 조회하는 경계를 보여 준다. worker heartbeat·lease·Job·Session timeout은 브라우저가 자체 판정하지 않고 서버가 반환한 terminal 상태만 표시한다. PROCESSING에서는 개인 REVIEW Chat과 Final clustering retry를 제공하지 않는다.

## 완료 기록 정책 검토 경로

교수자와 학생은 같은 manifest·녹음 player·canonical Transcript·질문 마인드맵·Answer·개인 REVIEW Chat 구조를 사용한다. 녹음 역할별 접근은 미정이므로 기본 상태는 `checking`이며 `playback=ready`는 허용 정책이 아니라 상호작용 검토 fixture다.

| 검토 항목                                 | 교수자 경로                                                                                                                                                                                                                                                                       | 학생 경로                                                                                                                                                                                                                                                                   |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 녹음 권한 확인·허용·거부                  | [`checking`](class-ended-professor.html), [`ready`](class-ended-professor.html?playback=ready), [`forbidden`](class-ended-professor.html?playback=forbidden)                                                                                                                      | [`checking`](class-ended-student.html), [`ready`](class-ended-student.html?playback=ready), [`forbidden`](class-ended-student.html?playback=forbidden)                                                                                                                      |
| Transcript seek 독립 상태                 | [`seeking`](class-ended-professor.html?playback=ready&seek=seeking), [`active`](class-ended-professor.html?playback=ready&seek=active), [`seek-error`](class-ended-professor.html?playback=ready&seek=seek-error)                                                                 | [`seeking`](class-ended-student.html?playback=ready&seek=seeking), [`active`](class-ended-student.html?playback=ready&seek=active), [`seek-error`](class-ended-student.html?playback=ready&seek=seek-error)                                                                 |
| Segment·Gap cursor 추가 페이지 실패       | [`transcript=page-error`](class-ended-professor.html?playback=ready&transcript=page-error)                                                                                                                                                                                        | [`transcript=page-error`](class-ended-student.html?playback=ready&transcript=page-error)                                                                                                                                                                                    |
| Cluster 목록·child cursor 분리            | [`clusters=normal`](class-ended-professor.html?clusters=normal), [`clusters=page-error`](class-ended-professor.html?clusters=page-error)                                                                                                                                          | [`clusters=normal`](class-ended-student.html?clusters=normal), [`clusters=page-error`](class-ended-student.html?clusters=page-error)                                                                                                                                        |
| HQ 실패·LIVE canonical 보존               | [`transcript=failed`](class-ended-professor.html?transcript=failed&summary=source-unavailable)                                                                                                                                                                                    | [`transcript=failed`](class-ended-student.html?transcript=failed&summary=source-unavailable)                                                                                                                                                                                |
| FINAL clustering·Answer organization 실패 | [`실패+교수자 retry`](class-ended-professor.html?clusters=cluster-failed&answers=organization-failed&jobs=partial-failure)                                                                                                                                                        | [`실패 읽기 전용`](class-ended-student.html?clusters=cluster-failed&answers=organization-failed&jobs=partial-failure)                                                                                                                                                       |
| retry 관찰                                | [`재시도 중`](class-ended-professor.html?clusters=cluster-retrying&answers=organization-retrying&jobs=retrying)                                                                                                                                                                   | [`재시도 상태만`](class-ended-student.html?clusters=cluster-retrying&answers=organization-retrying&jobs=retrying)                                                                                                                                                           |
| Summary 의미 분기                         | [`NO_FINAL_TRANSCRIPT`](class-ended-professor.html?transcript=empty&summary=not-applicable), [`SOURCE_UNAVAILABLE`](class-ended-professor.html?transcript=failed&summary=source-unavailable), [`DATA_ERROR`](class-ended-professor.html?transcript=data-error&summary=data-error) | [`NO_FINAL_TRANSCRIPT`](class-ended-student.html?transcript=empty&summary=not-applicable), [`SOURCE_UNAVAILABLE`](class-ended-student.html?transcript=failed&summary=source-unavailable), [`DATA_ERROR`](class-ended-student.html?transcript=data-error&summary=data-error) |
| 개인 REVIEW Chat·안전한 Evidence          | [`complete`](class-ended-professor.html?chat=complete), [`no-evidence`](class-ended-professor.html?chat=no-evidence), [`failed`](class-ended-professor.html?chat=failed)                                                                                                          | [`complete`](class-ended-student.html?chat=complete), [`no-evidence`](class-ended-student.html?chat=no-evidence), [`failed`](class-ended-student.html?chat=failed)                                                                                                          |

완료 기록의 Transcript·질문·Cluster·Answer는 독립 cursor 영역이다. Cluster 목록 cursor와 각 Cluster child cursor도 서로 범위를 침범하지 않는다. 교수자 manifest의 4개, 학생 manifest의 3개 Cluster는 목록 “더 보기”로 모두 접근할 수 있고 각 목록에는 `기타 질문` fallback fixture가 있다. “더 보기” 실패는 이미 불러온 항목을 유지하고 같은 cursor만 재시도한다.

Evidence의 공개 `source_kind`는 `MATERIAL|TRANSCRIPT|QUESTION|ANSWER`만 사용한다. `TRANSCRIPT` link는 Session·Transcript version·stable sequence 범위에 고정하고 `QUESTION` link는 학생 질문 또는 AI 대표질문 단건 경로를 사용한다. 안전한 `label`을 유지하되 `link=null`은 비활성화한다. Final Cluster member는 `source_kind=STUDENT_QUESTION|AI_REPRESENTATIVE`로 구분한다.

Transcript seek는 player와 독립된 `idle → seeking → active|seek-error` 상태이며 `active`가 되어도 사용자가 재생을 선택하기 전에는 player를 재생 중으로 바꾸지 않는다. 실패한 `RECORDING_TRANSCRIPTION`은 문서화된 system-orchestrated recovery만 표시하고 교수자 public retry control을 제공하지 않는다. 학생 DOM에는 제목·class 삭제, Material 추가·삭제, text Answer, shared Job retry control이 없다.

## 프로토타입과 실제 구현의 경계

- 버튼과 입력은 화면 흐름 확인을 위한 로컬 상태만 변경한다.
- 새로고침하면 목 상태가 초기화될 수 있다.
- 참여 코드, 사용자, Course와 class 정보는 모두 예시다.
- 네트워크 요청이 필요한 동작은 결과를 모의 표시한다.
- 프로덕션 React 구현 시 API 명세, OpenAPI와 권한 규칙을 다시 확인해야 한다.
