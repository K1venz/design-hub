import { useSearchParams } from 'react-router-dom'
import { SparklesIcon, WandSparklesIcon } from 'lucide-react'

import { AppShell } from '@/components/layout/AppShell'

/**
 * 「帮我设计」对话页 —— A 批占位骨架（登录内测）。
 * 读 Hero/快捷卡带来的首句 `?q=`，渲染对话布局；真流式编排（fetch+SSE、
 * 步骤条、费用确认、结果卡）待 B 批按 dev /chat 契约（0048）接入。
 */
export function ChatPage() {
  const [params] = useSearchParams()
  const seed = params.get('q')?.trim()

  return (
    <AppShell>
      <main className="min-h-0 flex-1 overflow-hidden pb-3 pr-3">
        <div className="mx-auto flex h-full max-w-3xl flex-col">
          {/* 对话流 */}
          <div className="flex-1 space-y-4 overflow-auto px-2 py-4">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-wb-ink-2">
              <span className="grid size-7 place-items-center rounded-[9px] bg-gradient-to-br from-wb-grad-from to-wb-grad-to text-white">
                <WandSparklesIcon className="size-4" />
              </span>
              帮我设计
              <span className="rounded-full bg-wb-tint-1 px-2 py-0.5 text-[11px] font-medium text-wb-brand-deep">内测</span>
            </div>

            {seed && (
              <div className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-wb-brand px-4 py-2.5 text-[14px] leading-relaxed text-white shadow-[0_8px_20px_-10px_rgba(91,91,214,.6)]">
                  {seed}
                </div>
              </div>
            )}

            <div className="flex justify-start">
              <div className="glass-panel max-w-[85%] rounded-2xl rounded-tl-md px-4 py-3">
                <p className="flex items-center gap-1.5 text-[13.5px] font-medium text-wb-ink-2">
                  <SparklesIcon className="size-4 text-wb-brand" /> 对话式出图正在内测调试中
                </p>
                <p className="mt-1.5 text-[13px] leading-relaxed text-wb-ink-5">
                  很快你就能在这里用大白话描述需求，我会一步步帮你理解、确认费用、直接出图。
                  这几天先到「商品套图 / 爆款复刻」工作台出图，效果一样好。
                </p>
              </div>
            </div>
          </div>

          {/* 输入区（占位禁用，B 批接真流） */}
          <div className="glass-panel rounded-[20px] p-3">
            <textarea
              disabled
              placeholder="对话功能即将开放，敬请期待…"
              className="h-[72px] w-full resize-none bg-transparent px-3 py-2 text-[14px] leading-relaxed text-wb-ink-4 outline-none placeholder:text-wb-faint-1"
            />
            <div className="flex justify-end px-1">
              <button
                disabled
                className="cursor-not-allowed rounded-full bg-wb-surface-5 px-4 py-1.5 text-[13px] font-semibold text-wb-faint-1"
              >
                发送
              </button>
            </div>
          </div>
        </div>
      </main>
    </AppShell>
  )
}
