import { useState, type ReactNode } from 'react'
import {
  DownloadIcon,
  ScanSearchIcon,
  SquarePenIcon,
  WallpaperIcon,
  XIcon,
} from 'lucide-react'
import { motion } from 'motion/react'
import { Link, useNavigate } from 'react-router-dom'

import { ReversePromptDialog } from '@/components/image-tools/ReversePromptDialog'
import { PipelineBeam } from '@/components/listing/PipelineBeam'
import { downloadImage } from '@/lib/download'
import type { ImageToolSource } from '@/lib/image-tools'
import { IMAGE_TYPE_FIELDS, type ResultSlot } from '@/lib/listing'

/** 出图加载中的温柔小字（按已出张数轮换，随进度自然变化）。 */
const LOADING_LINES = [
  '正在为你的商品认真打光…',
  '给画面找一个舒服的角落…',
  '光与影正在赶来…',
  '在调色盘上轻轻搅动…',
]

interface ResultGalleryProps {
  title: string
  slots: ResultSlot[]
  done: number
  total: number
  generating: boolean
  /** 空态提示与链路末节点标签（复刻页传自己的文案）。 */
  emptyHint?: string
  resultLabel?: string
  /** 已完成 job id：与 slot.imageKey 一起构成结果区编辑入口 /edit/:jobId/:imageKey。 */
  editJobId?: string
  /** 结果卡头右侧额外操作（如「查看配方」）——展示在「下载全部」左侧。 */
  headerAction?: ReactNode
}

export function ResultGallery({
  title, slots, done, total, generating,
  emptyHint = '上传产品图、写下卖点，点「开始出图」',
  resultLabel, editJobId, headerAction,
}: ResultGalleryProps) {
  const navigate = useNavigate()
  const [reverseSource, setReverseSource] =
    useState<ImageToolSource | null>(null)
  const ready = slots.filter((s) => s.url && !s.unavailable)
  // 套图流：任一槽带图型 → 按图型分组段渲染（顺序按 IMAGE_TYPE_FIELDS）。
  const grouped = slots.some((s) => s.imageType)
  const groups = grouped
    ? IMAGE_TYPE_FIELDS.map((f) => ({
        field: f,
        slots: slots.filter((s) => s.imageType === f.key),
      })).filter((g) => g.slots.length > 0)
    : []

  function openBackground(slot: ResultSlot) {
    if (slot.unavailable || !slot.imageKey || !slot.url) return
    navigate('/background', {
      state: {
        prefill: {
          source_kind: 'generated',
          source_id: slot.imageKey,
          source_url: slot.url,
        },
      },
    })
  }

  function reversePrompt(slot: ResultSlot) {
    if (slot.unavailable || !slot.imageKey) return
    setReverseSource({
      kind: 'generated',
      imageKey: slot.imageKey,
      previewUrl: slot.url ?? undefined,
    })
  }

  return (
    <div className="min-w-0 md:flex-1 md:overflow-auto">
      <div className="glass-panel mb-4 flex h-12 items-center justify-between gap-2 rounded-2xl px-5">
        <h2 className="text-[16px] font-semibold tracking-[-0.01em]">{title}</h2>
        <div className="flex items-center gap-2">
          {headerAction}
          {ready.length > 0 && (
            <button
              onClick={() =>
                ready.forEach((slot, index) => {
                  if (slot.url) {
                    void downloadImage(
                      slot.url,
                      `${slot.imageType ?? 'listing'}-${index + 1}.png`,
                    )
                  }
                })
              }
              className="rounded-full bg-wb-ink-2 px-3.5 py-1.5 text-[12.5px] font-medium text-white transition-opacity hover:opacity-90"
            >
              <DownloadIcon className="mr-1 inline size-3.5" /> 下载全部
            </button>
          )}
        </div>
      </div>

      {generating && total > 0 && (
        <>
          <div className="mb-1.5 h-1.5 overflow-hidden rounded-full bg-wb-surface-6">
            <div
              className="h-full bg-gradient-to-r from-wb-grad-from via-wb-grad-via to-wb-grad-to transition-[width] duration-300"
              style={{ width: `${total ? (done / total) * 100 : 0}%` }}
            />
          </div>
          <p className="mb-1 text-[12.5px] text-wb-ink-6">已出 {done} / {total} 张…</p>
          <p className="mb-4 text-[11.5px] text-wb-ink-7">
            {LOADING_LINES[done % LOADING_LINES.length]}
          </p>
        </>
      )}

      {slots.length === 0 ? (
        <div className="grid min-h-[62vh] place-items-center">
          <div className="flex flex-col items-center gap-7">
            <PipelineBeam resultLabel={resultLabel} />
            <p className="text-[14px] text-wb-faint-3">{emptyHint}</p>
          </div>
        </div>
      ) : grouped ? (
        <div className="space-y-6">
          {groups.map((g) => {
            const gDone = g.slots.filter(
              (s) => s.url || s.unavailable,
            ).length
            const gFailed = g.slots.filter((s) => s.error).length
            return (
              <section key={g.field.key}>
                <h3 className="mb-2.5 flex items-baseline gap-2 text-[14px] font-bold text-wb-ink-1">
                  {g.field.label}
                  <span className="text-[12px] font-normal text-wb-ink-6">
                    {gDone}/{g.slots.length}
                    {gFailed > 0 && <span className="ml-1 text-wb-red">（{gFailed} 失败）</span>}
                  </span>
                </h3>
                <SlotGrid
                  slots={g.slots}
                  namePrefix={g.field.key}
                  editJobId={editJobId}
                  onBackground={openBackground}
                  onReversePrompt={reversePrompt}
                />
              </section>
            )
          })}
        </div>
      ) : (
        <SlotGrid
          slots={slots}
          namePrefix="listing"
          editJobId={editJobId}
          onBackground={openBackground}
          onReversePrompt={reversePrompt}
        />
      )}
      <ReversePromptDialog
        source={reverseSource}
        onClose={() => setReverseSource(null)}
      />
    </div>
  )
}

