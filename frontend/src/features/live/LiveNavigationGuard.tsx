import { useBlocker } from 'react-router-dom'

import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'

export function LiveNavigationGuard({ active }: { active: boolean }) {
  const blocker = useBlocker(active)

  return (
    <Dialog
      open={blocker.state === 'blocked'}
      title="LIVE 수업 화면을 나갈까요?"
      description="실시간 음성 전송이 중단되고 진행 중인 로컬 녹음 마감을 시작합니다. 수업 자체는 종료되지 않습니다."
      onOpenChange={(open) => {
        if (!open && blocker.state === 'blocked') blocker.reset()
      }}
      actions={
        <>
          <Button
            variant="secondary"
            onClick={() => {
              if (blocker.state === 'blocked') blocker.reset()
            }}
          >
            화면에 머무르기
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              if (blocker.state === 'blocked') blocker.proceed()
            }}
          >
            전송을 중단하고 이동
          </Button>
        </>
      }
    >
      <p className="input-hint">
        수업을 끝내려면 이 창을 닫고 Header의 ‘수업 종료’를 사용하세요.
      </p>
    </Dialog>
  )
}
