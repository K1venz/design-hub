import { parseChatEvent, type ChatEvent } from '@/lib/chat'
import { useAuthStore } from '@/stores/auth-store'

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
  uploadIds?: string[]
}

/** POST /chat/messages —— 发一句话，流式收一轮（session/delta/step/tool/cost_confirm/end）。 */
export function sendChatMessage(input: SendMessageInput, onEvent: (e: ChatEvent) => void, signal?: AbortSignal) {
  return streamSSE(
    '/chat/messages',
    { session_id: input.sessionId, message: input.message, upload_ids: input.uploadIds ?? [] },
    onEvent,
    signal,
  )
}

/** POST /chat/confirm —— 显式确认/取消出图（费用闸用户动作）。 */
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
