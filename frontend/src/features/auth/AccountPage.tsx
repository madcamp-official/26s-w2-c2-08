import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { CourseRoleBadge } from '../../components/domain/LmsStatus'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Dialog } from '../../components/ui/Dialog'
import { LinkButton } from '../../components/ui/LinkButton'
import { Skeleton } from '../../components/ui/Skeleton'
import { Status } from '../../components/ui/Status'
import { courseListQueryOptions } from '../courses/queries'
import { logoutCurrentSession, withdrawCurrentUser } from './api'
import { currentUserQueryOptions } from './queries'

type CourseRole = 'PROFESSOR' | 'STUDENT'

function useAccountCourseList(role: CourseRole, enabled: boolean) {
  return useQuery({ ...courseListQueryOptions(role), enabled })
}

type AccountCourseQuery = ReturnType<typeof useAccountCourseList>

function courseCountCopy(query: AccountCourseQuery) {
  if (!query.isSuccess) return { accessible: '확인 중', visible: '—' }
  const count = query.data.items.length
  const hasMore = query.data.next_cursor !== null
  return {
    accessible: hasMore ? `${count}개 이상` : `${count}개`,
    visible: `${count}${hasMore ? '+' : ''}`,
  }
}

function AccountCourseRoleCard({
  query,
  role,
}: {
  query: AccountCourseQuery
  role: CourseRole
}) {
  const professor = role === 'PROFESSOR'
  const count = courseCountCopy(query)
  const title = professor ? '관리 중인 Course' : '참여 중인 Course'

  return (
    <Card
      as="article"
      className="account-course-role"
      aria-busy={query.isPending}
    >
      <header>
        <CourseRoleBadge role={role} />
        <span className="account-course-role__label">{title}</span>
      </header>

      {query.isPending && (
        <Skeleton label={`${title} 개수를 불러오는 중`} lines={2} />
      )}

      {query.isError && (
        <div className="account-course-role__error" role="alert">
          <strong>개수를 확인하지 못했습니다</strong>
          <p>다른 계정 정보는 계속 확인할 수 있습니다.</p>
          <Button variant="secondary" onClick={() => void query.refetch()}>
            다시 확인
          </Button>
        </div>
      )}

      {query.isSuccess && (
        <div className="account-course-role__count">
          <strong aria-label={`${title} ${count.accessible}`}>
            {count.visible}
          </strong>
          <span>Course</span>
          <p>
            {query.data.items.length === 0
              ? professor
                ? '아직 관리 중인 Course가 없습니다.'
                : '아직 참여 중인 Course가 없습니다.'
              : professor
                ? 'Course별 교수자 권한으로 관리합니다.'
                : 'Course별 학생 권한으로 참여합니다.'}
          </p>
        </div>
      )}
    </Card>
  )
}

