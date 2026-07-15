import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'

import { ApiError } from '../../api/errors'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { LinkButton } from '../../components/ui/LinkButton'
import { Skeleton } from '../../components/ui/Skeleton'
import { currentUserQueryOptions } from '../../features/auth/queries'
import { Dashboard } from '../../features/courses/Dashboard'

export function FoundationPage() {
  const currentUser = useQuery(currentUserQueryOptions)
  const queryClient = useQueryClient()
  const [courseAuthenticationExpired, setCourseAuthenticationExpired] =
    useState(false)
  const unauthenticated =
    courseAuthenticationExpired ||
    (currentUser.error instanceof ApiError && currentUser.error.status === 401)
  const handleCourseAuthenticationExpired = useCallback(() => {
    setCourseAuthenticationExpired(true)
    queryClient.clear()
  }, [queryClient])

  if (currentUser.isSuccess && !courseAuthenticationExpired) {
    return (
      <Dashboard
        displayName={currentUser.data.display_name}
        onAuthenticationExpired={handleCourseAuthenticationExpired}
      />
    )
  }

  return (
    <div className="public-landing">
      <section className="public-hero" aria-labelledby="page-title">
        <div className="public-hero__copy">
          <p className="eyebrow">God Of All Lectures</p>
          <h1 className="page-title" id="page-title">
            강의의 흐름을 놓치지 않도록
          </h1>
          <p className="page-description">
            실시간 Transcript부터 익명 질문, 개인 AI와 수업 기록까지. 수업의
            맥락을 한곳에서 이어 갑니다.
          </p>

          <div className="public-hero__actions">
            {unauthenticated && (
              <>
                <LinkButton to="/login?return_to=/">
                  로그인하고 시작하기
                </LinkButton>
                <LinkButton to="/signup?return_to=/" variant="secondary">
                  이메일로 가입하기
                </LinkButton>
              </>
            )}
            {currentUser.isPending && !courseAuthenticationExpired && (
              <div className="public-session-status">
                <Skeleton label="로그인 상태 확인 중" lines={1} />
              </div>
            )}
            {currentUser.isError && !unauthenticated && (
              <div className="public-session-error" role="alert">
                <p>로그인 상태를 확인하지 못했습니다.</p>
                <Button
                  variant="secondary"
                  onClick={() => void currentUser.refetch()}
                >
                  다시 확인
                </Button>
              </div>
            )}
          </div>
        </div>

        <Card
          as="aside"
          className="lecture-flow-preview"
          elevated
          aria-labelledby="preview-title"
        >
          <header className="lecture-flow-preview__header">
            <div>
              <p className="eyebrow">Lecture workspace</p>
              <h2 id="preview-title">
                하나의 강의,
                <br />
                이어지는 학습 흐름
              </h2>
            </div>
            <span className="status-chip status-chip--success">LIVE</span>
          </header>

          <section
            className="transcript-preview"
            aria-labelledby="transcript-preview-title"
          >
            <div className="public-preview-heading">
              <h3 id="transcript-preview-title">실시간 Transcript</h3>
              <span>수업 맥락</span>
            </div>
            <div className="transcript-preview__line">
              <span aria-hidden="true">10:24</span>
              <p>교수자의 설명이 시간 순서대로 기록됩니다.</p>
            </div>
            <div className="transcript-preview__line transcript-preview__line--partial">
              <span aria-hidden="true">10:25</span>
              <p>임시 인식 중 · 저장 전</p>
            </div>
          </section>

          <div className="learning-assist-preview">
            <section aria-labelledby="question-preview-title">
              <span
                className="learning-assist-preview__icon"
                aria-hidden="true"
              >
                ?
              </span>
              <div>
                <h3 id="question-preview-title">익명 질문</h3>
                <p>이름 노출 없이 질문하고 강의 맥락을 함께 확인합니다.</p>
              </div>
            </section>
            <section aria-labelledby="ai-preview-title">
              <span
                className="learning-assist-preview__icon"
                aria-hidden="true"
              >
                AI
              </span>
              <div>
                <h3 id="ai-preview-title">개인 AI</h3>
                <p>내 학습을 돕되 강의 참여와 기록 열람을 막지 않습니다.</p>
              </div>
            </section>
          </div>
        </Card>
      </section>

      <section className="learning-values" aria-labelledby="value-title">
        <header className="public-section-heading">
          <p className="eyebrow">A continuous learning loop</p>
          <h2 id="value-title">수업 전후의 맥락을 한곳에 모읍니다</h2>
          <p>
            강의 참여부터 이해 확인, 복습까지 필요한 정보에 바로 접근하세요.
          </p>
        </header>
        <div className="learning-values__grid">
          <Card as="article" className="learning-value-card">
            <span>01</span>
            <h3>수업 중 맥락 확인</h3>
            <p>실시간 Transcript로 놓친 설명을 빠르게 되짚습니다.</p>
          </Card>
          <Card as="article" className="learning-value-card">
            <span>02</span>
            <h3>질문과 학습 지원</h3>
            <p>익명 질문과 개인 AI를 서로 독립된 도구로 활용합니다.</p>
          </Card>
          <Card as="article" className="learning-value-card">
            <span>03</span>
            <h3>수업 후 복습</h3>
            <p>확정된 기록과 질문을 Course 안에서 다시 찾아봅니다.</p>
          </Card>
        </div>
      </section>
    </div>
  )
}
