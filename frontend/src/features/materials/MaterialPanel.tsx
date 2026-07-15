import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type ChangeEvent, useEffect, useRef, useState } from 'react'

import { apiUrl } from '../../api/client'
import { ApiError } from '../../api/errors'
import { MaterialStatusBadge } from '../../components/domain/LmsStatus'
import { PartialFailurePanel } from '../../components/feedback/PartialFailurePanel'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import {
  detachMaterial,
  type MaterialJob,
  retryMaterialJob,
  uploadSessionMaterial,
} from './api'
import {
  materialKeys,
  sessionMaterialJobsQueryOptions,
  sessionMaterialsQueryOptions,
} from './queries'

const MAX_UPLOAD_BYTES = 100_000_000
const MAX_MATERIALS = 10

interface MaterialPanelProps {
  sessionId: string
  professor: boolean
  sessionStatus: 'READY' | 'LIVE' | 'PROCESSING' | 'COMPLETED'
}

interface UploadQueueItem {
  error?: string
  file: File
  id: string
  idempotencyKey: string
  status: 'queued' | 'uploading' | 'failed'
}

interface DetachTarget {
  id: string
  idempotencyKey: string
  name: string
}

interface RetryIdentity {
  attempt: number
  idempotencyKey: string
  version: number
}

function uploadErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'FILE_TOO_LARGE') {
      return '파일 크기는 100,000,000 bytes 이하여야 합니다.'
    }
    if (error.code === 'UNSUPPORTED_MEDIA_TYPE') {
      return '유효한 PDF 파일만 업로드할 수 있습니다.'
    }
    if (error.code === 'MATERIAL_LIMIT_EXCEEDED') {
      return 'class당 강의자료는 최대 10개까지 연결할 수 있습니다.'
    }
    if (error.code === 'SESSION_STATE_CONFLICT') {
      return '현재 class 상태에서는 강의자료를 업로드할 수 없습니다.'
    }
    return error.message
  }
  return '강의자료를 업로드하지 못했습니다. 같은 파일을 다시 시도할 수 있습니다.'
}

function isPdf(file: File) {
  return (
    file.type === 'application/pdf' && file.name.toLowerCase().endsWith('.pdf')
  )
}

function retryStateChanged(error: unknown) {
  return (
    error instanceof ApiError &&
    (error.status === 404 ||
      error.code === 'AI_JOB_STATE_CONFLICT' ||
      error.code === 'AI_JOB_NOT_RETRYABLE' ||
      error.code === 'AI_JOB_RETRY_SYSTEM_MANAGED')
  )
}

export function MaterialPanel(props: MaterialPanelProps) {
  return <MaterialPanelContent key={props.sessionId} {...props} />
}

