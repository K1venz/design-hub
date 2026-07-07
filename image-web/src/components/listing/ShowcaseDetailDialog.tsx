import { SparklesIcon } from 'lucide-react'

import type { ShowcaseItem } from '@/api/showcase'
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
import type { SetPlan } from '@/lib/listing'

/**
 * showcase「查看详情」弹层（ISSUE-0053 落点 B，用户 07-07 细化）：大图 + 配方全项
 * （与 /set 生成界面配置项一一对应）+ 弹层内「做同款」CTA。查看详情无需登录（获客钩子），
 * 点做同款才由父级决定是否拦登录墙。RecipeFields 与历史「查看配方」共用展示件。
 */
export function ShowcaseDetailDialog({ item, onMakeSame }: { item: ShowcaseItem; onMakeSame: () => void }) {
  const r = item.recipe
  const plan: SetPlan = {
    白底: r.plan['白底'] ?? 0,
    场景: r.plan['场景'] ?? 0,
    卖点: r.plan['卖点'] ?? 0,
  }
  const view: RecipeView = {
    category: r.category,
    plan,
    ratio: r.ratio,
    styling: r.styling,
    modifiers: r.modifiers,
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className="flex-1 rounded-lg border border-wb-line-2 bg-white/70 px-3 py-1.5 text-[12px] font-medium text-wb-ink-3 transition-colors hover:border-wb-brand hover:text-wb-brand-deep"
        >
          查看详情
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{item.caption}</DialogTitle>
          <DialogDescription>实朴真实出品 · 这套图的完整配方，一键做同款</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 sm:flex-row">
          <div className="relative shrink-0 sm:w-44">
            <img
              src={item.url}
              alt={item.caption}
              loading="lazy"
              className="aspect-[4/3] w-full rounded-xl border border-wb-line-1 object-cover sm:aspect-auto"
            />
            <span className="absolute left-2 top-2 rounded-full bg-white/85 px-2 py-0.5 text-[11px] font-medium text-wb-brand-deep backdrop-blur">
              {item.image_type}
            </span>
          </div>
          <div className="min-w-0 flex-1">
            <RecipeFields view={view} />
          </div>
        </div>

        <DialogFooter>
          <Button onClick={onMakeSame}>
            <SparklesIcon /> 做同款
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
