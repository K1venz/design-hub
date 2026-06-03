import { useRef } from 'react'
import {
  CheckIcon,
  EyeIcon,
  FileTextIcon,
  type LucideIcon,
  PackageCheckIcon,
  PaletteIcon,
} from 'lucide-react'

import { AnimatedBeam } from '@/components/visual/AnimatedBeam'
import { PROJECT_STATUSES, type ProjectStatus } from '@/lib/project-status'
import { cn } from '@/lib/utils'

const ICONS: Record<ProjectStatus, LucideIcon> = {
  需求录入: FileTextIcon,
  设计中: PaletteIcon,
  客户审稿: EyeIcon,
  已交付: PackageCheckIcon,
}

/**
 * 项目状态流水线：4 节点 + 节点间发光流动光束。
 * 已走过的段点亮（光束流动），未到的段静态暗线；当前节点渐变高亮 + 光圈。
 */
export function ProjectPipeline({ current }: { current: ProjectStatus }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const n0 = useRef<HTMLDivElement>(null)
  const n1 = useRef<HTMLDivElement>(null)
  const n2 = useRef<HTMLDivElement>(null)
  const n3 = useRef<HTMLDivElement>(null)
  const nodeRefs = [n0, n1, n2, n3]
  const currentIdx = PROJECT_STATUSES.indexOf(current)

  return (
    <div ref={containerRef} className="relative flex w-full max-w-md items-start justify-between">
      {PROJECT_STATUSES.slice(0, -1).map((_, i) => (
        <AnimatedBeam
          key={i}
          containerRef={containerRef}
          fromRef={nodeRefs[i]}
          toRef={nodeRefs[i + 1]}
          active={currentIdx >= i + 1}
          pathWidth={2.5}
          duration={3}
          delay={i * 0.4}
        />
      ))}
      {PROJECT_STATUSES.map((s, i) => {
        const Icon = ICONS[s]
        const passed = currentIdx > i
        const active = currentIdx === i
        return (
          <div key={s} className="relative z-10 flex w-16 flex-col items-center gap-2">
            <div
              ref={nodeRefs[i]}
              className={cn(
                'flex size-10 items-center justify-center rounded-full border transition-colors',
                active
                  ? 'from-primary border-transparent bg-gradient-to-br to-violet-500 text-white shadow-[0_0_0_4px_oklch(0.55_0.07_196_/_0.16)]'
                  : passed
                    ? 'border-primary/30 bg-primary/10 text-primary'
                    : 'border-border bg-card text-muted-foreground/50',
              )}
            >
              {passed ? <CheckIcon className="size-4.5" /> : <Icon className="size-4.5" />}
            </div>
            <span
              className={cn(
                'text-center text-[11px] leading-tight',
                active
                  ? 'text-foreground font-medium'
                  : passed
                    ? 'text-muted-foreground'
                    : 'text-muted-foreground/50',
              )}
            >
              {s}
            </span>
          </div>
        )
      })}
    </div>
  )
}
