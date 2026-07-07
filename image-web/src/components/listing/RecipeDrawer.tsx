import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ScrollTextIcon, SparklesIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { IMAGE_TYPE_FIELDS, editModeLabel, planTotal, type ListingJobDetail } from '@/lib/listing'
import { jobToRecipe, recipeToPrefill } from '@/lib/recipe'

/** modifiers key → 展示名（未知 key 原样）。 */
const MODIFIER_LABELS: Record<string, string> = { platform: '平台', language: '语言', region: '地区' }

/**
 * 「查看配方」弹层（ISSUE-0053）：展示一张 job 的可复用配方（图型配比/比例/风格描述/平台），
 * 套图单额外给「复用配置出图」→ /set 预填。铁律：只展示用户输入，绝不含内部卡 prompt。
 * detail 由调用方（历史详情 / 工作台结果卡）已加载后传入，组件不自拉（DRY，避免双查）。
 */
export function RecipeDrawer({ detail }: { detail: ListingJobDetail }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const recipe = jobToRecipe(detail)

  function reuse() {
    const prefill = recipeToPrefill(recipe)
    if (!prefill) return
    setOpen(false)
    navigate('/set', { state: { prefill } })
  }

  const modeBadge =
    recipe.kind === 'clone' ? `复刻 · ${recipe.cloneMode}` : recipe.kind === 'edit' ? `编辑 · ${editModeLabel(recipe.editMode ?? '')}` : null

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <ScrollTextIcon /> 查看配方
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>配方</DialogTitle>
          <DialogDescription>
            可复用的生成配置——图型、比例、平台与风格描述。产品图与图上文案请自行提供。
          </DialogDescription>
        </DialogHeader>

        <dl className="space-y-3 text-[13px]">
          {modeBadge && (
            <div className="flex gap-3">
              <dt className="w-16 shrink-0 text-muted-foreground">模式</dt>
              <dd className="font-medium text-foreground">{modeBadge}</dd>
            </div>
          )}

          <div className="flex gap-3">
            <dt className="w-16 shrink-0 text-muted-foreground">{recipe.kind === 'set' ? '图型配比' : '张数'}</dt>
            <dd className="flex flex-wrap gap-1.5">
              {recipe.kind === 'set' && recipe.plan ? (
                <>
                  {IMAGE_TYPE_FIELDS.filter((f) => (recipe.plan?.[f.key] ?? 0) > 0).map((f) => (
                    <span key={f.key} className="rounded-md bg-muted px-2 py-0.5 font-medium text-foreground">
                      {f.label} ×{recipe.plan?.[f.key]}
                    </span>
                  ))}
                  <span className="self-center text-muted-foreground">共 {planTotal(recipe.plan)} 张</span>
                </>
              ) : (
                <span className="font-medium text-foreground">{recipe.n ?? 1} 张</span>
              )}
            </dd>
          </div>

          <div className="flex gap-3">
            <dt className="w-16 shrink-0 text-muted-foreground">比例</dt>
            <dd className="font-medium text-foreground">{recipe.ratio}</dd>
          </div>

          {Object.entries(recipe.modifiers).length > 0 && (
            <div className="flex gap-3">
              <dt className="w-16 shrink-0 text-muted-foreground">参数</dt>
              <dd className="flex flex-wrap gap-x-4 gap-y-1 text-foreground">
                {Object.entries(recipe.modifiers).map(([k, v]) => (
                  <span key={k}>
                    <span className="text-muted-foreground">{MODIFIER_LABELS[k] ?? k} </span>
                    {v}
                  </span>
                ))}
              </dd>
            </div>
          )}

          {recipe.prompt.trim() && (
            <div className="flex gap-3">
              <dt className="w-16 shrink-0 text-muted-foreground">风格描述</dt>
              <dd className="whitespace-pre-wrap leading-relaxed text-foreground">{recipe.prompt}</dd>
            </div>
          )}
        </dl>

        <DialogFooter>
          {recipe.reusable ? (
            <Button onClick={reuse}>
              <SparklesIcon /> 复用配置出图
            </Button>
          ) : (
            <p className="text-[12.5px] text-muted-foreground">
              复刻 / 编辑 / 单图单暂不支持一键复用，可参考上方配方手动新建。
            </p>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
