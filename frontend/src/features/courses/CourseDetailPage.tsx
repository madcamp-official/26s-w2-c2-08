import { useOutletContext } from 'react-router-dom'

import type { CourseWorkspaceContextValue } from '../course-workspace/context'
import { ProfessorCourseView } from './ProfessorCourseView'
import { StudentCourseView } from './StudentCourseView'

export function CourseDetailPage() {
  const { course: courseData } = useOutletContext<CourseWorkspaceContextValue>()

  if (courseData.role === 'PROFESSOR') {
    return <ProfessorCourseView course={courseData} />
  }

  return <StudentCourseView course={courseData} />
}
