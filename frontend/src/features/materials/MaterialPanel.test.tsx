import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

    const input = await screen.findByLabelText('PDF 파일')
    fireEvent.change(input, {
      target: {
        files: [
          new File(['%PDF-1.7'], 'lecture.pdf', { type: 'application/pdf' }),
        ],
      },
    })
    fireEvent.click(screen.getByRole('button', { name: '자료 업로드' }))

    expect(
      await screen.findByText('강의자료를 업로드하고 처리를 시작했습니다.'),
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
    expect(screen.queryByLabelText('PDF 파일')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '자료 업로드' }),
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

    fireEvent.change(await screen.findByLabelText('PDF 파일'), {
      target: {
        files: [
          new File(['%PDF-1.7'], 'large.pdf', { type: 'application/pdf' }),
        ],
      },
    })
    fireEvent.click(screen.getByRole('button', { name: '자료 업로드' }))

    expect(
      await screen.findByText('파일 크기는 100,000,000 bytes 이하여야 합니다.'),
    ).toBeInTheDocument()
  })
})
