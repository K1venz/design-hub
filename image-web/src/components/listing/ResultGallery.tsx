import { DownloadIcon, XIcon } from 'lucide-react'
import { motion } from 'motion/react'

import { PipelineBeam } from '@/components/listing/PipelineBeam'
import { downloadImage } from '@/lib/download'
import { IMAGE_TYPE_FIELDS } from '@/lib/listing'

export interface ResultSlot {
  url: string | null // null = generating（或失败，见 error）
  /** 套图流的图型标签（白底/场景/卖点）；单图流为空 → 不分组。 */
  imageType?: string
  /** 该张失败原因（image_failed 事件）；有值即失败槽。 */
  error?: string
}

interface ResultGalleryProps {
  title: string
  slots: ResultSlot[]
  done: number
  total: number
  generating: boolean
  /** 空态提示与链路末节点标签（复刻页传自己的文案）。 */
  emptyHint?: string
  resultLabel?: string
}

export function ResultGallery({
  title, slots, done, total, generating,
  emptyHint = '上传产品图、写下卖点，点「开始出图」',
  resultLabel,
}: ResultGalleryProps) {
  const ready = slots.filter((s) => s.url)
  // 套图流：任一槽带图型 → 按图型分组段渲染（顺序按 IMAGE_TYPE_FIELDS）。
  const grouped = slots.some((s) => s.imageType)
  const groups = grouped
    ? IMAGE_TYPE_FIELDS.map((f) => ({
        field: f,
        slots: slots.filter((s) => s.imageType === f.key),
      })).filter((g) => g.slots.length > 0)
    : []

  return (
    <div className="flex-1 overflow-auto p-6 lg:px-8">
      <div className="mb-3.5 flex items-center justify-between">
        <h2 className="text-[22px] font-semibold">{title}</h2>
        {ready.length > 0 && (
          <button
            onClick={() =>
              ready.forEach((s, i) => void downloadImage(s.url!, `${s.imageType ?? 'listing'}-${i + 1}.png`))
            }
            className="rounded-[10px] border border-[#ece8e2] bg-white px-3.5 py-2 text-[13px] text-[#4a443d]"
          >
            <DownloadIcon className="mr-1 inline size-4" /> 下载全部
          </button>
        )}
      </div>

      {generating && total > 0 && (
        <>
          <div className="mb-1.5 h-1.5 overflow-hidden rounded-full bg-[#eee7df]">
            <div
              className="h-full bg-gradient-to-r from-[#7c6cff] via-[#a855f7] to-[#ff9a62] transition-[width] duration-300"
              style={{ width: `${total ? (done / total) * 100 : 0}%` }}
            />
          </div>
          <p className="mb-4 text-[12.5px] text-[#8a857e]">已出 {done} / {total} 张…</p>
        </>
      )}

      {slots.length === 0 ? (
        <div className="grid min-h-[62vh] place-items-center">
          <div className="flex flex-col items-center gap-7">
            <PipelineBeam resultLabel={resultLabel} />
            <p className="text-[14px] text-[#bdb6ab]">{emptyHint}</p>
          </div>
        </div>
      ) : grouped ? (
        <div className="space-y-6">
          {groups.map((g) => {
            const gDone = g.slots.filter((s) => s.url).length
            const gFailed = g.slots.filter((s) => s.error).length
            return (
              <section key={g.field.key}>
                <h3 className="mb-2.5 flex items-baseline gap-2 text-[14px] font-bold text-[#1c1b1a]">
                  {g.field.label}
                  <span className="text-[12px] font-normal text-[#8a857e]">
                    {gDone}/{g.slots.length}
                    {gFailed > 0 && <span className="ml-1 text-[#c2410c]">（{gFailed} 失败）</span>}
                  </span>
                </h3>
                <SlotGrid slots={g.slots} namePrefix={g.field.key} />
              </section>
            )
          })}
        </div>
      ) : (
        <SlotGrid slots={slots} namePrefix="listing" />
      )}
    </div>
  )
}

function SlotGrid({ slots, namePrefix }: { slots: ResultSlot[]; namePrefix: string }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(208px,1fr))] gap-4">
      {slots.map((s, i) =>
        s.url ? (
          <motion.div
            key={i}
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            className="group relative aspect-square overflow-hidden rounded-2xl border border-[#ece8e2] bg-white"
          >
            <img src={s.url} alt="" className="size-full object-cover" />
            <button
              onClick={() => void downloadImage(s.url!, `${namePrefix}-${i + 1}.png`)}
              className="absolute bottom-2.5 right-2.5 rounded-[10px] bg-[#2c2824]/90 px-3 py-1.5 text-[12.5px] text-white opacity-0 transition-opacity group-hover:opacity-100"
            >
              <DownloadIcon className="mr-1 inline size-3.5" /> 下载
            </button>
          </motion.div>
        ) : s.error ? (
          // 失败槽：原因可见（SSE image_failed）；MVP 无单张重试（known-limits，整单可重出）
          <div
            key={i}
            title={s.error}
            className="grid aspect-square place-items-center rounded-2xl border border-dashed border-[#f0c8b4] bg-[#fdf6f2] p-3"
          >
            <div className="text-center">
              <XIcon className="mx-auto mb-1.5 size-5 text-[#c2410c]" />
              <p className="text-[12.5px] font-medium text-[#c2410c]">生成失败</p>
              <p className="mt-1 line-clamp-2 text-[11.5px] text-[#b08968]">{s.error}</p>
            </div>
          </div>
        ) : (
          <div
            key={i}
            className="grid aspect-square place-items-center rounded-2xl border border-dashed border-[#e4ddd2] bg-[#faf8f5]"
          >
            <div className="size-7 animate-spin rounded-full border-[3px] border-[#e7e0d6] border-t-[#7c6cff]" />
          </div>
        ),
      )}
    </div>
  )
}
