import { LinkButton } from '../../components/ui/LinkButton'
import { Card } from '../../components/ui/Card'
import { SessionStatusBadge } from '../../components/domain/LmsStatus'
import type { Course } from './api'

function sessionDescription(
  status?: NonNullable<Course['current_session']>['status'],
) {
  switch (status) {
    case 'READY':
      return '수업 자료와 제목을 확인하고 시작을 준비하는 단계입니다.'
    case 'LIVE':
      return '실시간 Transcript와 질문이 열려 있는 진행 중 class입니다.'
    case 'PROCESSING':
      return '수업은 끝났고 Transcript와 최종 기록을 정리하고 있습니다.'
    case 'COMPLETED':
      return '수업 기록 정리가 끝나 완료 기록을 확인할 수 있습니다.'
    default:
      return '현재 진행 중인 class가 없습니다.'
  }
}

function actionLabel(status: NonNullable<Course['current_session']>['status']) {
  switch (status) {
    case 'READY':
      return 'class 준비 계속하기'
    case 'LIVE':
      return '실시간 class 입장'
    case 'PROCESSING':
      return '정리 상태 보기'
    case 'COMPLETED':
      return '완료 기록 보기'
  }
}

interface CurrentClassCardProps {
  course: Course
  professor: boolean
}

export function CurrentClassCard({ course, professor }: CurrentClassCardProps) {
  const currentSession = course.current_session
  const studentWaiting = !professor && currentSession?.status === 'READY'

  return (
    <Card
      as="section"
      className="course-current-card"
      elevated
      aria-labelledby="current-session-title"
    >
      <div className="course-current-card__heading">
        <div>
          <p className="eyebrow">Current class</p>
          <h2 id="current-session-title">현재 class</h2>
        </div>
        {currentSession ? (
          <SessionStatusBadge status={currentSession.status} />
        ) : (
          <span className="course-current-card__empty-status">진행 없음</span>
        )}
      </div>

      {currentSession ? (
        <div className="course-current-card__body">
          <div>
            <h3>{currentSession.title}</h3>
            <p>{sessionDescription(currentSession.status)}</p>
          </div>
          <dl className="course-current-card__meta">
            <div>
              <dt>수업 날짜</dt>
              <dd>{currentSession.lecture_date}</dd>
            </div>
            <div>
              <dt>현재 상태</dt>
              <dd>
                {currentSession.status === 'READY'
                  ? '교수자 시작 대기'
                  : currentSession.status === 'LIVE'
                    ? '실시간 진행 중'
                    : currentSession.status === 'PROCESSING'
                      ? '기록 정리 중'
                      : '기록 완료'}
              </dd>
            </div>
          </dl>
        </div>
      ) : (
        <div className="course-current-card__empty">
          <strong>
            {professor
              ? '다음 class를 만들 수 있습니다.'
              : '교수자가 class를 열면 여기에 표시됩니다.'}
          </strong>
          <p>{sessionDescription()}</p>
        </div>
      )}

      <footer className="course-current-card__footer">
        {currentSession && !studentWaiting ? (
          <LinkButton to={`/sessions/${currentSession.id}`}>
            {actionLabel(currentSession.status)}
          </LinkButton>
        ) : currentSession && studentWaiting ? (
          <p className="course-current-card__waiting" role="status">
            별도 동작 없이 기다려 주세요. 시작되면 입장 동작이 열립니다.
          </p>
        ) : professor ? (
          <LinkButton to={`/courses/${course.id}/sessions/new`}>
            새 class 만들기
          </LinkButton>
        ) : (
          <p className="course-current-card__waiting" role="status">
            이 영역은 Course 상태가 바뀌면 자동으로 갱신됩니다.
          </p>
        )}
      </footer>
    </Card>
  )
}
