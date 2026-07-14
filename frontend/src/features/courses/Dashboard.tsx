import { useInfiniteQuery } from '@tanstack/react-query'
import { useEffect } from 'react'

import { ApiError } from '../../api/errors'
import {
  CourseRoleBadge,
  SessionStatusBadge,
} from '../../components/domain/LmsStatus'
import { PartialFailurePanel } from '../../components/feedback/PartialFailurePanel'
import { StatePanel } from '../../components/feedback/StatePanel'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { LinkButton } from '../../components/ui/LinkButton'
import { Skeleton } from '../../components/ui/Skeleton'
import { Status } from '../../components/ui/Status'
import type { Course } from './api'
import { courseInfiniteListQueryOptions } from './queries'

type CourseRole = 'PROFESSOR' | 'STUDENT'

function useDashboardCourseList(role: CourseRole) {
  return useInfiniteQuery(courseInfiniteListQueryOptions(role))
}

type CourseListQuery = ReturnType<typeof useDashboardCourseList>
type ActiveSessionStatus = 'READY' | 'LIVE' | 'PROCESSING'
type ActiveCourse = Course & {
  current_session: NonNullable<Course['current_session']> & {
    status: ActiveSessionStatus
  }
}

const activeSessionPriority = {
  LIVE: 0,
  READY: 1,
  PROCESSING: 2,
} as const

function queryCourses(query: CourseListQuery) {
  return query.data?.pages.flatMap((page) => page.items) ?? []
}

function hasActiveSession(course: Course): course is ActiveCourse {
  const status = course.current_session?.status
  return status === 'READY' || status === 'LIVE' || status === 'PROCESSING'
}

function selectActiveCourse(queries: CourseListQuery[]) {
  return queries
    .flatMap(queryCourses)
    .filter(hasActiveSession)
    .sort((left, right) => {
      const priorityDifference =
        activeSessionPriority[left.current_session.status] -
        activeSessionPriority[right.current_session.status]
      if (priorityDifference !== 0) return priorityDifference
      return right.current_session.lecture_date.localeCompare(
        left.current_session.lecture_date,
      )
    })[0]
}

function formatLectureDate(value: string) {
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'long',
    day: 'numeric',
    weekday: 'short',
    timeZone: 'Asia/Seoul',
  }).format(new Date(`${value}T00:00:00+09:00`))
}

function dashboardToday() {
  const now = new Date()
  return {
    dateTime: new Intl.DateTimeFormat('sv-SE', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      timeZone: 'Asia/Seoul',
    }).format(now),
    label: new Intl.DateTimeFormat('ko-KR', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      weekday: 'long',
      timeZone: 'Asia/Seoul',
    }).format(now),
  }
}

function sessionActionLabel(course: ActiveCourse) {
  switch (course.current_session.status) {
    case 'READY':
      return course.role === 'PROFESSOR'
        ? 'class 준비 화면 열기'
        : 'class 대기 화면 열기'
    case 'LIVE':
      return '실시간 class 들어가기'
    case 'PROCESSING':
      return '기록 정리 상태 보기'
  }
}

