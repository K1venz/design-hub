// 「帮我设计」对话域（ISSUE-0048 方案 C，契约 docs/帮我设计-chat-agent-技术契约-0048.md）。
// 纯类型 + 事件解析 + 状态 reducer；无 React/IO——单测在 chat.test.ts。
// job 出图事件 = 服务端「包一层」转发 listing TaskEvent，前端复用 parseListingEvent 渲染。

import { parseListingEvent, type ListingEvent } from '@/lib/listing'
import type { ResultSlot } from '@/components/listing/ResultGallery'
import type { components } from '@/api/schema'

export type ChatTool = 'generate' | 'clone' | 'edit'

export interface ChatPreviewImage {
  url: string
  imageKey?: string
  imageType?: string
}

export interface ChatEditSource {
  url: string
  imageKey: string
  imageType?: string
}

export function previewImageFromSlot(slot: ResultSlot): ChatPreviewImage | null {
  if (!slot.url) return null
  return { url: slot.url, imageKey: slot.imageKey, imageType: slot.imageType }
}

export function editSourceFromSlot(slot: ResultSlot): ChatEditSource | null {
  if (!slot.url || !slot.imageKey) return null
  return { url: slot.url, imageKey: slot.imageKey, imageType: slot.imageType }
}

export function consumeChatEditSource(source: ChatEditSource | null): {
  editSourceImageKey: string | undefined
  nextSelection: null
} {
  return {
    editSourceImageKey: source?.imageKey,
    nextSelection: null,
  }
}

/** 费用确认闸载荷（cost_confirm 事件）。 */
export interface CostConfirm {
  confirmToken: string
  tool: ChatTool
  count: number
  unitCost: string
  estimateCny: string
}

export interface ChatStep {
  phase: 'understood' | 'planning' | 'generating' | 'done' | string
  detail: string
}

/** 解析后的对话事件（判别联合）。job_event 内层已转成 ListingEvent。 */
export type ChatEvent =
  | { kind: 'session'; sessionId: string }
  | { kind: 'assistant_delta'; text: string }
  | { kind: 'step'; step: ChatStep }
  | { kind: 'tool_call'; tool: ChatTool }
  | { kind: 'cost_confirm'; confirm: CostConfirm }
  | { kind: 'assistant_end'; status: 'complete' | 'awaiting_confirm' | 'error' | string }
  | { kind: 'error'; code: string; message: string }
  | { kind: 'job_started'; jobId: string; tool: ChatTool; count: number }
  | { kind: 'job'; jobId: string; inner: ListingEvent; imageType?: string }
  | { kind: 'unknown' }

/**
 * 映射一条 SSE 命名事件到 ChatEvent。
 * `type` = SSE `event:` 行；`rawData` = `data:` 行 JSON。
 */
export function parseChatEvent(type: string, rawData: string): ChatEvent {
  const d = JSON.parse(rawData) as Record<string, unknown>
  switch (type) {
    case 'session':
      return { kind: 'session', sessionId: String(d.session_id ?? '') }
    case 'assistant_delta':
      return { kind: 'assistant_delta', text: String(d.text ?? '') }
    case 'step':
      return { kind: 'step', step: { phase: String(d.phase ?? ''), detail: String(d.detail ?? '') } }
    case 'tool_call':
      return { kind: 'tool_call', tool: (String(d.tool ?? 'generate') as ChatTool) }
    case 'cost_confirm':
      return {
        kind: 'cost_confirm',
        confirm: {
          confirmToken: String(d.confirm_token ?? ''),
          tool: String(d.tool ?? 'generate') as ChatTool,
          count: Number(d.count ?? 0),
          unitCost: String(d.unit_cost ?? ''),
          estimateCny: String(d.estimate_cny ?? ''),
        },
      }
    case 'assistant_end':
      return { kind: 'assistant_end', status: String(d.status ?? 'complete') }
    case 'error':
      return { kind: 'error', code: String(d.code ?? 'error'), message: String(d.message ?? '出错了') }
    case 'job_started':
      return {
        kind: 'job_started',
        jobId: String(d.job_id ?? ''),
        tool: String(d.tool ?? 'generate') as ChatTool,
        count: Number(d.count ?? 0),
      }
    case 'job_event': {
      // 信封：{job_id, type, data}；内层复用工作台 listing 事件解析
      const innerType = String(d.type ?? '')
      const innerData = JSON.stringify(d.data ?? {})
      const inner = parseListingEvent(innerType, innerData)
      return { kind: 'job', jobId: String(d.job_id ?? ''), inner, imageType: inner.kind === 'image' ? inner.imageType : undefined }
    }
    default:
      return { kind: 'unknown' }
  }
}

