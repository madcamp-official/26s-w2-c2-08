import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  ConnectionStatus,
  CourseRoleBadge,
  JobStatusBadge,
  MaterialStatusBadge,
  SessionStatusBadge,
} from './LmsStatus'

describe('LMS status components', () => {
  it('translates roles without changing their machine-readable state', () => {
    render(
      <>
        <CourseRoleBadge role="PROFESSOR" />
        <CourseRoleBadge role="STUDENT" />
      </>,
    )

    expect(screen.getByText('교수자')).toHaveAttribute(
      'data-course-role',
      'PROFESSOR',
    )
    expect(screen.getByText('학생')).toHaveAttribute(
      'data-course-role',
      'STUDENT',
    )
  })

  it.each([
    ['READY', '시작 전', 'ui-status--info'],
    ['LIVE', '진행 중', 'ui-status--danger'],
    ['PROCESSING', '기록 정리 중', 'ui-status--warning'],
    ['COMPLETED', '완료', 'ui-status--success'],
  ] as const)('maps Session %s to %s', (status, label, toneClass) => {
    render(<SessionStatusBadge status={status} />)

    expect(screen.getByText(label)).toHaveAttribute(
      'data-session-status',
      status,
    )
    expect(screen.getByText(label)).toHaveClass(toneClass)
  })

  it.each([
    ['PENDING', '대기 중'],
    ['RUNNING', '처리 중'],
    ['SUCCEEDED', '완료'],
    ['FAILED', '실패'],
    ['CANCELLED', '취소됨'],
    ['SUPERSEDED', '새 작업으로 대체됨'],
  ] as const)('maps AI Job %s to %s', (status, label) => {
    render(<JobStatusBadge status={status} />)

    expect(screen.getByText(label)).toHaveAttribute('data-job-status', status)
  })

  it.each([
    ['UPLOADED', '처리 대기'],
    ['PROCESSING', '처리 중'],
    ['READY', 'AI 참고 가능'],
    ['FAILED', '처리 실패'],
  ] as const)('maps Material %s to %s', (status, label) => {
    render(<MaterialStatusBadge status={status} />)

    expect(screen.getByText(label)).toHaveAttribute(
      'data-material-status',
      status,
    )
  })

  it.each([
    ['connecting', '실시간 연결 중'],
    ['connected', '실시간 연결됨'],
    ['reconnecting', '연결 복구 중'],
    ['stopped', '실시간 연결 종료'],
  ] as const)('announces realtime state %s', (state, label) => {
    render(<ConnectionStatus state={state} />)

    expect(screen.getByText(label)).toHaveAttribute(
      'data-connection-state',
      state,
    )
    expect(screen.getByText(label)).toHaveAttribute('aria-live', 'polite')
  })
})
