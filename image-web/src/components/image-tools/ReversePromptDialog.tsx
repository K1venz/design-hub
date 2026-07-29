import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CheckIcon,
  ClipboardIcon,
  Loader2Icon,
  RefreshCwIcon,
  SendIcon,
} from 'lucide-react'
import { toast } from 'sonner'

import { useReverseImagePrompt } from '@/api/image-tools'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type {
  ImageToolSource,
  ReversePromptResult,
} from '@/lib/image-tools'

export function ReversePromptDialog({
  source,
  onClose,
}: {
  source: ImageToolSource | null
  onClose: () => void
}) {
  const reverse = useReverseImagePrompt()
  const navigate = useNavigate()

  useEffect(() => {
    if (source) reverse.mutate(source)
    else reverse.reset()
    // Mutation methods are stable; source identity is the request boundary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source])

  function continueInChat(prompt: string) {
    onClose()
    navigate('/chat', { state: { q: prompt } })
  }

  return (
    <Dialog
      open={source !== null}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="max-h-[86vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-[17px]">
            <span className="grid size-8 place-items-center rounded-xl bg-wb-tint-1 text-wb-brand-deep">
              <ClipboardIcon className="size-4" />
            </span>
            反推提示词
          </DialogTitle>
          <DialogDescription>
            基于可见画面生成重建建议，不代表原作者的真实提示词。
          </DialogDescription>
        </DialogHeader>

        {reverse.isPending ? (
          <div className="grid min-h-56 place-items-center">
            <div className="text-center text-[13px] text-wb-ink-6">
              <Loader2Icon className="mx-auto mb-2 size-6 animate-spin text-wb-brand" />
              正在分析主体、构图、光线和风格…
            </div>
          </div>
        ) : reverse.isError ? (
          <div className="rounded-2xl border border-wb-red-line bg-wb-red-tint p-4">
            <p className="text-[13px] text-wb-red">
              {reverse.error instanceof Error
                ? reverse.error.message
                : '反推提示词失败'}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => source && reverse.mutate(source)}
            >
              <RefreshCwIcon /> 重试
            </Button>
          </div>
        ) : reverse.data ? (
          <ReversePromptContent
            result={reverse.data}
            onContinue={continueInChat}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

function ReversePromptContent({
  result,
  onContinue,
}: {
  result: ReversePromptResult
  onContinue: (prompt: string) => void
}) {
  const facts = [
    ['主体', result.subject],
    ['场景', result.scene],
    ['构图', result.composition],
    ['镜头', result.camera],
    ['光线', result.lighting],
    ['色彩', result.colors.join('、')],
    ['风格', result.style],
    [
      '可见文字',
      result.visible_text.length
        ? result.visible_text.join('、')
        : '未识别到明确文字',
    ],
  ]

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-wb-tint-line bg-wb-tint-3 p-4">
        <p className="text-[13.5px] font-semibold text-wb-ink-2">
          {result.summary}
        </p>
        <dl className="mt-3 grid gap-x-5 gap-y-2 text-[12.5px] sm:grid-cols-2">
          {facts.map(([label, value]) => (
            <div key={label} className="grid grid-cols-[56px_1fr] gap-2">
              <dt className="text-wb-ink-7">{label}</dt>
              <dd className="text-wb-ink-3">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <FactList
          title="重建约束"
          items={result.constraints}
          empty="无额外约束"
        />
        <FactList
          title="不确定项"
          items={result.uncertainties}
          empty="无"
        />
      </div>

      <PromptCard
        label="中文提示词"
        prompt={result.prompt_zh}
        onContinue={() => onContinue(result.prompt_zh)}
      />
      <PromptCard
        label="English prompt"
        prompt={result.prompt_en}
        onContinue={() => onContinue(result.prompt_en)}
      />
    </div>
  )
}

function FactList({
  title,
  items,
  empty,
}: {
  title: string
  items: string[]
  empty: string
}) {
  return (
    <section className="rounded-2xl border border-wb-line-1 bg-wb-surface-2 p-3.5">
      <h3 className="text-[12.5px] font-semibold text-wb-ink-2">{title}</h3>
      {items.length ? (
        <ul className="mt-2 space-y-1.5 text-[12px] leading-relaxed text-wb-ink-5">
          {items.map((item) => (
            <li key={item} className="flex gap-1.5">
              <CheckIcon className="mt-0.5 size-3.5 shrink-0 text-wb-brand" />
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-[12px] text-wb-ink-7">{empty}</p>
      )}
    </section>
  )
}

function PromptCard({
  label,
  prompt,
  onContinue,
}: {
  label: string
  prompt: string
  onContinue: () => void
}) {
  async function copy() {
    try {
      await navigator.clipboard.writeText(prompt)
      toast.success('提示词已复制')
    } catch {
      toast.error('复制失败，请手动选择提示词')
    }
  }

  return (
    <section className="rounded-2xl border border-wb-line-1 bg-white p-4 shadow-[0_8px_28px_-22px_rgba(40,40,90,.25)]">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-[13px] font-semibold text-wb-ink-2">{label}</h3>
        <div className="flex gap-1.5">
          <button
            type="button"
            onClick={() => void copy()}
            className="rounded-full border border-wb-line-1 px-3 py-1 text-[11.5px] text-wb-ink-4 hover:border-wb-brand-soft hover:text-wb-brand-deep"
          >
            <ClipboardIcon className="mr-1 inline size-3" /> 复制
          </button>
          <button
            type="button"
            onClick={onContinue}
            className="rounded-full bg-wb-brand px-3 py-1 text-[11.5px] text-white hover:bg-wb-brand-deep"
          >
            <SendIcon className="mr-1 inline size-3" /> 带入帮我设计
          </button>
        </div>
      </div>
      <p className="whitespace-pre-wrap text-[12.5px] leading-6 text-wb-ink-3">
        {prompt}
      </p>
    </section>
  )
}
