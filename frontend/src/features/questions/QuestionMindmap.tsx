import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
import { listQuestionClusterMembers, listQuestionClusters } from './api'
import { questionKeys } from './queries'
import type { AnswerTarget } from '../answers/api'

interface QuestionMindmapProps {
  sessionId: string
  onStartVoiceAnswer?: (target: AnswerTarget) => void
  answerCapturePending?: boolean
}

function clusteringStatus(
  state: Awaited<ReturnType<typeof listQuestionClusters>>['clustering_state'],
) {
  if (state.retry_job_id) return '분류 재시도 예약됨'
  if (state.active_job_id && state.last_job?.status === 'RUNNING')
    return '새 질문을 분류하는 중'
  if (state.pending) return '새 질문을 분류 대기 중'
  if (state.last_job?.status === 'FAILED') return '최근 분류에 실패했습니다'
  return '현재 질문 분류 결과'
}

export function QuestionMindmap({
  sessionId,
  onStartVoiceAnswer,
  answerCapturePending = false,
}: QuestionMindmapProps) {
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(
    null,
  )
  const clusters = useQuery({
    queryKey: questionKeys.clusters(sessionId),
    queryFn: ({ signal }) => listQuestionClusters(sessionId, signal),
  })

  const activeClusterId =
    selectedClusterId ?? clusters.data?.items[0]?.id ?? null

  const members = useQuery({
    queryKey: questionKeys.clusterMembers(sessionId, activeClusterId ?? ''),
    queryFn: ({ signal }) =>
      listQuestionClusterMembers(sessionId, activeClusterId ?? '', signal),
    enabled: Boolean(activeClusterId),
  })

  if (clusters.isPending) {
    return <StatePanel kind="loading" title="질문 마인드맵을 불러오는 중" />
  }
  if (clusters.isError) {
    return (
      <StatePanel kind="error" title="질문 마인드맵을 불러오지 못했습니다" />
    )
  }

  const state = clusters.data.clustering_state
  return (
    <section className="panel question-mindmap" aria-labelledby="mindmap-title">
      <header className="question-panel__heading">
        <div>
          <p className="eyebrow">Question map</p>
          <h2 id="mindmap-title">질문 마인드맵</h2>
          <p>
            AI 대표질문을 중심으로 익명 질문을 묶어 보여줍니다. 질문 원문은 별도
            목록에서도 그대로 확인할 수 있습니다.
          </p>
        </div>
        <span className="input-hint">{clusteringStatus(state)}</span>
      </header>

      <p className="question-mindmap__meta" aria-live="polite">
        generation {clusters.data.generation ?? '-'} · revision{' '}
        {state.current_revision}
        {state.last_job &&
          ` · 최근 Job ${state.last_job.status} (시도 ${state.last_job.attempt})`}
      </p>

      {clusters.data.items.length === 0 ? (
        <StatePanel
          kind="empty"
          title="아직 묶인 질문이 없습니다"
          description={
            state.pending
              ? '질문 저장은 완료되었습니다. 분류 결과가 준비되면 자동으로 표시됩니다.'
              : '수업 중 질문이 등록되면 AI가 마인드맵을 만듭니다.'
          }
        />
      ) : (
        <div className="question-mindmap__content">
          <ol
            className="question-mindmap__clusters"
            aria-label="AI 대표질문 목록"
          >
            {clusters.data.items.map((cluster) => (
              <li key={cluster.id}>
                <Button
                  variant={
                    activeClusterId === cluster.id ? 'secondary' : 'ghost'
                  }
                  aria-pressed={activeClusterId === cluster.id}
                  onClick={() => setSelectedClusterId(cluster.id)}
                >
                  <span>{cluster.representative_question.content}</span>
                  <small>{cluster.member_count}개 질문</small>
                </Button>
                {onStartVoiceAnswer && (
                  <Button
                    variant="ghost"
                    disabled={answerCapturePending}
                    onClick={() =>
                      onStartVoiceAnswer({
                        type: 'AI_REPRESENTATIVE_QUESTION',
                        representative_question_id:
                          cluster.representative_question.id,
                      })
                    }
                  >
                    대표질문 답변 시작
                  </Button>
                )}
              </li>
            ))}
          </ol>
          <div className="question-mindmap__members" aria-live="polite">
            {members.isPending && <p>질문 연결을 불러오는 중…</p>}
            {members.isError && (
              <p className="form-error">질문 연결을 불러오지 못했습니다.</p>
            )}
            {members.data && (
              <ol aria-label="선택한 대표질문의 연결 질문">
                {members.data.items.map((member) => (
                  <li key={`${member.source_kind}-${member.ordinal}`}>
                    {member.source_kind === 'STUDENT_QUESTION' ? (
                      <>
                        <span className="badge">학생 질문</span>
                        <p>{member.question.content}</p>
                      </>
                    ) : (
                      <>
                        <span className="badge">보존된 AI 대표질문</span>
                        <p>{member.representative_question.content}</p>
                      </>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
