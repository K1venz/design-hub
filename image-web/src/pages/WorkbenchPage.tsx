import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  HttpError,
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
  JOB_STATUS,
  type ListingJobDetail,
  type ListingJobSummary,
} from '@/lib/listing'
import { useWorkbenchStore } from '@/stores/workbench-store'

/** 商品套图工作台：左配置 / 右画布。单图（n=1 verified 流）/ 套图（plan 流）双模式。
 *
 *  结果区 = 当前登录账号「最近一单」listing_job 的实时视图（2026-07-01 设计稿）。
 *  后端两阶段落库后，进行中单也有行、详情返 200（status='生成中'），故状态机五分支：
 *   - 本会话续播：generate 返回 job_id → activeGenerating 订阅 SSE 逐张点亮。
 *   - 服务端进行中恢复（F5 硬刷新核心）：进入时取最近一单详情，若 status='生成中' 且非本会话
 *     正续播那单 → adoptActive 接回该 job：铺 n 张 shimmer + 订阅其 SSE 续播（回放已出图）。
 *   - 终态详情：完成/部分完成/失败 → detailToResultSlots 渲染（成功张带 image_key → 编辑入口）。
 *   - 恢复中/瞬时抖动：详情加载 or 5xx 重试 → 预铺 shimmer；持久 404（owner 隔离）→ 空态。
 *   - 空：新账号 / 从未出图。
 *  源在服务端故终态结果整页刷新不丢；进行中单 F5 后经详情对账重新 adopt 接回。 */
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
  const adoptActive = useWorkbenchStore((s) => s.adoptActive)
  const clearActive = useWorkbenchStore((s) => s.clearActive)
  const resetWorkbench = useWorkbenchStore((s) => s.reset)
  const generate = useListingGenerate()
  const generateSet = useListingSetGenerate()
  const qc = useQueryClient()

  // 「最近一单」= 账号本人时间倒序首条（服务端源，F5 不丢）。
  const latest = useListingJobs(1, 0)
  const latestJob = latest.data?.[0]
  // 视图 job：本会话进行中的一单优先（含接回态），否则回落服务端最近一单。
  const viewJobId = activeJobId ?? latestJob?.job_id
  // 续播态（本会话发起 or 已接回）由 SSE 驱动，不拉详情；其余态拉详情对账。
  const detail = useListingJob(activeGenerating ? undefined : viewJobId)
  const detailIsOwner404 = detail.error instanceof HttpError && detail.error.status === 404

  // 「新建任务」：清即时态；结果区回落最近一单/空态（不碰服务端历史）。
  useEffect(() => newTaskBus.subscribe(() => resetWorkbench()), [resetWorkbench])

  // F5 恢复：详情显示服务端还有单在跑（生成中）且非本会话正播那单 → 接回续播其 SSE。
  useEffect(() => {
    if (activeGenerating) return
    const d = detail.data
    if (d && d.status === JOB_STATUS.generating && d.job_id !== activeJobId) {
      adoptActive(d.job_id, Math.max(d.n, 1))
    }
  }, [detail.data, activeGenerating, activeJobId, adoptActive])

  // F1 释放：终态后 latest 重取已是该 job 且终态详情就位 → 释放即时态回落纯服务端驱动。
  // 时序保证无缝：viewJobId 释放前后同为该 job、终态详情分支已接管渲染，仅清内存指针。
  useEffect(() => {
    if (activeGenerating || !activeJobId) return
    const d = detail.data
    if (
      latestJob?.job_id === activeJobId &&
      d?.job_id === activeJobId &&
      d.status !== JOB_STATUS.generating
    ) {
      clearActive()
    }
  }, [activeGenerating, activeJobId, latestJob?.job_id, detail.data, clearActive])

  // 进行中单的 SSE 续播（仅本会话续播态订阅；完成/失败即停）。
  useListingEvents(activeGenerating ? activeJobId : null, (e) => {
    if (e.kind === 'image') {
      // 套图带 image_type 填该组首个空槽；单图/接回态无标签占位按到达序填。
      setActiveSlots((prev) => {
        const i = prev.findIndex((s) => canFill(s, e.imageType))
        if (i < 0) return prev
        const next = [...prev]
        next[i] = { ...next[i], url: e.url }
        return next
      })
      setActiveDone((d) => d + 1)
    } else if (e.kind === 'image_failed') {
      // 单张失败：标记该组首个待出槽（原因可见；MVP 无单张重试）
      setActiveSlots((prev) => {
        const i = prev.findIndex((s) => canFill(s, e.imageType))
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
    detailIsOwner404,
    latestJob,
    latestLoading: latest.isLoading,
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

/** SSE 到达的图能否落入某空槽：未出且未失败，且（图/槽任一无标签 或 标签相符）。
 *  套图本会话有标签占位 → 按型对位；接回态无标签占位 → 带型图按序填（不回填标签，
 *  保持无型 flat 展示，终态由详情重铺分组）。 */
function canFill(slot: ResultSlot, imageType: string | undefined): boolean {
  if (slot.url !== null || slot.error) return false
  return imageType == null || slot.imageType == null || slot.imageType === imageType
}

/** 结果区槽位来源判定（续播即时态 / 服务端终态详情 / 恢复占位 / 空态），保持 ResultGallery 纯展示。 */
function deriveView(args: {
  activeGenerating: boolean
  activeJobId: string | null
  activeSlots: ResultSlot[]
  activeDone: number
  viewJobId: string | undefined
  detail: ListingJobDetail | undefined
  detailError: boolean
  detailIsOwner404: boolean
  latestJob: ListingJobSummary | undefined
  latestLoading: boolean
}): { slots: ResultSlot[]; done: number; editJobId: string | undefined } {
  const {
    activeGenerating, activeJobId, activeSlots, activeDone, viewJobId,
    detail, detailError, detailIsOwner404, latestJob, latestLoading,
  } = args
  if (activeGenerating) {
    // 续播中（本会话发起 or 接回服务端进行中单）：进行中槽位 + 进度。
    return { slots: activeSlots, done: activeDone, editJobId: undefined }
  }
  if (detail && detail.job_id === viewJobId && detail.status !== JOB_STATUS.generating) {
    // 终态权威快照：完成/部分完成/失败（含失败张失败槽）。进行中详情不在此渲染（走接回续播）。
    const slots = detailToResultSlots(detail) as ResultSlot[]
    return { slots, done: slots.filter((s) => s.url).length, editJobId: detail.job_id }
  }
  if (activeJobId) {
    // 本会话刚终态、详情接手前：保留已累积槽位桥接（避免闪回上一单/闪空），编辑入口待详情到达。
    return { slots: activeSlots, done: activeSlots.filter((s) => s.url).length, editJobId: undefined }
  }
  if (detailError && detailIsOwner404) {
    // 持久 404（owner 隔离 / 该单确不存在）→ fail-soft 空态，不白屏。
    return { slots: [], done: 0, editJobId: undefined }
  }
  if (viewJobId) {
    // 恢复中（详情加载 / 瞬时 5xx 重试中）：按最近一单已出张数预铺 shimmer，避免闪空/白屏。
    const n = Math.max(latestJob?.image_count ?? 1, 1)
    return { slots: Array.from({ length: n }, () => ({ url: null }) as ResultSlot), done: 0, editJobId: undefined }
  }
  if (latestLoading) {
    // 首绘最近一单加载中：占位 shimmer，避免「闪空态再弹结果」。
    return { slots: [{ url: null }], done: 0, editJobId: undefined }
  }
  // 新账号 / 从未出图：空态。
  return { slots: [], done: 0, editJobId: undefined }
}
