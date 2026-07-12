# Claude Code Project Guidance

이 저장소의 공통 AI 협업 규칙은 [`AGENTS.md`](./AGENTS.md)가 최종 기준이다.
Claude Code는 작업 전에 `AGENTS.md`를 읽고 적용한다.

## Claude Code 전용 안내

- 프로젝트 Skill은 `.claude/skills/<skill-name>/SKILL.md`에서 발견한다.
- `/goal-user-flow`는 화면별 커밋과 사용자 흐름별 새 Draft PR 작업에 사용한다.
- `/goal-contract-sync`는 제품·API·DB·화면·아키텍처 계약의 정합성 검토에 사용한다.
- Skill의 공통 원본은 `agent-skills/<skill-name>/SKILL.md`다. `.claude/skills` 복사본만 단독으로 수정하지 않는다.
- 공통 규칙을 이 파일에 반복하지 않는다. 도구를 가리지 않는 규칙은 `AGENTS.md`에 추가한다.
- Claude 전용 설정이 필요할 때만 이 파일이나 `.claude/` 아래의 별도 설정에 추가한다.

Skill이나 AI 협업 규칙을 변경하면 `AGENTS.md`, 공통 원본, `.agents/skills`와
`.claude/skills` 사이의 정합성을 함께 확인한다.
