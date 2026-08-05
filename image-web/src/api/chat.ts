import { parseChatEvent, type ChatEvent, type ChatSessionSummary, type ChatSessionDetail } from '@/lib/chat'
import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'
import { useAuthStore } from '@/stores/auth-store'
import type { ChatImageOptionsPayload } from '@/lib/chat-image-options'

/** 从一个 SSE 帧（event:/data: 行块）取出事件名与 data JSON。 */
function parseFrame(frame: string): { event: string; data: string } | null {
  let event = ''
  const dataLines: string[] = []
  for (const raw of frame.split('\n')) {
    const line = raw.replace(/\r$/, '')
    if (line.startsWith(':')) continue // 注释/心跳
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''))
  }
  if (!event || dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}

/**
 * fetch + ReadableStream 读 SSE（POST body + Bearer 头，非原生 EventSource）。
 * 逐帧解析 → parseChatEvent → onEvent。fail-fast：非 2xx 抛错。I/O 域。
 */
async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = useAuthStore.getState().token
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`对话请求失败（${res.status}）`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const frame = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      const parsed = parseFrame(frame)
      if (parsed) onEvent(parseChatEvent(parsed.event, parsed.data))
    }
  }
}

export interface SendMessageInput {
  sessionId: string | null
  message: string
  chatModel: string
  imageModel: string
  imageOptions: ChatImageOptionsPayload
  uploadIds?: string[]
  editSourceImageKey?: string
}

export type ChatMessageBody = components['schemas']['ChatMessageRequest']

export function buildChatMessageBody(input: SendMessageInput): ChatMessageBody {
  const body: ChatMessageBody = {
    session_id: input.sessionId,
    message: input.message,
    chat_model: input.chatModel,
    image_model: input.imageModel,
    image_options: input.imageOptions,
    upload_ids: input.uploadIds ?? [],
  }
  if (input.editSourceImageKey) {
    body.edit_source_image_key = input.editSourceImageKey
  }
  return body
}

/** POST /chat/messages —— 发一句话，流式收一轮（session/delta/step/tool/generation_confirm/end）。 */
export function sendChatMessage(input: SendMessageInput, onEvent: (e: ChatEvent) => void, signal?: AbortSignal) {
  return streamSSE('/chat/messages', buildChatMessageBody(input), onEvent, signal)
}

/** POST /chat/confirm —— 显式确认或取消当前生成。 */
export function confirmChat(
  input: { sessionId: string; confirmToken: string; action: 'confirm' | 'cancel' },
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
) {
  return streamSSE(
    '/chat/confirm',
    { session_id: input.sessionId, confirm_token: input.confirmToken, action: input.action },
    onEvent,
    signal,
  )
}

// ── 会话历史 CRUD（ISSUE-0051）：走类型化契约客户端（auth 中间件注入 Bearer、单一契约源）──
/** 会话列表 react-query 键（发消息后 invalidate 触发侧栏刷新）。 */
export const CHAT_SESSIONS_KEY = ['chat', 'sessions'] as const

/** GET /chat/sessions → 本人会话列表（updated_at desc）。 */
export async function listChatSessions(): Promise<ChatSessionSummary[]> {
  const { data, error } = await api.GET('/chat/sessions')
  if (error || !data) throw new Error(errorMessage(error, '获取会话列表失败'))
  return data
}

/** GET /chat/sessions/{id} → 会话转录（非本人 / 不存在 → 404 anti-enum）。 */
export async function getChatSession(id: string): Promise<ChatSessionDetail> {
  const { data, error } = await api.GET('/chat/sessions/{session_id}', {
    params: { path: { session_id: id } },
  })
  if (error || !data) throw new Error(errorMessage(error, '获取会话失败'))
  return data
}

/** DELETE /chat/sessions/{id} → 硬删（非本人 / 不存在 → 404，CASCADE 删消息）。 */
export async function deleteChatSession(id: string): Promise<void> {
  const { error } = await api.DELETE('/chat/sessions/{session_id}', {
    params: { path: { session_id: id } },
  })
  if (error) throw new Error(errorMessage(error, '删除会话失败'))
}