function SlotGrid({
  slots,
  namePrefix,
  editJobId,
  onBackground,
  onReversePrompt,
}: {
  slots: ResultSlot[]
  namePrefix: string
  editJobId?: string
  onBackground: (slot: ResultSlot) => void
  onReversePrompt: (slot: ResultSlot) => void
}) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(208px,1fr))] gap-4">
      {slots.map((s, i) =>
        s.unavailable ? (
          <div
            key={i}
            className="grid aspect-square place-items-center rounded-2xl border border-dashed border-wb-line-3 bg-wb-surface-3 p-4"
          >
            <p className="text-center text-[12.5px] text-wb-ink-6">
              该图片暂不可用
            </p>
          </div>
        ) : s.url ? (
          <motion.div
            key={i}
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            whileHover={{ y: -3 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="group relative aspect-square overflow-hidden rounded-2xl border border-white/70 bg-white shadow-[0_6px_24px_-10px_rgba(40,40,90,.14)] transition-shadow hover:shadow-[0_14px_32px_-12px_rgba(40,40,90,.22)]"
          >
            <img src={s.url} alt="" className="size-full object-cover" />
            <div className="absolute inset-x-2 bottom-2 grid grid-cols-2 gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
              {editJobId && s.imageKey ? (
                <Link
                  to={`/edit/${editJobId}/${s.imageKey}`}
                  className="rounded-lg bg-wb-ink-2/90 px-2 py-1.5 text-center text-[11.5px] text-white"
                >
                  <SquarePenIcon className="mr-1 inline size-3" /> 继续编辑
                </Link>
              ) : (
                <span />
              )}
              {s.imageKey ? (
                <button
                  type="button"
                  onClick={() => onBackground(s)}
                  className="rounded-lg bg-wb-ink-2/90 px-2 py-1.5 text-[11.5px] text-white"
                >
                  <WallpaperIcon className="mr-1 inline size-3" /> 换背景
                </button>
              ) : (
                <span />
              )}
              {s.imageKey ? (
                <button
                  type="button"
                  onClick={() => onReversePrompt(s)}
                  className="rounded-lg bg-wb-ink-2/90 px-2 py-1.5 text-[11.5px] text-white"
                >
                  <ScanSearchIcon className="mr-1 inline size-3" /> 反推提示词
                </button>
              ) : (
                <span />
              )}
              <button
                type="button"
                onClick={() =>
                  s.url
                    ? void downloadImage(
                        s.url,
                        `${namePrefix}-${i + 1}.png`,
                      )
                    : undefined
                }
                className="rounded-lg bg-wb-ink-2/90 px-2 py-1.5 text-[11.5px] text-white"
              >
                <DownloadIcon className="mr-1 inline size-3" /> 下载
              </button>
            </div>
          </motion.div>
        ) : s.error ? (
          // 失败槽：原因可见（SSE image_failed）；MVP 无单张重试（known-limits，整单可重出）
          <div
            key={i}
            title={s.error}
            className="grid aspect-square place-items-center rounded-2xl border border-dashed border-wb-red-line bg-wb-red-tint p-3"
          >
            <div className="text-center">
              <XIcon className="mx-auto mb-1.5 size-5 text-wb-red" />
              <p className="text-[12.5px] font-medium text-wb-red">生成失败</p>
              <p className="mt-1 line-clamp-2 text-[11.5px] text-wb-warm-muted">{s.error}</p>
            </div>
          </div>
        ) : (
          <div
            key={i}
            className="shimmer grid aspect-square place-items-center rounded-2xl border border-dashed border-wb-line-3 bg-wb-surface-1"
          >
            <div className="size-7 animate-spin rounded-full border-[3px] border-wb-line-2 border-t-wb-brand" />
          </div>
        ),
      )}
    </div>
  )
}
