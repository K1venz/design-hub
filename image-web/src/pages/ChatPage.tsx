import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ImagePlusIcon, Loader2Icon, SendIcon, SparklesIcon, WandSparklesIcon, XIcon } from 'lucide-react'

import { AppShell } from '@/components/layout/AppShell'
import { sendChatMessage, confirmChat } from '@/api/chat'
import { useUploadImage } from '@/api/listing'
import { downloadImage } from '@/lib/download'
import {
  applyChatEvent, clearAwaiting, initialChatState, pushUserMessage,
  type ChatBubble, type ChatState, type CostConfirm,
} from '@/lib/chat'
import type { UploadedImage } from '@/lib/listing'

const PHASE_LABEL: Record<string, string> = {
  understood: '已理解需求',
  planning: '正在规划',
  generating: '正在出图',
  done: '完成',
}

/**
 * 「帮我设计」对话页（登录内测，方案 C）。Hero/快捷卡带来的 `?q=` 自动发首条。
 * 流式气泡 + 步骤条 + 工具透明 + 费用确认闸 + 出图结果卡（job_event 复用工作台渲染）。
 */
export function ChatPage() {
  const [params] = useSearchParams()
  const [state, setState] = useState<ChatState>(initialChatState)
  const [draft, setDraft] = useState('')
  const [attached, setAttached] = useState<UploadedImage[]>([])
  const upload = useUploadImage()
  const abortRef = useRef<AbortController | null>(null)
  const stateRef = useRef(state)
  useEffect(() => {
    stateRef.current = state
  }, [state])
  const fileRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const on = (e: Parameters<typeof applyChatEvent>[1]) => setState((prev) => applyChatEvent(prev, e))

  async function send(message: string, uploadIds?: string[]) {
    const text = message.trim()
    if (!text || stateRef.current.streaming || stateRef.current.awaiting) return
    setState((prev) => pushUserMessage(prev, text, uploadIds && uploadIds.length ? attached.map((a) => a.url) : undefined))
    setDraft('')
    setAttached([])
    abortRef.current?.abort() // 中止上一条在途流（至多一条活跃）
    const ac = new AbortController()
    abortRef.current = ac
    try {
      await sendChatMessage({ sessionId: stateRef.current.sessionId, message: text, uploadIds }, on, ac.signal)
    } catch (err) {
      if (!ac.signal.aborted) {
        setState((prev) => ({ ...prev, streaming: false }))
        toast.error(err instanceof Error ? err.message : '对话请求失败')
      }
    }
  }

  async function resolveConfirm(action: 'confirm' | 'cancel', c: CostConfirm) {
    const sid = stateRef.current.sessionId
    if (!sid) return
    setState((prev) => clearAwaiting(prev))
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    try {
      await confirmChat({ sessionId: sid, confirmToken: c.confirmToken, action }, on, ac.signal)
    } catch (err) {
      if (!ac.signal.aborted) {
        setState((prev) => ({ ...prev, streaming: false }))
        toast.error(err instanceof Error ? err.message : '确认请求失败')
      }
    }
  }

  // Hero/快捷卡首句：进页自动发一次（guard 防 StrictMode 双发）
  const seededRef = useRef(false)
  useEffect(() => {
    const seed = params.get('q')?.trim()
    if (seed && !seededRef.current) {
      seededRef.current = true
      void send(seed)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 新内容滚到底
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [state.bubbles, state.slots, state.awaiting])

  async function onPickFiles(files: FileList | null) {
    if (!files?.length) return
    for (const f of Array.from(files).slice(0, 3 - attached.length)) {
      try {
        const up = await upload.mutateAsync(f)
        setAttached((prev) => [...prev, up])
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '图片上传失败')
      }
    }
    if (fileRef.current) fileRef.current.value = ''
  }

  const busy = state.streaming || state.awaiting !== null

  return (
    <AppShell>
      <main className="min-h-0 flex-1 overflow-hidden pb-3 pr-3">
        <div className="mx-auto flex h-full max-w-3xl flex-col">
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-auto px-2 py-4">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-wb-ink-2">
              <span className="grid size-7 place-items-center rounded-[9px] bg-gradient-to-br from-wb-grad-from to-wb-grad-to text-white">
                <WandSparklesIcon className="size-4" />
              </span>
              帮我设计
              <span className="rounded-full bg-wb-tint-1 px-2 py-0.5 text-[11px] font-medium text-wb-brand-deep">内测</span>
            </div>

            {state.bubbles.length === 0 && !state.streaming && (
              <p className="pt-6 text-center text-[13.5px] text-wb-ink-6">
                用大白话说说你的产品和想要的效果，我来帮你出图。
              </p>
            )}

            {state.bubbles.map((b, i) => (
              <Bubble key={i} bubble={b} awaiting={state.awaiting} onResolve={resolveConfirm} />
            ))}

            {state.jobTotal > 0 && (
              <ResultBlock slots={state.slots} done={state.jobDone} total={state.jobTotal} />
            )}

            {state.streaming && !state.awaiting && (
              <div className="flex items-center gap-2 px-1 text-[12.5px] text-wb-ink-6">
                <Loader2Icon className="size-3.5 animate-spin" /> 思考中…
              </div>
            )}

            {state.error && (
              <div className="rounded-xl border border-wb-red-line bg-wb-red-tint px-3 py-2 text-[12.5px] text-wb-red">
                {state.error.message}
              </div>
            )}
          </div>

          {/* 输入区 */}
          <div className="glass-panel rounded-[20px] p-3">
            {attached.length > 0 && (
              <div className="mb-1.5 flex gap-2 px-1">
                {attached.map((a, i) => (
                  <span key={a.id} className="relative">
                    <img src={a.url} alt="" className="size-12 rounded-lg border border-wb-line-1 object-cover" />
                    <button
                      onClick={() => setAttached((prev) => prev.filter((_, j) => j !== i))}
                      className="absolute -right-1.5 -top-1.5 grid size-4 place-items-center rounded-full bg-wb-ink-2 text-white"
                    >
                      <XIcon className="size-2.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') void send(draft, attached.map((a) => a.id))
              }}
              disabled={busy}
              placeholder={state.awaiting ? '请先确认或取消上面的出图…' : '描述你的产品和想要的效果…'}
              className="h-[72px] w-full resize-none bg-transparent px-3 py-2 text-[14px] leading-relaxed text-wb-ink-2 outline-none placeholder:text-wb-faint-1 disabled:opacity-60"
            />
            <div className="flex items-center justify-between px-1">
              <button
                onClick={() => fileRef.current?.click()}
                disabled={busy || attached.length >= 3}
                className="flex items-center gap-1.5 rounded-full border border-wb-line-1 bg-white/70 px-3 py-1.5 text-[12.5px] font-medium text-wb-ink-4 transition-colors hover:border-wb-brand-soft hover:text-wb-brand-deep disabled:opacity-50"
              >
                {upload.isPending ? <Loader2Icon className="size-4 animate-spin" /> : <ImagePlusIcon className="size-4" />}
                添加图片
              </button>
              <input
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                hidden
                onChange={(e) => void onPickFiles(e.target.files)}
              />
              <button
                onClick={() => void send(draft, attached.map((a) => a.id))}
                disabled={busy || !draft.trim()}
                className="flex items-center gap-1.5 rounded-full bg-gradient-to-r from-wb-grad-from to-wb-grad-to px-4 py-1.5 text-[13px] font-semibold text-white shadow-[0_8px_20px_-8px_rgba(91,91,214,.6)] transition-opacity disabled:opacity-45"
              >
                发送 <SendIcon className="size-3.5" />
              </button>
            </div>
          </div>
        </div>
      </main>
    </AppShell>
  )
}

function Bubble({
  bubble, awaiting, onResolve,
}: {
  bubble: ChatBubble
  awaiting: CostConfirm | null
  onResolve: (action: 'confirm' | 'cancel', c: CostConfirm) => void
}) {
  if (bubble.role === 'user') {
    return (
      <div className="flex flex-col items-end gap-1.5">
        {bubble.images && bubble.images.length > 0 && (
          <div className="flex gap-1.5">
            {bubble.images.map((u, i) => (
              <img key={i} src={u} alt="" className="size-14 rounded-lg border border-wb-line-1 object-cover" />
            ))}
          </div>
        )}
        {bubble.text && (
          <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-wb-brand px-4 py-2.5 text-[14px] leading-relaxed text-white shadow-[0_8px_20px_-10px_rgba(91,91,214,.6)]">
            {bubble.text}
          </div>
        )}
      </div>
    )
  }

  const activeCost = bubble.cost && awaiting?.confirmToken === bubble.cost.confirmToken ? bubble.cost : null
  return (
    <div className="flex justify-start">
      <div className="glass-panel max-w-[88%] space-y-2.5 rounded-2xl rounded-tl-md px-4 py-3">
        {bubble.steps.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {bubble.steps.map((s, i) => (
              <span key={i} className="flex items-center gap-1 rounded-full bg-wb-tint-1 px-2 py-0.5 text-[11px] font-medium text-wb-brand-deep">
                <SparklesIcon className="size-3" />
                {PHASE_LABEL[s.phase] ?? s.phase}
                {s.detail ? ` · ${s.detail}` : ''}
              </span>
            ))}
          </div>
        )}
        {bubble.text && <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-wb-ink-2">{bubble.text}</p>}
        {bubble.cost && <CostCard cost={bubble.cost} active={activeCost !== null} onResolve={onResolve} />}
      </div>
    </div>
  )
}

function CostCard({
  cost, active, onResolve,
}: {
  cost: CostConfirm
  active: boolean
  onResolve: (action: 'confirm' | 'cancel', c: CostConfirm) => void
}) {
  return (
    <div className="rounded-xl border border-wb-brand-soft bg-wb-tint-3 p-3">
      <p className="text-[13px] font-medium text-wb-ink-2">
        本次将出 <span className="font-bold text-wb-brand-deep">{cost.count}</span> 张，预计
        <span className="font-bold text-wb-brand-deep"> ¥{cost.estimateCny}</span>
      </p>
      <p className="mt-0.5 text-[11.5px] text-wb-ink-6">确认后开始出图并计费；不确认不扣费。</p>
      {active ? (
        <div className="mt-2.5 flex gap-2">
          <button
            onClick={() => onResolve('confirm', cost)}
            className="rounded-full bg-gradient-to-r from-wb-grad-from to-wb-grad-to px-4 py-1.5 text-[12.5px] font-semibold text-white"
          >
            确认出图
          </button>
          <button
            onClick={() => onResolve('cancel', cost)}
            className="rounded-full border border-wb-line-1 bg-white px-4 py-1.5 text-[12.5px] font-medium text-wb-ink-4"
          >
            取消
          </button>
        </div>
      ) : (
        <p className="mt-2 text-[11.5px] font-medium text-wb-ink-5">已处理</p>
      )}
    </div>
  )
}

function ResultBlock({ slots, done, total }: { slots: { url: string | null; imageType?: string; error?: string }[]; done: number; total: number }) {
  const generating = done < total && slots.some((s) => s.url === null && !s.error)
  return (
    <div className="glass-panel max-w-[88%] rounded-2xl rounded-tl-md p-3">
      <p className="mb-2 px-1 text-[12.5px] font-medium text-wb-ink-3">
        出图结果 <span className="text-wb-ink-6">{done}/{total}</span>
        {generating && <Loader2Icon className="ml-1.5 inline size-3 animate-spin text-wb-brand" />}
      </p>
      <div className="grid grid-cols-3 gap-2">
        {slots.map((s, i) =>
          s.url ? (
            <div key={i} className="group relative aspect-square overflow-hidden rounded-xl border border-wb-line-1 bg-white">
              <img src={s.url} alt="" className="size-full object-cover" />
              <button
                onClick={() => void downloadImage(s.url!, `${s.imageType ?? 'chat'}-${i + 1}.png`)}
                className="absolute bottom-1.5 right-1.5 rounded-lg bg-wb-ink-2/90 px-2 py-1 text-[11px] text-white opacity-0 transition-opacity group-hover:opacity-100"
              >
                下载
              </button>
            </div>
          ) : s.error ? (
            <div key={i} title={s.error} className="grid aspect-square place-items-center rounded-xl border border-dashed border-wb-red-line bg-wb-red-tint p-2 text-center text-[11px] text-wb-red">
              生成失败
            </div>
          ) : (
            <div key={i} className="grid aspect-square place-items-center rounded-xl border border-dashed border-wb-line-3 bg-wb-surface-1">
              <div className="size-5 animate-spin rounded-full border-2 border-wb-line-2 border-t-wb-brand" />
            </div>
          ),
        )}
      </div>
    </div>
  )
}
