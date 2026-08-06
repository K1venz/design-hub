import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  isModelUnavailableError,
  useListingClone,
  useListingEvents,
} from '@/api/listing'
import { CloneConfigPanel, type CloneConfig } from '@/components/listing/CloneConfigPanel'
import { ResultGallery } from '@/components/listing/ResultGallery'
import type { ResultSlot } from '@/lib/listing'
import { newTaskBus } from '@/components/listing/new-task-bus'
import { useEditEntries } from '@/components/listing/use-edit-entries'
import {
  requireSelectedImageModel,
  useImageModelSelection,
} from '@/components/models/image-model-context'
import { ImageModelSelector } from '@/components/models/ImageModelSelector'
import { DEFAULT_CLONE_MODE, DEFAULT_LISTING_CONFIG, type UploadedImage } from '@/lib/listing'

const DEFAULT_CLONE_CONFIG: CloneConfig = {
  modifiers: DEFAULT_LISTING_CONFIG.modifiers,
  ratio: '1:1',
  cloneMode: DEFAULT_CLONE_MODE,
  prompt: '',
}

/** 爆款图复刻工作台：双角色上传（产品 1 + 参考 1~2）→ 两档复刻 → 1 张产出（复用 SSE/画廊）。 */
export function CloneWorkbenchPage() {
  const [config, setConfig] = useState<CloneConfig>(DEFAULT_CLONE_CONFIG)
  const [product, setProduct] = useState<UploadedImage[]>([])
  const [references, setReferences] = useState<UploadedImage[]>([])
  const [resetKey, setResetKey] = useState(0)
  const [jobId, setJobId] = useState<string | null>(null)
  const [slots, setSlots] = useState<ResultSlot[]>([])
  const [done, setDone] = useState(0)
  const clone = useListingClone()
  const modelSelection = useImageModelSelection()
  const editEntries = useEditEntries(setSlots)

  useEffect(
    () =>
      newTaskBus.subscribe(() => {
        setConfig(DEFAULT_CLONE_CONFIG)
        setProduct([])
        setReferences([])
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
      setSlots((prev) => {
        const i = prev.findIndex((s) => s.url === null && !s.error)
        if (i < 0) return prev
        const next = [...prev]
        next[i] = { ...next[i], url: e.url }
        return next
      })
      setDone((d) => d + 1)
    } else if (e.kind === 'image_failed') {
      setSlots((prev) => {
        const i = prev.findIndex((s) => s.url === null && !s.error)
        if (i < 0) return prev
        const next = [...prev]
        next[i] = { ...next[i], error: e.error }
        return next
      })
    } else if (e.kind === 'failed') {
      toast.error(`复刻失败：${e.error}`)
      setJobId(null)
    } else if (e.kind === 'completed') {
      if (jobId) editEntries.markCompleted(jobId)
      setJobId(null)
    }
  })

  async function onGenerate() {
    const imageModel = requireSelectedImageModel(modelSelection)
    editEntries.reset()
    setSlots([{ url: null }])
    setDone(0)
    try {
      const { job_id } = await clone.mutateAsync({
        imageModel,
        productUploadIds: product.map((u) => u.id),
        referenceUploadIds: references.map((u) => u.id),
        cloneMode: config.cloneMode,
        prompt: config.prompt,
        ratio: config.ratio,
        modifiers: config.modifiers,
      })
      setJobId(job_id)
    } catch (err) {
      setSlots([])
      if (isModelUnavailableError(err)) {
        modelSelection.retry()
        toast.error('刚选择的图片模型已不可用，表单已保留，请重新选择。')
      } else {
        toast.error(err instanceof Error ? err.message : '复刻请求失败')
      }
    }
  }

  const generating = clone.isPending || jobId !== null

  return (
    <>
      <CloneConfigPanel
        key={resetKey}
        config={config}
        product={product}
        references={references}
        pending={generating}
        modelReady={modelSelection.state === 'ready'}
        modelSelector={
          <ImageModelSelector
            selection={modelSelection}
            disabled={generating}
          />
        }
        onConfigChange={setConfig}
        onProductChange={setProduct}
        onReferencesChange={setReferences}
        onGenerate={onGenerate}
      />
      <ResultGallery
        title="爆款图复刻"
        slots={slots}
        done={done}
        total={slots.length}
        generating={generating}
        emptyHint="上传产品图与参考爆款图，点「开始复刻」"
        resultLabel="复刻成品"
        editJobId={editEntries.completedJobId}
      />
    </>
  )
}
