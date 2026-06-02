import { useState } from 'react'
import { DownloadIcon, FileCheck2Icon } from 'lucide-react'
import { toast } from 'sonner'

import { useExport, useProjectImages, type ExportFormat } from '@/api/export'
import { ImageThumb } from '@/components/generate/ImageThumb'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

const FORMATS: ExportFormat[] = ['jpg', 'png', 'pdf']

export function ExportTab({ projectId }: { projectId: number }) {
  const images = useProjectImages(projectId)
  const exporter = useExport(projectId)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [formats, setFormats] = useState<Set<ExportFormat>>(new Set(['jpg']))
  const [resizeOn, setResizeOn] = useState(false)
  const [w, setW] = useState(800)
  const [h, setH] = useState(800)
  const [zip, setZip] = useState(true)

  function toggleImage(id: number) {
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }
  function selectKept() {
    setSelected(new Set((images.data ?? []).filter((i) => i.kept).map((i) => i.image_id)))
  }
  function toggleFormat(f: ExportFormat) {
    setFormats((s) => {
      const n = new Set(s)
      if (n.has(f)) n.delete(f)
      else n.add(f)
      return n
    })
  }

  async function run() {
    if (selected.size === 0 || formats.size === 0) return
    try {
      await exporter.mutateAsync({
        image_ids: [...selected],
        formats: [...formats],
        resize: resizeOn ? { w, h } : null,
        zip,
      })
      toast.success('导出完成')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '导出失败')
    }
  }

  return (
    <div className="space-y-5">
      <Card className="space-y-4 p-5">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground">选择图片</h3>
          <Button variant="ghost" size="sm" onClick={selectKept}>
            选中已保留
          </Button>
        </div>
        {images.isLoading ? (
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="aspect-square w-full" />
            ))}
          </div>
        ) : images.data && images.data.length > 0 ? (
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
            {images.data.map((img) => {
              const on = selected.has(img.image_id)
              return (
                <button
                  key={img.image_id}
                  type="button"
                  onClick={() => toggleImage(img.image_id)}
                  className={cn(
                    'relative overflow-hidden rounded-lg border text-left transition-colors',
                    on ? 'border-primary ring-primary/30 ring-2' : 'border-border/70',
                  )}
                >
                  <ImageThumb url={img.url} className="aspect-square w-full" />
                  <div className="flex items-center justify-between px-1.5 py-1">
                    <span className="text-muted-foreground font-mono text-[10px]">
                      第{img.round_no}轮·{img.subscene}
                    </span>
                    {img.kept && (
                      <Badge className="bg-primary/12 text-primary px-1 text-[9px]">留</Badge>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        ) : (
          <p className="text-muted-foreground py-8 text-center text-sm">项目暂无可导出的图片。</p>
        )}
      </Card>

      <Card className="space-y-5 p-5">
        <div className="space-y-2">
          <Label>导出格式</Label>
          <div className="flex gap-2">
            {FORMATS.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => toggleFormat(f)}
                className={cn(
                  'rounded-full border px-3 py-1 text-sm uppercase transition-colors',
                  formats.has(f)
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:bg-accent/50',
                )}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex items-center gap-2">
            <Switch checked={resizeOn} onCheckedChange={setResizeOn} id="resize" />
            <Label htmlFor="resize" className="cursor-pointer">
              改尺寸
            </Label>
            {resizeOn && (
              <div className="flex items-center gap-1.5">
                <Input
                  type="number"
                  value={w}
                  onChange={(e) => setW(Number(e.target.value) || 0)}
                  className="h-8 w-20"
                />
                <span className="text-muted-foreground text-sm">×</span>
                <Input
                  type="number"
                  value={h}
                  onChange={(e) => setH(Number(e.target.value) || 0)}
                  className="h-8 w-20"
                />
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={zip} onCheckedChange={setZip} id="zip" />
            <Label htmlFor="zip" className="cursor-pointer">
              打包 zip
            </Label>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button
            onClick={() => void run()}
            disabled={selected.size === 0 || formats.size === 0 || exporter.isPending}
          >
            <DownloadIcon className="size-4" />
            {exporter.isPending ? '导出中…' : `导出 ${selected.size} 张`}
          </Button>
          <span className="text-muted-foreground text-xs">
            按 PRD 命名归档（项目/子场景/轮次）
          </span>
        </div>
      </Card>

      {exporter.data && (
        <Card className="space-y-3 p-5">
          <div className="text-primary flex items-center gap-2 text-sm">
            <FileCheck2Icon className="size-4" />
            导出完成 · {exporter.data.files.length} 个文件
            {exporter.data.package_url && <span className="text-muted-foreground">· 已打包 zip</span>}
          </div>
          <ul className="space-y-1">
            {exporter.data.files.map((f) => (
              <li key={f.filename} className="text-muted-foreground font-mono text-xs">
                {f.filename}
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground/70 text-xs">
            文件落在后端归档目录；浏览器下载需后端图床（ISSUE-0016）。
          </p>
        </Card>
      )}
    </div>
  )
}
