import { useState } from 'react'
import { Dialog as DialogPrimitive } from 'radix-ui'
import { AnimatePresence, motion, type Variants } from 'motion/react'
import { SparklesIcon, XIcon } from 'lucide-react'

import type { ShowcaseItem } from '@/api/showcase'
import { Button } from '@/components/ui/button'
import { categoryLabel, IMAGE_TYPE_FIELDS, planTotal, type SetPlan } from '@/lib/listing'

// 参考件动画（GPU 纪律：仅 transform/opacity）。容器 fade+scale + 逐行 staggerChildren spring。
const containerV: Variants = {
  hidden: { opacity: 0, scale: 0.95 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.4, ease: 'easeInOut', staggerChildren: 0.1 },
  },
  exit: { opacity: 0, scale: 0.95, transition: { duration: 0.15 } },
}
const rowV: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 100 } },
}

/**
 * showcase「查看详情」弹卡（ISSUE-0053 落点 B，用户 07-07 视觉/动画拍板 #981）：
 * 窄卡居中卡形——顶部大图 + 居中标题(caption) + 发丝分隔行列表(label 左 muted / value 右深色，
 * 末行「风格描述」无线加粗成块) + 通栏 h-12「做同款」CTA（品牌紫）。配方全项与 /set 配置项一一对应。
 * 动画=容器 fade+scale .4s + staggerChildren 0.1 逐行 spring 弹入 + AnimatePresence 开合（motion/react）。
 * 查看详情无需登录（recipe 公开、纯展示）；做同款由父级 onMakeSame 决定是否拦登录墙。
 */
export function ShowcaseDetailDialog({ item, onMakeSame }: { item: ShowcaseItem; onMakeSame: () => void }) {
  const [open, setOpen] = useState(false)
  const r = item.recipe
  const plan: SetPlan = { 白底: r.plan['白底'] ?? 0, 场景: r.plan['场景'] ?? 0, 卖点: r.plan['卖点'] ?? 0 }
  const planText =
    IMAGE_TYPE_FIELDS.filter((f) => plan[f.key] > 0)
      .map((f) => `${f.label} ×${plan[f.key]}`)
      .join('  ') + ` · 共 ${planTotal(plan)} 张`

  // 行列表（末行「风格描述」单独强调，见下），与 /set 生成界面配置项一一对应。
  const rows: { label: string; value: string }[] = [
    { label: '品类', value: categoryLabel(r.category) },
    { label: '图型配比', value: planText },
    { label: '比例', value: r.ratio },
    { label: '平台', value: r.modifiers.platform ?? '—' },
    { label: '地区 · 语言', value: `${r.modifiers.region ?? ''} · ${r.modifiers.language ?? ''}` },
  ]

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>
        <button
          type="button"
          className="flex-1 rounded-lg border border-wb-line-2 bg-white/70 px-3 py-1.5 text-[12px] font-medium text-wb-ink-3 transition-colors hover:border-wb-brand hover:text-wb-brand-deep"
        >
          查看详情
        </button>
      </DialogPrimitive.Trigger>

      <AnimatePresence>
        {open && (
          <DialogPrimitive.Portal forceMount>
            <DialogPrimitive.Overlay asChild forceMount>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm"
              />
            </DialogPrimitive.Overlay>

            <DialogPrimitive.Content asChild forceMount>
              <motion.div
                variants={containerV}
                initial="hidden"
                animate="visible"
                exit="exit"
                className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-black/5 bg-white p-6 shadow-lg outline-none"
              >
                <div className="relative mb-4 overflow-hidden rounded-xl">
                  <img
                    src={item.url}
                    alt={item.caption}
                    loading="lazy"
                    className="aspect-[4/3] w-full object-cover"
                  />
                  <span className="absolute left-2 top-2 rounded-full bg-white/85 px-2 py-0.5 text-[11px] font-medium text-wb-brand-deep backdrop-blur">
                    {item.image_type}
                  </span>
                </div>

                <DialogPrimitive.Title className="text-center text-base font-semibold text-wb-ink-1">
                  {item.caption}
                </DialogPrimitive.Title>
                <DialogPrimitive.Description className="mt-1 text-center text-[12px] text-wb-ink-6">
                  实朴真实出品 · 这套图的完整配方
                </DialogPrimitive.Description>

                <dl className="mt-4 text-[13px]">
                  {rows.map((row) => (
                    <motion.div
                      key={row.label}
                      variants={rowV}
                      className="flex items-start justify-between gap-3 border-b border-wb-line-1 py-2"
                    >
                      <dt className="shrink-0 text-wb-ink-6">{row.label}</dt>
                      <dd className="text-right font-medium text-wb-ink-2">{row.value}</dd>
                    </motion.div>
                  ))}
                  {r.styling.trim() && (
                    <motion.div variants={rowV} className="pt-3">
                      <dt className="mb-1 text-wb-ink-6">风格描述</dt>
                      <dd className="whitespace-pre-wrap font-semibold leading-relaxed text-wb-ink-1">{r.styling}</dd>
                    </motion.div>
                  )}
                </dl>

                <motion.div variants={rowV} className="mt-5">
                  <Button
                    onClick={onMakeSame}
                    size="lg"
                    className="h-12 w-full bg-wb-brand text-[14px] text-white hover:bg-wb-brand-deep"
                  >
                    <SparklesIcon /> 做同款
                  </Button>
                </motion.div>

                <DialogPrimitive.Close asChild>
                  <button
                    type="button"
                    aria-label="关闭"
                    className="absolute right-3 top-3 rounded-md bg-white/70 p-1 text-wb-ink-4 backdrop-blur transition-colors hover:text-wb-ink-1"
                  >
                    <XIcon className="size-4" />
                  </button>
                </DialogPrimitive.Close>
              </motion.div>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitive.Root>
  )
}