function DashboardSpotlight({
  professorCourses,
  studentCourses,
}: {
  professorCourses: CourseListQuery
  studentCourses: CourseListQuery
}) {
  const queries = [professorCourses, studentCourses]
  const activeCourse = selectActiveCourse(queries)
  const isPending = queries.some((query) => query.isPending)
  const failedQueries = queries.filter((query) => query.isError)

  return (
    <section className="dashboard-overview" aria-label="현재 class와 빠른 실행">
      <Card
        as="section"
        className="dashboard-spotlight"
        elevated
        aria-labelledby="active-class-title"
      >
        <header className="dashboard-spotlight__heading">
          <p className="eyebrow">Current class</p>
          {activeCourse && (
            <div className="dashboard-spotlight__status">
              <CourseRoleBadge role={activeCourse.role} />
              <SessionStatusBadge
                status={activeCourse.current_session.status}
              />
            </div>
          )}
        </header>

        {activeCourse ? (
          <div className="dashboard-spotlight__body">
            <p>{activeCourse.title}</p>
            <h2 id="active-class-title">
              {activeCourse.current_session.title}
            </h2>
            <p className="dashboard-spotlight__date">
              {formatLectureDate(activeCourse.current_session.lecture_date)} ·{' '}
              {activeCourse.role === 'PROFESSOR' ? '교수자' : '학생'}
            </p>
            <LinkButton to={`/sessions/${activeCourse.current_session.id}`}>
              {sessionActionLabel(activeCourse)}
            </LinkButton>
          </div>
        ) : isPending ? (
          <div className="dashboard-spotlight__pending" aria-busy="true">
            <h2 id="active-class-title">현재 class를 확인하고 있습니다</h2>
            <Skeleton label="현재 active class를 불러오는 중" lines={3} />
          </div>
        ) : failedQueries.length > 0 ? (
          <div className="dashboard-spotlight__empty">
            <Status tone="warning">확인 필요</Status>
            <h2 id="active-class-title">
              현재 class 상태를 모두 확인하지 못했습니다
            </h2>
            <p>확인된 Course는 아래에서 계속 이용할 수 있습니다.</p>
            <Button
              variant="secondary"
              onClick={() =>
                void Promise.all(failedQueries.map((query) => query.refetch()))
              }
            >
              실패한 목록 다시 확인
            </Button>
          </div>
        ) : (
          <div className="dashboard-spotlight__empty">
            <Status>대기 중</Status>
            <h2 id="active-class-title">현재 진행 중인 class가 없습니다</h2>
            <p>
              시작 전·진행 중·기록 정리 중인 class가 생기면 이곳에 가장 먼저
              표시됩니다.
            </p>
          </div>
        )}
      </Card>

      <Card as="aside" className="dashboard-quick-actions">
        <div>
          <p className="eyebrow">Quick actions</p>
          <h2>Course 바로 시작하기</h2>
          <p>새 수업방을 만들거나 받은 코드로 참여하세요.</p>
        </div>
        <LinkButton to="/courses/new">Course 만들기</LinkButton>
        <LinkButton to="/courses/join" variant="secondary">
          코드로 참여하기
        </LinkButton>
      </Card>
    </section>
  )
}

function CourseCard({ course }: { course: Course }) {
  const activeSession = hasActiveSession(course) ? course.current_session : null
  const professor = course.role === 'PROFESSOR'

  return (
    <Card as="article" className="course-card" elevated>
      <div className="course-card__topline">
        <CourseRoleBadge role={course.role} />
        {activeSession ? (
          <SessionStatusBadge status={activeSession.status} />
        ) : (
          <Status>현재 class 없음</Status>
        )}
      </div>

      <div className="course-card__identity">
        <h3>{course.title}</h3>
        <p>{course.semester}</p>
      </div>

      {activeSession && (
        <div className="course-card__current">
          <span>현재 class</span>
          <strong>{activeSession.title}</strong>
          <small>{formatLectureDate(activeSession.lecture_date)}</small>
        </div>
      )}

      {professor && course.join_code && (
        <div className="course-card__code">
          <span>참여 코드</span>
          <strong>{course.join_code}</strong>
        </div>
      )}

      <div className="course-card__actions">
        {activeSession && (
          <LinkButton to={`/sessions/${activeSession.id}`}>
            class 열기
          </LinkButton>
        )}
        <LinkButton
          to={`/courses/${course.id}`}
          variant={activeSession ? 'secondary' : 'primary'}
        >
          Course 보기
        </LinkButton>
      </div>
    </Card>
  )
}

