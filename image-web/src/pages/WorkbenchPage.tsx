import { FolderKanbanIcon, SparklesIcon } from 'lucide-react'

import { PagePlaceholder } from '@/components/PagePlaceholder'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { useCurrentUser } from '@/stores/auth-store'

export function WorkbenchPage() {
  const user = useCurrentUser()
  return (
    <div className="space-y-8">
      <Card className="from-primary/6 border-primary/15 animate-in fade-in-50 slide-in-from-bottom-1 relative overflow-hidden bg-gradient-to-br to-card p-7 duration-500">
        <div className="paper-grain pointer-events-none absolute inset-0 opacity-50" />
        <div className="relative flex items-center gap-2 text-sm text-primary">
          <SparklesIcon className="size-4" />
          <span>已登录 · 会话就绪</span>
        </div>
        <h2 className="font-display relative mt-3 text-2xl tracking-tight text-foreground">
          你好，{user.name}
        </h2>
        <p className="relative mt-1.5 flex items-center gap-2 text-sm text-muted-foreground">
          <Badge variant="secondary" className="font-medium">
            {user.role}
          </Badge>
          {user.dept && <span>{user.dept}</span>}
          <span className="text-muted-foreground/60">·</span>
          <span className="font-mono text-xs">{user.user_id}</span>
        </p>
      </Card>

      <PagePlaceholder
        icon={FolderKanbanIcon}
        title="项目工作台"
        description="一单一档：客户 / 项目 / 4 态状态机 / 标准化需求单 / 出图配置。从这里发起出图、选稿、改稿、交付。"
        endpoints={['/customers*', '/projects*', '/projects/{id}/brief']}
        pkg="FE-1 / FE-2"
      />
    </div>
  )
}
