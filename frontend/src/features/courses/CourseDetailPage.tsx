import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { rotateCourseJoinCode } from './api'
import {
  courseDetailQueryOptions,
  courseKeys,
  courseSessionsQueryOptions,
} from './queries'

function sessionCopy(status?: string) {
  switch (status) {
    case 'READY':
      return ['시작 전', '교수자가 class를 준비하고 있습니다.']
    case 'LIVE':
      return ['진행 중', '지금 실시간 class가 진행 중입니다.']
    case 'PROCESSING':
      return ['정리 중', '수업 기록과 고품질 Transcript를 정리하고 있습니다.']
    default:
      return ['현재 class 없음', '새 class가 만들어지면 이곳에 표시됩니다.']
  }
}

export function CourseDetailPage() {
  const { courseId = '' } = useParams()
  const course = useQuery(courseDetailQueryOptions(courseId))
  const sessions = useQuery(courseSessionsQueryOptions(courseId))
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [rotateOpen, setRotateOpen] = useState(false)
  const rotate = useMutation({
    mutationFn: () => rotateCourseJoinCode(courseId, crypto.randomUUID()),
    onSuccess: (updated) => {
      queryClient.setQueryData(courseKeys.detail(courseId), updated)
      void queryClient.invalidateQueries({
        queryKey: courseKeys.list('PROFESSOR'),
      })
      setRotateOpen(false)
      showToast({ tone: 'success', message: '새 참여 코드로 교체했습니다.' })
    },
    onError: () => {
      showToast({ tone: 'error', message: '참여 코드를 교체하지 못했습니다.' })
    },
  })

  if (course.isPending) {
    return <StatePanel kind="loading" title="Course를 불러오는 중" />
  }
  if (course.error instanceof ApiError && course.error.status === 403) {
    return (
      <StatePanel
        kind="forbidden"
        title="이 Course에 접근할 권한이 없습니다"
        description="현재 계정의 Course 멤버십을 확인해 주세요."
      />
    )
  }
  if (course.error instanceof ApiError && course.error.status === 404) {
    return <StatePanel kind="not-found" title="Course를 찾을 수 없습니다" />
  }
  if (course.isError) {
    return (
      <StatePanel
        kind="error"
        title="Course를 불러오지 못했습니다"
        actionLabel="다시 시도"
        onAction={() => void course.refetch()}
      />
    )
  }

  const courseData = course.data
  const professor = courseData.role === 'PROFESSOR'
  const [sessionState, sessionDescription] = sessionCopy(
    courseData.current_session?.status,
  )

  async function copyJoinCode() {
    if (!professor || !courseData.join_code) return
    try {
      await navigator.clipboard.writeText(courseData.join_code)
      showToast({ tone: 'success', message: '참여 코드를 복사했습니다.' })
    } catch {
      showToast({ tone: 'error', message: '참여 코드를 복사하지 못했습니다.' })
    }
  }

  return (
    <div className="course-detail-page">
      <header className="course-detail-hero">
        <div>
          <span className="badge">{professor ? '교수자' : '학생'}</span>
          <h1>{courseData.title}</h1>
          <p>{courseData.semester}</p>
        </div>
        <Link className="button button--ghost" to="/">
          대시보드로 돌아가기
        </Link>
      </header>

      <div className="course-detail-grid">
        <section
          className="panel current-session-card"
          aria-labelledby="current-session-title"
        >
          <p className="eyebrow">Current class</p>
          <h2 id="current-session-title">{sessionState}</h2>
          <p>{sessionDescription}</p>
          {courseData.current_session && (
            <dl className="session-meta">
              <div>
                <dt>class</dt>
                <dd>{courseData.current_session.title}</dd>
              </div>
              <div>
                <dt>날짜</dt>
                <dd>{courseData.current_session.lecture_date}</dd>
              </div>
            </dl>
          )}
          {courseData.current_session ? (
            <Link
              className="button button--secondary"
              to={`/sessions/${courseData.current_session.id}`}
            >
              현재 class 보기
            </Link>
          ) : professor ? (
            <Link
              className="button button--primary"
              to={`/courses/${courseId}/sessions/new`}
            >
              새 class 만들기
            </Link>
          ) : null}
        </section>

        {professor ? (
          <aside
            className="panel professor-controls"
            aria-labelledby="join-code-title"
          >
            <div>
              <p className="eyebrow">Owner control</p>
              <h2 id="join-code-title">학생 참여 코드</h2>
              <p>
                이 코드는 자동 만료되지 않으며 회전하면 이전 코드는 즉시 무효가
                됩니다.
              </p>
            </div>
            <strong className="join-code-display">
              {courseData.join_code}
            </strong>
            <div className="form-actions">
              <Button variant="secondary" onClick={() => void copyJoinCode()}>
                코드 복사
              </Button>
              <Button variant="danger" onClick={() => setRotateOpen(true)}>
                새 코드로 교체
              </Button>
            </div>
          </aside>
        ) : (
          <aside
            className="panel student-course-note"
            aria-labelledby="student-role-title"
          >
            <p className="eyebrow">Student</p>
            <h2 id="student-role-title">학생 Course</h2>
            <p>
              현재 class 상태와 완료된 강의 기록을 이 Course에서 확인할 수
              있습니다.
            </p>
          </aside>
        )}
      </div>

      <section
        className="panel session-history"
        aria-labelledby="session-history-title"
      >
        <div>
          <p className="eyebrow">Class history</p>
          <h2 id="session-history-title">지난 class</h2>
        </div>
        {sessions.isPending ? (
          <p>class 목록을 불러오는 중입니다.</p>
        ) : sessions.isError ? (
          <p>
            class 목록을 불러오지 못했습니다. Course 상태는 계속 확인할 수
            있습니다.
          </p>
        ) : sessions.data.items.filter((item) => item.status === 'COMPLETED')
            .length === 0 ? (
          <p>아직 완료된 class가 없습니다.</p>
        ) : (
          <ul className="session-history__list">
            {sessions.data.items
              .filter((item) => item.status === 'COMPLETED')
              .map((item) => (
                <li key={item.id}>
                  <Link to={`/sessions/${item.id}`}>
                    <strong>{item.title}</strong>
                    <span>{item.lecture_date} · 완료</span>
                  </Link>
                </li>
              ))}
          </ul>
        )}
      </section>

      {professor && (
        <Dialog
          open={rotateOpen}
          title="참여 코드를 새로 만들까요?"
          description="완료되는 즉시 현재 코드는 더 이상 사용할 수 없습니다."
          onOpenChange={setRotateOpen}
          actions={
            <>
              <Button
                variant="secondary"
                disabled={rotate.isPending}
                onClick={() => setRotateOpen(false)}
              >
                취소
              </Button>
              <Button
                variant="danger"
                disabled={rotate.isPending}
                onClick={() => rotate.mutate()}
              >
                {rotate.isPending ? '교체 중…' : '새 코드로 교체'}
              </Button>
            </>
          }
        >
          <p>학생들에게 새 코드를 다시 안내해야 합니다.</p>
        </Dialog>
      )}
    </div>
  )
}
