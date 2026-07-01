import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  useListingGenerate,
  useListingSetGenerate,
  useListingEvents,
  useListingJobs,
  useListingJob,
} from '@/api/listing'
import { ListingConfigPanel } from '@/components/listing/ListingConfigPanel'
import { ResultGallery, type ResultSlot } from '@/components/listing/ResultGallery'
import { newTaskBus } from '@/components/listing/new-task-bus'
import {
  detailToResultSlots,
  IMAGE_TYPE_FIELDS,
  type ListingJobDetail,
  type ListingJobSummary,
} from '@/lib/listing'
import { useWorkbenchStore } from '@/stores/workbench-store'

/** 商品套图工作台：左配置 / 右画布。单图（n=1 verified 流）/ 套图（plan 流）双模式。
 *
 *  结果区 = 当前登录账号「最近一单」listing_job 的实时视图（2026-07-01 设计稿）：
 *   - 进入/F5：GET /listing/jobs?limit=1 取最近一单 → 详情对账（终态权威快照）→ 渲染结果/失败/空态。
 *   - 发起新一单：generate 返回 job_id 即成为进行中视图 + 订阅 SSE 逐张点亮；完成后失效刷新
 *     最近一单查询，由服务端详情接手（自带 image_key → 「基于此图再编辑」入口）。
 *  源在服务端故终态结果整页刷新不丢；进行中态靠 store 即时态跨页续播（F5 回落最近一单）。 */
export function WorkbenchPage() {
  const config = useWorkbenchStore((s) => s.config)
  const setConfig = useWorkbenchStore((s) => s.setConfig)
  const uploaded = useWorkbenchStore((s) => s.uploaded)
  const setUploaded = useWorkbenchStore((s) => s.setUploaded)
  const resetKey = useWorkbenchStore((s) => s.resetKey)
  const activeJobId = useWorkbenchStore((s) => s.activeJobId)
  const activeSlots = useWorkbenchStore((s) => s.activeSlots)
  const activeDone = useWorkbenchStore((s) => s.activeDone)
  const activeGenerating = useWorkbenchStore((s) => s.activeGenerating)
  const setActiveJobId = useWorkbenchStore((s) => s.setActiveJobId)
  const setActiveSlots = useWorkbenchStore((s) => s.setActiveSlots)
  const setActiveDone = useWorkbenchStore((s) => s.setActiveDone)
  const setActiveGenerating = useWorkbenchStore((s) => s.setActiveGenerating)
  const startActive = useWorkbenchStore((s) => s.startActive)
  const clearActive = useWorkbenchStore((s) => s.clearActive)
  const resetWorkbench = useWorkbenchStore((s) => s.reset)
  const generate = useListingGenerate()
  const generateSet = useListingSetGenerate()
  const qc = useQueryClient()

  // 「最近一单」= 账号本人时间倒序首条（服务端源，F5 不丢）。
  const latest = useListingJobs(1, 0)
  const latestJob = latest.data?.[0]
  // 视图 job：本会话进行中的一单优先，否则回落服务端最近一单。
  const viewJobId = activeJobId ?? latestJob?.job_id
  // 进行中单在后端终态前无历史行（详情会 404），故仅在非续播态拉详情对账。
  const detail = useListingJob(activeGenerating ? undefined : viewJobId)

  // 「新建任务」：清即时态；结果区回落最近一单/空态（不碰服务端历史）。
  useEffect(() => newTaskBus.subscribe(() => resetWorkbench()), [resetWorkbench])

  // 进行中单的 SSE 续播（仅本会话续播态订阅；完成/失败即停）。
  useListingEvents(activeGenerating ? activeJobId : null, (e) => {
    if (e.kind === 'image') {
      // 套图带 image_type 填该组首个空槽；单图无标签按到达序填
      setActiveSlots((prev) => {
        const i = prev.findIndex(
          (s) => s.url === null && !s.error && (e.imageType ? s.imageType === e.imageType : true),
        )
        if (i < 0) return prev
        const next = [...prev]
        next[i] = { ...next[i], url: e.url }
        return next
      })
      setActiveDone((d) => d + 1)
    } else if (e.kind === 'image_failed') {
      // 单张失败：标记该组首个待出槽（原因可见；MVP 无单张重试）
      setActiveSlots((prev) => {
        const i = prev.findIndex(
          (s) => s.url === null && !s.error && (e.imageType ? s.imageType === e.imageType : true),
        )
        if (i < 0) return prev
        const next = [...prev]
        next[i] = { ...next[i], error: e.error }
        return next
      })
    } else if (e.kind === 'failed') {
      toast.error(`出图失败：${e.error}`)
      setActiveGenerating(false)
      void qc.invalidateQueries({ queryKey: ['listing', 'jobs'] })
    } else if (e.kind === 'completed') {
      // 终态权威快照落库：停续播 + 失效最近一单 → 服务端详情接手（自带 image_key）
      setActiveGenerating(false)
      void qc.invalidateQueries({ queryKey: ['listing', 'jobs'] })
    }
  })

  async function onGenerate() {
    const isSet = config.mode === 'set'
    // 预铺槽位：套图按图型分组顺序铺（带标签），单图铺 n 个无标签槽
    const planned: ResultSlot[] = isSet
      ? IMAGE_TYPE_FIELDS.flatMap((f) =>
          Array.from({ length: config.plan[f.key] }, () => ({ url: null, imageType: f.key }) as ResultSlot),
        )
      : Array.from({ length: config.n }, () => ({ url: null }))
    startActive(planned)
    try {
      const { job_id } = isSet
        ? await generateSet.mutateAsync({
            uploadIds: uploaded.map((u) => u.id),
            prompt: config.prompt,
            ratio: config.ratio,
            plan: config.plan,
            overlayTexts: config.overlayTexts,
            modifiers: config.modifiers,
          })
        : await generate.mutateAsync({
            uploadIds: uploaded.map((u) => u.id),
            prompt: config.prompt,
            ratio: config.ratio,
            n: config.n,
            modifiers: config.modifiers,
          })
      setActiveJobId(job_id)
    } catch (err) {
      clearActive()
      toast.error(err instanceof Error ? err.message : '出图请求失败')
    }
  }

  const pending = generate.isPending || generateSet.isPending || activeGenerating
  const view = deriveView({
    activeGenerating,
    activeJobId,
    activeSlots,
    activeDone,
    viewJobId,
    detail: detail.data,
    detailError: detail.isError,
    latestJob,
  })

  return (
    <>
      <ListingConfigPanel
        key={resetKey}
        config={config}
        uploaded={uploaded}
        pending={pending}
        onConfigChange={setConfig}
        onUploadedChange={setUploaded}
        onGenerate={onGenerate}
      />
      <ResultGallery
        title="商品套图"
        slots={view.slots}
        done={view.done}
        total={view.slots.length}
        generating={activeGenerating}
        editJobId={view.editJobId}
      />
    </>
  )
}

