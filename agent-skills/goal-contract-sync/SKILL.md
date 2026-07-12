---
name: goal-contract-sync
description: Review and synchronize GOAL product, IA, screen, API, OpenAPI, database, ERD, architecture, and prototype contracts. Use whenever an implementation or document change affects endpoints, payloads, events, authentication, authorization, roles, states, tables, constraints, storage, processes, or user flows, and when asked to audit documentation consistency. Separate unresolved decisions instead of inventing them.
---

# GOAL Contract Sync

변경의 실제 책임 문서를 찾고 외부 계약, 내부 무결성과 사용자 표현이 서로 어긋나지 않게 한다.

## 1. 변경 분류

1. `AGENTS.md`를 읽는다.
2. 변경된 파일과 요청에서 관찰 가능한 동작 변화를 한 문장으로 정리한다.
3. 요청이 읽기 전용 감사인지 실제 문서·구현 동기화인지 구분한다. 감사 요청에서는 파일과 Git 상태를 변경하지 않는다.
4. 다음 표로 기준 문서와 파생 문서를 선택한다.

| 변경                        | 함께 검토할 문서                                   |
| --------------------------- | -------------------------------------------------- |
| 사용자 문제·MVP 범위·기능   | 기획안, 기능명세서, IA                             |
| 화면 진입·상태·권한·동작    | IA, 화면설계서, Prototype 또는 실제 UI             |
| endpoint·payload·오류·인증  | API 명세서, OpenAPI                                |
| WebSocket·STT·event·재연결  | API 명세서, OpenAPI 확장, 기술명세서, 시스템구성도 |
| table·column·enum·FK·index  | DB 스키마, ERD                                     |
| 삭제·보관·transaction·AIJob | DB 스키마, ERD, API 명세서, 시스템구성도           |
| framework·process·storage   | 기술명세서, 시스템구성도                           |
| VM·GPU·network·배포         | KCloud VM 사양, 시스템구성도, 실행 문서            |

## 2. 기준과 현재 상태 확인

- 제품 문서, API 계약, DB 무결성과 실행 경계의 책임을 구분한다.
- 문서의 `현재 구현`, `준비됨`, `MVP 목표`, `미정` 상태를 보존한다.
- 구현이 있다는 이유만으로 초안 계약을 조용히 덮어쓰지 않는다.
- 최신 결정과 오래된 표현이 충돌하면 근거와 영향 범위를 기록하고 함께 수정하거나 명시적인 후속 항목으로 남긴다.
- 문서에서 확인할 수 없는 provider, threshold, retention, SLO와 배포 결정을 임의로 정하지 않는다.

## 3. 교차 계약 점검

관련 변경에 대해서만 다음 항목을 비교한다. 내부 표현만 바뀌고 외부 동작이
같으면 제품·화면 문서를 확대하지 않는다. 사용자에게 보이는 정보, 동작이나
권한이 바뀌면 제품·화면 문서까지 포함한다.

- resource와 field 이름, 타입, required·nullable, 기본값
- enum과 상태 전이
- Course별 역할과 endpoint·화면 권한
- PK·FK·UNIQUE·CHECK·index와 `ON DELETE`
- 멱등성, transaction commit 경계와 재시도 방식
- REST canonical 조회와 WebSocket event 경계
- partial·final, 임시·영구 저장과 retention
- AIJob의 visibility, requester, target과 결과 추적
- 오류 code, HTTP status와 사용자 표시
- 화면의 loading·empty·부분 실패·권한 없음 표현

상세 결정은 Skill 본문에서 재정의하지 않고 선택한 기준 문서의 최신 내용을 따른다.

## 4. 수정 규칙

- 하나의 결정은 책임 문서에만 상세히 정의하고 다른 문서는 링크나 필요한 요약만 둔다.
- API 사람이 읽는 설명과 기계 판독 `openapi.yaml`을 같은 변경에서 맞춘다.
- DB 표와 Mermaid ERD가 같은 테이블·관계·삭제 정책을 표현하게 한다.
- 화면설계서와 Prototype이 같은 역할, 상태와 진입·이탈을 표현하게 한다.
- architecture 문서는 미구현 목표를 현재 실행 구성처럼 쓰지 않는다.
- 결정되지 않은 내용은 `미정 사항`에 질문, 영향과 결정 시점을 기록한다.
- 사용자가 문서 초안만 요청하면 SQLAlchemy 모델, migration과 실행 코드를 만들지 않는다.

## 5. 검증

변경 유형에 맞게 다음을 수행한다.

1. 관련 용어·enum·endpoint·table 이름을 `rg`로 교차 검색한다.
2. Markdown과 YAML formatter 또는 parser를 실행한다.
3. 상대 경로 링크 대상이 존재하는지 확인한다.
4. Mermaid 변경이 있으면 parser 또는 render 검사를 실행한다.
5. OpenAPI 변경은 가능한 validator로 문법과 `$ref`를 확인한다.
6. DB 구현이 포함되면 migration 적용과 관련 테스트를 실행한다.
7. `git diff --check`와 changed-files 범위를 확인한다.

검증 도구가 없거나 실행하지 못한 항목은 성공으로 표시하지 않고 이유와 수동 확인 방법을 남긴다.

## 6. 완료 보고

다음을 보고한다.

- 변경한 계약과 최종 책임 문서
- 함께 동기화한 파일
- 확인한 현재 구현과 MVP 목표 차이
- 실행한 formatter·parser·test와 결과
- 남겨 둔 미정 사항, 문서 충돌과 후속 구현 범위
