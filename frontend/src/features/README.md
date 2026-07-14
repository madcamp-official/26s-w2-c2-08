# Feature boundaries

화면과 사용자 흐름 코드는 도메인별 `features` 하위 폴더에 둔다.

- `auth`: 로그인, 로그아웃, 인증 복구
- `courses`: Course 생성, 참여, 목록과 설정
- `sessions`: class 생성, 자료 업로드와 상태 전이
- `live`: 실시간 Transcript, 질문, 반응과 재연결
- `records`: 완료 기록, 요약, Q&A와 복습 Chat
- `health`: 애플리케이션 기반에서 사용하는 API 연결 확인 예시

여러 도메인이 공유하는 UI는 `components`, 통신 기반은 `api`, 프레임워크와
무관한 공통 로직은 `lib`에 둔다. Feature가 다른 Feature의 내부 파일을 직접
가져오지 않도록 한다.
