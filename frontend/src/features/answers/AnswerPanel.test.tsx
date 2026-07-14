import { fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { AppProviders } from '../../app/providers'
import { server } from '../../test/server'
import { AnswerPanel } from './AnswerPanel'

const sessionId = '30000000-0000-0000-0000-000000000001'
const answerId = '40000000-0000-0000-0000-000000000001'

const answer = {
  id: answerId,
  session_id: sessionId,
  answer_type: 'VOICE',
  status: 'COMPLETED',
  version: 2,
  target: {
    type: 'STUDENT_QUESTION',
    question_id: '50000000-0000-0000-0000-000000000001',
  },
  target_text_snapshot: '왜 음수 가중치에서는 사용할 수 없나요?',
  text_content: '기존 교수자 설명',
  source_transcript_version_id: '60000000-0000-0000-0000-000000000001',
  canonical_transcript_mapping: null,
  organization_state: {
    status: 'NOT_STARTED',
    job_id: null,
    attempt: null,
    retryable: false,
    organization: null,
  },
  capture_started_after_sequence: 4,
  start_sequence: 5,
  end_sequence: 8,
  started_at: '2026-07-14T00:00:00Z',
  completed_at: '2026-07-14T00:01:00Z',
  updated_at: '2026-07-14T00:01:00Z',
}

describe('AnswerPanel', () => {
  it('keeps the local text draft when a version conflict occurs', async () => {
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/answers`, () =>
        HttpResponse.json({ items: [answer], next_cursor: null }),
      ),
      http.get(`*/api/v1/sessions/${sessionId}/questions`, () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.patch(`*/api/v1/answers/${answerId}`, async ({ request }) => {
        expect(await request.json()).toEqual({
          text_content: '내 로컬 초안',
          expected_version: 2,
        })
        return HttpResponse.json(
          {
            error: {
              code: 'ANSWER_VERSION_CONFLICT',
              message: '다른 변경이 먼저 저장되었습니다.',
              request_id: 'req_test',
              details: {
                current_version: 3,
                current_text_content: '다른 교수자의 최신 설명',
              },
            },
          },
          { status: 409 },
        )
      }),
    )

    render(
      <AppProviders>
        <AnswerPanel
          sessionId={sessionId}
          professor
          sessionStatus="COMPLETED"
        />
      </AppProviders>,
    )

    fireEvent.click(await screen.findByRole('button', { name: '텍스트 수정' }))
    fireEvent.change(screen.getByLabelText('교수자 텍스트 답변'), {
      target: { value: '내 로컬 초안' },
    })
    fireEvent.click(screen.getByRole('button', { name: '저장' }))

    expect(
      await screen.findByText(
        '다른 변경이 먼저 저장되었습니다. 작성 중인 내용은 그대로 유지합니다.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('교수자 텍스트 답변')).toHaveValue(
      '내 로컬 초안',
    )
  })
})
