import { useState } from 'react'
import { ImageIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 候选图/素材缩略图：仅 http(s)/data/blob 可渲染。
 * 后端当前落 `mock://` / `file://`（无 HTTP 图床，见 ISSUE-0016）→ 占位图标。
 * 后端补静态图床后自动显示真图。
 */
export function ImageThumb({ url, className }: { url: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  const renderable = /^(https?:|data:|blob:)/.test(url)

  if (!renderable || failed) {
    return (
      <div
        className={cn(
          'bg-muted/60 text-muted-foreground flex items-center justify-center',
          className,
        )}
      >
        <ImageIcon className="size-7" strokeWidth={1.5} />
      </div>
    )
  }
  return (
    <img
      src={url}
      onError={() => setFailed(true)}
      className={cn('object-cover', className)}
      alt=""
    />
  )
}