function MaterialPanelContent({
  sessionId,
  professor,
  sessionStatus,
}: MaterialPanelProps) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const detachTriggerRef = useRef<HTMLButtonElement | null>(null)
  const retryKeys = useRef<Record<string, RetryIdentity>>({})
  const [queue, setQueue] = useState<UploadQueueItem[]>([])
  const [selectionError, setSelectionError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [detachTarget, setDetachTarget] = useState<DetachTarget | null>(null)
  const materials = useQuery(sessionMaterialsQueryOptions(sessionId))
  const jobs = useQuery({
    ...sessionMaterialJobsQueryOptions(sessionId),
    enabled: professor,
  })
  const canManage = professor && sessionStatus !== 'PROCESSING'
  const materialJobStateSignature = (jobs.data?.items ?? [])
    .map((job) => `${job.id}:${job.version}:${job.attempt}:${job.status}`)
    .join('|')

  useEffect(() => {
    if (!materialJobStateSignature) return
    void queryClient.invalidateQueries({
      queryKey: materialKeys.session(sessionId),
    })
  }, [materialJobStateSignature, queryClient, sessionId])

  function refresh() {
    void queryClient.invalidateQueries({
      queryKey: materialKeys.session(sessionId),
    })
    void queryClient.invalidateQueries({
      queryKey: materialKeys.jobs(sessionId),
    })
  }

  function closeDetachDialog() {
    detach.reset()
    setDetachTarget(null)
    requestAnimationFrame(() => detachTriggerRef.current?.focus())
  }

  const detach = useMutation({
    mutationFn: (target: DetachTarget) =>
      detachMaterial(target.id, target.idempotencyKey),
    onSuccess: () => {
      setDetachTarget(null)
      refresh()
      showToast({ tone: 'success', message: '강의자료 연결을 해제했습니다.' })
      requestAnimationFrame(() => headingRef.current?.focus())
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 404) {
        setDetachTarget(null)
        refresh()
        showToast({
          tone: 'error',
          message: '이미 해제된 자료입니다. 최신 목록을 다시 불러왔습니다.',
        })
        requestAnimationFrame(() => headingRef.current?.focus())
      } else if (
        error instanceof ApiError &&
        error.code === 'MATERIAL_DELETE_CONFLICT'
      ) {
        refresh()
      }
    },
  })
  const retry = useMutation({
    mutationFn: (job: MaterialJob) => {
      const existing = retryKeys.current[job.id]
      const identity =
        existing?.attempt === job.attempt && existing.version === job.version
          ? existing
          : {
              attempt: job.attempt,
              idempotencyKey: crypto.randomUUID(),
              version: job.version,
            }
      retryKeys.current[job.id] = identity
      return retryMaterialJob(job.id, identity.idempotencyKey)
    },
    onSuccess: (_accepted, job) => {
      delete retryKeys.current[job.id]
      refresh()
      showToast({
        tone: 'success',
        message: '강의자료 처리를 다시 요청했습니다.',
      })
    },
    onError: (error, job) => {
      refresh()
      if (retryStateChanged(error)) {
        delete retryKeys.current[job.id]
        showToast({
          tone: 'error',
          message:
            '작업 상태가 이미 변경되었습니다. 최신 자료 상태를 다시 불러왔습니다.',
        })
      }
    },
  })

  const latestFailedJobByMaterial = new Map<string, MaterialJob>()
  for (const job of jobs.data?.items ?? []) {
    const materialId = job.target.resource_id
    if (
      job.job_type === 'MATERIAL_PROCESSING' &&
      job.status === 'FAILED' &&
      job.retryable &&
      job.target.resource_type === 'MATERIAL' &&
      materialId &&
      !latestFailedJobByMaterial.has(materialId)
    ) {
      // The API returns newest jobs first. Keep the first failed job for a
      // Material instead of allowing an older attempt to overwrite it.
      latestFailedJobByMaterial.set(materialId, job)
    }
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    if (files.length === 0) return

    const attachedCount = materials.data?.items.length ?? MAX_MATERIALS
    let remaining = Math.max(0, MAX_MATERIALS - attachedCount - queue.length)
    const accepted: UploadQueueItem[] = []
    const errors: string[] = []

    for (const file of files) {
      if (!isPdf(file)) {
        errors.push(`${file.name}: PDF 파일만 선택할 수 있습니다.`)
        continue
      }
      if (file.size > MAX_UPLOAD_BYTES) {
        errors.push(`${file.name}: 100,000,000 bytes를 초과했습니다.`)
        continue
      }
      if (remaining === 0) {
        errors.push(`최대 ${MAX_MATERIALS}개까지만 연결할 수 있습니다.`)
        continue
      }
      accepted.push({
        file,
        id: crypto.randomUUID(),
        idempotencyKey: crypto.randomUUID(),
        status: 'queued',
      })
      remaining -= 1
    }

    setQueue((current) => [...current, ...accepted])
    setSelectionError(errors.length > 0 ? errors.join(' ') : null)
    event.target.value = ''
  }

  async function uploadQueuedFiles() {
    if (!materials.data || uploading || queue.length === 0) return
    const remaining = Math.max(0, MAX_MATERIALS - materials.data.items.length)
    if (queue.length > remaining) {
      setSelectionError(
        `현재 남은 자리는 ${remaining}개입니다. 파일을 줄인 뒤 다시 시도해 주세요.`,
      )
      return
    }

    setUploading(true)
    setSelectionError(null)
    let successCount = 0
    for (const item of queue) {
      setQueue((current) =>
        current.map((candidate) =>
          candidate.id === item.id
            ? { ...candidate, error: undefined, status: 'uploading' }
            : candidate,
        ),
      )
      try {
        await uploadSessionMaterial(sessionId, item.file, item.idempotencyKey)
        successCount += 1
        setQueue((current) =>
          current.filter((candidate) => candidate.id !== item.id),
        )
        refresh()
      } catch (error) {
        setQueue((current) =>
          current.map((candidate) =>
            candidate.id === item.id
              ? {
                  ...candidate,
                  error: uploadErrorMessage(error),
                  status: 'failed',
                }
              : candidate,
          ),
        )
      }
    }
    setUploading(false)
    refresh()
    if (successCount > 0) {
      showToast({
        tone: 'success',
        message: `${successCount}개 강의자료 업로드를 접수했습니다.`,
      })
    }
  }

  return (
    <section className="panel material-panel" aria-labelledby="material-title">
      <div className="material-panel__heading">
        <div>
          <p className="eyebrow">Course material</p>
          <h2 id="material-title" ref={headingRef} tabIndex={-1}>
            강의자료
          </h2>
          <p>
            PDF는 선택 사항이며, 처리 완료된 자료만 AI 답변의 근거로 사용합니다.
          </p>
        </div>
        {materials.data && (
          <strong className="material-panel__count">
            {materials.data.items.length}/{MAX_MATERIALS}
          </strong>
        )}
      </div>

      {canManage && materials.data && (
        <div className="material-upload" aria-label="강의자료 업로드">
          <div className="material-upload__picker">
            <label htmlFor={`material-files-${sessionId}`}>PDF 파일 선택</label>
            <input
              ref={fileInputRef}
              id={`material-files-${sessionId}`}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              disabled={
                uploading || materials.data.items.length >= MAX_MATERIALS
              }
              aria-describedby={
                selectionError ? `material-files-error-${sessionId}` : undefined
              }
              aria-invalid={Boolean(selectionError)}
              onChange={onFileChange}
            />
            <p>파일당 최대 100 MB · class당 연결된 자료 최대 10개</p>
          </div>

          {queue.length > 0 && (
            <ul
              className="material-upload__queue"
              aria-label="업로드 대기 파일"
            >
              {queue.map((item) => (
                <li key={item.id}>
                  <div>
                    <strong>{item.file.name}</strong>
                    <span>
                      {item.status === 'uploading'
                        ? '업로드 중…'
                        : item.status === 'failed'
                          ? '업로드 실패 · 같은 요청으로 재시도 가능'
                          : `${item.file.size.toLocaleString('ko-KR')} bytes`}
                    </span>
                    {item.error && <p role="alert">{item.error}</p>}
                  </div>
                  <Button
                    variant="ghost"
                    disabled={uploading}
                    aria-label={`${item.file.name} 선택 취소`}
                    onClick={() =>
                      setQueue((current) =>
                        current.filter((candidate) => candidate.id !== item.id),
                      )
                    }
                  >
                    취소
                  </Button>
                </li>
              ))}
            </ul>
          )}

          {selectionError && (
            <p
              className="form-error"
              id={`material-files-error-${sessionId}`}
              role="alert"
            >
              {selectionError}
            </p>
          )}

          <div className="material-upload__actions">
            <Button
              variant="secondary"
              disabled={queue.length === 0 || uploading}
              onClick={() => void uploadQueuedFiles()}
            >
              {uploading
                ? '파일 업로드 중…'
                : `선택한 ${queue.length}개 업로드`}
            </Button>
            <span>실패한 파일은 성공한 파일과 분리해 다시 시도합니다.</span>
          </div>
        </div>
      )}

      {professor && sessionStatus === 'PROCESSING' && (
        <p className="input-hint">
          수업 기록을 정리하는 동안에는 강의자료를 변경할 수 없습니다.
        </p>
      )}

      {professor && jobs.isError && (
        <PartialFailurePanel
          title="자료 처리 작업 상태를 불러오지 못했습니다"
          description="자료 목록은 유지됩니다. 실패 작업의 재시도 가능 여부만 다시 확인합니다."
          actions={
            <Button variant="secondary" onClick={() => void jobs.refetch()}>
              작업 상태 다시 시도
            </Button>
          }
        />
      )}

      {materials.isPending && (
        <StatePanel kind="loading" title="강의자료를 불러오는 중" />
      )}
      {materials.isError && (
        <StatePanel
          kind="error"
          title="강의자료를 불러오지 못했습니다"
          actionLabel="자료 목록 다시 시도"
          onAction={() => void materials.refetch()}
        />
      )}
      {materials.data?.items.length === 0 && (
        <StatePanel
          kind="empty"
          title="연결된 강의자료가 없습니다"
          description={
            professor
              ? 'PDF 없이도 수업을 시작할 수 있습니다.'
              : '교수자가 자료를 연결하면 이곳에서 열람할 수 있습니다.'
          }
        />
      )}
      {materials.data && materials.data.items.length > 0 && (
        <ul className="material-list" aria-label="연결된 강의자료 목록">
          {materials.data.items.map((material) => {
            const readable = material.processing_status !== 'FAILED'
            const retryJob = latestFailedJobByMaterial.get(material.id)
            const retrying =
              retry.isPending && retry.variables?.id === retryJob?.id
            return (
              <li key={material.id}>
                <div className="material-list__copy">
                  <div className="material-list__title">
                    <strong>{material.display_name}</strong>
                    <MaterialStatusBadge status={material.processing_status} />
                  </div>
                  <p>
                    {material.byte_size.toLocaleString('ko-KR')} bytes
                    {material.page_count ? ` · ${material.page_count}쪽` : ''}
                  </p>
                  {material.processing_status === 'FAILED' && (
                    <p>업로드된 파일을 사용할 수 없습니다.</p>
                  )}
                </div>
                <div className="material-list__actions">
                  {readable ? (
                    <a
                      className="button button--ghost"
                      href={apiUrl(`/api/v1/materials/${material.id}/content`)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      PDF 열기
                    </a>
                  ) : (
                    <span className="input-hint">본문을 열 수 없음</span>
                  )}
                  {canManage && retryJob && (
                    <Button
                      variant="secondary"
                      disabled={retry.isPending}
                      onClick={() => retry.mutate(retryJob)}
                    >
                      {retrying ? '재시도 요청 중…' : '처리 다시 시도'}
                    </Button>
                  )}
                  {canManage && (
                    <Button
                      variant="ghost"
                      aria-label={`${material.display_name} 연결 해제`}
                      onClick={(event) => {
                        detachTriggerRef.current = event.currentTarget
                        detach.reset()
                        setDetachTarget({
                          id: material.id,
                          idempotencyKey: crypto.randomUUID(),
                          name: material.display_name,
                        })
                      }}
                    >
                      연결 해제
                    </Button>
                  )}
                </div>
                {retry.isError && retry.variables?.id === retryJob?.id && (
                  <p className="form-error" role="alert">
                    {retryStateChanged(retry.error)
                      ? '작업 상태가 이미 변경되었습니다. 최신 목록을 확인해 주세요.'
                      : '처리를 다시 요청하지 못했습니다. 같은 요청으로 재시도할 수 있습니다.'}
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {canManage && detachTarget && (
        <Dialog
          open
          title="강의자료 연결을 해제할까요?"
          description={`${detachTarget.name}은(는) 즉시 자료 목록과 이후 AI 검색에서 제외됩니다.`}
          onOpenChange={(open) => {
            if (!open && !detach.isPending) {
              closeDetachDialog()
            }
          }}
          actions={
            <>
              <Button
                variant="secondary"
                disabled={detach.isPending}
                onClick={closeDetachDialog}
              >
                취소
              </Button>
              <Button
                variant="danger"
                disabled={detach.isPending}
                onClick={() => detach.mutate(detachTarget)}
              >
                {detach.isPending ? '해제 중…' : '연결 해제'}
              </Button>
            </>
          }
        >
          {detach.isError && (
            <p className="form-error" role="alert">
              {detach.error instanceof ApiError &&
              detach.error.code === 'MATERIAL_DELETE_CONFLICT'
                ? '자료 상태가 바뀌어 해제하지 못했습니다. 최신 목록을 확인해 주세요.'
                : '연결을 해제하지 못했습니다. 같은 요청으로 다시 시도할 수 있습니다.'}
            </p>
          )}
        </Dialog>
      )}
    </section>
  )
}
