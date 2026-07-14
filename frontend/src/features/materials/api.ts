import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type LectureMaterial = components['schemas']['LectureMaterial']
export type LectureMaterialListResponse =
  components['schemas']['LectureMaterialListResponse']

export async function listSessionMaterials(
  sessionId: string,
  signal?: AbortSignal,
): Promise<LectureMaterialListResponse> {
  try {
    const { data, error, response } = await apiClient.GET(
      '/api/v1/sessions/{session_id}/materials',
      {
        params: { path: { session_id: sessionId }, query: { limit: 100 } },
        signal,
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('Material 목록 응답이 비어 있습니다.')
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function uploadSessionMaterial(
  sessionId: string,
  file: File,
  idempotencyKey: string,
) {
  try {
    const { data, error, response } = await apiClient.POST(
      '/api/v1/sessions/{session_id}/materials',
      {
        params: {
          path: { session_id: sessionId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
        // openapi-typescript models `format: binary` as string. The multipart
        // serializer still receives the browser File value at runtime.
        body: { file: file as unknown as string },
        bodySerializer: () => {
          const form = new FormData()
          form.append('file', file, file.name)
          return form
        },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('Material 업로드 응답이 비어 있습니다.')
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function detachMaterial(
  materialId: string,
  idempotencyKey: string,
): Promise<void> {
  try {
    const { error, response } = await apiClient.DELETE(
      '/api/v1/materials/{material_id}',
      {
        params: {
          path: { material_id: materialId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
  } catch (error) {
    throw normalizeApiError(error)
  }
}
