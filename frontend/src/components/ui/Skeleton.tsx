interface SkeletonProps {
  label?: string
  lines?: number
}

export function Skeleton({
  label = '콘텐츠를 불러오는 중',
  lines = 3,
}: SkeletonProps) {
  return (
    <div className="ui-skeleton" role="status" aria-label={label}>
      {Array.from({ length: lines }, (_, index) => (
        <span key={index} aria-hidden="true" />
      ))}
    </div>
  )
}
