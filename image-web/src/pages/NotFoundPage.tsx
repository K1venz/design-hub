import { Link } from 'react-router-dom'
import { CompassIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <div className="paper-grain flex min-h-svh flex-col items-center justify-center gap-5 bg-background px-6 text-center">
      <div className="bg-primary/8 text-primary flex size-16 items-center justify-center rounded-2xl">
        <CompassIcon className="size-8" strokeWidth={1.6} />
      </div>
      <div className="space-y-1.5">
        <p className="font-display text-5xl text-foreground">404</p>
        <h1 className="text-lg font-semibold text-foreground">页面不存在</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          你访问的地址没有对应页面，可能已移动或尚未实现。
        </p>
      </div>
      <Button asChild variant="outline">
        <Link to="/">返回首页</Link>
      </Button>
    </div>
  )
}
