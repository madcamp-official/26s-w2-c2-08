import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { AppProviders } from '../../app/providers'
import { server } from '../../test/server'
import { MaterialPanel } from './MaterialPanel'

const sessionId = '30000000-0000-0000-0000-000000000001'
const material = {
  id: '40000000-0000-0000-0000-000000000001',
  session_id: sessionId,
  display_name: 'lecture.pdf',
  mime_type: 'application/pdf' as const,
  byte_size: 1234,
  page_count: 1,
  processing_status: 'READY' as const,
  created_at: '2026-07-14T00:00:00Z',
}

const failedMaterial = {
  ...material,
  processing_status: 'FAILED' as const,
  page_count: null,
}

const failedMaterialJob = {
  id: '50000000-0000-0000-0000-000000000001',
  session_id: sessionId,
  job_type: 'MATERIAL_PROCESSING' as const,
  visibility: 'SHARED' as const,
  status: 'FAILED' as const,
  attempt: 1,
  version: 2,
  progress: null,
  retryable: true,
  blocks_session_completion: false,
  clustering: null,
  error: {
    code: 'MATERIAL_PROCESSING_FAILED',
    message: '강의자료 처리에 실패했습니다.',
    retryable: true,
  },
  target: {
    resource_type: 'MATERIAL' as const,
    resource_id: material.id,
    resource_url: null,
  },
  result: null,
  result_unavailable_reason: null,
  created_at: '2026-07-14T00:00:00Z',
  updated_at: '2026-07-14T00:01:00Z',
  started_at: '2026-07-14T00:00:10Z',
  finished_at: '2026-07-14T00:01:00Z',
}

function renderPanel(professor: boolean) {
  render(
    <AppProviders>
      <MaterialPanel
        sessionId={sessionId}
        professor={professor}
        sessionStatus="READY"
      />
    </AppProviders>,
  )
}

