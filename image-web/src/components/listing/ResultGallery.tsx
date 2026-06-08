import { DownloadIcon } from 'lucide-react'
import { motion } from 'motion/react'

import { PipelineBeam } from '@/components/listing/PipelineBeam'
import { downloadImage } from '@/lib/download'

export interface ResultSlot {
  url: string | null // null = generating
}

interface ResultGalleryProps {
  title: string
  slots: ResultSlot[]
  done: number
  total: number
  generating: boolean
}

export function ResultGallery({ title, slots, done, total, generating }: ResultGalleryProps) {
  const ready = slots.filter((s) => s.url)
  return (
    <div className="flex-1 overflow-auto p-6 lg:px-8">
      <div className="mb-3.5 flex items-center justify-between">
        <h2 className="text-[22px] font-semibold">{title}</h2>
        {ready.length > 0 && (
          <button
            onClick={() => ready.forEach((s, i) => void downloadImage(s.url!, `listing-${i + 1}.png`))}
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
            <PipelineBeam />
            <p className="text-[14px] text-[#bdb6ab]">上传产品图、写下卖点，点「开始出图」</p>
          </div>
        </div>
      ) : (
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
                  onClick={() => void downloadImage(s.url!, `listing-${i + 1}.png`)}
                  className="absolute bottom-2.5 right-2.5 rounded-[10px] bg-[#2c2824]/90 px-3 py-1.5 text-[12.5px] text-white opacity-0 transition-opacity group-hover:opacity-100"
                >
                  <DownloadIcon className="mr-1 inline size-3.5" /> 下载
                </button>
              </motion.div>
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
      )}
    </div>
  )
}
