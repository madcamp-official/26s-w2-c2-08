import type { components } from '../../api/generated/schema'
import type { RealtimeConnectionState } from '../../features/realtime/client'
import { Status, type StatusTone } from '../ui/Status'

type CourseRole = components['schemas']['CourseRole']
type SessionStatus = components['schemas']['LectureSessionStatus']
type JobStatus = components['schemas']['AIJobStatus']

const sessionStatusCopy: Record<
  SessionStatus,
  { label: string; tone: StatusTone }
> = {
  READY: { label: '시작 전', tone: 'info' },
  LIVE: { label: '진행 중', tone: 'danger' },
  PROCESSING: { label: '기록 정리 중', tone: 'warning' },
  COMPLETED: { label: '완료', tone: 'success' },
}

const jobStatusCopy: Record<JobStatus, { label: string; tone: StatusTone }> = {
  PENDING: { label: '대기 중', tone: 'neutral' },
  RUNNING: { label: '처리 중', tone: 'info' },
  SUCCEEDED: { label: '완료', tone: 'success' },
  FAILED: { label: '실패', tone: 'danger' },
  CANCELLED: { label: '취소됨', tone: 'neutral' },
  SUPERSEDED: { label: '새 작업으로 대체됨', tone: 'neutral' },
}

const connectionStatusCopy: Record<
  RealtimeConnectionState,
  { label: string; tone: StatusTone }
> = {
  connecting: { label: '실시간 연결 중', tone: 'info' },
  connected: { label: '실시간 연결됨', tone: 'success' },
  reconnecting: { label: '연결 복구 중', tone: 'warning' },
  stopped: { label: '실시간 연결 종료', tone: 'neutral' },
}

export function CourseRoleBadge({ role }: { role: CourseRole }) {
  return (
    <Status
      data-course-role={role}
      tone={role === 'PROFESSOR' ? 'info' : 'neutral'}
    >
      {role === 'PROFESSOR' ? '교수자' : '학생'}
    </Status>
  )
}

export function SessionStatusBadge({ status }: { status: SessionStatus }) {
  const copy = sessionStatusCopy[status]
  return (
    <Status data-session-status={status} tone={copy.tone}>
      {copy.label}
    </Status>
  )
}

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const copy = jobStatusCopy[status]
  return (
    <Status data-job-status={status} tone={copy.tone}>
      {copy.label}
    </Status>
  )
}

export function ConnectionStatus({
  state,
}: {
  state: RealtimeConnectionState
}) {
  const copy = connectionStatusCopy[state]
  return (
    <Status aria-live="polite" data-connection-state={state} tone={copy.tone}>
      {copy.label}
    </Status>
  )
}
