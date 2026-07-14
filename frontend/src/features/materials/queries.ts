import { queryOptions } from '@tanstack/react-query'

import {
  listMaterialJobs,
  listSessionMaterials,
  type LectureMaterialListResponse,
} from './api'

export const materialKeys = {
  all: ['materials'] as const,
  session: (sessionId: string) => ['materials', 'session', sessionId] as const,
  jobs: (sessionId: string) => ['materials', 'jobs', sessionId] as const,
}

export function materialsNeedPolling(
  data: LectureMaterialListResponse | undefined,
) {
  return Boolean(
    data?.items.some(
      (material) =>
        material.processing_status === 'UPLOADED' ||
        material.processing_status === 'PROCESSING',
    ),
  )
}

export function sessionMaterialsQueryOptions(sessionId: string) {
  return queryOptions({
    queryKey: materialKeys.session(sessionId),
    queryFn: ({ signal }) => listSessionMaterials(sessionId, signal),
    refetchInterval: (query) =>
      materialsNeedPolling(query.state.data) ? 3_000 : false,
  })
}

export function sessionMaterialJobsQueryOptions(sessionId: string) {
  return queryOptions({
    queryKey: materialKeys.jobs(sessionId),
    queryFn: ({ signal }) => listMaterialJobs(sessionId, signal),
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (job) => job.status === 'PENDING' || job.status === 'RUNNING',
      )
        ? 3_000
        : false,
  })
}
