import { Link, useOutletContext, useParams } from 'react-router-dom'

import type { CourseWorkspaceContextValue } from '../course-workspace/context'
import { CurrentClassCard } from './CurrentClassCard'
import { ProfessorCourseView } from './ProfessorCourseView'

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
  const { course: courseData } = useOutletContext<CourseWorkspaceContextValue>()

  if (courseData.role === 'PROFESSOR') {
    return <ProfessorCourseView course={courseData} />
  }

  const [sessionState, sessionDescription] = sessionCopy(
    courseData.current_session?.status,
  )

  return (
    <div className="course-detail-page">
      <div className="course-detail-grid">
        <CurrentClassCard course={courseData} professor={false} />
        <aside
          className="panel student-course-note"
          aria-labelledby="student-role-title"
        >
          <p className="eyebrow">Student</p>
          <h2 id="student-role-title">학생 Course</h2>
          <p>{sessionState}</p>
          <p>{sessionDescription}</p>
          <Link
            className="button button--ghost"
            to={`/courses/${courseId}/materials`}
          >
            Course 자료 보기
          </Link>
        </aside>
      </div>
    </div>
  )
}
