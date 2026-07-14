import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Dialog } from '../../components/ui/Dialog'
import type { Course } from './api'
import { deleteCourse, rotateCourseJoinCode } from './api'
import { courseKeys } from './queries'
import { CurrentClassCard } from './CurrentClassCard'

export function ProfessorCourseView({ course }: { course: Course }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [rotateOpen, setRotateOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const rotateKey = useRef<string | null>(null)
  const deleteKey = useRef<string | null>(null)

  const rotate = useMutation({
    mutationFn: () =>
      rotateCourseJoinCode(
        course.id,
        (rotateKey.current ??= crypto.randomUUID()),
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(courseKeys.detail(course.id), updated)
      void queryClient.invalidateQueries({
        queryKey: courseKeys.list('PROFESSOR'),
      })
      setRotateOpen(false)
      rotateKey.current = null
      showToast({ tone: 'success', message: '새 참여 코드로 교체했습니다.' })
    },
    onError: () => {
      showToast({ tone: 'error', message: '참여 코드를 교체하지 못했습니다.' })
    },
  })
  const remove = useMutation({
    mutationFn: () =>
      deleteCourse(course.id, (deleteKey.current ??= crypto.randomUUID())),
    onSuccess: () => {
      setDeleteOpen(false)
      deleteKey.current = null
      queryClient.removeQueries({ queryKey: courseKeys.detail(course.id) })
      void queryClient.invalidateQueries({ queryKey: courseKeys.all })
      showToast({ tone: 'success', message: 'Course를 삭제했습니다.' })
      void navigate('/', { replace: true })
    },
    onError: (error) => {
      if (
        error instanceof ApiError &&
        error.code === 'COURSE_HAS_ACTIVE_SESSION'
      ) {
        void queryClient.invalidateQueries({
          queryKey: courseKeys.detail(course.id),
        })
      }
      const message =
        error instanceof ApiError && error.code === 'COURSE_HAS_ACTIVE_SESSION'
          ? '활성 class가 있어 Course를 삭제할 수 없습니다.'
          : 'Course를 삭제하지 못했습니다. 현재 상태를 다시 확인해 주세요.'
      showToast({ tone: 'error', message })
    },
  })

  async function copyJoinCode() {
    if (!course.join_code) return
    try {
      await navigator.clipboard.writeText(course.join_code)
      showToast({ tone: 'success', message: '참여 코드를 복사했습니다.' })
    } catch {
      showToast({ tone: 'error', message: '참여 코드를 복사하지 못했습니다.' })
    }
  }

  return (
    <div className="course-overview course-overview--professor">
      <div className="course-overview__intro">
        <div>
          <p className="eyebrow">Professor workspace</p>
          <h2>수업 운영 개요</h2>
          <p>
            현재 class를 준비하고 학생 참여를 관리합니다. 완료된 기록은 왼쪽
            archive와 class 목록에서 언제든 다시 열 수 있습니다.
          </p>
        </div>
        <span className="course-overview__role-note">
          이 Course의 유일한 owner
        </span>
      </div>

      <div className="course-overview__grid">
        <CurrentClassCard course={course} professor />

        <Card
          as="aside"
          className="course-access-card"
          aria-labelledby="join-code-title"
        >
          <div className="course-access-card__heading">
            <div>
              <p className="eyebrow">Student access</p>
              <h2 id="join-code-title">학생 참여 코드</h2>
            </div>
            <span>6자리</span>
          </div>
          <p className="course-access-card__description">
            자동 만료되지 않습니다. 코드를 교체하면 이전 코드는 즉시 사용할 수
            없습니다.
          </p>
          <strong className="course-access-card__code">
            {course.join_code}
          </strong>
          <div className="course-access-card__actions">
            <Button variant="secondary" onClick={() => void copyJoinCode()}>
              코드 복사
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                rotate.reset()
                rotateKey.current = null
                setRotateOpen(true)
              }}
            >
              새 코드로 교체
            </Button>
          </div>
        </Card>
      </div>

      <Card as="section" className="course-owner-zone">
        <div>
          <p className="eyebrow">Owner settings</p>
          <h2>Course 관리</h2>
          <p>
            삭제하면 모든 구성원의 접근과 참여 코드가 즉시 무효화되며 복구할 수
            없습니다.
          </p>
        </div>
        <div className="course-owner-zone__action">
          <Button
            variant="danger"
            disabled={Boolean(course.current_session)}
            onClick={() => {
              remove.reset()
              deleteKey.current = null
              setDeleteOpen(true)
            }}
          >
            Course 삭제
          </Button>
          {course.current_session && (
            <p>현재 class가 완료된 뒤에만 삭제할 수 있습니다.</p>
          )}
        </div>
      </Card>

      <Dialog
        open={rotateOpen}
        title="참여 코드를 새로 만들까요?"
        description="완료되는 즉시 현재 코드는 더 이상 사용할 수 없습니다."
        onOpenChange={(open) => {
          if (!open && !rotate.isPending) {
            rotate.reset()
            rotateKey.current = null
          }
          setRotateOpen(open)
        }}
        actions={
          <>
            <Button
              variant="secondary"
              disabled={rotate.isPending}
              onClick={() => {
                rotate.reset()
                rotateKey.current = null
                setRotateOpen(false)
              }}
            >
              취소
            </Button>
            <Button
              variant="danger"
              disabled={rotate.isPending}
              onClick={() => rotate.mutate()}
            >
              {rotate.isPending ? '교체 중…' : '새 코드로 교체'}
            </Button>
          </>
        }
      >
        <p>학생들에게 새 코드를 다시 안내해야 합니다.</p>
        {rotate.isError && (
          <p className="form-error" role="alert">
            참여 코드를 교체하지 못했습니다. 기존 코드는 유지되었습니다.
          </p>
        )}
      </Dialog>

      <Dialog
        open={deleteOpen}
        title="Course를 삭제할까요?"
        description="현재 class가 없는 Course만 삭제할 수 있으며, 삭제 후 복구할 수 없습니다."
        onOpenChange={(open) => {
          if (!open && !remove.isPending) {
            remove.reset()
            deleteKey.current = null
          }
          setDeleteOpen(open)
        }}
        actions={
          <>
            <Button
              variant="secondary"
              disabled={remove.isPending}
              onClick={() => {
                remove.reset()
                deleteKey.current = null
                setDeleteOpen(false)
              }}
            >
              취소
            </Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              {remove.isPending ? '삭제 중…' : 'Course 삭제'}
            </Button>
          </>
        }
      >
        <p>
          학생은 더 이상 이 Course와 완료 기록에 접근할 수 없습니다. private
          PDF·녹음 파일은 별도 worker가 정리합니다.
        </p>
        {remove.isError && (
          <p className="form-error" role="alert">
            {remove.error instanceof ApiError &&
            remove.error.code === 'COURSE_HAS_ACTIVE_SESSION'
              ? '다른 탭에서 active class가 만들어졌습니다. Course 상태를 다시 확인해 주세요.'
              : 'Course를 삭제하지 못했습니다. 현재 정보는 유지되었습니다.'}
          </p>
        )}
      </Dialog>
    </div>
  )
}
