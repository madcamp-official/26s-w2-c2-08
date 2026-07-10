import { useEffect, useState } from 'react'

import { fetchHealth } from './api/health'
import './App.css'

type HealthState =
  | { kind: 'loading' }
  | { kind: 'healthy'; apiStatus: string }
  | { kind: 'error' }

function App() {
  const [health, setHealth] = useState<HealthState>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    void fetchHealth(controller.signal)
      .then((response) => {
        setHealth({
          kind: 'healthy',
          apiStatus:
            typeof response.status === 'string' ? response.status : 'ok',
        })
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }

        setHealth({ kind: 'error' })
      })

    return () => controller.abort()
  }, [attempt])

  const retryHealthCheck = () => {
    setHealth({ kind: 'loading' })
    setAttempt((value) => value + 1)
  }

  return (
    <main className="app-shell">
      <section className="status-card" aria-labelledby="app-title">
        <p className="eyebrow">AI lecture companion</p>
        <h1 id="app-title">ToBeDetermined</h1>
        <p className="description">
          실시간 질문과 수업 기록을 연결하는 강의 학습 보조 서비스
        </p>

        {health.kind === 'loading' && (
          <p className="health health--loading" role="status">
            API 상태 확인 중…
          </p>
        )}

        {health.kind === 'healthy' && (
          <p className="health health--success" role="status">
            API 연결 정상 · {health.apiStatus}
          </p>
        )}

        {health.kind === 'error' && (
          <div className="health-error" role="alert">
            <p className="health health--error">API에 연결할 수 없습니다.</p>
            <button type="button" onClick={retryHealthCheck}>
              다시 시도
            </button>
          </div>
        )}
      </section>
    </main>
  )
}

export default App
