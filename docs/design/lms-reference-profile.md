# LMS 디자인 레퍼런스 프로필

> 실행 ID: `20260715-0157`
>
> 적용 대상: `frontend/src`의 production React UI
>
> 원본 보존: ZIP과 추출 PNG는 저장소 밖에서 읽기 전용으로 검사했으며 이 문서에 복제하지 않는다.

## 1. 목적과 우선순위

이 프로필은 제공된 5개 ZIP에서 일관된 시각 언어만 추출해 GOAL의 실제 제품
계약에 적용하는 고정 기준이다. 레퍼런스의 정보 구조·문구·로고·상거래 기능은
복사하지 않는다. 디자인 판단이 충돌하면 다음 순서를 따른다.

1. GOAL 제품·API·권한·상태 계약
2. 접근성과 세 viewport의 실제 사용성
3. 이 문서의 공통 token·component 규칙
4. 화면별 Primary reference
5. Secondary·Structure-only reference

Figma MCP나 다른 디자인 사이트는 이 작업의 기준에 포함하지 않는다.

## 2. 원본 무결성 및 inventory

모든 archive entry에 대해 absolute path, Windows drive path와 `..` 경로가 없음을
검사한 뒤 실행별 OS 임시 디렉터리에만 추출했다. 32개 PNG는 이미지 decoder로
열어 크기를 확인했다.

| Archive                                          | SHA-256                                                            | PNG 수 |
| ------------------------------------------------ | ------------------------------------------------------------------ | -----: |
| `Learning Management System (Community).zip`     | `80f048e2ffa60ecac4cd28b8d029d6c2ea10cba420dd32eafe0e1882690adb81` |      6 |
| `Learning Management System (Community) (1).zip` | `cb7467f568ebb691d1f5c7f5402f0ad3b01c49fa0710ddf6c807ec8416cb53d0` |      2 |
| `Learning Management System (Community) (2).zip` | `e8bb16672033917d817a1b82f3f38cf220511cda74e1fd4d045ff8e2ddc0617c` |      3 |
| `Learning Management System (Community) (3).zip` | `53295ca5369fe6cb2b0ca9f6259d7398d7085d1fef2f74737fd1b164d0ae8d0f` |     17 |
| `Learning Management System (Community) (4).zip` | `8c6adabdd29e3b4b08e60a4eb3f2146bb0c05058c2bb5b7397a15cc6e4759984` |      4 |

### 이미지 목록

| Archive | 이미지                            |       크기 | 분류                    |
| ------- | --------------------------------- | ---------: | ----------------------- |
| `(1)`   | `backend-component.png`           |  4087×2073 | Primary component       |
| `(1)`   | `front-component.png`             |  4280×1506 | Primary component       |
| 기본    | `Frame 427319124.png`             |    802×448 | Secondary detail        |
| 기본    | `Frame 427319130.png`             |    500×621 | Secondary detail        |
| 기본    | `Frame 427319129.png`             |    720×241 | Reference-only          |
| 기본    | `Frame 427319137.png`             |    281×701 | Reference-only          |
| 기본    | `Frame 427319138.png`             |    500×561 | Reference-only          |
| 기본    | `Frame 427319150.png`             |     746×68 | Excluded                |
| `(2)`   | `Homescreen-login-and-signup.png` |  6240×4653 | Structure-only          |
| `(2)`   | `categories.png`                  |  3600×3778 | Structure-only          |
| `(2)`   | `Section 1.png`                   |  5017×1277 | Structure-only          |
| `(3)`   | `Frame 427318988.png`             |  1440×3994 | Primary page            |
| `(3)`   | `signup.png`                      |  1440×1024 | Primary page            |
| `(3)`   | `category-page.png`               |  1440×2996 | Primary page            |
| `(3)`   | `course-page.png`                 |  1440×3990 | Primary page            |
| `(3)`   | `profile page.png`                |  1440×2178 | Primary page            |
| `(3)`   | `profile page-1.png`              |  1440×1672 | Primary page            |
| `(3)`   | `order-complete-1.png`            |  1440×3152 | Primary page structure  |
| `(3)`   | `mentor-page.png`                 |  1440×2581 | Secondary               |
| `(3)`   | `order-complete.png`              |  1440×1024 | Secondary state         |
| `(3)`   | `frontend/input form.png`         |     776×58 | Secondary detail        |
| `(3)`   | `checkout.png`                    |  1440×1201 | Excluded                |
| `(3)`   | `shopping-cart.png`               |  1440×1471 | Excluded                |
| `(3)`   | `profile page-2.png`              |  1440×1316 | Excluded                |
| `(3)`   | `profile page-3.png`              |  1440×1316 | Excluded                |
| `(3)`   | `profile page-4.png`              |  1440×1316 | Excluded                |
| `(3)`   | `profile page-5.png`              |  1440×1316 | Excluded                |
| `(3)`   | `Front End.png`                   |   2260×338 | Excluded fragment       |
| `(4)`   | `courses-mod.png`                 | 20704×1881 | Secondary admin pattern |
| `(4)`   | `communication-mod.png`           |  8976×1304 | Secondary admin pattern |
| `(4)`   | `revenue and settings.png`        |  3112×1304 | Pattern-only            |
| `(4)`   | `Admin.png`                       |   1546×358 | Excluded title asset    |