/** 结果区槽位来源判定（进行中即时态 / 服务端详情 / 恢复占位 / 空态），保持 ResultGallery 纯展示。 */
function deriveView(args: {
  activeGenerating: boolean
  activeJobId: string | null
  activeSlots: ResultSlot[]
  activeDone: number
  viewJobId: string | undefined
  detail: ListingJobDetail | undefined
  detailError: boolean
  latestJob: ListingJobSummary | undefined
}): { slots: ResultSlot[]; done: number; editJobId: string | undefined } {
  const { activeGenerating, activeJobId, activeSlots, activeDone, viewJobId, detail, detailError, latestJob } = args
  if (activeGenerating) {
    // 本会话续播中：进行中槽位 + 进度。
    return { slots: activeSlots, done: activeDone, editJobId: undefined }
  }
  if (detailError) {
    // owner 隔离 404 / 详情不可达 → fail-soft 空态，不白屏。
    return { slots: [], done: 0, editJobId: undefined }
  }
  if (detail && detail.job_id === viewJobId) {
    // 终态权威快照：成功图（带 image_key → 编辑入口）/ 整单失败合成失败槽。
    const slots = detailToResultSlots(detail) as ResultSlot[]
    return { slots, done: slots.filter((s) => s.url).length, editJobId: detail.job_id }
  }
  if (activeJobId) {
    // 本会话刚完成、详情接手前：保留已累积槽位（避免闪空），编辑入口待详情到达。
    return { slots: activeSlots, done: activeSlots.filter((s) => s.url).length, editJobId: undefined }
  }
  if (viewJobId) {
    // 恢复中（详情加载）：按最近一单已出张数预铺 shimmer 占位，避免闪空态。
    const n = Math.max(latestJob?.image_count ?? 1, 1)
    return { slots: Array.from({ length: n }, () => ({ url: null }) as ResultSlot), done: 0, editJobId: undefined }
  }
  // 新账号 / 从未出图：空态。
  return { slots: [], done: 0, editJobId: undefined }
}
