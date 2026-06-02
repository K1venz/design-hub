import { Loader2Icon } from 'lucide-react'

import { BrandMark } from '@/components/brand/Wordmark'

export function FullPageLoader({ label = '载入中…' }: { label?: string }) {
  return (
    <div className="paper-grain flex min-h-svh flex-col items-center justify-center gap-5 bg-background">
      <div className="relative">
        <BrandMark className="size-11 opacity-90" />
        <Loader2Icon className="text-primary/70 absolute -right-1.5 -bottom-1.5 size-4 animate-spin" />
      </div>
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  )
}
