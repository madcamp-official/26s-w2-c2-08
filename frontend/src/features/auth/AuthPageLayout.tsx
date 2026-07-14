import type { ReactNode } from 'react'

import { Card } from '../../components/ui/Card'

interface AuthPageLayoutProps {
  children: ReactNode
  description: string
  eyebrow: string
  formLabel: string
  title: string
  titleId: string
}

export function AuthPageLayout({
  children,
  description,
  eyebrow,
  formLabel,
  title,
  titleId,
}: AuthPageLayoutProps) {
  return (
    <div className="auth-page">
      <section className="auth-intro" aria-labelledby={titleId}>
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h1 className="page-title" id={titleId}>
            {title}
          </h1>
          <p className="page-description">{description}</p>
        </div>

        <ol className="auth-learning-loop" aria-label="GOAL 학습 흐름">
          <li>
            <span>01</span>
            <div>
              <strong>강의 참여</strong>
              <p>Course별 역할에 맞는 강의 공간으로 들어갑니다.</p>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <strong>맥락 확인</strong>
              <p>Transcript와 질문으로 수업의 흐름을 이어 갑니다.</p>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <strong>기록 복습</strong>
              <p>수업이 끝난 뒤에도 확정된 기록을 다시 봅니다.</p>
            </div>
          </li>
        </ol>
      </section>

      <Card as="section" className="auth-panel" elevated aria-label={formLabel}>
        {children}
      </Card>
    </div>
  )
}
