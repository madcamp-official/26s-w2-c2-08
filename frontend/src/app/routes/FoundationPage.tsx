import { HealthStatus } from '../../features/health/HealthStatus'

export function FoundationPage() {
  return (
    <div className="foundation-grid">
      <section className="foundation-hero" aria-labelledby="page-title">
        <p className="eyebrow">God Of All Lectures</p>
        <h1 className="page-title" id="page-title">
          강의의 흐름을 놓치지 않도록
        </h1>
        <p className="page-description">
          익명 질문과 실시간 학습 지원, 수업 기록 기반 복습을 하나의 흐름으로
          연결합니다.
        </p>
      </section>

      <aside className="panel foundation-status" aria-labelledby="status-title">
        <div>
          <p className="eyebrow">System status</p>
          <h2 id="status-title">서비스 준비 상태</h2>
          <p>화면 기능을 시작하기 전에 API 연결 상태를 확인합니다.</p>
        </div>
        <HealthStatus />
      </aside>
    </div>
  )
}
