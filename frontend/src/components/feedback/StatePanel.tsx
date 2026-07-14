import { Button } from '../ui/Button'

export type StatePanelKind =
  | 'loading'
  | 'empty'
  | 'error'
  | 'unauthorized'
  | 'forbidden'
  | 'not-found'
  | 'conflict'
  | 'validation'

interface StateCopy {
  icon: string
  title: string
  description: string
}

const stateCopy: Record<StatePanelKind, StateCopy> = {
  loading: {
    icon: '…',
    title: '불러오는 중입니다',
    description: '잠시만 기다려 주세요.',
  },
  empty: {
    icon: '＋',
    title: '아직 표시할 내용이 없습니다',
    description: '새 내용을 만들거나 잠시 후 다시 확인해 주세요.',
  },
  error: {
    icon: '!',
    title: '정보를 불러오지 못했습니다',
    description: '네트워크 연결을 확인하고 다시 시도해 주세요.',
  },
  unauthorized: {
    icon: '→',
    title: '로그인이 필요합니다',
    description: '로그인한 뒤 다시 이용해 주세요.',
  },
  forbidden: {
    icon: '×',
    title: '접근 권한이 없습니다',
    description: 'Course에서 부여된 역할과 접근 권한을 확인해 주세요.',
  },
  'not-found': {
    icon: '?',
    title: '요청한 페이지를 찾을 수 없습니다',
    description: '주소가 올바른지 확인하거나 홈으로 이동해 주세요.',
  },
  conflict: {
    icon: '↻',
    title: '현재 상태가 변경되었습니다',
    description: '최신 정보를 확인한 뒤 다시 시도해 주세요.',
  },
  validation: {
    icon: '!',
    title: '입력 내용을 확인해 주세요',
    description: '표시된 항목을 수정한 뒤 다시 시도해 주세요.',
  },
}

interface StatePanelProps {
  kind: StatePanelKind
  title?: string
  description?: string
  actionLabel?: string
  onAction?: () => void
}

export function StatePanel({
  kind,
  title,
  description,
  actionLabel,
  onAction,
}: StatePanelProps) {
  const copy = stateCopy[kind]
  const isAlert = kind !== 'loading' && kind !== 'empty'

  return (
    <section
      className="state-panel"
      role={isAlert ? 'alert' : 'status'}
      aria-busy={kind === 'loading'}
    >
      <div className="state-panel__content">
        <span className="state-panel__icon" aria-hidden="true">
          {copy.icon}
        </span>
        <h2>{title ?? copy.title}</h2>
        <p>{description ?? copy.description}</p>
        {actionLabel && onAction && (
          <Button onClick={onAction}>{actionLabel}</Button>
        )}
      </div>
    </section>
  )
}
