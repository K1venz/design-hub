import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ScrollTextIcon, SparklesIcon } from 'lucide-react'

import { RecipeFields, type RecipeView } from '@/components/listing/RecipeFields'
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
import { editModeLabel, type ListingJobDetail } from '@/lib/listing'
import { jobToRecipe, recipeToPrefill } from '@/lib/recipe'

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

  const view: RecipeView = {
    category: recipe.category,
    modeBadge:
      recipe.kind === 'clone'
        ? `复刻 · ${recipe.cloneMode}`
        : recipe.kind === 'edit'
          ? `编辑 · ${editModeLabel(recipe.editMode ?? '')}`
          : null,
    plan: recipe.kind === 'set' ? recipe.plan : undefined,
    singleN: recipe.kind === 'single' ? recipe.n : undefined,
    ratio: recipe.ratio,
    styling: recipe.prompt,
    modifiers: recipe.modifiers,
  }

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

        <RecipeFields view={view} />

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
