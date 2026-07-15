import type { ReactNode } from 'react'

import {
  CourseRoleBadge,
  SessionStatusBadge,
} from '../../components/domain/LmsStatus'
import { PageHeader } from '../../components/layout/PageHeader'
import { Card } from '../../components/ui/Card'
import { LinkButton } from '../../components/ui/LinkButton'
import type { Course, LectureSession } from '../courses/api'
import { SessionRecordPage } from './SessionRecordPage'

interface EndedClassLayoutProps {
  course: Course
  management?: ReactNode
  professor: boolean
  refreshWarning?: ReactNode
  screenId: 'ENDED_CLASS_PAGE_PROF' | 'ENDED_CLASS_PAGE_STUD'
  session: LectureSession
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'long',
  }).format(new Date(`${value}T00:00:00`))
}

function formatDateTime(value: string | null) {
  if (!value) return '기록 없음'
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

const recordSections = [
  ['#material-title', '강의자료'],
  ['#recording-playback-title', '녹음'],
  ['#record-summary-title', '요약'],
  ['#record-transcript-title', 'Transcript'],
  ['#record-questions-title', '질문'],
  ['#final-question-cluster-list-title', '질문 목록'],
  ['#record-answers-title', '답변'],
  ['#record-jobs-title', '작업 상태'],
  ['#personal-ai-REVIEW', '복습 AI'],
] as const

export function EndedClassLayout({
  course,
  management,
  professor,
  refreshWarning,
  screenId,
  session,
}: EndedClassLayoutProps) {
  return (
    <section
      className="ended-class-page"
      aria-labelledby="ended-class-title"
      data-ended-class-role={course.role}
    >
      <PageHeader
        eyebrow={`${screenId} · COMPLETED`}
        title={session.title}
        titleId="ended-class-title"
        description={
          <div className="ended-class-header__description">
            <CourseRoleBadge role={course.role} />
            <SessionStatusBadge status="COMPLETED" />
            <span>{course.title}</span>
            <span>{formatDate(session.lecture_date)}</span>
          </div>
        }
        actions={
          <LinkButton variant="ghost" to={`/courses/${session.course_id}`}>
            Course로 돌아가기
          </LinkButton>
        }
      />

      {refreshWarning}

      <div className="ended-class-intro">
        <Card
          as="section"
          className="ended-class-completion"
          aria-labelledby="ended-class-completion-title"
        >
          <div className="ended-class-completion__copy">
            <span className="ended-class-completion__mark" aria-hidden="true">
              ✓
            </span>
            <div>
              <p className="eyebrow">Review workspace</p>
              <h2 id="ended-class-completion-title">
                복습할 수업 기록이 준비되었습니다
              </h2>
              <p>
                최종 Transcript와 질문·답변·요약은 영역별로 불러옵니다. 한
                영역에 문제가 생겨도 준비된 다른 기록과 복습 AI는 유지됩니다.
              </p>
            </div>
          </div>
          <dl className="ended-class-timeline">
            <div>
              <dt>수업 날짜</dt>
              <dd>{formatDate(session.lecture_date)}</dd>
            </div>
            <div>
              <dt>시작</dt>
              <dd>{formatDateTime(session.started_at)}</dd>
            </div>
            <div>
              <dt>종료</dt>
              <dd>{formatDateTime(session.ended_at)}</dd>
            </div>
            <div>
              <dt>기록 확정</dt>
              <dd>{formatDateTime(session.completed_at)}</dd>
            </div>
          </dl>
        </Card>

        {management}
      </div>

      <nav className="ended-class-toc" aria-label="완료 수업 기록 바로가기">
        {recordSections.map(([href, label]) => (
          <a key={href} href={href}>
            {label}
          </a>
        ))}
      </nav>

      <SessionRecordPage
        sessionId={session.id}
        professor={professor}
        presentation="ended"
      />
    </section>
  )
}
