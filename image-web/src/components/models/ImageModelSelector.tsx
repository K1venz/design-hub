import { Loader2Icon, RefreshCwIcon, TriangleAlertIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import type { ImageModelSelection } from '@/components/models/image-model-context'

export function ImageModelSelector({
  selection,
  disabled = false,
}: {
  selection: ImageModelSelection
  disabled?: boolean
}) {
  if (selection.state === 'loading') {
    return (
      <div
        role="status"
        className="flex items-center gap-2 rounded-xl border border-wb-line-1 bg-wb-surface-1 px-3 py-2.5 text-[12.5px] text-wb-ink-6"
      >
        <Loader2Icon className="size-3.5 animate-spin" />
        正在加载可用图片模型…
      </div>
    )
  }
  if (selection.state === 'error') {
    return (
      <div
        role="alert"
        className="rounded-xl border border-wb-red-line bg-wb-red-tint p-3 text-[12.5px] text-wb-red"
      >
        <p className="font-medium">图片模型加载失败，表单内容已保留。</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-2 h-7 bg-white"
          onClick={selection.retry}
        >
          <RefreshCwIcon className="size-3.5" />
          重试
        </Button>
      </div>
    )
  }
  if (selection.state === 'empty') {
    return (
      <div
        role="alert"
        className="flex items-start gap-2 rounded-xl border border-wb-amber-line bg-wb-amber-tint p-3 text-[12.5px] leading-relaxed text-wb-amber"
      >
        <TriangleAlertIcon className="mt-0.5 size-3.5 shrink-0" />
        当前没有可用的图片模型，请联系管理员完成配置。
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      <Label htmlFor="image-model-selector">图片模型</Label>
      <select
        id="image-model-selector"
        aria-describedby="image-model-help"
        value={selection.modelId ?? ''}
        disabled={disabled}
        onChange={(event) => selection.select(event.target.value)}
        className="h-10 w-full rounded-xl border border-wb-line-1 bg-white px-3 text-[13px] text-wb-ink-2 outline-none transition-colors focus-visible:border-wb-brand-soft disabled:cursor-not-allowed disabled:opacity-60"
      >
        {selection.state === 'selection_required' ? (
          <option value="" disabled>
            请选择图片模型
          </option>
        ) : null}
        {selection.models.map((model) => (
          <option key={model.id} value={model.id}>
            {model.display_name}
          </option>
        ))}
      </select>
      <p
        id="image-model-help"
        className="text-[11px] leading-relaxed text-wb-ink-7"
      >
        {selection.state === 'selection_required'
          ? '之前选择的模型已不可用，请重新选择后再生成。'
          : disabled
            ? '任务运行期间不能切换模型。'
            : '选择会按当前账号保存，并同步用于所有出图工具与对话。'}
      </p>
    </div>
  )
}