// ── 对话状态（纯 reducer，UI 消费）─────────────────────────
export interface ChatBubble {
  role: 'user' | 'assistant'
  text: string
  images?: string[]
  steps: ChatStep[]
  tools: ChatTool[]
  /** assistant 气泡携带的费用确认卡（awaiting）；确认/取消后清。 */
  cost?: CostConfirm
  ended?: boolean
  /** 回显专用：该 assistant 气泡对应的出图 job（转录只存 job_id，图靠 useListingJob 现签）。 */
  jobId?: string
}

export interface ChatState {
  sessionId: string | null
  bubbles: ChatBubble[]
  /** 当前出图结果槽（job_event 填充，复用工作台槽模型）。 */
  slots: ResultSlot[]
  /** 当前实时出图任务；任务结束后据此补拉稳定 image_key。 */
  activeJobId: string | null
  jobDone: number
  jobTotal: number
  /** 有 awaiting confirm 时非空——UI 据此渲染确认卡并禁用输入。 */
  awaiting: CostConfirm | null
  streaming: boolean
  error: { code: string; message: string } | null
}

export const CHAT_WELCOME_COPY =
  '我可以基于你上传的图片制作全品类主图、场景图、卖点图、海报、Logo/品牌视觉，也支持爆款复刻和连续编辑。普通出图支持多种比例；如需 4K，请在需求中明确写出“4K”，4K 当前仅支持 16:9 横版。上传至少 1 张图片，再告诉我想做什么即可。'

export interface ChatInputKey {
  key: string
  shiftKey: boolean
  isComposing: boolean
}

export function shouldSubmitChatInput(event: ChatInputKey): boolean {
  return event.key === 'Enter' && !event.shiftKey && !event.isComposing
}

export function shouldShowChatWelcome(state: ChatState): boolean {
  return state.bubbles.length === 0 && !state.streaming
}

export function initialChatState(): ChatState {
  return {
    sessionId: null,
    bubbles: [],
    slots: [],
    activeJobId: null,
    jobDone: 0,
    jobTotal: 0,
    awaiting: null,
    streaming: false,
    error: null,
  }
}

/** 追加用户消息（本地即时回显，发送前调用）。 */
export function pushUserMessage(state: ChatState, text: string, images?: string[]): ChatState {
  const bubble: ChatBubble = { role: 'user', text, images, steps: [], tools: [] }
  return { ...state, bubbles: [...state.bubbles, bubble], streaming: true, error: null }
}

function lastAssistant(bubbles: ChatBubble[]): number {
  for (let i = bubbles.length - 1; i >= 0; i--) if (bubbles[i].role === 'assistant') return i
  return -1
}

/** 确保末尾存在“本轮”assistant 气泡（用户气泡之后）——增量事件写入它。 */
function ensureAssistant(state: ChatState): { bubbles: ChatBubble[]; idx: number } {
  const bubbles = [...state.bubbles]
  const last = bubbles[bubbles.length - 1]
  if (!last || last.role === 'user' || last.ended) {
    bubbles.push({ role: 'assistant', text: '', steps: [], tools: [] })
  }
  return { bubbles, idx: bubbles.length - 1 }
}

