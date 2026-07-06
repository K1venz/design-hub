import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2Icon, MessagesSquareIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { toast } from 'sonner'

import { CHAT_SESSIONS_KEY, deleteChatSession, listChatSessions } from '@/api/chat'
import { cn } from '@/lib/utils'

/**
 * 「帮我设计」会话侧栏（ISSUE-0051）：会话列表（updated_at 倒序）+ 新建 + 删除。
 * 纯展示/交互——选中/新建交回 ChatPage 驱动回显（getChatSession→气泡）与状态重置。
 * 列表数据 react-query 缓存；发消息后由 ChatPage invalidate 触发刷新（标题/消息数变化）。
 */
export function SessionSidebar({
  activeId,
  loadingId,
  onSelect,
  onNew,
}: {
  activeId: string | null
  loadingId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}) {
  const qc = useQueryClient()
  const sessions = useQuery({ queryKey: CHAT_SESSIONS_KEY, queryFn: listChatSessions })

  const del = useMutation({
    mutationFn: deleteChatSession,
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: CHAT_SESSIONS_KEY })
      if (id === activeId) onNew() // 删的是当前会话 → 回到新对话
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : '删除失败'),
  })

  return (
    <aside className="glass-panel hidden w-[228px] shrink-0 flex-col self-stretch p-3 md:flex">
      <button
        onClick={onNew}
        className="mb-2 flex items-center justify-center gap-1.5 rounded-[12px] bg-gradient-to-r from-wb-grad-from to-wb-grad-to px-3 py-2 text-[13px] font-semibold text-white shadow-[0_8px_20px_-8px_rgba(91,91,214,.6)] transition-opacity hover:opacity-90"
      >
        <PlusIcon className="size-4" /> 新对话
      </button>

      <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        {sessions.isLoading ? (
          <div className="flex items-center gap-2 px-3 py-2 text-[12.5px] text-wb-ink-6">
            <Loader2Icon className="size-3.5 animate-spin" /> 加载会话…
          </div>
        ) : sessions.error ? (
          <p className="px-3 py-2 text-[12.5px] text-wb-red">会话列表加载失败</p>
        ) : !sessions.data?.length ? (
          <div className="flex flex-col items-center gap-1.5 px-3 pt-10 text-center text-wb-faint-1">
            <MessagesSquareIcon className="size-6" />
            <p className="text-[12px]">还没有对话</p>
          </div>
        ) : (
          sessions.data.map((s) => {
            const active = s.id === activeId
            return (
              <div
                key={s.id}
                onClick={() => onSelect(s.id)}
                className={cn(
                  'group flex cursor-pointer items-center gap-2 rounded-[11px] px-3 py-2 text-[13px] text-wb-ink-5 transition-colors hover:bg-white/70 hover:text-wb-ink-2',
                  active && 'bg-wb-brand font-semibold text-white hover:bg-wb-brand hover:text-white',
                )}
              >
                {loadingId === s.id ? (
                  <Loader2Icon className="size-3.5 shrink-0 animate-spin" />
                ) : (
                  <MessagesSquareIcon className={cn('size-3.5 shrink-0', active ? 'text-white/90' : 'text-wb-faint-1')} />
                )}
                <span className="min-w-0 flex-1 truncate">{s.title || '未命名对话'}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    del.mutate(s.id)
                  }}
                  disabled={del.isPending}
                  title="删除对话"
                  className={cn(
                    'shrink-0 rounded-md p-0.5 opacity-0 transition-opacity group-hover:opacity-100',
                    active ? 'text-white/80 hover:text-white' : 'text-wb-faint-1 hover:text-wb-red',
                  )}
                >
                  <Trash2Icon className="size-3.5" />
                </button>
              </div>
            )
          })
        )}
      </div>
    </aside>
  )
}
