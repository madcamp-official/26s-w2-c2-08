import { NavLink } from 'react-router-dom'

const archiveLinks = [
  { path: 'materials', label: 'PDF 자료' },
  { path: 'transcripts', label: 'Transcript' },
  { path: 'summaries', label: 'AI 요약' },
  { path: 'qna', label: '질의응답' },
] as const

export function CourseSidebar() {
  return (
    <nav className="course-workspace-nav" aria-label="Course 기록 탐색">
      {archiveLinks.map((item) => (
        <NavLink
          className={({ isActive }) =>
            `course-workspace-nav__link${isActive ? ' course-workspace-nav__link--active' : ''}`
          }
          key={item.path}
          to={item.path}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}
