import { useRef, useState } from 'react'
import { ImageUpIcon, ImageIcon } from 'lucide-react'
import { toast } from 'sonner'

import { useAssets, useUploadAsset, type AssetKind } from '@/api/assets'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const KIND_TONE: Record<AssetKind, string> = {
  产品图: 'bg-teal-50 text-teal-700 border-teal-200',
  参考图: 'bg-amber-50 text-amber-700 border-amber-200',
}

function filename(url: string): string {
  return url.split(/[/\\]/).pop() || url
}

export function AssetPanel({ projectId }: { projectId: number }) {
  const assets = useAssets(projectId)
  const upload = useUploadAsset(projectId)
  const [kind, setKind] = useState<AssetKind>('产品图')
  const fileRef = useRef<HTMLInputElement>(null)

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) {
      try {
        await upload.mutateAsync({ file, kind })
        toast.success(`已上传「${kind}」${file.name}`)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '上传素材失败')
      }
    }
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <Card className="space-y-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-foreground">素材</h3>
          <p className="text-xs text-muted-foreground">上传产品图（图生图保真源）与参考图。</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={kind} onValueChange={(v) => setKind(v as AssetKind)}>
            <SelectTrigger size="sm" className="w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="产品图">产品图</SelectItem>
              <SelectItem value="参考图">参考图</SelectItem>
            </SelectContent>
          </Select>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => void onPick(e)}
          />
          <Button
            size="sm"
            disabled={upload.isPending}
            onClick={() => fileRef.current?.click()}
          >
            <ImageUpIcon className="size-4" />
            {upload.isPending ? '上传中…' : '上传'}
          </Button>
        </div>
      </div>

      {assets.isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : assets.data && assets.data.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {assets.data.map((a) => (
            <div key={a.id} className="border-border/70 overflow-hidden rounded-lg border">
              <div className="bg-muted/50 text-muted-foreground flex h-20 items-center justify-center">
                <ImageIcon className="size-6" strokeWidth={1.6} />
              </div>
              <div className="space-y-1 p-2">
                <Badge variant="outline" className={KIND_TONE[a.kind]}>
                  {a.kind}
                </Badge>
                <p className="text-muted-foreground truncate text-[11px]" title={filename(a.url)}>
                  {filename(a.url)}
                </p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-muted-foreground rounded-lg border border-dashed py-10 text-center text-sm">
          还没有素材，上传产品图开始。
        </div>
      )}
    </Card>
  )
}
