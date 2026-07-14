import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type ChangeEvent, useRef, useState } from 'react'

import { apiUrl } from '../../api/client'
import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import { detachMaterial, uploadSessionMaterial } from './api'
import { materialKeys, sessionMaterialsQueryOptions } from './queries'

const MAX_UPLOAD_BYTES = 100_000_000

interface MaterialPanelProps {
  sessionId: string
  professor: boolean
  sessionStatus: 'READY' | 'LIVE' | 'PROCESSING' | 'COMPLETED'
}

function statusLabel(status: string) {
  switch (status) {
    case 'UPLOADED':
      return '업로드됨'
    case 'PROCESSING':
      return '처리 중'
    case 'READY':
      return '준비됨'
    default:
      return '처리 실패'
  }
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
    return error.message
  }
  return '강의자료를 업로드하지 못했습니다. 다시 시도해 주세요.'
}

export function MaterialPanel({
  sessionId,
  professor,
  sessionStatus,
}: MaterialPanelProps) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedFileError, setSelectedFileError] = useState<string | null>(
    null,
  )
  const [detachTarget, setDetachTarget] = useState<{
    id: string
    name: string
  } | null>(null)
  const materials = useQuery(sessionMaterialsQueryOptions(sessionId))
  const canManage = professor && sessionStatus !== 'PROCESSING'

  function refresh() {
    void queryClient.invalidateQueries({
      queryKey: materialKeys.session(sessionId),
    })
  }

  const upload = useMutation({
    mutationFn: (file: File) =>
      uploadSessionMaterial(sessionId, file, crypto.randomUUID()),
    onSuccess: () => {
      setSelectedFile(null)
      setSelectedFileError(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      refresh()
      showToast({
        tone: 'success',
        message: '강의자료를 업로드하고 처리를 시작했습니다.',
      })
    },
  })
  const detach = useMutation({
    mutationFn: (materialId: string) =>
      detachMaterial(materialId, crypto.randomUUID()),
    onSuccess: () => {
      setDetachTarget(null)
      refresh()
      showToast({ tone: 'success', message: '강의자료 연결을 해제했습니다.' })
    },
  })

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    if (!file) return
    if (file.type !== 'application/pdf') {
      setSelectedFile(null)
      setSelectedFileError('PDF 파일만 선택할 수 있습니다.')
      return
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setSelectedFile(null)
      setSelectedFileError('파일 크기는 100,000,000 bytes 이하여야 합니다.')
      return
    }
    setSelectedFile(file)
    setSelectedFileError(null)
  }

  return (
    <section className="panel material-panel" aria-labelledby="material-title">
      <div className="material-panel__heading">
        <div>
          <p className="eyebrow">Course material</p>
          <h2 id="material-title">강의자료</h2>
          <p>
            PDF만 연결할 수 있으며, 처리 실패한 자료는 본문을 열 수 없습니다.
          </p>
        </div>
      </div>

      {canManage && (
        <div className="material-upload" aria-label="강의자료 업로드">
          <label>
            <span>PDF 파일</span>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              onChange={onFileChange}
            />
          </label>
          <div className="form-actions">
            <Button
              variant="secondary"
              disabled={!selectedFile || upload.isPending}
              onClick={() => selectedFile && upload.mutate(selectedFile)}
            >
              {upload.isPending ? '업로드 중…' : '자료 업로드'}
            </Button>
            {selectedFile && (
              <span className="input-hint">{selectedFile.name}</span>
            )}
          </div>
          {selectedFileError && (
            <p className="form-error">{selectedFileError}</p>
          )}
          {upload.isError && (
            <p className="form-error">{uploadErrorMessage(upload.error)}</p>
          )}
        </div>
      )}

      {professor && sessionStatus === 'PROCESSING' && (
        <p className="input-hint">
          수업 기록을 정리하는 동안에는 강의자료를 변경할 수 없습니다.
        </p>
      )}

      {materials.data && (
        <p className="input-hint">
          연결된 강의자료 {materials.data.items.length}/10개
        </p>
      )}

      {materials.isPending && (
        <StatePanel kind="loading" title="강의자료를 불러오는 중" />
      )}
      {materials.isError && (
        <StatePanel kind="error" title="강의자료를 불러오지 못했습니다" />
      )}
      {materials.data?.items.length === 0 && (
        <StatePanel
          kind="empty"
          title="연결된 강의자료가 없습니다"
          description={
            professor
              ? 'PDF를 올리면 수업 시작 전에 처리 상태를 확인할 수 있습니다.'
              : '교수자가 자료를 연결하면 이곳에서 열람할 수 있습니다.'
          }
        />
      )}
      {materials.data && materials.data.items.length > 0 && (
        <ul className="material-list" aria-label="연결된 강의자료 목록">
          {materials.data.items.map((material) => {
            const readable = material.processing_status !== 'FAILED'
            return (
              <li key={material.id}>
                <div>
                  <strong>{material.display_name}</strong>
                  <p>
                    {statusLabel(material.processing_status)} ·{' '}
                    {material.byte_size.toLocaleString('ko-KR')} bytes
                    {material.page_count ? ` · ${material.page_count}쪽` : ''}
                  </p>
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
                  {canManage && (
                    <Button
                      variant="ghost"
                      aria-label={`${material.display_name} 연결 해제`}
                      onClick={() =>
                        setDetachTarget({
                          id: material.id,
                          name: material.display_name,
                        })
                      }
                    >
                      연결 해제
                    </Button>
                  )}
                </div>
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
          onOpenChange={(open) => !open && setDetachTarget(null)}
          actions={
            <>
              <Button
                variant="secondary"
                disabled={detach.isPending}
                onClick={() => setDetachTarget(null)}
              >
                취소
              </Button>
              <Button
                variant="danger"
                disabled={detach.isPending}
                onClick={() => detach.mutate(detachTarget.id)}
              >
                {detach.isPending ? '해제 중…' : '연결 해제'}
              </Button>
            </>
          }
        >
          {detach.isError && (
            <p className="form-error">연결을 해제하지 못했습니다.</p>
          )}
        </Dialog>
      )}
    </section>
  )
}