## 3. Reference 계층

### Primary component

- `backend-component.png`: 인증 후 shell, 짙은 navigation, 밝은 작업 canvas,
  얇은 border의 panel, compact table, status, upload와 업무형 밀도의 기준이다.
- `front-component.png`: public header, form, course card, accordion, tab, filter와
  기본 control 상태의 기준이다. 가격·별점·장바구니 의미는 제외한다.

### Primary page

- `Frame 427318988.png`: 공개 메인의 큰 계층과 section rhythm
- `signup.png`: 인증 화면의 split composition, form label과 control rhythm
- `category-page.png`: 카드 grid와 filter/list 밀도
- `course-page.png`: Course 상세 section, tab, accordion과 보조 rail
- `profile page.png`: 계정 shell과 grouped information card
- `profile page-1.png`: 인증 후 dashboard의 content hierarchy
- `order-complete-1.png`: 넓은 main과 보조 rail의 비율만 사용

### Secondary와 Structure-only

- `Frame 427319124.png`는 dashboard KPI/card 계층, `Frame 427319130.png`는
  message bubble·composer의 미세 표현만 참고한다. 회전·crop된 홍보 캡처이므로
  전체 layout의 근거로 사용하지 않는다.
- `mentor-page.png`, `order-complete.png`, `input form.png`는 identity·성공 상태·
  control detail을 보완한다.
- `Homescreen-login-and-signup.png`, `categories.png`, `Section 1.png`는
  저충실도 wireframe이므로 큰 영역 구성만 참고한다. 시각 token을 추출하지 않는다.
- `(4)`의 admin board는 교수자 관리·archive toolbar·master-detail·upload 패턴에만
  사용한다. GOAL의 전역 navigation이나 제품 역할을 정의하지 않는다.

## 4. 시각 token

제품 문서에는 기존 violet·lime을 고정하는 brand color 계약이 없다. 따라서
레퍼런스에서 확인한 slate/navy와 blue를 하나의 primary 시각 언어로 채택한다.

| 역할                | Source value                    | 적용 원칙                              |
| ------------------- | ------------------------------- | -------------------------------------- |
| 강한 ink/navigation | `#020617`, `#0F172A`, `#1E293B` | 제목, dark navigation, 고대비 control  |
| surface             | `#FFFFFF`, `#F8FAFC`            | card·input·public page                 |
| canvas              | `#F1F5F9`                       | 인증 후 작업 배경                      |
| border              | `#E2E8F0`                       | control·card·구획선                    |
| muted text          | `#64748B`                       | meta와 설명, 작은 글자의 대비는 재확인 |
| action              | `#2563EB`, `#3B82F6`            | primary CTA, active navigation, focus  |
| success             | `#15803D` 계열                  | 완료·연결 정상                         |
| warning             | `#B45309` 계열                  | 처리·주의·재연결                       |
| danger              | `#B91C1C` 계열                  | 실패·파괴 동작                         |

