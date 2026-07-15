import { useState, type ReactNode } from 'react'

import {
  CourseRoleBadge,
  SessionStatusBadge,
} from '../../components/domain/LmsStatus'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { Field } from '../../components/ui/Field'
import { LinkButton } from '../../components/ui/LinkButton'
import type { Course, LectureSession } from '../courses/api'
import { LocalRecordingPanel } from '../recordings/LocalRecordingPanel'
import { SessionRecordPage } from './SessionRecordPage'

interface ProcessingClassViewProps {
  course: Course
  onRename: (title: string) => Promise<unknown>
  refreshWarning?: ReactNode
  renameError?: string | null
  renamePending: boolean
  session: LectureSession
}

export function ProcessingClassView({
  course,
  onRename,
  refreshWarning,
  renameError,
  renamePending,
  session,
}: ProcessingClassViewProps) {
  const professor = course.role === 'PROFESSOR'
  const [managementOpen, setManagementOpen] = useState(false)
  const [titleEdit, setTitleEdit] = useState({
    canonical: session.title,
    dirty: false,
    value: session.title,
  })
  if (titleEdit.canonical !== session.title) {
    const preserveDraft = titleEdit.dirty && titleEdit.value !== session.title
    setTitleEdit({
      canonical: session.title,
      dirty: preserveDraft,
      value: preserveDraft ? titleEdit.value : session.title,
    })
  }
  const title = titleEdit.value

  return (
    <section
      className="processing-class-page"
      aria-labelledby="processing-class-title"
    >
      <header className="processing-class-toolbar">
        <div className="processing-class-toolbar__context">
          <h1 id="processing-class-title">{session.title}</h1>
          <div className="processing-class-toolbar__meta">
            <CourseRoleBadge role={course.role} />
            <SessionStatusBadge status="PROCESSING" />
            <span>{course.title}</span>
            <span>{session.lecture_date}</span>
          </div>
        </div>
        <div className="processing-class-toolbar__actions">
          {professor && (
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

      {professor && (
        <Dialog
          open={managementOpen}
          title="처리 중 class 관리"
          description="기록 정리는 계속 진행되며, 여기에서는 제목과 브라우저 녹음 상태만 관리합니다."
          onOpenChange={setManagementOpen}
        >
          <section className="processing-class-management">
            <div>
              <p className="eyebrow">Professor control</p>
              <h2>class 제목</h2>
              <p>기록 정리 중에는 제목만 수정할 수 있습니다.</p>
            </div>
            <Field
              htmlFor={`processing-class-title-input-${session.id}`}
              label="class 제목"
              error={renameError ?? undefined}
              hint="비워 저장하면 서버가 수업 시각을 기준으로 제목을 만듭니다."
            >
              <input
                id={`processing-class-title-input-${session.id}`}
                value={title}
                onChange={(event) =>
                  setTitleEdit((current) => ({
                    ...current,
                    dirty: event.target.value !== session.title,
                    value: event.target.value,
                  }))
                }
              />
            </Field>
            <Button
              variant="secondary"
              disabled={renamePending || !titleEdit.dirty}
              onClick={() => void onRename(title).catch(() => undefined)}
            >
              {renamePending ? '저장 중…' : '제목 저장'}
            </Button>
            <LocalRecordingPanel
              sessionId={session.id}
              stream={null}
              clientStreamId={null}
              sessionStatus="PROCESSING"
            />
          </section>
        </Dialog>
      )}

      <SessionRecordPage
        sessionId={session.id}
        professor={professor}
        presentation="processing"
      />
    </section>
  )
}
