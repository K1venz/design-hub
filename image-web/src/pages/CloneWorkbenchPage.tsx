import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useListingClone, useListingEvents } from '@/api/listing'
import { CloneConfigPanel, type CloneConfig } from '@/components/listing/CloneConfigPanel'
import { ResultGallery, type ResultSlot } from '@/components/listing/ResultGallery'
import { newTaskBus } from '@/components/listing/new-task-bus'
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
      }),
    [],
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
      setJobId(null)
    }
  })

  async function onGenerate() {
    setSlots([{ url: null }])
    setDone(0)
    try {
      const { job_id } = await clone.mutateAsync({
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
      toast.error(err instanceof Error ? err.message : '复刻请求失败')
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
      />
    </>
  )
}
