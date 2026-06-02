import { useState } from 'react'
import { SaveIcon } from 'lucide-react'
import { toast } from 'sonner'

import { useUpsertBrief, type Brief } from '@/api/brief'
import { TagInput } from '@/components/TagInput'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

const STYLE_OPTIONS = [
  '高端轻奢',
  '极简北欧',
  '国潮中式',
  '科技未来',
  '清新自然',
  '运动机能',
  '喜庆节日',
]

/** 需求单表单（PRD 8 字段）。PUT 为全量替换语义，保存即提交全部字段. */
export function BriefForm({ projectId, initial }: { projectId: number; initial: Brief | null }) {
  const [materialTypes, setMaterialTypes] = useState<string[]>(initial?.material_types ?? [])
  const [sizes, setSizes] = useState<string[]>(initial?.sizes ?? [])
  const [styles, setStyles] = useState<string[]>(initial?.styles ?? [])
  const [resolution, setResolution] = useState(initial?.resolution ?? '')
  const [bleed, setBleed] = useState(initial?.bleed ?? '')
  const [copyText, setCopyText] = useState(initial?.copy_text ?? '')
  const [taboo, setTaboo] = useState(initial?.taboo ?? '')
  const upsert = useUpsertBrief(projectId)

  function toggleStyle(s: string) {
    setStyles((p) => (p.includes(s) ? p.filter((x) => x !== s) : [...p, s]))
  }

  async function save() {
    try {
      await upsert.mutateAsync({
        material_types: materialTypes,
        sizes,
        styles,
        resolution: resolution.trim() || null,
        bleed: bleed.trim() || null,
        copy_text: copyText.trim() || null,
        taboo: taboo.trim() || null,
      })
      toast.success('需求单已保存')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存需求单失败')
    }
  }

  return (
    <Card className="space-y-5 p-6">
      <form
        className="space-y-5"
        onSubmit={(e) => {
          e.preventDefault()
          void save()
        }}
      >
        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="brief-materials">物料类型</Label>
            <TagInput
              id="brief-materials"
              value={materialTypes}
              onChange={setMaterialTypes}
              placeholder="如：主图、详情图、直通车（回车添加）"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="brief-sizes">尺寸</Label>
            <TagInput
              id="brief-sizes"
              value={sizes}
              onChange={setSizes}
              placeholder="如：1024×1024、800×1200（回车添加）"
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label>风格</Label>
          <div className="flex flex-wrap gap-2">
            {STYLE_OPTIONS.map((s) => {
              const active = styles.includes(s)
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleStyle(s)}
                  className={cn(
                    'rounded-full border px-3 py-1 text-sm transition-colors',
                    active
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground hover:bg-accent/50',
                  )}
                >
                  {s}
                </button>
              )
            })}
          </div>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="brief-resolution">分辨率</Label>
            <Input
              id="brief-resolution"
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
              placeholder="如：300dpi"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="brief-bleed">出血</Label>
            <Input
              id="brief-bleed"
              value={bleed}
              onChange={(e) => setBleed(e.target.value)}
              placeholder="如：3mm"
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="brief-copy">文案</Label>
          <Textarea
            id="brief-copy"
            value={copyText}
            onChange={(e) => setCopyText(e.target.value)}
            placeholder="主标题 / 卖点文案"
            rows={2}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="brief-taboo">禁忌</Label>
          <Textarea
            id="brief-taboo"
            value={taboo}
            onChange={(e) => setTaboo(e.target.value)}
            placeholder="不可出现的元素 / 合规要求"
            rows={2}
          />
        </div>

        <div className="flex justify-end">
          <Button type="submit" disabled={upsert.isPending}>
            <SaveIcon className="size-4" />
            {upsert.isPending ? '保存中…' : '保存需求单'}
          </Button>
        </div>
      </form>
    </Card>
  )
}
