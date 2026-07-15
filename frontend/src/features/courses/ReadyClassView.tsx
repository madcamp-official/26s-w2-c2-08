import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type ReactNode, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import {
  CourseRoleBadge,
  SessionStatusBadge,
} from '../../components/domain/LmsStatus'
import { useToast } from '../../components/feedback/toast-context'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Dialog } from '../../components/ui/Dialog'
import { Field } from '../../components/ui/Field'
import { LinkButton } from '../../components/ui/LinkButton'
import { MaterialPanel } from '../materials/MaterialPanel'
import {
  materialKeys,
  sessionMaterialsQueryOptions,
} from '../materials/queries'
import type { Course, LectureSession } from './api'
import { deleteSession, startSession, updateSessionTitle } from './api'
import { courseKeys } from './queries'

interface ReadyClassViewProps {
  course: Course
  refreshWarning?: ReactNode
  session: LectureSession
}

export function ReadyClassView({
  course,
  refreshWarning,
  session,
}: ReadyClassViewProps) {
  const titleId = useId()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const professor = course.role === 'PROFESSOR'
  const materials = useQuery(sessionMaterialsQueryOptions(session.id))
  const [titleEdit, setTitleEdit] = useState({
    canonical: session.title,
    dirty: false,
    value: session.title,
  })
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [recordingAcknowledged, setRecordingAcknowledged] = useState(false)
  const deleteKey = useRef<string | null>(null)

  if (titleEdit.canonical !== session.title) {
    const preserveDraft = titleEdit.dirty && titleEdit.value !== session.title
    setTitleEdit({
      canonical: session.title,
      dirty: preserveDraft,
      value: preserveDraft ? titleEdit.value : session.title,
    })
  }

  const title = titleEdit.value
  const titleDirty = titleEdit.dirty

  function refreshCourse() {
    void queryClient.invalidateQueries({
      queryKey: courseKeys.detail(session.course_id),
    })
    void queryClient.invalidateQueries({
      queryKey: courseKeys.sessions(session.course_id),
    })
  }

  const rename = useMutation({
    mutationFn: () => updateSessionTitle(session.id, title.trim()),
    onSuccess: (updated) => {
      queryClient.setQueryData(courseKeys.session(session.id), updated)
      setTitleEdit({
        canonical: updated.title,
        dirty: false,
        value: updated.title,
      })
      refreshCourse()
      showToast({ tone: 'success', message: 'class 제목을 저장했습니다.' })
    },
  })
  const start = useMutation({
    mutationFn: () => startSession(session.id),
    onSuccess: (updated) => {
      queryClient.setQueryData(courseKeys.session(session.id), updated)
      refreshCourse()
      showToast({ tone: 'success', message: '실시간 class를 시작했습니다.' })
    },
    onError: (error) => {
      if (
        error instanceof ApiError &&
        error.code === 'MATERIAL_PROCESSING_ACTIVE'
      ) {
        void queryClient.invalidateQueries({
          queryKey: materialKeys.session(session.id),
        })
      }
      if (
        error instanceof ApiError &&
        error.code === 'SESSION_STATE_CONFLICT'
      ) {
        void queryClient.invalidateQueries({
          queryKey: courseKeys.session(session.id),
        })
        refreshCourse()
      }
    },
  })
  const remove = useMutation({
    mutationFn: () =>
      deleteSession(session.id, (deleteKey.current ??= crypto.randomUUID())),
    onSuccess: () => {
      setDeleteOpen(false)
      deleteKey.current = null
      refreshCourse()
      showToast({ tone: 'success', message: 'READY class를 삭제했습니다.' })
      void navigate(`/courses/${session.course_id}`, { replace: true })
    },
  })

  const hasProcessingMaterial = materials.data?.items.some(
    (material) => material.processing_status === 'PROCESSING',
  )
  const materialBlocksStart =
    materials.isPending || materials.isError || Boolean(hasProcessingMaterial)
  const startBlocked = materialBlocksStart || !recordingAcknowledged

  return (
    <section
      className="class-ready-page"
      aria-labelledby="session-detail-title"
    >
      <PageHeader
        eyebrow="CLASS_CREATE_PAGE · READY"
        title={session.title}
        titleId="session-detail-title"
        description={
          <div className="class-ready-header__description">
            <CourseRoleBadge role={course.role} />
            <SessionStatusBadge status="READY" />
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

      {professor ? (
        <div className="class-ready-layout">
          <div className="class-ready-main">
            <Card
              as="section"
              className="class-ready-summary"
              elevated
              aria-labelledby="ready-summary-title"
            >
              <div className="class-ready-step-heading">
                <span aria-hidden="true">1</span>
                <div>
                  <p className="eyebrow">Class information</p>
                  <h2 id="ready-summary-title">READY class 정보</h2>
                  <p>수업 날짜는 유지되고 제목만 언제든 수정할 수 있습니다.</p>
                </div>
              </div>

              <dl className="class-ready-summary__meta">
                <div>
                  <dt>Course</dt>
                  <dd>{course.title}</dd>
                </div>
                <div>
                  <dt>수업 날짜</dt>
                  <dd>{session.lecture_date}</dd>
                </div>
                <div>
                  <dt>시작 시각</dt>
                  <dd>LIVE 전환 시 확정</dd>
                </div>
              </dl>

              <div className="class-ready-title-form">
                <Field
                  htmlFor={titleId}
                  label="class 제목"
                  hint="비워 저장하면 생성 시 확정한 서버 자동 제목으로 돌아갑니다."
                >
                  <input
                    value={title}
                    disabled={rename.isPending}
                    onChange={(event) => {
                      const nextTitle = event.target.value
                      setTitleEdit({
                        canonical: session.title,
                        dirty: nextTitle !== session.title,
                        value: nextTitle,
                      })
                      if (rename.isError) rename.reset()
                    }}
                  />
                </Field>
                <Button
                  variant="secondary"
                  disabled={rename.isPending || !titleDirty}
                  onClick={() => rename.mutate()}
                >
                  {rename.isPending ? '제목 저장 중…' : '제목 저장'}
                </Button>
              </div>
              {rename.isError && (
                <p className="form-error" role="alert">
                  제목을 저장하지 못했습니다. 입력은 유지되었습니다.
                </p>
              )}
            </Card>

            <div className="class-ready-material-step">
              <div className="class-ready-step-heading">
                <span aria-hidden="true">2</span>
                <div>
                  <p className="eyebrow">Optional material</p>
                  <h2>강의자료 준비</h2>
                  <p>
                    PDF가 없어도 시작할 수 있고, 처리 중인 자료만 시작을
                    막습니다.
                  </p>
                </div>
              </div>
              <MaterialPanel
                sessionId={session.id}
                professor
                sessionStatus="READY"
              />
            </div>
          </div>

          <aside className="class-ready-rail" aria-label="수업 시작 준비 상태">
            <Card className="class-ready-launch" elevated>
              <div>
                <p className="eyebrow">Ready to teach</p>
                <h2>수업 시작 준비</h2>
                <p>
                  시작하면 Session은 LIVE로 바뀌고 실시간 Transcript와 질문이
                  열립니다.
                </p>
              </div>
              <ul className="class-ready-checklist">
                <li>
                  <span aria-hidden="true">✓</span>
                  class 기본 정보 확인
                </li>
                <li>
                  <span aria-hidden="true">
                    {materials.isSuccess && !hasProcessingMaterial ? '✓' : '·'}
                  </span>
                  {materials.isPending
                    ? '강의자료 상태 확인 중'
                    : materials.isError
                      ? '강의자료 상태 확인 필요'
                      : hasProcessingMaterial
                        ? '처리 중인 PDF 완료 대기'
                        : `${materials.data.items.length}개 PDF 상태 확인`}
                </li>
              </ul>
              <label className="class-ready-recording-consent">
                <input
                  type="checkbox"
                  checked={recordingAcknowledged}
                  disabled={start.isPending}
                  onChange={(event) =>
                    setRecordingAcknowledged(event.target.checked)
                  }
                />
                <span>
                  <strong>수업 원본 녹음 저장에 동의합니다.</strong>
                  <small>
                    시작 후 교수자 마이크가 연결되면 이 브라우저에 원본을 자동
                    저장하고, 수업 종료 뒤 고품질 Transcript 처리를 위해
                    업로드합니다.
                  </small>
                </span>
              </label>
              <Button
                className="class-ready-launch__button"
                disabled={start.isPending || startBlocked}
                onClick={() => start.mutate()}
              >
                {start.isPending ? '수업 시작 중…' : '수업 시작'}
              </Button>
              {materialBlocksStart && (
                <p className="class-ready-launch__hint">
                  {hasProcessingMaterial
                    ? '처리 중인 PDF가 READY 또는 FAILED가 되면 시작할 수 있습니다.'
                    : '강의자료 목록을 확인한 뒤 시작할 수 있습니다.'}
                </p>
              )}
              {!recordingAcknowledged && (
                <p className="class-ready-launch__hint">
                  수업을 시작하려면 원본 녹음 저장 동의를 확인해 주세요.
                </p>
              )}
              {start.isError && (
                <p className="form-error" role="alert">
                  {start.error instanceof ApiError &&
                  start.error.code === 'MATERIAL_PROCESSING_ACTIVE'
                    ? '서버에서 처리 중인 강의자료를 확인했습니다. 목록을 갱신합니다.'
                    : '수업을 시작하지 못했습니다. 최신 상태를 다시 확인해 주세요.'}
                </p>
              )}
            </Card>

            <Card className="class-ready-delete">
              <h2>READY class 삭제</h2>
              <p>삭제하면 연결된 준비 상태를 되돌릴 수 없습니다.</p>
              <Button
                variant="ghost"
                onClick={() => {
                  remove.reset()
                  deleteKey.current = null
                  setDeleteOpen(true)
                }}
              >
                class 삭제
              </Button>
            </Card>
          </aside>
        </div>
      ) : (
        <div className="class-ready-student">
          <Card as="section" elevated>
            <SessionStatusBadge status="READY" />
            <h2>교수자가 수업을 준비하고 있습니다.</h2>
            <p>
              별도 동작 없이 기다려 주세요. LIVE로 전환되면 Course의 현재
              class에서 입장할 수 있습니다.
            </p>
            <LinkButton
              variant="secondary"
              to={`/courses/${session.course_id}`}
            >
              Course로 돌아가기
            </LinkButton>
          </Card>
          <MaterialPanel
            sessionId={session.id}
            professor={false}
            sessionStatus="READY"
          />
        </div>
      )}

      {professor && (
        <Dialog
          open={deleteOpen}
          title="READY class를 삭제할까요?"
          description="삭제 후에는 되돌릴 수 없습니다."
          onOpenChange={(open) => {
            if (!open && remove.isPending) return
            if (!open) {
              remove.reset()
              deleteKey.current = null
            }
            setDeleteOpen(open)
          }}
          actions={
            <>
              <Button
                variant="secondary"
                disabled={remove.isPending}
                onClick={() => {
                  remove.reset()
                  deleteKey.current = null
                  setDeleteOpen(false)
                }}
              >
                취소
              </Button>
              <Button
                variant="danger"
                disabled={remove.isPending}
                onClick={() => remove.mutate()}
              >
                {remove.isPending ? '삭제 중…' : 'READY class 삭제'}
              </Button>
            </>
          }
        >
          {remove.isError && (
            <p className="form-error" role="alert">
              class를 삭제하지 못했습니다. 같은 요청으로 다시 시도할 수
              있습니다.
            </p>
          )}
        </Dialog>
      )}
    </section>
  )
}
