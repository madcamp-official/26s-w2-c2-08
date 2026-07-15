import type { ReactNode } from 'react'

import type { Course, LectureSession } from '../courses/api'
import { EndedClassLayout } from './EndedClassLayout'

interface StudentEndedClassViewProps {
  course: Course
  refreshWarning?: ReactNode
  session: LectureSession
}

export function StudentEndedClassView({
  course,
  refreshWarning,
  session,
}: StudentEndedClassViewProps) {
  return (
    <EndedClassLayout
      course={course}
      professor={false}
      refreshWarning={refreshWarning}
      screenId="ENDED_CLASS_PAGE_STUD"
      session={session}
    />
  )
}
