import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useListingGenerate, useListingSetGenerate, useListingEvents } from '@/api/listing'
import { ListingConfigPanel } from '@/components/listing/ListingConfigPanel'
import { ResultGallery, type ResultSlot } from '@/components/listing/ResultGallery'
import { newTaskBus } from '@/components/listing/new-task-bus'
import { useEditEntries } from '@/components/listing/use-edit-entries'
import {
  DEFAULT_LISTING_CONFIG, IMAGE_TYPE_FIELDS,
  type ListingConfig, type UploadedImage,
} from '@/lib/listing'

/** 商品套图工作台：左配置 / 右画布。单图（n=1 verified 流）/ 套图（plan 流）双模式；
 *  两步流——先上传预览(uploaded)，出图带 upload_ids；SSE 逐张到达（套图按图型落组）。 */
export function WorkbenchPage() {
  const [config, setConfig] = useState<ListingConfig>(DEFAULT_LISTING_CONFIG)
  const [uploaded, setUploaded] = useState<UploadedImage[]>([])
  const [resetKey, setResetKey] = useState(0) // bump → 重挂 ConfigPanel 清空上传器内部态
  const [jobId, setJobId] = useState<string | null>(null)
  const [slots, setSlots] = useState<ResultSlot[]>([])
  const [done, setDone] = useState(0)
  const generate = useListingGenerate()
  const generateSet = useListingSetGenerate()
  const editEntries = useEditEntries(setSlots)

  // 「新建任务」：清空一切回到初始
  useEffect(
    () =>
      newTaskBus.subscribe(() => {
        setConfig(DEFAULT_LISTING_CONFIG)
        setUploaded([])
        setResetKey((k) => k + 1)
        setJobId(null)
        setSlots([])
        setDone(0)
        editEntries.reset()
      }),
    [editEntries],
  )

  useListingEvents(jobId, (e) => {
    if (e.kind === 'image') {
      // 套图带 image_type 填该组首个空槽；单图无标签按到达序填
      setSlots((prev) => {
        const i = prev.findIndex(
          (s) => s.url === null && !s.error && (e.imageType ? s.imageType === e.imageType : true),
        )
        if (i < 0) return prev
        const next = [...prev]
        next[i] = { ...next[i], url: e.url }
        return next
      })
      setDone((d) => d + 1)
    } else if (e.kind === 'image_failed') {
      // 单张失败：标记该组首个待出槽（原因可见；MVP 无单张重试）
      setSlots((prev) => {
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
      setJobId(null)
    } else if (e.kind === 'completed') {
      // 完成态补拉详情合并 image_key → 结果区挂「基于此图再编辑」（ISSUE-0040）
      if (jobId) editEntries.markCompleted(jobId)
      setJobId(null)
    }
  })

  async function onGenerate() {
    editEntries.reset()
    const isSet = config.mode === 'set'
    // 预铺槽位：套图按图型分组顺序铺（带标签），单图铺 n 个无标签槽
    const planned: ResultSlot[] = isSet
      ? IMAGE_TYPE_FIELDS.flatMap((f) =>
          Array.from({ length: config.plan[f.key] }, () => ({ url: null, imageType: f.key }) as ResultSlot),
        )
      : Array.from({ length: config.n }, () => ({ url: null }))
    setSlots(planned)
    setDone(0)
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
      setJobId(job_id)
    } catch (err) {
      setSlots([])
      toast.error(err instanceof Error ? err.message : '出图请求失败')
    }
  }

  const generating = generate.isPending || generateSet.isPending || jobId !== null
  // 以已铺槽位为准（防止生成中改步进器导致进度分母漂移）
  const total = slots.length

  return (
    <>
      <ListingConfigPanel
        key={resetKey}
        config={config}
        uploaded={uploaded}
        pending={generating}
        onConfigChange={setConfig}
        onUploadedChange={setUploaded}
        onGenerate={onGenerate}
      />
      <ResultGallery
        title="商品套图"
        slots={slots}
        done={done}
        total={total}
        generating={generating}
        editJobId={editEntries.completedJobId}
      />
    </>
  )
}
