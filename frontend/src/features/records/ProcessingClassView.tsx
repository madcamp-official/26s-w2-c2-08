import { useState, type ReactNode } from 'react'

import {
  CourseRoleBadge,
  SessionStatusBadge,
} from '../../components/domain/LmsStatus'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
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

function formatDateTime(value: string | null) {
  if (!value) return '확인 중'
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
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
      <PageHeader
        eyebrow="CLASS_PROCESSING_STATE · PROCESSING"
        title={session.title}
        titleId="processing-class-title"
        description={
          <div className="processing-class-header__description">
            <CourseRoleBadge role={course.role} />
            <SessionStatusBadge status="PROCESSING" />
            <span>{course.title}</span>
            <span>{session.lecture_date}</span>
          </div>
        }
        actions={
          <LinkButton variant="ghost" to={`/courses/${session.course_id}`}>
            Course로 돌아가기
          </LinkButton>
        }
      />

      {refreshWarning}

      <div className="processing-class-intro">
        <Card
          as="section"
          className="processing-class-authority"
          aria-labelledby="processing-authority-title"
        >
          <span
            className="processing-class-authority__pulse"
            aria-hidden="true"
          />
          <div>
            <p className="eyebrow">Server processing</p>
            <h2 id="processing-authority-title">
              서버가 수업 기록을 정리하고 있습니다
            </h2>
            <p>
              완료 여부는 작업 개수나 브라우저 상태가 아니라 서버의 class 상태로
              판단합니다. 준비된 기록은 아래에서 먼저 확인할 수 있습니다.
            </p>
          </div>
          <dl>
            <div>
              <dt>수업 시작</dt>
              <dd>{formatDateTime(session.started_at)}</dd>
            </div>
            <div>
              <dt>수업 종료</dt>
              <dd>{formatDateTime(session.ended_at)}</dd>
            </div>
          </dl>
        </Card>

        {professor && (
          <Card
            as="section"
            className="processing-class-title-card"
            aria-labelledby="processing-title-edit-heading"
          >
            <div>
              <p className="eyebrow">Professor control</p>
              <h2 id="processing-title-edit-heading">class 제목</h2>
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
          </Card>
        )}
      </div>

      {professor && (
        <div className="processing-class-local-recording">
          <LocalRecordingPanel
            sessionId={session.id}
            stream={null}
            clientStreamId={null}
            sessionStatus="PROCESSING"
          />
        </div>
      )}

      <SessionRecordPage
        sessionId={session.id}
        professor={professor}
        presentation="processing"
      />
    </section>
  )
}
