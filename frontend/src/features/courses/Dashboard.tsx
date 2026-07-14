import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { StatePanel } from '../../components/feedback/StatePanel'
import type { Course } from './api'
import { courseListQueryOptions } from './queries'

function currentSessionLabel(course: Course) {
  switch (course.current_session?.status) {
    case 'READY':
      return '시작 전 class'
    case 'LIVE':
      return '진행 중 class'
    case 'PROCESSING':
      return '정리 중 class'
    default:
      return '현재 class 없음'
  }
}

function CourseCard({ course }: { course: Course }) {
  const professor = course.role === 'PROFESSOR'
  return (
    <article className="course-card">
      <div className="course-card__topline">
        <span className="badge">{professor ? '교수자' : '학생'}</span>
        <span className="course-card__session">
          {currentSessionLabel(course)}
        </span>
      </div>
      <div>
        <h3>{course.title}</h3>
        <p>{course.semester}</p>
      </div>
      {professor && course.join_code && (
        <div className="course-card__code">
          <span>참여 코드</span>
          <strong>{course.join_code}</strong>
        </div>
      )}
      <Link className="button button--secondary" to={`/courses/${course.id}`}>
        Course 열기
      </Link>
    </article>
  )
}

function CourseSection({ role }: { role: 'PROFESSOR' | 'STUDENT' }) {
  const courses = useQuery(courseListQueryOptions(role))
  const professor = role === 'PROFESSOR'
  const title = professor ? '내가 관리 중인 Course' : '내가 참여 중인 Course'

  return (
    <section
      className="dashboard-section"
      aria-labelledby={`course-${role.toLowerCase()}`}
    >
      <header className="section-heading">
        <div>
          <p className="eyebrow">{professor ? 'Professor' : 'Student'}</p>
          <h2 id={`course-${role.toLowerCase()}`}>{title}</h2>
        </div>
        <span className="badge">{courses.data?.items.length ?? '—'}</span>
      </header>
      {courses.isPending && (
        <StatePanel kind="loading" title={`${title}를 불러오는 중`} />
      )}
      {courses.isError && (
        <StatePanel
          kind="error"
          title={`${title}를 불러오지 못했습니다`}
          actionLabel="다시 시도"
          onAction={() => void courses.refetch()}
        />
      )}
      {courses.isSuccess && courses.data.items.length === 0 && (
        <StatePanel
          kind="empty"
          title={
            professor
              ? '아직 만든 Course가 없습니다'
              : '아직 참여한 Course가 없습니다'
          }
          description={
            professor
              ? '새 Course를 만들면 이곳에서 교수자 권한으로 관리합니다.'
              : '교수자에게 받은 참여 코드로 Course에 들어오세요.'
          }
        />
      )}
      {courses.isSuccess && courses.data.items.length > 0 && (
        <div className="course-grid">
          {courses.data.items.map((course) => (
            <CourseCard course={course} key={course.id} />
          ))}
        </div>
      )}
    </section>
  )
}

export function Dashboard({ displayName }: { displayName: string }) {
  return (
    <div className="dashboard-page">
      <header className="dashboard-hero">
        <div>
          <p className="eyebrow">Your lecture workspace</p>
          <h1>{displayName}님, 오늘의 강의를 이어가세요.</h1>
          <p>
            Course마다 교수자와 학생 역할을 따로 확인하고 필요한 화면으로
            이동합니다.
          </p>
        </div>
        <div className="dashboard-actions" aria-label="Course 빠른 실행">
          <Link className="button button--primary" to="/courses/new">
            Course 만들기
          </Link>
          <Link className="button button--secondary" to="/courses/join">
            코드로 참여하기
          </Link>
        </div>
      </header>
      <CourseSection role="PROFESSOR" />
      <CourseSection role="STUDENT" />
    </div>
  )
}
