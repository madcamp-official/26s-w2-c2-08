import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Outlet, useLocation, useParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { CourseRoleBadge } from '../../components/domain/LmsStatus'
import { StatePanel } from '../../components/feedback/StatePanel'
import { AuthenticationExpiredRedirect } from '../auth/AuthenticationExpiredRedirect'
import { courseDetailQueryOptions } from '../courses/queries'
import { CourseClassRail } from './CourseClassRail'
import { CourseSidebar } from './CourseSidebar'
import type { CourseWorkspaceContextValue } from './context'

export function CourseWorkspaceLayout() {
  const { courseId = '' } = useParams()
  const location = useLocation()
  const course = useQuery(courseDetailQueryOptions(courseId))
  const [classRailOpen, setClassRailOpen] = useState(
    () =>
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(min-width: 901px)').matches,
  )

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
  if (course.error instanceof ApiError && course.error.status === 401) {
    return (
      <AuthenticationExpiredRedirect
        returnTo={`${location.pathname}${location.search}${location.hash}`}
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

  const context: CourseWorkspaceContextValue = { course: course.data }

  return (
    <div className="course-workspace-page" data-course-role={course.data.role}>
      <header className="course-detail-hero">
        <div>
          <CourseRoleBadge role={course.data.role} />
          <p className="eyebrow">Course workspace</p>
          <h1>{course.data.title}</h1>
          <p>
            {course.data.semester} · 이 Course 안에서만{' '}
            {course.data.role === 'PROFESSOR' ? '교수자' : '학생'} 권한을
            사용합니다.
          </p>
        </div>
        <Link className="button button--ghost" to="/">
          대시보드로 돌아가기
        </Link>
      </header>

      <div className="course-workspace">
        <CourseSidebar />
        <details
          className="course-class-rail-shell"
          open={classRailOpen}
          onToggle={(event) => setClassRailOpen(event.currentTarget.open)}
        >
          <summary>class 목록 열기·닫기</summary>
          <CourseClassRail course={course.data} />
        </details>
        <section
          className="course-workspace__content"
          id="course-workspace-content"
          aria-label="Course 본문"
        >
          <Outlet context={context} />
        </section>
      </div>
    </div>
  )
}
