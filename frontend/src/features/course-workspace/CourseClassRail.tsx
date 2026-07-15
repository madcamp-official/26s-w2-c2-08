import { useInfiniteQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { Button } from '../../components/ui/Button'
import { Skeleton } from '../../components/ui/Skeleton'
import type { Course } from '../courses/api'
import { courseCompletedSessionsInfiniteQueryOptions } from '../courses/queries'

function currentSessionCopy(status?: string) {
  switch (status) {
    case 'READY':
      return '시작 전'
    case 'LIVE':
      return '진행 중'
    case 'PROCESSING':
      return '정리 중'
    default:
      return '현재 class 없음'
  }
}

function sessionStartLabel(startedAt: string | null, lectureDate: string) {
  if (!startedAt) return lectureDate
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Seoul',
  }).format(new Date(startedAt))
}

export function CourseClassRail({ course }: { course: Course }) {
  const sessions = useInfiniteQuery(
    courseCompletedSessionsInfiniteQueryOptions(course.id),
  )
  const completedSessions =
    sessions.data?.pages.flatMap((page) => page.items) ?? []
  const currentSession = course.current_session

  return (
    <aside className="course-class-rail" aria-label="class 목록">
      <section
        className="course-class-rail__live"
        aria-labelledby="course-live-class-title"
      >
        <p className="eyebrow" id="course-live-class-title">
          LIVE CLASS
        </p>
        <strong>{currentSessionCopy(currentSession?.status)}</strong>
        {currentSession &&
        !(course.role === 'STUDENT' && currentSession.status === 'READY') ? (
          <>
            <span>{currentSession.title}</span>
            <Link
              className="course-class-rail__session-link"
              to={`/sessions/${currentSession.id}`}
            >
              class 보기
            </Link>
          </>
        ) : currentSession ? (
          <span role="status">
            교수자가 class를 시작하면 입장 동작이 열립니다.
          </span>
        ) : (
          <span>진행 중인 class가 생기면 이곳에 표시됩니다.</span>
        )}
      </section>

      <section
        className="course-class-rail__history"
        aria-labelledby="course-class-history-title"
      >
        <div className="course-class-rail__heading">
          <p className="eyebrow">Class history</p>
          <h2 id="course-class-history-title">지난 class</h2>
        </div>

        {sessions.isPending ? (
          <Skeleton label="지난 class 목록을 불러오는 중" lines={3} />
        ) : sessions.isError && completedSessions.length === 0 ? (
          <div role="alert" className="course-class-rail__state">
            <p>class 목록을 불러오지 못했습니다.</p>
            <Button variant="secondary" onClick={() => void sessions.refetch()}>
              다시 시도
            </Button>
          </div>
        ) : completedSessions.length === 0 ? (
          <p>아직 완료된 class가 없습니다.</p>
        ) : (
          <ul className="course-class-rail__list">
            {completedSessions.map((session) => (
              <li key={session.id}>
                <Link to={`/sessions/${session.id}`}>
                  <strong>{session.title}</strong>
                  <span>
                    {sessionStartLabel(
                      session.started_at,
                      session.lecture_date,
                    )}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}

        {sessions.isError && completedSessions.length > 0 && (
          <div role="alert" className="course-class-rail__state">
            <p>다음 class를 불러오지 못했습니다. 표시된 목록은 유지됩니다.</p>
            <Button variant="secondary" onClick={() => void sessions.refetch()}>
              다시 시도
            </Button>
          </div>
        )}
        {sessions.hasNextPage && (
          <Button
            variant="secondary"
            disabled={sessions.isFetchingNextPage}
            onClick={() => void sessions.fetchNextPage()}
          >
            {sessions.isFetchingNextPage
              ? '불러오는 중…'
              : '지난 class 더 보기'}
          </Button>
        )}
      </section>
    </aside>
  )
}
