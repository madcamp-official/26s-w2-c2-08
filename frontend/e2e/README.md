# Production visual verification

이 디렉터리는 `frontend/src`의 production route를 실제 Vite 앱으로 렌더링해
검증한다. API 응답은 Playwright의 browser route에서만 제공되며 production
bundle에는 fixture, scenario query 또는 demo 분기를 추가하지 않는다.

- 로컬 브라우저 설치: `pnpm visual:install`
- 15개 화면 계약을 포함한 production route 시나리오 × 3 viewport: `pnpm visual:foundation`
- 완료 화면 정적 Prototype·상태 전환 × 3 viewport: `pnpm visual:prototypes`
- 전체 visual suite: `pnpm visual:test`

각 scenario는 화면 heading, 실제 사용한 HTTP 계약, 미등록 요청, browser error,
가로 overflow와 44px 미만 주요 control을 검사한다. PNG는
`test-results/playwright` 아래에 생성되고 HTML report에 첨부되며 Git에는
추가하지 않는다. 이후 화면 PR은 같은 방식으로 scenario와 API fixture를
확장한다.
