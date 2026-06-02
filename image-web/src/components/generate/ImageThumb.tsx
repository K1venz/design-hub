import { useState } from 'react'
import { ImageIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 候选图/素材缩略图。可渲染源：http(s)/data/blob。
 * 后端暂无 HTTP 图床（ISSUE-0016）：`mock://` 无字节 → 占位；`file://` 仅 **开发期**
 * 经 Vite 本地图床中间件 `/__localimg` 显示真图（见 vite.config）。生产待后端图床。
 */
function toSrc(url: string): string | null {
  if (/^(https?:|data:|blob:)/.test(url)) return url
  if (import.meta.env.DEV && url.startsWith('file://')) {
    return `/__localimg?p=${encodeURIComponent(url.slice('file://'.length))}`
  }
  return null
}

export function ImageThumb({ url, className }: { url: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  const src = toSrc(url)

  if (!src || failed) {
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
      src={src}
      onError={() => setFailed(true)}
      className={cn('object-cover', className)}
      alt=""
    />
  )
}
