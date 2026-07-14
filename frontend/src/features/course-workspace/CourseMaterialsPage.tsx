import { useInfiniteQuery } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'

import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
import type { CourseWorkspaceContextValue } from './context'
import { courseMaterialsInfiniteQueryOptions } from './queries'

const materialStatusCopy = {
  UPLOADED: '처리 대기',
  PROCESSING: '처리 중',
  READY: '사용 가능',
  FAILED: '처리 실패',
} as const

function hasMaterialUrls(item: object): item is {
  content_url: string
  download_url: string
} {
  return (
    'content_url' in item &&
    typeof item.content_url === 'string' &&
    'download_url' in item &&
    typeof item.download_url === 'string'
  )
}

export function CourseMaterialsPage() {
  const { course } = useOutletContext<CourseWorkspaceContextValue>()
  const materials = useInfiniteQuery(
    courseMaterialsInfiniteQueryOptions(course.id),
  )
  const items = materials.data?.pages.flatMap((page) => page.items) ?? []

  if (materials.isPending) {
    return <StatePanel kind="loading" title="PDF 자료를 모으는 중" />
  }

  if (materials.isError && items.length === 0) {
    return (
      <StatePanel
        kind="error"
        title="PDF 자료를 불러오지 못했습니다"
        description="Course와 class 목록은 유지됩니다. 자료 영역만 다시 시도해 주세요."
        actionLabel="다시 시도"
        onAction={() => void materials.refetch()}
      />
    )
  }

  return (
    <section className="course-archive-page" aria-labelledby="materials-title">
      <header className="course-archive-heading">
        <div>
          <p className="eyebrow">Course archive</p>
          <h2 id="materials-title">모든 class의 PDF 자료</h2>
          <p>
            현재 class와 지난 class에 연결된 PDF를 열거나 개별 다운로드할 수
            있습니다.
          </p>
        </div>
        <span className="badge">{items.length}개 표시</span>
      </header>

      {items.length === 0 ? (
        <StatePanel
          kind="empty"
          title="연결된 PDF 자료가 없습니다"
          description="class에 자료가 추가되면 이곳에서 함께 확인할 수 있습니다."
        />
      ) : (
        <ul className="course-material-archive" aria-live="polite">
          {items.map((item) => (
            <li key={item.material.id} className="panel">
              <div className="course-material-archive__session">
                <span className="badge">{item.session.status}</span>
                <strong>{item.session.title}</strong>
                <span>{item.session.lecture_date}</span>
              </div>
              <div className="course-material-archive__file">
                <div>
                  <strong>{item.material.display_name}</strong>
                  <span>
                    {item.material.byte_size.toLocaleString('ko-KR')} bytes ·{' '}
                    {materialStatusCopy[item.material.processing_status]}
                  </span>
                </div>
                {hasMaterialUrls(item) ? (
                  <div className="course-material-archive__actions">
                    <a
                      className="button button--ghost"
                      href={item.content_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      새 탭에서 열기
                    </a>
                    <a
                      className="button button--secondary"
                      href={item.download_url}
                    >
                      다운로드
                    </a>
                  </div>
                ) : (
                  <span className="course-material-archive__unavailable">
                    원문을 사용할 수 없습니다
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {materials.isError && items.length > 0 && (
        <div className="course-archive-page__page-error" role="alert">
          <p>다음 자료를 불러오지 못했습니다. 표시된 자료는 유지됩니다.</p>
          <Button
            variant="secondary"
            onClick={() => void materials.fetchNextPage()}
          >
            다시 시도
          </Button>
        </div>
      )}

      {materials.hasNextPage && !materials.isError && (
        <Button
          variant="secondary"
          disabled={materials.isFetchingNextPage}
          onClick={() => void materials.fetchNextPage()}
        >
          {materials.isFetchingNextPage ? '불러오는 중…' : 'PDF 자료 더 보기'}
        </Button>
      )}
    </section>
  )
}