function CourseSection({
  courses,
  role,
}: {
  courses: CourseListQuery
  role: CourseRole
}) {
  const professor = role === 'PROFESSOR'
  const title = professor ? '내가 관리 중인 Course' : '내가 참여 중인 Course'
  const items = queryCourses(courses)
  const countLabel =
    courses.isPending || courses.isError
      ? '—'
      : `${items.length}${courses.hasNextPage ? '+' : ''}개 Course`

  return (
    <section
      className="dashboard-section"
      aria-busy={courses.isPending || courses.isFetchingNextPage}
      aria-labelledby={`course-${role.toLowerCase()}`}
    >
      <header className="dashboard-section__heading">
        <div>
          <p className="eyebrow">{professor ? 'Professor' : 'Student'}</p>
          <div className="dashboard-section__title-row">
            <h2 id={`course-${role.toLowerCase()}`}>{title}</h2>
            <span
              className="dashboard-section__count"
              aria-label={`${title} ${countLabel}`}
            >
              {countLabel}
            </span>
          </div>
          <p>
            {professor
              ? '교수자 권한으로 class와 참여 코드를 관리합니다.'
              : '학생 권한으로 class에 참여하고 기록을 확인합니다.'}
          </p>
        </div>
      </header>

      {courses.isPending && (
        <div className="course-grid" role="status">
          <Card className="course-card course-card--skeleton">
            <Skeleton label={`${title}를 불러오는 중`} lines={5} />
          </Card>
          <Card
            className="course-card course-card--skeleton"
            aria-hidden="true"
          >
            <Skeleton lines={5} />
          </Card>
        </div>
      )}

      {courses.isError && (
        <PartialFailurePanel
          title={`${title}를 불러오지 못했습니다`}
          description="다른 역할의 Course는 계속 확인할 수 있습니다. 이 목록만 다시 요청하세요."
          actions={
            <Button variant="secondary" onClick={() => void courses.refetch()}>
              이 목록 다시 시도
            </Button>
          }
        />
      )}

      {courses.isSuccess && items.length === 0 && (
        <Card className="course-section-empty">
          <Status tone="neutral">0개 Course</Status>
          <h3>
            {professor
              ? '아직 만든 Course가 없습니다'
              : '아직 참여한 Course가 없습니다'}
          </h3>
          <p>
            {professor
              ? '새 Course를 만들면 이곳에서 교수자 권한으로 관리합니다.'
              : '교수자에게 받은 참여 코드로 Course에 들어오세요.'}
          </p>
          <LinkButton to={professor ? '/courses/new' : '/courses/join'}>
            {professor ? '첫 Course 만들기' : '참여 코드 입력하기'}
          </LinkButton>
        </Card>
      )}

      {items.length > 0 && (
        <div className="course-grid">
          {items.map((course) => (
            <CourseCard course={course} key={course.id} />
          ))}
        </div>
      )}

      {courses.isFetchNextPageError && (
        <PartialFailurePanel
          title="다음 Course를 불러오지 못했습니다"
          description="이미 표시한 Course는 그대로 유지했습니다. 다음 목록만 다시 요청하세요."
          actions={
            <Button
              variant="secondary"
              onClick={() => void courses.fetchNextPage()}
            >
              다음 목록 다시 시도
            </Button>
          }
        />
      )}

      {courses.hasNextPage && !courses.isFetchNextPageError && (
        <Button
          className="dashboard-section__more"
          variant="secondary"
          disabled={courses.isFetchingNextPage}
          onClick={() => void courses.fetchNextPage()}
        >
          {courses.isFetchingNextPage
            ? 'Course 더 불러오는 중…'
            : 'Course 더 보기'}
        </Button>
      )}
    </section>
  )
}

export function Dashboard({
  displayName,
  onAuthenticationExpired,
}: {
  displayName: string
  onAuthenticationExpired: () => void
}) {
  const professorCourses = useDashboardCourseList('PROFESSOR')
  const studentCourses = useDashboardCourseList('STUDENT')
  const today = dashboardToday()
  const authenticationExpired = [professorCourses, studentCourses].some(
    (query) => query.error instanceof ApiError && query.error.status === 401,
  )

  useEffect(() => {
    if (authenticationExpired) onAuthenticationExpired()
  }, [authenticationExpired, onAuthenticationExpired])

  if (authenticationExpired) {
    return (
      <StatePanel
        kind="loading"
        title="로그인 상태를 다시 확인하는 중"
        description="Course 정보를 숨기고 안전한 비로그인 화면으로 전환합니다."
      />
    )
  }

  return (
    <div className="dashboard-page">
      <PageHeader
        eyebrow="Your lecture workspace"
        title={`${displayName}님, 오늘의 강의를 이어가세요.`}
        description={
          <>
            <p>
              Course마다 교수자와 학생 역할을 따로 확인하고 다음 class로 바로
              이동합니다.
            </p>
            <time className="dashboard-today" dateTime={today.dateTime}>
              {today.label}
            </time>
          </>
        }
      />

      <DashboardSpotlight
        professorCourses={professorCourses}
        studentCourses={studentCourses}
      />

      <div className="dashboard-course-groups">
        <CourseSection courses={professorCourses} role="PROFESSOR" />
        <CourseSection courses={studentCourses} role="STUDENT" />
      </div>
    </div>
  )
}
