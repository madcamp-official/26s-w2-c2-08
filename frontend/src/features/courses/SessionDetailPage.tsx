import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { MaterialPanel } from '../materials/MaterialPanel'
import { sessionMaterialsQueryOptions } from '../materials/queries'
import {
  deleteSession,
  endSession,
  startSession,
  updateSessionTitle,
} from './api'
import {
  courseDetailQueryOptions,
  courseKeys,
  sessionQueryOptions,
} from './queries'

function statusCopy(status: string) {
  switch (status) {
    case 'READY':
      return ['시작 전', '강의자료를 준비한 뒤 수업을 시작할 수 있습니다.']
    case 'LIVE':
      return [
        '진행 중',
        '실시간 수업이 진행 중입니다. 종료하면 수업 기록 정리가 시작됩니다.',
      ]
    case 'PROCESSING':
      return [
        '정리 중',
        '후처리 worker가 기록을 정리하고 있습니다. 완료 여부는 class 상태로만 확인합니다.',
      ]
    default:
      return [
        '완료',
        '수업 기록이 완성되었습니다. 다음 class를 만들 수 있습니다.',
      ]
  }
}

export function SessionDetailPage() {
  const { sessionId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const session = useQuery(sessionQueryOptions(sessionId))
  const course = useQuery({
    ...courseDetailQueryOptions(session.data?.course_id ?? ''),
    enabled: Boolean(session.data),
  })
  const materials = useQuery(sessionMaterialsQueryOptions(sessionId))
  const [title, setTitle] = useState<string | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const endKey = useRef<string | null>(null)
  const deleteKey = useRef<string | null>(null)

  function refreshCourse() {
    if (session.data) {
      void queryClient.invalidateQueries({
        queryKey: courseKeys.detail(session.data.course_id),
      })
      void queryClient.invalidateQueries({
        queryKey: courseKeys.sessions(session.data.course_id),
      })
    }
  }

  const rename = useMutation({
    mutationFn: () =>
      updateSessionTitle(sessionId, title ?? session.data?.title ?? ''),
    onSuccess: (updated) => {
      queryClient.setQueryData(courseKeys.session(sessionId), updated)
      setTitle(null)
      refreshCourse()
      showToast({ tone: 'success', message: 'class 제목을 저장했습니다.' })
    },
  })
  const start = useMutation({
    mutationFn: () => startSession(sessionId),
    onSuccess: (updated) => {
      queryClient.setQueryData(courseKeys.session(sessionId), updated)
      refreshCourse()
    },
  })
  const end = useMutation({
    mutationFn: () =>
      endSession(sessionId, (endKey.current ??= crypto.randomUUID())),
    onSuccess: (accepted) => {
      queryClient.setQueryData(courseKeys.session(sessionId), accepted.session)
      refreshCourse()
      showToast({
        tone: 'success',
        message: '수업을 종료하고 기록 정리를 시작했습니다.',
      })
    },
  })
  const remove = useMutation({
    mutationFn: () =>
      deleteSession(sessionId, (deleteKey.current ??= crypto.randomUUID())),
    onSuccess: () => {
      setDeleteOpen(false)
      if (session.data) {
        void queryClient.invalidateQueries({
          queryKey: courseKeys.detail(session.data.course_id),
        })
      }
      navigate(`/courses/${session.data?.course_id ?? ''}`, { replace: true })
    },
  })

  if (session.isPending)
    return <StatePanel kind="loading" title="class를 불러오는 중" />
  if (session.error instanceof ApiError && session.error.status === 404) {
    return <StatePanel kind="not-found" title="class를 찾을 수 없습니다" />
  }
  if (session.error instanceof ApiError && session.error.status === 403) {
    return (
      <StatePanel kind="forbidden" title="이 class에 접근할 권한이 없습니다" />
    )
  }
  if (session.isError)
    return <StatePanel kind="error" title="class를 불러오지 못했습니다" />

  const data = session.data
  const [statusTitle, statusDescription] = statusCopy(data.status)
  const canDelete = data.status === 'READY' || data.status === 'COMPLETED'
  const professor = course.data?.role === 'PROFESSOR'
  const hasProcessingMaterial = materials.data?.items.some(
    (material) => material.processing_status === 'PROCESSING',
  )

  return (
    <section
      className="course-form-page"
      aria-labelledby="session-detail-title"
    >
      <header className="course-form-heading">
        <p className="eyebrow">Class lifecycle</p>
        <span
          className={`status-chip status-chip--${data.status.toLowerCase()}`}
        >
          {statusTitle}
        </span>
        <h1 id="session-detail-title">{data.title}</h1>
        <p>{statusDescription}</p>
      </header>
      <div className="panel course-form session-detail-card">
        <dl className="session-meta">
          <div>
            <dt>수업 날짜</dt>
            <dd>{data.lecture_date}</dd>
          </div>
          <div>
            <dt>시작 시각</dt>
            <dd>
              {data.started_at
                ? new Date(data.started_at).toLocaleString('ko-KR')
                : '아직 시작 전'}
            </dd>
          </div>
        </dl>

        {professor ? (
          <>
            <label>
              <span>class 제목</span>
              <input
                value={title ?? data.title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <p className="input-hint">
              비워 저장하면 생성 시각 기준의 서버 자동 제목으로 돌아갑니다.
            </p>
            {rename.isError && (
              <p className="form-error" role="alert">
                제목을 저장하지 못했습니다.
              </p>
            )}
            <div className="form-actions">
              <Button
                variant="secondary"
                disabled={rename.isPending}
                onClick={() => rename.mutate()}
              >
                {rename.isPending ? '저장 중…' : '제목 저장'}
              </Button>
              {data.status === 'READY' && (
                <>
                  <Button
                    disabled={start.isPending || Boolean(hasProcessingMaterial)}
                    onClick={() => start.mutate()}
                  >
                    {start.isPending ? '시작 중…' : '수업 시작'}
                  </Button>
                  {hasProcessingMaterial && (
                    <span className="input-hint">
                      처리 중인 강의자료가 완료되거나 실패하면 수업을 시작할 수
                      있습니다.
                    </span>
                  )}
                </>
              )}
              {data.status === 'LIVE' && (
                <Button
                  variant="danger"
                  disabled={end.isPending}
                  onClick={() => end.mutate()}
                >
                  {end.isPending ? '종료 중…' : '수업 종료'}
                </Button>
              )}
              {canDelete && (
                <Button variant="ghost" onClick={() => setDeleteOpen(true)}>
                  class 삭제
                </Button>
              )}
              <Link
                className="button button--ghost"
                to={`/courses/${data.course_id}`}
              >
                Course로 돌아가기
              </Link>
            </div>
          </>
        ) : (
          <>
            <p className="input-hint">
              학생은 class 상태와 수업 기록을 읽기 전용으로 확인합니다.
            </p>
            <div className="form-actions">
              <Link
                className="button button--ghost"
                to={`/courses/${data.course_id}`}
              >
                Course로 돌아가기
              </Link>
            </div>
          </>
        )}
        {professor && (start.isError || end.isError) && (
          <p className="form-error" role="alert">
            {start.error instanceof ApiError &&
            start.error.code === 'MATERIAL_PROCESSING_ACTIVE'
              ? '처리 중인 강의자료가 있어 시작할 수 없습니다.'
              : '상태를 변경하지 못했습니다. 현재 class를 다시 확인해 주세요.'}
          </p>
        )}
      </div>
      <MaterialPanel
        sessionId={data.id}
        professor={professor}
        sessionStatus={data.status}
      />
      {professor && (
        <Dialog
          open={deleteOpen}
          title="class를 삭제할까요?"
          description="삭제 후에는 되돌릴 수 없습니다."
          onOpenChange={setDeleteOpen}
          actions={
            <>
              <Button
                variant="secondary"
                disabled={remove.isPending}
                onClick={() => setDeleteOpen(false)}
              >
                취소
              </Button>
              <Button
                variant="danger"
                disabled={remove.isPending}
                onClick={() => remove.mutate()}
              >
                {remove.isPending ? '삭제 중…' : '삭제'}
              </Button>
            </>
          }
        >
          {remove.isError && <p role="alert">class를 삭제하지 못했습니다.</p>}
        </Dialog>
      )}
    </section>
  )
}