다음 색은 제품 UI token에서 제외한다.

- `#E5E5E5`: component board canvas
- `#9747FF`: Figma selection outline
- `#D6BBFB`, `#B2DDFF`: 마케팅 illustration 배경

### Typography

- family: Pretendard, Noto Sans KR, Inter와 system sans-serif
- body: 14~~16px, line-height 1.5~~1.65, weight 400~500
- meta: 12~13px, line-height 1.45 이상
- card heading: 18~~24px, weight 600~~700
- page heading: 28~40px, weight 700, 지나치게 좁은 자간을 피한다.
- 긴 한국어 본문은 한 줄 65~75자 수준으로 제한한다.

### Spacing, radius와 elevation

- 4px를 최소 단위, 8px를 기본 rhythm으로 사용한다.
- control 내부 padding은 12~~16px, card는 20~~24px, section gap은 24~40px다.
- control radius는 8~~10px, card radius는 12~~16px다.
- pill은 상태 badge·filter chip처럼 의미가 있을 때만 쓴다.
- shadow는 `0 2px 8px rgba(15, 23, 42, 0.06)` 수준으로 절제하고
  기본 구획은 border로 표현한다.
- 주요 control은 최소 44px 높이와 touch area를 보장한다.

## 5. Navigation과 responsive shell

- public·auth 화면: 얇은 top header, GOAL brand, 로그인·가입처럼 현재 계약에
  존재하는 동작만 제공한다.
- 인증 후 dashboard: content-first top navigation을 기본으로 하되 Course
  workspace처럼 정보 구조가 깊은 화면에서만 dark course-scoped sidebar를 쓴다.
- 교수자 화면: 작업 동작과 archive 탐색을 명확히 하되 전역 Admin처럼 보이게
  만들지 않는다.
- 학생 화면: 동일 정보 구조를 공유하면서 교수자 관리 control을 DOM에서 제거하고
  밀도를 낮춘다.
- 768px 이하: 고정 sidebar를 compact top bar·drawer 또는 horizontal tab으로
  전환한다.
- 375px: main column을 우선하고 rail은 문서 순서상 뒤로 이동한다. table은
  의미를 유지하는 card/list로 전환하거나 명시적인 scroll region을 제공한다.

## 6. 공통 component 문법

### Button과 Field

- primary는 action blue와 흰 text, secondary는 흰 surface와 slate border다.
- destructive는 danger token을 사용하고 일반 CTA와 시각적으로 구분한다.
- icon-only control에는 accessible name이 필요하다.
- field는 항상 visible label을 갖고 error message를 해당 control과 연결한다.
- focus는 2~3px blue ring으로 표현하며 색상만으로 오류를 전달하지 않는다.

### Card, Status와 feedback

- card는 white surface, 1px border와 얕은 shadow를 기본으로 한다.
- badge는 `READY`, `LIVE`, `PROCESSING`, `COMPLETED` 등 실제 계약 상태만
  표시한다. 임의의 `ACTIVE`, `DRAFT`, `PUBLISHED`를 만들지 않는다.
- loading은 Skeleton과 텍스트 status를 함께 제공한다.
- empty, unavailable, error, forbidden과 partial failure를 서로 구분한다.
- Toast는 보조 feedback이며 중요한 오류를 화면의 유일한 정보로 두지 않는다.
- Dialog는 native modal 동작, Escape, focus trap과 trigger focus return을 보장한다.

### Domain pattern

- Course: 역할·학기·current class를 한눈에 읽고 주요 진입 동작은 하나로 둔다.
- Transcript: 시간 순서와 partial/final/gap을 구분하고 기록 playback 위치가 있는
  문장만 seek control을 제공한다.
- Question: 학생 질문·AI 대표질문의 source를 구분하고 작성자 식별자를 노출하지
  않는다.
- 개인 AI: LIVE Summary·Chat과 COMPLETED REVIEW Chat을 같은 panel 체계로
  표현하되 `PROCESSING`에서는 form을 제공하지 않는다.
