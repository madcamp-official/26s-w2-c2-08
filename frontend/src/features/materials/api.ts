import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type LectureMaterial = components['schemas']['LectureMaterial']
export type LectureMaterialListResponse =
  components['schemas']['LectureMaterialListResponse']

interface MaterialJobSource {
  attempt: number
  id: string
  job_type: components['schemas']['AIJobType']
  retryable: boolean
  status: components['schemas']['AIJobStatus']
  target: components['schemas']['AIJobResourceLink']
  version: number
}

export interface MaterialJob {
  attempt: number
  id: string
  job_type: 'MATERIAL_PROCESSING'
  retryable: boolean
  status: components['schemas']['AIJobStatus']
  target: {
    resource_id: string
    resource_type: 'MATERIAL'
    resource_url: string | null
  }
  version: number
}

export interface MaterialJobListResponse {
  items: MaterialJob[]
  next_cursor: string | null
}

export interface MaterialJobAcceptedResponse {
  job: MaterialJob
}

function materialJobFromApi(job: MaterialJobSource): MaterialJob {
  if (
    job.job_type !== 'MATERIAL_PROCESSING' ||
    job.target.resource_type !== 'MATERIAL' ||
    !job.target.resource_id
  ) {
    throw new Error('Material 처리 작업 응답 계약이 올바르지 않습니다.')
  }

  return {
    attempt: job.attempt,
    id: job.id,
    job_type: job.job_type,
    retryable: job.retryable,
    status: job.status,
    target: {
      resource_id: job.target.resource_id,
      resource_type: job.target.resource_type,
      resource_url: job.target.resource_url,
    },
    version: job.version,
  }
}

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

export async function listMaterialJobs(
  sessionId: string,
  signal?: AbortSignal,
): Promise<MaterialJobListResponse> {
  try {
    const { data, error, response } = await apiClient.GET(
      '/api/v1/sessions/{session_id}/jobs',
      {
        params: {
          path: { session_id: sessionId },
          query: { job_type: 'MATERIAL_PROCESSING', limit: 100 },
        },
        signal,
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('강의자료 처리 작업 응답이 비어 있습니다.')
    return {
      items: data.items.map(materialJobFromApi),
      next_cursor: data.next_cursor,
    }
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function retryMaterialJob(
  jobId: string,
  idempotencyKey: string,
): Promise<MaterialJobAcceptedResponse> {
  try {
    const { data, error, response } = await apiClient.POST(
      '/api/v1/jobs/{job_id}/retry',
      {
        params: {
          path: { job_id: jobId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    if (!data) throw new Error('강의자료 처리 재시도 응답이 비어 있습니다.')
    return { job: materialJobFromApi(data.job) }
  } catch (error) {
    throw normalizeApiError(error)
  }
}
