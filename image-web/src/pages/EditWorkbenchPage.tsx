import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { useListingEdit, useListingEvents, useListingJob } from '@/api/listing'
import { EditConfigPanel, type EditConfig, type EditSource } from '@/components/listing/EditConfigPanel'
import { ResultGallery, type ResultSlot } from '@/components/listing/ResultGallery'
import { newTaskBus } from '@/components/listing/new-task-bus'
import { useEditEntries } from '@/components/listing/use-edit-entries'
import {
  DEFAULT_EDIT_MODE, DEFAULT_LISTING_CONFIG, IMAGE_SUCCESS_STATUS, RATIOS,
  type ListingJobDetail, type Ratio,
} from '@/lib/listing'

/** 编辑表单种子：ratio/modifiers 预填父 job（「不动 = 继承」），无父时退全局默认。 */
function seedConfig(d: ListingJobDetail | undefined): EditConfig {
  const ratio =
    d && (RATIOS as readonly string[]).includes(d.ratio) ? (d.ratio as Ratio) : DEFAULT_LISTING_CONFIG.ratio
  return {
    editMode: DEFAULT_EDIT_MODE,
    prompt: '',
    ratio,
    modifiers: { ...DEFAULT_LISTING_CONFIG.modifiers, ...(d?.modifiers ?? {}) },
  }
}

/** 二次编辑工作台：源图只读（路由定上下文）→ 微调/重做 → 1 张产出（复用 SSE/画廊）。
 *  路由 /edit/:jobId/:imageKey——jobId 纯前端上下文（拉父详情定位源图/预填），
 *  请求体只带 source_image_key（owner/parent 链服务端反解，终契约 #657/#659）。 */
export function EditWorkbenchPage() {
  const { jobId, imageKey } = useParams<{ jobId: string; imageKey: string }>()
  const parent = useListingJob(jobId)
  const d = parent.data

  const [config, setConfig] = useState<EditConfig>(() => seedConfig(undefined))
  const [jobIdRunning, setJobIdRunning] = useState<string | null>(null)
  const [slots, setSlots] = useState<ResultSlot[]>([])
  const [done, setDone] = useState(0)
  const edit = useListingEdit()
  const editEntries = useEditEntries(setSlots)

  // 父详情到达后按父值播种一次（per 父 job）；「新建任务」重置回同一种子（源图随路由保留）
  const seededFor = useRef<string | null>(null)
  useEffect(() => {
    if (d && seededFor.current !== d.job_id) {
      seededFor.current = d.job_id
      setConfig(seedConfig(d))
    }
  }, [d])
  useEffect(
    () =>
      newTaskBus.subscribe(() => {
        setConfig(seedConfig(parent.data))
        setJobIdRunning(null)
        setSlots([])
        setDone(0)
        editEntries.reset()
      }),
    [parent.data, editEntries],
  )

  // 仅成功张可作源（失败张前端无入口 + 后端 404 双层，Q-δ）
  const sourceImg = d?.images.find(
    (img) => img.image_key === imageKey && img.status === IMAGE_SUCCESS_STATUS,
  )
  const source: EditSource | null =
    d && sourceImg
      ? {
          url: sourceImg.url,
          imageType: sourceImg.image_type ?? undefined,
          jobId: d.job_id,
          parentRatio: d.ratio,
        }
      : null

  useListingEvents(jobIdRunning, (e) => {
    if (e.kind === 'image') {
      setSlots((prev) => (prev.length ? [{ ...prev[0], url: e.url }] : prev))
      setDone(1)
    } else if (e.kind === 'image_failed') {
      setSlots((prev) => (prev.length ? [{ ...prev[0], error: e.error }] : prev))
    } else if (e.kind === 'failed') {
      toast.error(`编辑失败：${e.error}`)
      setJobIdRunning(null)
    } else if (e.kind === 'completed') {
      // 编辑成品自己也可再编辑 → 连续迭代页内闭环
      if (jobIdRunning) editEntries.markCompleted(jobIdRunning)
      setJobIdRunning(null)
    }
  })

  async function onGenerate() {
    if (!imageKey) return
    editEntries.reset()
    setSlots([{ url: null }])
    setDone(0)
    try {
      const { job_id } = await edit.mutateAsync({
        sourceImageKey: imageKey,
        editMode: config.editMode,
        prompt: config.prompt,
        ratio: config.ratio,
        modifiers: config.modifiers,
      })
      setJobIdRunning(job_id)
    } catch (err) {
      setSlots([])
      toast.error(err instanceof Error ? err.message : '编辑请求失败')
    }
  }

  // 非本人 / 不存在 → 详情 404（anti-enum 同口径），复用历史详情的空态文案
  if (parent.isError) {
    return (
      <div className="grid flex-1 place-items-center p-6">
        <div className="rounded-2xl border border-[#ece8e2] bg-white p-10 text-center text-sm text-[#8a857e]">
          任务不存在或无权查看。
          <Link to="/history" className="ml-2 text-[#4733b8] hover:underline">
            返回历史
          </Link>
        </div>
      </div>
    )
  }
  if (parent.isLoading) {
    return (
      <div className="grid flex-1 place-items-center">
        <div className="size-7 animate-spin rounded-full border-[3px] border-[#e7e0d6] border-t-[#7c6cff]" />
      </div>
    )
  }

  const generating = edit.isPending || jobIdRunning !== null

  return (
    <>
      <EditConfigPanel
        config={config}
        source={source}
        pending={generating}
        onConfigChange={setConfig}
        onGenerate={onGenerate}
      />
      <ResultGallery
        title="二次编辑"
        slots={slots}
        done={done}
        total={slots.length}
        generating={generating}
        emptyHint="确认源图、写下新要求，点「开始编辑」"
        resultLabel="编辑成品"
        editJobId={editEntries.completedJobId}
      />
    </>
  )
}
