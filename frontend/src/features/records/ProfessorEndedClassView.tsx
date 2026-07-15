import { useState, type ReactNode } from 'react'

import { ApiError } from '../../api/errors'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Dialog } from '../../components/ui/Dialog'
import { Field } from '../../components/ui/Field'
import type { Course, LectureSession } from '../courses/api'
import { EndedClassLayout } from './EndedClassLayout'

interface ProfessorEndedClassViewProps {
  course: Course
  deleteError?: unknown
  deletePending: boolean
  onDelete: () => Promise<unknown>
  onRename: (title: string) => Promise<unknown>
  onResetDelete: () => void
  refreshWarning?: ReactNode
  renameError?: string | null
  renamePending: boolean
  session: LectureSession
}

function deleteErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 404) {
    return '이미 삭제된 class입니다. Course로 돌아가 최신 목록을 확인해 주세요.'
  }
  if (error instanceof ApiError) return error.message
  return 'class를 삭제하지 못했습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.'
}

export function ProfessorEndedClassView({
  course,
  deleteError,
  deletePending,
  onDelete,
  onRename,
  onResetDelete,
  refreshWarning,
  renameError,
  renamePending,
  session,
}: ProfessorEndedClassViewProps) {
  const [title, setTitle] = useState(session.title)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const titleDirty = title !== session.title

  return (
    <>
      <EndedClassLayout
        course={course}
        professor
        refreshWarning={refreshWarning}
        screenId="ENDED_CLASS_PAGE_PROF"
        session={session}
        management={
          <Card
            as="section"
            className="ended-class-management"
            aria-labelledby="ended-class-management-title"
          >
            <div>
              <p className="eyebrow">Professor control</p>
              <h2 id="ended-class-management-title">완료 class 관리</h2>
              <p>
                제목과 보존 범위만 관리합니다. 확정 Transcript와 질문 기록은
                편집하지 않습니다.
              </p>
            </div>
            <Field
              htmlFor={`ended-class-title-input-${session.id}`}
              label="class 제목"
              error={renameError ?? undefined}
              hint="비워 저장하면 서버가 수업 시각을 기준으로 제목을 만듭니다."
            >
              <input
                id={`ended-class-title-input-${session.id}`}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </Field>
            <div className="ended-class-management__actions">
              <Button
                variant="secondary"
                disabled={renamePending || !titleDirty}
                onClick={() => void onRename(title).catch(() => undefined)}
              >
                {renamePending ? '저장 중…' : '제목 저장'}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  onResetDelete()
                  setDeleteOpen(true)
                }}
              >
                class 삭제
              </Button>
            </div>
          </Card>
        }
      />

      <Dialog
        open={deleteOpen}
        title="완료 class를 삭제할까요?"
        description="삭제 후에는 되돌릴 수 없으며 연결된 완료 기록도 더 이상 조회할 수 없습니다."
        onOpenChange={(open) => {
          if (!open && !deletePending) onResetDelete()
          setDeleteOpen(open)
        }}
        actions={
          <>
            <Button
              variant="secondary"
              disabled={deletePending}
              onClick={() => setDeleteOpen(false)}
            >
              취소
            </Button>
            <Button
              variant="danger"
              disabled={deletePending}
              onClick={() => void onDelete().catch(() => undefined)}
            >
              {deletePending ? '삭제 중…' : '완료 class 삭제'}
            </Button>
          </>
        }
      >
        {deleteError ? (
          <p role="alert">{deleteErrorMessage(deleteError)}</p>
        ) : (
          <p>
            강의자료와 Transcript·질문·답변·AI 결과의 삭제 정책은 서버 계약에
            따라 처리됩니다.
          </p>
        )}
      </Dialog>
    </>
  )
}
