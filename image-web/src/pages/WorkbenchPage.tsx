import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useListingGenerate, useListingEvents } from '@/api/listing'
import { ListingConfigPanel } from '@/components/listing/ListingConfigPanel'
import { ResultGallery, type ResultSlot } from '@/components/listing/ResultGallery'
import { newTaskBus } from '@/components/listing/new-task-bus'
import { DEFAULT_LISTING_CONFIG, type ListingConfig } from '@/lib/listing'

/** 商品套图工作台：左配置 / 右画布。无 project；出图走 /listing/* 异步 + SSE。 */
export function WorkbenchPage() {
  const [config, setConfig] = useState<ListingConfig>(DEFAULT_LISTING_CONFIG)
  const [files, setFiles] = useState<File[]>([])
  const [jobId, setJobId] = useState<string | null>(null)
  const [slots, setSlots] = useState<ResultSlot[]>([])
  const [done, setDone] = useState(0)
  const generate = useListingGenerate()

  // 「新建任务」：清空一切回到初始
  useEffect(
    () =>
      newTaskBus.subscribe(() => {
        setConfig(DEFAULT_LISTING_CONFIG)
        setFiles([])
        setJobId(null)
        setSlots([])
        setDone(0)
      }),
    [],
  )

  useListingEvents(jobId, (e) => {
    if (e.kind === 'image') {
      // 后端 image_generated 不带 index：按到达顺序填第一个空槽
      setSlots((prev) => {
        const i = prev.findIndex((s) => s.url === null)
        if (i < 0) return prev
        const next = [...prev]
        next[i] = { url: e.url }
        return next
      })
      setDone((d) => d + 1)
    } else if (e.kind === 'failed') {
      toast.error(`出图失败：${e.error}`)
      setJobId(null)
    } else if (e.kind === 'completed') {
      setJobId(null)
    }
  })

  async function onGenerate() {
    setSlots(Array.from({ length: config.n }, () => ({ url: null })))
    setDone(0)
    try {
      const { job_id } = await generate.mutateAsync({
        images: files,
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

  const generating = generate.isPending || jobId !== null

  return (
    <>
      <ListingConfigPanel
        config={config}
        files={files}
        pending={generating}
        onConfigChange={setConfig}
        onFilesChange={setFiles}
        onGenerate={onGenerate}
      />
      <ResultGallery title="商品套图" slots={slots} done={done} total={config.n} generating={generating} />
    </>
  )
}