/** 事件 reducer：把一条 ChatEvent 折进状态（纯函数）。 */
export function applyChatEvent(state: ChatState, ev: ChatEvent): ChatState {
  switch (ev.kind) {
    case 'session':
      return { ...state, sessionId: ev.sessionId }
    case 'assistant_delta': {
      const { bubbles, idx } = ensureAssistant(state)
      bubbles[idx] = { ...bubbles[idx], text: bubbles[idx].text + ev.text }
      return { ...state, bubbles }
    }
    case 'step': {
      const { bubbles, idx } = ensureAssistant(state)
      bubbles[idx] = { ...bubbles[idx], steps: [...bubbles[idx].steps, ev.step] }
      return { ...state, bubbles }
    }
    case 'tool_call': {
      const { bubbles, idx } = ensureAssistant(state)
      bubbles[idx] = { ...bubbles[idx], tools: [...bubbles[idx].tools, ev.tool] }
      return { ...state, bubbles }
    }
    case 'cost_confirm': {
      const { bubbles, idx } = ensureAssistant(state)
      bubbles[idx] = { ...bubbles[idx], cost: ev.confirm }
      return { ...state, bubbles, awaiting: ev.confirm }
    }
    case 'assistant_end': {
      const i = lastAssistant(state.bubbles)
      if (i < 0) return { ...state, streaming: false }
      const bubbles = [...state.bubbles]
      bubbles[i] = { ...bubbles[i], ended: true }
      return { ...state, bubbles, streaming: false }
    }
    case 'error':
      return { ...state, streaming: false, error: { code: ev.code, message: ev.message } }
    case 'job_started':
      return {
        ...state,
        awaiting: null,
        slots: Array.from({ length: ev.count }, () => ({ url: null }) as ResultSlot),
        activeJobId: ev.jobId,
        jobDone: 0,
        jobTotal: ev.count,
      }
    case 'job': {
      // chat 的 job_started 只给 count、槽无预设图型，故按到达序填首个空槽，
      // 用事件自带的 image_type 给槽打标（结果卡展示用）。
      const e = ev.inner
      if (e.kind === 'image') {
        const slots = [...state.slots]
        const j = slots.findIndex((s) => s.url === null && !s.error)
        if (j >= 0) slots[j] = { ...slots[j], url: e.url, imageType: e.imageType ?? slots[j].imageType }
        return { ...state, slots, jobDone: state.jobDone + 1 }
      }
      if (e.kind === 'image_failed') {
        const slots = [...state.slots]
        const j = slots.findIndex((s) => s.url === null && !s.error)
        if (j >= 0) slots[j] = { ...slots[j], error: e.error, imageType: e.imageType ?? slots[j].imageType }
        return { ...state, slots }
      }
      return state
    }
    default:
      return state
  }
}

/** 清空 awaiting（用户点取消后本地即时反映；服务端 cancel 流会补收尾语）。 */
export function clearAwaiting(state: ChatState): ChatState {
  return { ...state, awaiting: null, streaming: true }
}

// ── 会话历史持久化 + 回显（ISSUE-0051）：类型由 OpenAPI codegen 派生（单一契约源）──
/** GET /chat/sessions 列表项（侧栏，updated_at 倒序、带消息数）。 */
export type ChatSessionSummary = components['schemas']['ChatSessionSummaryOut']

/** GET /chat/sessions/{id} 的一条转录消息（只存 user 消息 + assistant 最终答复 + job_id，取舍①）。 */
export type ChatTranscriptMessage = components['schemas']['ChatMessageOut']

/** GET /chat/sessions/{id} 完整转录回显。 */
export type ChatSessionDetail = components['schemas']['ChatTranscriptOut']

/**
 * 把持久化转录还原成 UI 气泡（回显）：过程态（流式/步骤/费用卡）不落库故为空；
 * assistant 消息的 job_id 挂上（UI 据此 useListingJob 现签重渲出图卡，取舍②）；
 * user 消息的 attachment_upload_ids 经 previewOf 转成预览 url（/api/uploads/{id}?access_token=）。
 * previewOf 由调用方注入（需 token，属 IO/presentation，纯函数不自取）。
 */
export function sessionMessagesToBubbles(
  messages: ChatTranscriptMessage[],
  previewOf: (uploadId: string) => string,
): ChatBubble[] {
  return messages
    .slice()
    .sort((a, b) => a.seq - b.seq)
    .map((m) => ({
      role: m.role === 'assistant' ? 'assistant' : 'user',
      text: m.content,
      images: m.attachment_upload_ids?.length ? m.attachment_upload_ids.map(previewOf) : undefined,
      steps: [],
      tools: [],
      ended: true,
      jobId: m.job_id ?? undefined,
    }))
}
