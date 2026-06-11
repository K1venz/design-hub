import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'

import { useListingJob } from '@/api/listing'
import type { ResultSlot } from '@/components/listing/ResultGallery'
import { mergeSlotsWithDetail } from '@/lib/listing'

/**
 * 结果区「基于此图再编辑」入口（ISSUE-0040）：task_completed 后补拉 job 详情
 * （复用 useListingJob 同一 GET，零新端点），把 image_key 合并进槽位 → 每张成功
 * 槽可挂编辑入口。补拉失败 fail-soft：槽位维持 SSE 态、入口不出现，不打断主流程。
 */
export function useEditEntries(setSlots: Dispatch<SetStateAction<ResultSlot[]>>) {
  const [completedJobId, setCompletedJobId] = useState<string | null>(null)
  const detail = useListingJob(completedJobId ?? undefined)
  const mergedFor = useRef<string | null>(null)

  useEffect(() => {
    const d = detail.data
    if (!d || !completedJobId || d.job_id !== completedJobId) return
    if (mergedFor.current === completedJobId) return
    mergedFor.current = completedJobId
    setSlots((prev) => mergeSlotsWithDetail(prev, d.images))
  }, [detail.data, completedJobId, setSlots])

  const markCompleted = useCallback((jobId: string) => setCompletedJobId(jobId), [])
  const reset = useCallback(() => {
    setCompletedJobId(null)
    mergedFor.current = null
  }, [])

  return { completedJobId: completedJobId ?? undefined, markCompleted, reset }
}
