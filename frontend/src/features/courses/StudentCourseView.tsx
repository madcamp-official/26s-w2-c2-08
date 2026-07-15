import { Card } from '../../components/ui/Card'
import { LinkButton } from '../../components/ui/LinkButton'
import type { Course } from './api'
import { CurrentClassCard } from './CurrentClassCard'

const learningAccess = [
  {
    title: '실시간 수업',
    description: '진행 중 class의 Transcript를 읽고 익명 질문을 남깁니다.',
  },
  {
    title: '완료 기록',
    description: '수업이 끝난 뒤 PDF, Transcript, 요약과 답변을 확인합니다.',
  },
  {
    title: '개인 복습 AI',
    description: '선택한 class 기록을 근거로 나만의 복습 대화를 이어갑니다.',
  },
] as const

export function StudentCourseView({ course }: { course: Course }) {
  return (
    <div className="course-overview course-overview--student">
      <div className="course-overview__intro">
        <div>
          <p className="eyebrow">Student workspace</p>
          <h2>학생 학습 공간</h2>
          <p>
            현재 class 상태를 확인하고, 완료된 수업의 자료와 학습 기록을 한
            Course 안에서 이어서 살펴봅니다.
          </p>
        </div>
        <span className="course-overview__role-note">
          이 Course에서는 학생 권한
        </span>
      </div>

      <div className="course-overview__grid">
        <CurrentClassCard course={course} professor={false} />

        <Card
          as="aside"
          className="course-student-access"
          aria-labelledby="student-access-title"
        >
          <div>
            <p className="eyebrow">Learning access</p>
            <h2 id="student-access-title">학생이 이용할 수 있어요</h2>
          </div>
          <ol className="course-student-access__list">
            {learningAccess.map((item, index) => (
              <li key={item.title}>
                <span aria-hidden="true">{index + 1}</span>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <Card
        as="section"
        className="course-student-archive"
        aria-labelledby="student-archive-title"
      >
        <div>
          <p className="eyebrow">Course archive</p>
          <h2 id="student-archive-title">필요한 기록부터 열어보세요</h2>
          <p>
            자료, Transcript, AI 요약과 질의응답은 같은 Course 권한으로
            확인합니다.
          </p>
        </div>
        <div className="course-student-archive__actions">
          <LinkButton variant="secondary" to="materials">
            PDF 자료
          </LinkButton>
          <LinkButton variant="secondary" to="transcripts">
            Transcript
          </LinkButton>
          <LinkButton variant="secondary" to="summaries">
            AI 요약
          </LinkButton>
          <LinkButton variant="secondary" to="qna">
            질의응답
          </LinkButton>
        </div>
      </Card>
    </div>
  )
}
