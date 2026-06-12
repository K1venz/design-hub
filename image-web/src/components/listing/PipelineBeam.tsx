import { type ReactNode, type RefObject, useRef } from 'react'
import { ImagesIcon, SparklesIcon, UploadIcon } from 'lucide-react'

import { AnimatedBeam } from '@/components/visual/AnimatedBeam'

const GRAD_FROM = 'var(--wb-grad-from)'
const GRAD_TO = 'var(--wb-grad-to)'

function Node({
  nodeRef,
  icon,
  label,
  active,
}: {
  nodeRef: RefObject<HTMLDivElement | null>
  icon: ReactNode
  label: string
  active: boolean
}) {
  return (
    <div className="relative z-10 flex flex-col items-center gap-2">
      <div
        ref={nodeRef}
        className={`grid size-14 place-items-center rounded-2xl border bg-white text-wb-brand shadow-[0_12px_30px_-16px_rgba(60,50,40,0.3)] transition-colors duration-500 ${
          active ? 'border-wb-grad-via' : 'border-wb-line-1'
        }`}
      >
        {icon}
      </div>
      <span className="text-[12px] font-medium text-wb-ink-6">{label}</span>
    </div>
  )
}

/**
 * 出图链路光束：产品原图 → AI 出图 → 产出（默认「商品套图」，复刻页可换标签）。
 * 把空画布的留白换成有品牌感的链路图；`active` 时光束沿路径流动、节点点亮。
 */
export function PipelineBeam({
  active = true,
  resultLabel = '商品套图',
}: {
  active?: boolean
  resultLabel?: string
}) {
  const container = useRef<HTMLDivElement>(null)
  const from = useRef<HTMLDivElement>(null)
  const mid = useRef<HTMLDivElement>(null)
  const to = useRef<HTMLDivElement>(null)
  return (
    <div ref={container} className="relative flex items-center justify-center gap-20 py-4 sm:gap-28">
      <Node nodeRef={from} icon={<UploadIcon className="size-6" />} label="产品原图" active={active} />
      <Node nodeRef={mid} icon={<SparklesIcon className="size-6" />} label="AI 出图" active={active} />
      <Node nodeRef={to} icon={<ImagesIcon className="size-6" />} label={resultLabel} active={active} />
      <AnimatedBeam
        containerRef={container}
        fromRef={from}
        toRef={mid}
        active={active}
        pathWidth={2.5}
        duration={2.6}
        gradientStartColor={GRAD_FROM}
        gradientStopColor={GRAD_TO}
      />
      <AnimatedBeam
        containerRef={container}
        fromRef={mid}
        toRef={to}
        active={active}
        pathWidth={2.5}
        duration={2.6}
        delay={0.5}
        gradientStartColor={GRAD_FROM}
        gradientStopColor={GRAD_TO}
      />
    </div>
  )
}
