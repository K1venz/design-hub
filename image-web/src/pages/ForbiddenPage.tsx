import { Link } from 'react-router-dom'
import { ShieldXIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'

export function ForbiddenPage() {
  return (
    <div className="paper-grain flex min-h-svh flex-col items-center justify-center gap-5 bg-background px-6 text-center">
      <div className="bg-destructive/8 text-destructive flex size-16 items-center justify-center rounded-2xl">
        <ShieldXIcon className="size-8" strokeWidth={1.6} />
      </div>
      <div className="space-y-1.5">
        <p className="font-display text-5xl text-foreground">403</p>
        <h1 className="text-lg font-semibold text-foreground">无权访问</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          该页面仅对管理者开放。如需权限，请联系负责人调整角色。
        </p>
      </div>
      <Button asChild variant="outline">
        <Link to="/">返回工作台</Link>
      </Button>
    </div>
  )
}