export function AccountPage() {
  const currentUser = useQuery(currentUserQueryOptions)
  const professorCourses = useAccountCourseList(
    'PROFESSOR',
    currentUser.isSuccess,
  )
  const studentCourses = useAccountCourseList('STUDENT', currentUser.isSuccess)
  const queryClient = useQueryClient()
  const location = useLocation()
  const { showToast } = useToast()
  const [logoutOpen, setLogoutOpen] = useState(false)
  const [withdrawOpen, setWithdrawOpen] = useState(false)
  const [logoutCompleted, setLogoutCompleted] = useState(false)
  const [withdrawCompleted, setWithdrawCompleted] = useState(false)
  const [withdrawError, setWithdrawError] = useState<string | null>(null)
  const logout = useMutation({
    mutationFn: logoutCurrentSession,
    onSuccess: () => {
      setLogoutCompleted(true)
      setLogoutOpen(false)
      queryClient.clear()
    },
    onError: () => {
      showToast({
        tone: 'error',
        message: '로그아웃하지 못했습니다. 현재 Session은 그대로 유지됩니다.',
      })
    },
  })
  const withdraw = useMutation({
    mutationFn: withdrawCurrentUser,
    onMutate: () => setWithdrawError(null),
    onSuccess: () => {
      setWithdrawCompleted(true)
      setWithdrawOpen(false)
      queryClient.clear()
    },
    onError: (error) => {
      const message =
        error instanceof ApiError &&
        error.code === 'OWNED_COURSE_REQUIRES_DELETION'
          ? '생성한 Course를 먼저 삭제한 뒤 계정을 탈퇴할 수 있습니다.'
          : '계정을 탈퇴하지 못했습니다. 현재 Session은 그대로 유지됩니다.'
      setWithdrawError(message)
      showToast({ tone: 'error', message })
    },
  })

  if (logoutCompleted) {
    return <Navigate replace to="/login?logged_out=1" />
  }
  if (withdrawCompleted) {
    return <Navigate replace to="/login?withdrawn=1" />
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
  const hasOwnedCourse =
    professorCourses.isSuccess && professorCourses.data.items.length > 0
  const ownerCheckUnavailable =
    professorCourses.isPending || professorCourses.isError

  return (
    <section className="account-page">
      <PageHeader
        eyebrow="Account"
        title="내 정보"
        description={
          <p>
            기본 계정 정보와 Course별 역할을 확인하고 현재 Session을 안전하게
            관리합니다.
          </p>
        }
        actions={
          <LinkButton to="/" variant="secondary">
            대시보드로 돌아가기
          </LinkButton>
        }
      />

      <div className="account-primary-grid">
        <Card as="article" className="profile-card" elevated>
          <div className="profile-card__identity">
            {user.avatar_url ? (
              <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" />
            ) : (
              <span className="profile-card__fallback" aria-hidden="true">
                {user.display_name.slice(0, 1)}
              </span>
            )}
            <div>
              <Status tone="success">인증됨</Status>
              <h2>{user.display_name}</h2>
              <p>{user.email ?? '공개된 이메일 없음'}</p>
            </div>
          </div>
        </Card>

        <Card
          as="section"
          className="account-course-summary"
          elevated
          aria-labelledby="account-course-title"
        >
          <header className="account-section-heading">
            <div>
              <p className="eyebrow">Course roles</p>
              <h2 id="account-course-title">Course별 역할</h2>
            </div>
            <LinkButton to="/" variant="secondary">
              전체 Course 보기
            </LinkButton>
          </header>
          <p className="account-section-description">
            교수자·학생 역할은 계정 전체가 아니라 각 Course에서 따로 정해집니다.
          </p>
          <div className="account-course-summary__grid">
            <AccountCourseRoleCard query={professorCourses} role="PROFESSOR" />
            <AccountCourseRoleCard query={studentCourses} role="STUDENT" />
          </div>
        </Card>
      </div>

      <div className="account-management-grid">
        <Card as="section" className="account-security">
          <div>
            <p className="eyebrow">Session security</p>
            <h2>로그인 Session</h2>
            <p>공용 기기에서는 이용 후 반드시 로그아웃하세요.</p>
          </div>
          <Button variant="danger" onClick={() => setLogoutOpen(true)}>
            로그아웃
          </Button>
        </Card>

        <Card as="section" className="account-danger-zone">
          <div>
            <p className="eyebrow">Account removal</p>
            <h2>계정 탈퇴</h2>
            <p>
              직접 만든 Course를 모두 삭제한 뒤에만 계정을 영구적으로 탈퇴할 수
              있습니다.
            </p>
          </div>
          <Button
            variant="secondary"
            onClick={() => {
              setWithdrawError(null)
              withdraw.reset()
              setWithdrawOpen(true)
            }}
          >
            계정 탈퇴 검토
          </Button>
        </Card>
      </div>

      <Dialog
        open={logoutOpen}
        title="GOAL에서 로그아웃할까요?"
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

      <Dialog
        open={withdrawOpen}
        title="GOAL 계정을 탈퇴할까요?"
        description="탈퇴 후에는 현재 Session이 종료되며 계정을 복구할 수 없습니다."
        onOpenChange={setWithdrawOpen}
        actions={
          <>
            <Button
              variant="secondary"
              disabled={withdraw.isPending}
              onClick={() => setWithdrawOpen(false)}
            >
              취소
            </Button>
            {hasOwnedCourse && (
              <LinkButton to="/" variant="secondary">
                관리 Course 확인
              </LinkButton>
            )}
            <Button
              variant="danger"
              disabled={
                ownerCheckUnavailable || hasOwnedCourse || withdraw.isPending
              }
              onClick={() => withdraw.mutate()}
            >
              {withdraw.isPending ? '탈퇴 중…' : '계정 탈퇴'}
            </Button>
          </>
        }
      >
        <div className="withdraw-review">
          {professorCourses.isPending && (
            <div className="withdraw-review__notice" role="status">
              <strong>관리 Course를 확인하고 있습니다</strong>
              <p>확인이 끝난 뒤 탈퇴 가능 여부를 안내합니다.</p>
            </div>
          )}
          {professorCourses.isError && (
            <div className="withdraw-review__notice" role="alert">
              <strong>관리 Course를 확인하지 못했습니다</strong>
              <p>확인되지 않은 상태에서는 계정 탈퇴를 진행하지 않습니다.</p>
              <Button
                variant="secondary"
                onClick={() => void professorCourses.refetch()}
              >
                관리 Course 다시 확인
              </Button>
            </div>
          )}
          {hasOwnedCourse && (
            <div
              className="withdraw-review__notice withdraw-review__notice--danger"
              role="alert"
            >
              <strong>관리 중인 Course가 남아 있습니다</strong>
              <p>생성한 Course를 먼저 삭제한 뒤 계정을 탈퇴할 수 있습니다.</p>
            </div>
          )}
          {withdrawError && (
            <div
              className="withdraw-review__notice withdraw-review__notice--danger"
              role="alert"
            >
              <strong>탈퇴를 완료하지 못했습니다</strong>
              <p>{withdrawError}</p>
            </div>
          )}
        </div>
      </Dialog>
    </section>
  )
}
