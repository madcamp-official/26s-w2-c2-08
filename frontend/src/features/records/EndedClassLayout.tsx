import { useState, type ReactNode } from 'react'

import {
  CourseRoleBadge,
  SessionStatusBadge,
} from '../../components/domain/LmsStatus'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
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

export function EndedClassLayout({
  course,
  management,
  professor,
  refreshWarning,
  screenId,
  session,
}: EndedClassLayoutProps) {
  const [managementOpen, setManagementOpen] = useState(false)

  return (
    <section
      className="ended-class-page"
      aria-labelledby="ended-class-title"
      data-ended-class-role={course.role}
      data-ended-class-screen={screenId}
    >
      <header className="ended-class-toolbar">
        <div className="ended-class-toolbar__context">
          <h1 id="ended-class-title">{session.title}</h1>
          <div className="ended-class-toolbar__meta">
            <CourseRoleBadge role={course.role} />
            <SessionStatusBadge status="COMPLETED" />
            <span>{course.title}</span>
            <span>{formatDate(session.lecture_date)}</span>
          </div>
        </div>
        <div className="ended-class-toolbar__actions">
          {management && (
            <Button variant="ghost" onClick={() => setManagementOpen(true)}>
              class 관리
            </Button>
          )}
          <LinkButton variant="ghost" to={`/courses/${session.course_id}`}>
            Course로
          </LinkButton>
        </div>
      </header>

      {refreshWarning}

      <SessionRecordPage
        sessionId={session.id}
        professor={professor}
        presentation="ended"
      />

      {management && (
        <Dialog
          open={managementOpen}
          title="완료 class 관리"
          description="학습 영역과 분리해 제목과 보존 범위만 관리합니다."
          onOpenChange={setManagementOpen}
        >
          {management}
        </Dialog>
      )}
    </section>
  )
}
