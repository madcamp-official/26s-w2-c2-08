import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { PartialFailurePanel } from '../feedback/PartialFailurePanel'
import { PageHeader } from '../layout/PageHeader'
import { Button } from './Button'
import { Card } from './Card'
import { Field } from './Field'
import { LinkButton } from './LinkButton'
import { Skeleton } from './Skeleton'

describe('shared UI primitives', () => {
  it('connects field labels, help text, and validation errors to the control', () => {
    const { rerender } = render(
      <Field
        htmlFor="course-title"
        label="Course 이름"
        hint="40자 이내"
        required
      >
        <input id="legacy-id" />
      </Field>,
    )

    const input = screen.getByRole('textbox', { name: 'Course 이름' })
    expect(input).toHaveAttribute('id', 'course-title')
    expect(input).toBeRequired()
    expect(input).toHaveAttribute('aria-required', 'true')
    expect(input).toHaveAccessibleDescription('40자 이내')

    rerender(
      <Field
        htmlFor="course-title"
        label="Course 이름"
        error="Course 이름을 입력해 주세요."
      >
        <input />
      </Field>,
    )

    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Course 이름을 입력해 주세요.',
    )
  })

  it('renders composable layout, navigation, and loading primitives', () => {
    render(
      <MemoryRouter>
        <PageHeader
          eyebrow="Course"
          title="내 Course"
          description="수업 공간을 선택하세요."
          actions={<LinkButton to="/courses/new">Course 만들기</LinkButton>}
        />
        <Card as="section" aria-label="최근 Course" elevated>
          <Skeleton label="Course 목록 불러오는 중" lines={2} />
        </Card>
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: '내 Course' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Course 만들기' })).toHaveAttribute(
      'href',
      '/courses/new',
    )
    expect(screen.getByRole('region', { name: '최근 Course' })).toBeVisible()
    expect(
      screen.getByRole('status', { name: 'Course 목록 불러오는 중' }),
    ).toBeVisible()
  })

  it('keeps a partial failure scoped and exposes its recovery action', () => {
    render(
      <PartialFailurePanel
        title="질문만 불러오지 못했습니다"
        description="Transcript와 수업 참여는 계속 사용할 수 있습니다."
        actions={<Button variant="secondary">질문 다시 불러오기</Button>}
      />,
    )

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Transcript와 수업 참여는 계속')
    expect(
      screen.getByRole('button', { name: '질문 다시 불러오기' }),
    ).toBeEnabled()
  })

  it('prevents navigation when a link button is aria-disabled', () => {
    render(
      <MemoryRouter>
        <LinkButton aria-disabled to="/courses/new">
          Course 만들기
        </LinkButton>
      </MemoryRouter>,
    )

    const link = screen.getByRole('link', { name: 'Course 만들기' })
    expect(link).toHaveAttribute('aria-disabled', 'true')
    expect(link).toHaveAttribute('tabindex', '-1')
    expect(fireEvent.click(link)).toBe(false)
  })
})