- realtime: session event, audio publisher, 로컬 녹음, STT와 AI 실패를 독립
  상태로 표시한다.
- processing: HQ STT, canonical 전환, Answer mapping·정리, FINAL Summary와
  clustering을 하나의 전체 성공·실패 badge로 합치지 않는다.

## 7. 화면별 고정 매핑

| 화면 ID                  | Primary                          | Secondary/제약                                                |
| ------------------------ | -------------------------------- | ------------------------------------------------------------- |
| `MAIN_PAGE`              | `Frame 427318988.png`            | `Homescreen-login-and-signup.png`; marketplace section은 제외 |
| `LOGIN_PAGE`             | `signup.png`                     | `input form.png`; 계약에 없는 provider 제외                   |
| `EMAIL_SIGNUP_PAGE`      | `signup.png`                     | visible label과 account 계약 우선                             |
| `MAIN_PAGE_AUTH`         | `profile page-1.png`             | `category-page.png`; Course dashboard로만 해석                |
| `MY_INFO_PAGE`           | `profile page.png`               | SNS·판매·교사 등록 제외                                       |
| `COURSE_CREATE_PAGE`     | `signup.png`의 form rhythm       | `order-complete.png`의 성공 표현                              |
| `COURSE_JOIN_PAGE`       | `signup.png`의 form rhythm       | 참여 코드 계약 우선                                           |
| `COURSE_PAGE_PROF`       | `course-page.png`                | backend 관리 패턴, Course-scoped navigation                   |
| `COURSE_PAGE_STUD`       | `course-page.png`                | 교수자 control 제거, 학생 밀도 완화                           |
| `CLASS_CREATE_PAGE`      | `course-page.png` section        | backend form·upload 패턴                                      |
| `LIVE_CLASS_PAGE_PROF`   | `order-complete-1.png` main+rail | Transcript·질문·AI·교수자 control 계약 우선                   |
| `LIVE_CLASS_PAGE_STUD`   | `order-complete-1.png` main+rail | 교수자 control을 DOM에 렌더링하지 않음                        |
| `CLASS_PROCESSING_STATE` | 공통 Class shell                 | `order-complete.png` centered state; 독립 task 상태 유지      |
| `ENDED_CLASS_PAGE_PROF`  | `order-complete-1.png`           | course section·backend archive toolbar                        |
| `ENDED_CLASS_PAGE_STUD`  | `order-complete-1.png`           | 교수자 관리 control 제거                                      |

## 8. 사용 금지 의미

다음은 레퍼런스에 보이더라도 GOAL에 이식하지 않는다.

- price, cart, checkout, coupon, discount, revenue와 commission
- rating, 공개 course review와 testimonial을 제품 데이터처럼 표현하는 UI
- mentor directory, instructor recruitment, seller/customer 모델
- SEO·catalog publishing과 상품형 `Draft → Publish`
- 계정 전역 Admin 역할과 Course별 역할을 무시하는 navigation
- SNS profile, 사람 간 P2P messaging와 마케팅 CTA
- 계약에 없는 export, promotion, block/delete 동작
- Byway logo·문구·사진·illustration 등 원본 브랜드 자산

특히 `profile page-5.png`의 사람 간 채팅은 개인 AI Chat의 의미 근거로 사용하지
않는다. GOAL의 개인 AI는 요청자 전용 결과, polling, Evidence와 상태 계약을 따른다.

## 9. 검증 기준

각 화면은 Prototype이 아닌 실제 Vite route에서 1440px·768px·375px으로
렌더링한다. Reference와의 비교는 pixel copy가 아니라 다음 항목을 평가한다.

1. token과 component의 일관성
2. 정보·동작의 시각적 우선순위
3. 역할·상태·부분 실패의 명확성
4. 세 viewport에서의 재배치와 읽기 순서
5. keyboard focus, 44px target, reduced motion과 WCAG AA 대비

원본 레퍼런스와 다른 결과가 제품 계약·접근성·반응형 사용성을 더 정확히
표현한다면 그 차이를 유지하고 화면별 검증 보고서에 이유를 기록한다.
