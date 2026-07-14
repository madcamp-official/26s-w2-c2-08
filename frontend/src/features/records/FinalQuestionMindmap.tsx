import { useInfiniteQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
import {
  listFinalQuestionClusterMembers,
  listFinalQuestionClusters,
} from './api'
import { recordKeys } from './queries'

function clusteringCopy(status: string) {
  if (status === 'FAILED')
    return '최종 질문 분류를 완료하지 못했습니다. 기존 질문 목록은 계속 확인할 수 있습니다.'
  if (status === 'PENDING' || status === 'RUNNING')
    return '최종 질문 분류 결과를 준비하고 있습니다.'
  return null
}

export function FinalQuestionMindmap({ sessionId }: { sessionId: string }) {
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(
    null,
  )
  const clusters = useInfiniteQuery({
    queryKey: recordKeys.finalClusters(sessionId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listFinalQuestionClusters(sessionId, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor,
  })
  const clusterItems = useMemo(
    () => clusters.data?.pages.flatMap((page) => page.items) ?? [],
    [clusters.data],
  )
  const firstPage = clusters.data?.pages[0]

  const selectedCluster =
    clusterItems.find((cluster) => cluster.id === selectedClusterId) ?? null
  const members = useInfiniteQuery({
    queryKey: recordKeys.finalClusterMembers(
      sessionId,
      selectedCluster?.id ?? 'none',
    ),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listFinalQuestionClusterMembers(
        sessionId,
        selectedCluster!.id,
        pageParam,
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor,
    enabled: Boolean(selectedCluster),
  })
  const memberItems = members.data?.pages.flatMap((page) => page.items) ?? []
  const finalJob =
    firstPage?.clustering_state.last_job?.mode === 'FINAL'
      ? firstPage.clustering_state.last_job
      : null
  const stateCopy = firstPage && clusteringCopy(finalJob?.status ?? 'SUCCEEDED')

  return (
    <section
      className="panel final-mindmap"
      aria-labelledby="final-mindmap-title"
    >
      <header className="question-panel__heading">
        <div>
          <p className="eyebrow">Final question map</p>
          <h2 id="final-mindmap-title">최종 질문 마인드맵</h2>
          <p>
            후처리에서 확정된 분류만 표시하며, 수업 중 분류 결과와 섞지
            않습니다.
          </p>
        </div>
        {firstPage?.generation !== null &&
          firstPage?.generation !== undefined && (
            <span className="input-hint">
              generation {firstPage.generation}
            </span>
          )}
      </header>

      {stateCopy && (
        <p className="input-hint" role="status">
          {stateCopy}
        </p>
      )}
      {finalJob && (
        <p className="input-hint">
          마지막 최종 분류 · {finalJob.status} · {finalJob.attempt}번째 시도
        </p>
      )}
      {clusters.isPending && (
        <StatePanel kind="loading" title="최종 질문 분류를 불러오는 중" />
      )}
      {clusters.isError && (
        <StatePanel
          kind="error"
          title="최종 질문 분류를 불러오지 못했습니다"
          actionLabel="분류 다시 불러오기"
          onAction={() => void clusters.refetch()}
        />
      )}
      {clusters.data && clusterItems.length === 0 && (
        <StatePanel
          kind="empty"
          title="확정된 질문 분류가 없습니다"
          description="질문이 없거나 최종 분류 결과가 아직 준비되지 않았습니다."
        />
      )}
      {clusterItems.length > 0 && (
        <div className="final-mindmap__layout">
          <ol className="mindmap-clusters" aria-label="최종 Cluster 목록">
            {clusterItems.map((cluster) => (
              <li key={cluster.id}>
                <button
                  type="button"
                  aria-pressed={selectedCluster?.id === cluster.id}
                  aria-expanded={selectedCluster?.id === cluster.id}
                  aria-controls={`final-cluster-members-${cluster.id}`}
                  onClick={() => setSelectedClusterId(cluster.id)}
                >
                  <strong>{cluster.representative_question.content}</strong>
                  <span>
                    {cluster.member_count}개 질문 · 최초 generation{' '}
                    {cluster.representative_question.created_in_generation}
                  </span>
                </button>
              </li>
            ))}
          </ol>
          <div
            id={
              selectedCluster
                ? `final-cluster-members-${selectedCluster.id}`
                : undefined
            }
            className="mindmap-members"
            aria-live="polite"
          >
            {!selectedCluster && (
              <p className="input-hint">
                Cluster를 선택하면 포함된 질문을 표시합니다.
              </p>
            )}
            {selectedCluster?.finalized_at && (
              <p className="input-hint">
                최종 확정{' '}
                {new Date(selectedCluster.finalized_at).toLocaleString('ko-KR')}
              </p>
            )}
            {selectedCluster && members.isPending && <p>질문을 불러오는 중…</p>}
            {selectedCluster && members.isError && (
              <StatePanel
                kind="error"
                title="Cluster 질문을 불러오지 못했습니다"
                actionLabel="다시 불러오기"
                onAction={() => void members.refetch()}
              />
            )}
            {selectedCluster && memberItems.length > 0 && (
              <ol
                aria-label={`${selectedCluster.representative_question.content} Cluster 질문`}
              >
                {memberItems.map((member) => (
                  <li key={`${member.source_kind}-${member.ordinal}`}>
                    <strong>
                      {member.source_kind === 'STUDENT_QUESTION'
                        ? '학생 질문'
                        : '보존된 대표질문'}
                    </strong>
                    <span>
                      {member.source_kind === 'STUDENT_QUESTION'
                        ? member.question.content
                        : member.representative_question.content}
                    </span>
                  </li>
                ))}
              </ol>
            )}
            {selectedCluster && members.data && memberItems.length === 0 && (
              <p className="input-hint">이 Cluster에 표시할 질문이 없습니다.</p>
            )}
            {selectedCluster && members.hasNextPage && (
              <Button
                variant="secondary"
                disabled={members.isFetchingNextPage}
                onClick={() => void members.fetchNextPage()}
              >
                {members.isFetchingNextPage
                  ? '질문 불러오는 중…'
                  : 'Cluster 질문 더 보기'}
              </Button>
            )}
          </div>
        </div>
      )}
      {clusters.hasNextPage && (
        <Button
          variant="secondary"
          disabled={clusters.isFetchingNextPage}
          onClick={() => void clusters.fetchNextPage()}
        >
          {clusters.isFetchingNextPage
            ? '분류 불러오는 중…'
            : 'Cluster 더 보기'}
        </Button>
      )}
    </section>
  )
}
