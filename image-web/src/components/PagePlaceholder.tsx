import type { LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'

interface PagePlaceholderProps {
  icon: LucideIcon
  title: string
  description: string
  /** 该页将消费的后端端点（契约清单 §3）. */
  endpoints?: string[]
  /** 所属前端工作包，如 "FE-1". */
  pkg?: string
}

/**
 * FE-0 骨架占位页：证明「登录→鉴权→路由→按角色导航」链路跑通；
 * 同时自文档化该页归属的工作包与契约，供 FE-1~7 接手。
 */
export function PagePlaceholder({
  icon: Icon,
  title,
  description,
  endpoints,
  pkg,
}: PagePlaceholderProps) {
  return (
    <div className="animate-in fade-in-50 slide-in-from-bottom-1 space-y-6 duration-500">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1.5">
          <h2 className="text-xl font-semibold tracking-tight text-foreground">{title}</h2>
          <p className="max-w-xl text-sm text-muted-foreground">{description}</p>
        </div>
        {pkg && (
          <Badge variant="outline" className="border-primary/30 text-primary shrink-0 font-mono">
            {pkg}
          </Badge>
        )}
      </div>

      <Card className="border-border/70 relative overflow-hidden border-dashed bg-card/60 p-8">
        <div className="paper-grain pointer-events-none absolute inset-0 opacity-60" />
        <div className="relative flex flex-col items-center gap-4 py-10 text-center">
          <div className="bg-primary/8 text-primary flex size-14 items-center justify-center rounded-2xl">
            <Icon className="size-7" strokeWidth={1.6} />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium text-foreground">骨架占位 · 待 {pkg ?? '后续'} 实现</p>
            <p className="text-xs text-muted-foreground">页面框架与导航已就绪，业务交互待接入。</p>
          </div>
          {endpoints && endpoints.length > 0 && (
            <div className="mt-2 flex max-w-lg flex-wrap items-center justify-center gap-1.5">
              {endpoints.map((e) => (
                <code
                  key={e}
                  className="bg-muted text-muted-foreground rounded-md px-2 py-1 font-mono text-[11px]"
                >
                  {e}
                </code>
              ))}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
