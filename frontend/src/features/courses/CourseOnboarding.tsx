import { useEffect, useRef, type ReactNode } from 'react'

import { Card } from '../../components/ui/Card'
import { LinkButton } from '../../components/ui/LinkButton'
import { Status, type StatusTone } from '../../components/ui/Status'

interface CourseFlowGuideProps {
  ariaLabel: string
  note: ReactNode
  steps: string[]
  title: string
}

export function CourseFlowGuide({
  ariaLabel,
  note,
  steps,
  title,
}: CourseFlowGuideProps) {
  return (
    <aside className="course-onboarding-guide" aria-label={ariaLabel}>
      <Card as="section">
        <p className="eyebrow">Course guide</p>
        <h2>{title}</h2>
        <ol className="course-onboarding-steps">
          {steps.map((step, index) => (
            <li key={step}>
              <span aria-hidden="true">{index + 1}</span>
              <p>{step}</p>
            </li>
          ))}
        </ol>
      </Card>
      <Card className="course-onboarding-note" as="section">
        <strong>기억해 주세요</strong>
        <p>{note}</p>
      </Card>
    </aside>
  )
}

interface CourseFlowResultProps {
  actions: ReactNode
  children?: ReactNode
  description: ReactNode
  details: Array<{ label: string; value: ReactNode }>
  statusLabel: string
  statusTone?: StatusTone
  title: string
}

export function CourseFlowResult({
  actions,
  children,
  description,
  details,
  statusLabel,
  statusTone = 'success',
  title,
}: CourseFlowResultProps) {
  const titleRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    titleRef.current?.focus()
  }, [])

  return (
    <section className="course-onboarding-page" aria-live="polite">
      <Card className="course-flow-result" elevated>
        <Status tone={statusTone}>{statusLabel}</Status>
        <div className="course-flow-result__copy">
          <h1 ref={titleRef} tabIndex={-1}>
            {title}
          </h1>
          <p>{description}</p>
        </div>
        <dl className="course-flow-result__summary">
          {details.map((detail) => (
            <div key={detail.label}>
              <dt>{detail.label}</dt>
              <dd>{detail.value}</dd>
            </div>
          ))}
        </dl>
        {children}
        <div className="course-flow-result__actions">{actions}</div>
      </Card>
    </section>
  )
}

interface CourseMutationExpiredStateProps {
  description: string
  onBeforeNavigate?: () => void
  returnTo: string
}

export function CourseMutationExpiredState({
  description,
  onBeforeNavigate,
  returnTo,
}: CourseMutationExpiredStateProps) {
  const titleRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    titleRef.current?.focus()
  }, [])

  return (
    <section className="course-onboarding-page">
      <Card className="course-flow-result" elevated>
        <Status tone="warning">인증 만료</Status>
        <div className="course-flow-result__copy">
          <h1 ref={titleRef} tabIndex={-1}>
            로그인 상태를 다시 확인해 주세요
          </h1>
          <p>{description}</p>
        </div>
        <div className="course-flow-result__actions">
          <LinkButton
            onClick={onBeforeNavigate}
            to={`/login?return_to=${encodeURIComponent(returnTo)}`}
          >
            다시 로그인
          </LinkButton>
          <LinkButton onClick={onBeforeNavigate} to="/" variant="ghost">
            홈으로 이동
          </LinkButton>
        </div>
      </Card>
    </section>
  )
}
