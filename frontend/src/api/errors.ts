import type { components } from './generated/schema'

type ErrorResponse = components['schemas']['ErrorResponse']

export type ApiErrorKind =
  | 'unauthorized'
  | 'forbidden'
  | 'not-found'
  | 'conflict'
  | 'validation'
  | 'rate-limit'
  | 'dependency'
  | 'unknown'

interface ApiErrorOptions {
  status?: number
  code?: string
  requestId?: string
  details?: Record<string, unknown> | null
  cause?: unknown
}

const statusMessages: Record<number, string> = {
  401: '로그인이 필요합니다.',
  403: '이 작업을 수행할 권한이 없습니다.',
  404: '요청한 정보를 찾을 수 없습니다.',
  409: '현재 상태에서는 요청을 처리할 수 없습니다.',
  422: '입력한 내용을 다시 확인해 주세요.',
  429: '요청이 많습니다. 잠시 후 다시 시도해 주세요.',
  502: '연결된 서비스에서 응답하지 않습니다.',
  503: '서비스를 일시적으로 사용할 수 없습니다.',
}

function kindFromStatus(status?: number): ApiErrorKind {
  switch (status) {
    case 401:
      return 'unauthorized'
    case 403:
      return 'forbidden'
    case 404:
      return 'not-found'
    case 409:
      return 'conflict'
    case 422:
      return 'validation'
    case 429:
      return 'rate-limit'
    case 502:
    case 503:
      return 'dependency'
    default:
      return 'unknown'
  }
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  if (typeof value !== 'object' || value === null || !('error' in value)) {
    return false
  }

  const error = value.error
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string' &&
    'message' in error &&
    typeof error.message === 'string' &&
    'request_id' in error &&
    typeof error.request_id === 'string'
  )
}

export class ApiError extends Error {
  readonly status?: number
  readonly code: string
  readonly requestId?: string
  readonly details?: Record<string, unknown> | null
  readonly kind: ApiErrorKind

  constructor(message: string, options: ApiErrorOptions = {}) {
    super(message, { cause: options.cause })
    this.name = 'ApiError'
    this.status = options.status
    this.code = options.code ?? 'UNKNOWN_ERROR'
    this.requestId = options.requestId
    this.details = options.details
    this.kind = kindFromStatus(options.status)
  }
}

export function apiErrorFromResponse(
  response: Response,
  payload: unknown,
): ApiError {
  if (isErrorResponse(payload)) {
    return new ApiError(payload.error.message, {
      status: response.status,
      code: payload.error.code,
      requestId: payload.error.request_id,
      details: payload.error.details,
    })
  }

  return new ApiError(
    statusMessages[response.status] ?? '요청을 처리하지 못했습니다.',
    {
      status: response.status,
      code: `HTTP_${response.status}`,
    },
  )
}

export function normalizeApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error
  }

  return new ApiError('네트워크 연결을 확인하고 다시 시도해 주세요.', {
    code: 'NETWORK_ERROR',
    cause: error,
  })
}
