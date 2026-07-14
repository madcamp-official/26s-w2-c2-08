import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { logoutCurrentSession } from './api'
import { currentUserQueryKey, currentUserQueryOptions } from './queries'

export function AccountPage() {
  const currentUser = useQuery(currentUserQueryOptions)
  const queryClient = useQueryClient()
  const location = useLocation()
  const { showToast } = useToast()
  const [logoutOpen, setLogoutOpen] = useState(false)
  const [logoutCompleted, setLogoutCompleted] = useState(false)
  const logout = useMutation({
    mutationFn: logoutCurrentSession,
    onSuccess: () => {
      setLogoutCompleted(true)
      queryClient.removeQueries({ queryKey: currentUserQueryKey })
      setLogoutOpen(false)
    },
    onError: () => {
      showToast({
        tone: 'error',
        message: '로그아웃하지 못했습니다. 현재 Session은 그대로 유지됩니다.',
      })
    },
  })

  if (logoutCompleted) {
    return <Navigate replace to="/login?logged_out=1" />
  }

  if (currentUser.isPending) {
    return (
      <StatePanel
        kind="loading"
        title="내 정보를 불러오는 중"
        description="서버 Session과 기본 프로필을 확인하고 있습니다."
      />
    )
  }

  if (
    currentUser.error instanceof ApiError &&
    currentUser.error.status === 401
  ) {
    const returnTo = `${location.pathname}${location.search}${location.hash}`
    return (
      <Navigate
        replace
        to={`/login?return_to=${encodeURIComponent(returnTo)}`}
      />
    )
  }

  if (currentUser.isError) {
    return (
      <StatePanel
        kind="error"
        title="내 정보를 불러오지 못했습니다"
        description="계정 정보를 숨긴 상태입니다. 잠시 후 다시 시도해 주세요."
        actionLabel="다시 시도"
        onAction={() => void currentUser.refetch()}
      />
    )
  }

  const user = currentUser.data
  return (
    <section className="account-page" aria-labelledby="account-title">
      <header className="account-heading">
        <div>
          <p className="eyebrow">Account</p>
          <h1 id="account-title">내 정보</h1>
          <p>기본 정보와 현재 GOAL 로그인 Session을 확인합니다.</p>
        </div>
      </header>

      <div className="account-layout">
        <article className="panel profile-card">
          <div className="profile-card__identity">
            {user.avatar_url ? (
              <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" />
            ) : (
              <span className="profile-card__fallback" aria-hidden="true">
                {user.display_name.slice(0, 1)}
              </span>
            )}
            <div>
              <span className="status-chip status-chip--success">인증됨</span>
              <h2>{user.display_name}</h2>
              <p>{user.email ?? '공개된 이메일 없음'}</p>
            </div>
          </div>
          <dl className="account-details">
            <div>
              <dt>로그인 방식</dt>
              <dd>GOAL 서버 Session</dd>
            </div>
            <div>
              <dt>계정 역할</dt>
              <dd>고정 역할 없음 · Course별 역할 사용</dd>
            </div>
          </dl>
        </article>

        <aside className="panel account-security">
          <div>
            <p className="eyebrow">Security</p>
            <h2>로그인 Session</h2>
            <p>공용 기기에서는 이용 후 반드시 로그아웃하세요.</p>
          </div>
          <Button variant="danger" onClick={() => setLogoutOpen(true)}>
            로그아웃
          </Button>
        </aside>
      </div>

      <Dialog
        open={logoutOpen}
        title="GOAL에서 로그아웃할까요?"
        description="서버 Session을 폐기하고 이 브라우저의 Cookie를 만료합니다."
        onOpenChange={setLogoutOpen}
        actions={
          <>
            <Button
              variant="secondary"
              disabled={logout.isPending}
              onClick={() => setLogoutOpen(false)}
            >
              취소
            </Button>
            <Button
              variant="danger"
              disabled={logout.isPending}
              onClick={() => logout.mutate()}
            >
              {logout.isPending ? '로그아웃 중…' : '로그아웃'}
            </Button>
          </>
        }
      >
        <p>다시 이용하려면 Google 또는 이메일로 로그인해야 합니다.</p>
      </Dialog>
    </section>
  )
}