describe('MaterialPanel', () => {
  it('uploads a PDF through the typed API client and refreshes the list', async () => {
    let uploaded = false
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json({
          items: uploaded ? [material] : [],
          next_cursor: null,
        }),
      ),
      http.post(
        `*/api/v1/sessions/${sessionId}/materials`,
        async ({ request }) => {
          const form = await request.formData()
          const file = form.get('file')
          expect(file).not.toBeNull()
          expect((file as Blob).type).toBe('application/pdf')
          uploaded = true
          return HttpResponse.json(
            {
              material: {
                ...material,
                processing_status: 'UPLOADED',
                page_count: null,
              },
              job: {
                id: '50000000-0000-0000-0000-000000000001',
                session_id: sessionId,
                job_type: 'MATERIAL_PROCESSING',
                visibility: 'SHARED',
                status: 'PENDING',
                attempt: 1,
                version: 1,
                blocks_session_completion: false,
                retryable: false,
                available_at: '2026-07-14T00:00:00Z',
                started_at: null,
                heartbeat_at: null,
                finished_at: null,
                error_code: null,
                error_message: null,
                result_kind: null,
                result_id: null,
                created_at: '2026-07-14T00:00:00Z',
                updated_at: '2026-07-14T00:00:00Z',
              },
            },
            { status: 202 },
          )
        },
      ),
    )
    renderPanel(true)

    const input = await screen.findByLabelText('PDF 파일 선택')
    fireEvent.change(input, {
      target: {
        files: [
          new File(['%PDF-1.7'], 'lecture.pdf', { type: 'application/pdf' }),
        ],
      },
    })
    fireEvent.click(screen.getByRole('button', { name: '선택한 1개 업로드' }))

    expect(
      await screen.findByText('1개 강의자료 업로드를 접수했습니다.'),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByText('lecture.pdf')).toBeInTheDocument(),
    )
  })

  it('keeps upload and detach controls out of a student DOM', async () => {
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json({ items: [material], next_cursor: null }),
      ),
    )
    renderPanel(false)

    expect(await screen.findByText('lecture.pdf')).toBeInTheDocument()
    expect(screen.queryByLabelText('PDF 파일 선택')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /선택한 .*개 업로드/ }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'lecture.pdf 연결 해제' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'PDF 열기' })).toBeInTheDocument()
  })

  it('shows the server file-size contract when an upload is rejected', async () => {
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json(
          {
            error: {
              code: 'FILE_TOO_LARGE',
              message: '파일 크기는 100,000,000 bytes 이하여야 합니다.',
              request_id: 'req_material_test',
              details: { max_upload_bytes: 100000000 },
            },
          },
          { status: 413 },
        ),
      ),
    )
    renderPanel(true)

    fireEvent.change(await screen.findByLabelText('PDF 파일 선택'), {
      target: {
        files: [
          new File(['%PDF-1.7'], 'large.pdf', { type: 'application/pdf' }),
        ],
      },
    })
    fireEvent.click(screen.getByRole('button', { name: '선택한 1개 업로드' }))

    expect(
      await screen.findByText('파일 크기는 100,000,000 bytes 이하여야 합니다.'),
    ).toBeInTheDocument()
  })

  it('uploads multiple PDFs independently and keeps the failed file idempotency key', async () => {
    const requestKeys: string[] = []
    let requestCount = 0
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post(
        `*/api/v1/sessions/${sessionId}/materials`,
        async ({ request }) => {
          const form = await request.formData()
          const file = form.get('file') as File
          requestKeys.push(request.headers.get('Idempotency-Key') ?? '')
          requestCount += 1
          if (requestCount === 2) {
            return HttpResponse.json(
              {
                error: {
                  code: 'DEPENDENCY_UNAVAILABLE',
                  message: '잠시 후 다시 시도해 주세요.',
                  request_id: 'req_material_partial',
                  details: null,
                },
              },
              { status: 503 },
            )
          }
          return HttpResponse.json(
            {
              material: { ...material, display_name: file.name },
              job: failedMaterialJob,
            },
            { status: 202 },
          )
        },
      ),
    )
    renderPanel(true)

    fireEvent.change(await screen.findByLabelText('PDF 파일 선택'), {
      target: {
        files: [
          new File(['%PDF-first'], 'first.pdf', {
            type: 'application/pdf',
          }),
          new File(['%PDF-second'], 'second.pdf', {
            type: 'application/pdf',
          }),
        ],
      },
    })
    fireEvent.click(screen.getByRole('button', { name: '선택한 2개 업로드' }))

    expect(
      await screen.findByText('잠시 후 다시 시도해 주세요.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('first.pdf')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '선택한 1개 업로드' }))

    await waitFor(() =>
      expect(screen.queryByText('second.pdf')).not.toBeInTheDocument(),
    )
    expect(requestKeys).toHaveLength(3)
    expect(requestKeys[0]).not.toBe('')
    expect(requestKeys[1]).not.toBe(requestKeys[0])
    expect(requestKeys[2]).toBe(requestKeys[1])
  })

  it('retries a failed Material job with the same idempotency key', async () => {
    const keys: string[] = []
    let attempts = 0
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json({ items: [failedMaterial], next_cursor: null }),
      ),
      http.get(`*/api/v1/sessions/${sessionId}/jobs`, () =>
        HttpResponse.json({ items: [failedMaterialJob], next_cursor: null }),
      ),
      http.post('*/api/v1/jobs/:jobId/retry', ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key') ?? '')
        attempts += 1
        if (attempts === 1) {
          return HttpResponse.json(
            {
              error: {
                code: 'DEPENDENCY_UNAVAILABLE',
                message: '잠시 후 다시 시도해 주세요.',
                request_id: 'req_job_retry',
                details: null,
              },
            },
            { status: 503 },
          )
        }
        return HttpResponse.json({
          job: {
            ...failedMaterialJob,
            status: 'PENDING',
            attempt: 2,
            error: null,
          },
        })
      }),
    )
    renderPanel(true)

    fireEvent.click(
      await screen.findByRole('button', { name: '처리 다시 시도' }),
    )
    expect(
      await screen.findByText(
        '처리를 다시 요청하지 못했습니다. 같은 요청으로 재시도할 수 있습니다.',
      ),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '처리 다시 시도' }))

    expect(
      await screen.findByText('강의자료 처리를 다시 요청했습니다.'),
    ).toBeInTheDocument()
    expect(keys).toHaveLength(2)
    expect(keys[0]).not.toBe('')
    expect(keys[1]).toBe(keys[0])
  })

  it('uses a new idempotency key after the canonical failed attempt advances', async () => {
    const keys: string[] = []
    let sourceAttempt = 1
    let jobRequests = 0
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json({ items: [failedMaterial], next_cursor: null }),
      ),
      http.get(`*/api/v1/sessions/${sessionId}/jobs`, () => {
        jobRequests += 1
        return HttpResponse.json({
          items: [
            {
              ...failedMaterialJob,
              attempt: sourceAttempt,
              version: sourceAttempt + 1,
            },
          ],
          next_cursor: null,
        })
      }),
      http.post('*/api/v1/jobs/:jobId/retry', ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key') ?? '')
        if (keys.length === 1) {
          sourceAttempt = 2
          return HttpResponse.json(
            {
              error: {
                code: 'DEPENDENCY_UNAVAILABLE',
                message: '응답을 확인하지 못했습니다.',
                request_id: 'req_job_retry_ambiguous',
                details: null,
              },
            },
            { status: 503 },
          )
        }
        return HttpResponse.json({
          job: {
            ...failedMaterialJob,
            status: 'PENDING',
            attempt: 3,
            version: 4,
            retryable: false,
            error: null,
          },
        })
      }),
    )
    renderPanel(true)

    fireEvent.click(
      await screen.findByRole('button', { name: '처리 다시 시도' }),
    )
    await screen.findByText(
      '처리를 다시 요청하지 못했습니다. 같은 요청으로 재시도할 수 있습니다.',
    )
    await waitFor(() => expect(jobRequests).toBeGreaterThanOrEqual(2))
    fireEvent.click(screen.getByRole('button', { name: '처리 다시 시도' }))

    expect(
      await screen.findByText('강의자료 처리를 다시 요청했습니다.'),
    ).toBeInTheDocument()
    expect(keys).toHaveLength(2)
    expect(keys[1]).not.toBe(keys[0])
  })

  it('refreshes canonical state when a retry target changed in another client', async () => {
    let changed = false
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json({
          items: [changed ? material : failedMaterial],
          next_cursor: null,
        }),
      ),
      http.get(`*/api/v1/sessions/${sessionId}/jobs`, () =>
        HttpResponse.json({
          items: changed ? [] : [failedMaterialJob],
          next_cursor: null,
        }),
      ),
      http.post('*/api/v1/jobs/:jobId/retry', () => {
        changed = true
        return HttpResponse.json(
          {
            error: {
              code: 'AI_JOB_STATE_CONFLICT',
              message: '작업 상태가 이미 변경되었습니다.',
              request_id: 'req_job_retry_conflict',
              details: null,
            },
          },
          { status: 409 },
        )
      }),
    )
    renderPanel(true)

    fireEvent.click(
      await screen.findByRole('button', { name: '처리 다시 시도' }),
    )

    expect(
      await screen.findByText(
        '작업 상태가 이미 변경되었습니다. 최신 자료 상태를 다시 불러왔습니다.',
      ),
    ).toBeInTheDocument()
    expect(await screen.findByText('AI 참고 가능')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '처리 다시 시도' }),
    ).not.toBeInTheDocument()
  })

  it('allows only one failed Material retry request at a time', async () => {
    const secondMaterial = {
      ...failedMaterial,
      id: '40000000-0000-0000-0000-000000000002',
      display_name: 'second.pdf',
    }
    const secondJob = {
      ...failedMaterialJob,
      id: '50000000-0000-0000-0000-000000000002',
      target: { ...failedMaterialJob.target, resource_id: secondMaterial.id },
    }
    let releaseRetry: (() => void) | undefined
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json({
          items: [failedMaterial, secondMaterial],
          next_cursor: null,
        }),
      ),
      http.get(`*/api/v1/sessions/${sessionId}/jobs`, () =>
        HttpResponse.json({
          items: [failedMaterialJob, secondJob],
          next_cursor: null,
        }),
      ),
      http.post('*/api/v1/jobs/:jobId/retry', async () => {
        await new Promise<void>((resolve) => {
          releaseRetry = resolve
        })
        return HttpResponse.json({
          job: {
            ...failedMaterialJob,
            status: 'PENDING',
            attempt: 2,
            version: 3,
            retryable: false,
            error: null,
          },
        })
      }),
    )
    renderPanel(true)

    const retryButtons = await screen.findAllByRole('button', {
      name: '처리 다시 시도',
    })
    fireEvent.click(retryButtons[0])

    await waitFor(() => expect(releaseRetry).toBeDefined())
    expect(retryButtons[0]).toBeDisabled()
    expect(retryButtons[1]).toBeDisabled()
    releaseRetry?.()
    expect(
      await screen.findByText('강의자료 처리를 다시 요청했습니다.'),
    ).toBeInTheDocument()
  })

  it('refreshes the Material after its processing Job reaches a new state', async () => {
    let retried = false
    let materialRequests = 0
    let readyAfterRequest = Number.POSITIVE_INFINITY
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () => {
        materialRequests += 1
        return HttpResponse.json({
          items: [
            materialRequests >= readyAfterRequest ? material : failedMaterial,
          ],
          next_cursor: null,
        })
      }),
      http.get(`*/api/v1/sessions/${sessionId}/jobs`, () =>
        HttpResponse.json({
          items: [
            retried
              ? {
                  ...failedMaterialJob,
                  status: 'SUCCEEDED',
                  attempt: 2,
                  version: 3,
                  retryable: false,
                  error: null,
                  result: {
                    resource_type: 'MATERIAL',
                    resource_id: material.id,
                    resource_url: null,
                  },
                }
              : failedMaterialJob,
          ],
          next_cursor: null,
        }),
      ),
      http.post('*/api/v1/jobs/:jobId/retry', () => {
        retried = true
        readyAfterRequest = materialRequests + 2
        return HttpResponse.json({
          job: {
            ...failedMaterialJob,
            status: 'PENDING',
            attempt: 2,
            version: 3,
            retryable: false,
            error: null,
          },
        })
      }),
    )
    renderPanel(true)

    fireEvent.click(
      await screen.findByRole('button', { name: '처리 다시 시도' }),
    )

    expect(await screen.findByText('AI 참고 가능')).toBeInTheDocument()
    expect(materialRequests).toBeGreaterThanOrEqual(3)
  })

  it('keeps one idempotency key while retrying a Material detach', async () => {
    const keys: string[] = []
    let attempts = 0
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json({ items: [material], next_cursor: null }),
      ),
      http.get(`*/api/v1/sessions/${sessionId}/jobs`, () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.delete('*/api/v1/materials/:materialId', ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key') ?? '')
        attempts += 1
        if (attempts === 1) {
          return HttpResponse.json(
            {
              error: {
                code: 'DEPENDENCY_UNAVAILABLE',
                message: '잠시 후 다시 시도해 주세요.',
                request_id: 'req_detach_retry',
                details: null,
              },
            },
            { status: 503 },
          )
        }
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderPanel(true)

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'lecture.pdf 연결 해제',
      }),
    )
    const dialog = screen.getByRole('dialog', {
      name: '강의자료 연결을 해제할까요?',
    })
    fireEvent.click(within(dialog).getByRole('button', { name: '연결 해제' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      '같은 요청으로 다시 시도할 수 있습니다',
    )
    fireEvent.click(within(dialog).getByRole('button', { name: '연결 해제' }))

    expect(
      await screen.findByText('강의자료 연결을 해제했습니다.'),
    ).toBeInTheDocument()
    expect(keys).toHaveLength(2)
    expect(keys[0]).not.toBe('')
    expect(keys[1]).toBe(keys[0])
  })

  it('returns focus to the Material detach trigger after Escape', async () => {
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json({ items: [material], next_cursor: null }),
      ),
      http.get(`*/api/v1/sessions/${sessionId}/jobs`, () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderPanel(true)

    const trigger = await screen.findByRole('button', {
      name: 'lecture.pdf 연결 해제',
    })
    trigger.focus()
    fireEvent.click(trigger)
    const dialog = screen.getByRole('dialog', {
      name: '강의자료 연결을 해제할까요?',
    })

    fireEvent(dialog, new Event('cancel', { cancelable: true }))

    await waitFor(() => expect(trigger).toHaveFocus())
    expect(
      screen.queryByRole('dialog', {
        name: '강의자료 연결을 해제할까요?',
      }),
    ).not.toBeInTheDocument()
  })

  it('accepts only the remaining Material slots from a multiple selection', async () => {
    const attached = Array.from({ length: 9 }, (_, index) => ({
      ...material,
      id: `40000000-0000-0000-0000-${String(index + 1).padStart(12, '0')}`,
      display_name: `lecture-${index + 1}.pdf`,
    }))
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/materials`, () =>
        HttpResponse.json({ items: attached, next_cursor: null }),
      ),
      http.get(`*/api/v1/sessions/${sessionId}/jobs`, () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderPanel(true)

    fireEvent.change(await screen.findByLabelText('PDF 파일 선택'), {
      target: {
        files: [
          new File(['%PDF-first'], 'first.pdf', {
            type: 'application/pdf',
          }),
          new File(['%PDF-second'], 'second.pdf', {
            type: 'application/pdf',
          }),
        ],
      },
    })

    expect(
      screen.getByRole('button', { name: '선택한 1개 업로드' }),
    ).toBeInTheDocument()
    expect(screen.getByText('first.pdf')).toBeInTheDocument()
    expect(screen.queryByText('second.pdf')).not.toBeInTheDocument()
    expect(
      screen.getByText('최대 10개까지만 연결할 수 있습니다.'),
    ).toBeInTheDocument()
  })
})
