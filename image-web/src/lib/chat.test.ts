import { describe, it, expect } from 'vitest'

import {
  parseChatEvent,
  applyChatEvent,
  pushUserMessage,
  clearAwaiting,
  CHAT_WELCOME_COPY,
  editSourceFromSlot,
  initialChatState,
  previewImageFromSlot,
  sessionMessagesToBubbles,
  shouldSubmitChatInput,
  shouldShowChatWelcome,
  type ChatState,
  type ChatTranscriptMessage,
} from '@/lib/chat'

describe('chat input keyboard', () => {
  it('submits on Enter', () => {
    expect(shouldSubmitChatInput({ key: 'Enter', shiftKey: false, isComposing: false })).toBe(true)
  })

  it('keeps Shift+Enter for a newline', () => {
    expect(shouldSubmitChatInput({ key: 'Enter', shiftKey: true, isComposing: false })).toBe(false)
  })

  it('does not submit while an IME composition is active', () => {
    expect(shouldSubmitChatInput({ key: 'Enter', shiftKey: false, isComposing: true })).toBe(false)
  })

  it('ignores non-Enter keys', () => {
    expect(shouldSubmitChatInput({ key: 'a', shiftKey: false, isComposing: false })).toBe(false)
  })
})

describe('new chat capability card', () => {
  it('shows only for an idle empty session and describes unrestricted visual scope', () => {
    const empty = initialChatState()
    expect(shouldShowChatWelcome(empty)).toBe(true)
    expect(CHAT_WELCOME_COPY).toContain('任意品类')
    expect(CHAT_WELCOME_COPY).toContain('至少 1 张图片')
    expect(CHAT_WELCOME_COPY).toContain('Logo')
    expect(CHAT_WELCOME_COPY).not.toContain('食品、服装、美妆、鞋类、数码')

    expect(shouldShowChatWelcome(pushUserMessage(empty, '做一张海报'))).toBe(false)
    expect(shouldShowChatWelcome({ ...empty, streaming: true })).toBe(false)
  })
})

describe('chat result image actions', () => {
  it('creates an edit source only after a stable image key exists', () => {
    expect(editSourceFromSlot({ url: 'https://img/result.png' })).toBeNull()
    expect(
      editSourceFromSlot({
        url: 'https://img/result.png',
        imageKey: 'result.png',
        imageType: '场景',
      }),
    ).toEqual({
      url: 'https://img/result.png',
      imageKey: 'result.png',
      imageType: '场景',
    })
  })

  it('allows preview before a stable edit key exists', () => {
    expect(previewImageFromSlot({ url: 'https://img/live.png' })).toEqual({
      url: 'https://img/live.png',
      imageKey: undefined,
      imageType: undefined,
    })
  })

  it('rejects preview for an unfinished result slot', () => {
    expect(previewImageFromSlot({ url: null })).toBeNull()
  })
})

describe('parseChatEvent', () => {
  it('maps session / assistant_delta / step / tool_call', () => {
    expect(parseChatEvent('session', '{"session_id":"s1"}')).toEqual({ kind: 'session', sessionId: 's1' })
    expect(parseChatEvent('assistant_delta', '{"text":"你好"}')).toEqual({ kind: 'assistant_delta', text: '你好' })
    expect(parseChatEvent('step', '{"phase":"understood","detail":"花生·套图·5张"}')).toEqual({
      kind: 'step',
      step: { phase: 'understood', detail: '花生·套图·5张' },
    })
    expect(parseChatEvent('tool_call', '{"tool":"generate","args":{}}')).toEqual({ kind: 'tool_call', tool: 'generate' })
  })

  it('maps cost_confirm with camelCased fields', () => {
    const e = parseChatEvent(
      'cost_confirm',
      '{"confirm_token":"ct_1","tool":"generate","count":5,"unit_cost":"0.40","estimate_cny":"2.00"}',
    )
    expect(e).toEqual({
      kind: 'cost_confirm',
      confirm: { confirmToken: 'ct_1', tool: 'generate', count: 5, unitCost: '0.40', estimateCny: '2.00' },
    })
  })

  it('maps assistant_end / error / job_started', () => {
    expect(parseChatEvent('assistant_end', '{"status":"awaiting_confirm"}')).toEqual({
      kind: 'assistant_end',
      status: 'awaiting_confirm',
    })
    expect(parseChatEvent('error', '{"code":"session_job_limit","message":"超出本会话上限"}')).toEqual({
      kind: 'error',
      code: 'session_job_limit',
      message: '超出本会话上限',
    })
    expect(parseChatEvent('job_started', '{"job_id":"j1","tool":"generate","count":5}')).toEqual({
      kind: 'job_started',
      jobId: 'j1',
      tool: 'generate',
      count: 5,
    })
  })

  it('unwraps job_event → inner listing event via parseListingEvent', () => {
    const e = parseChatEvent(
      'job_event',
      '{"job_id":"j1","type":"image_generated","data":{"url":"http://x/1.png","seed":0,"image_type":"白底"}}',
    )
    expect(e).toEqual({
      kind: 'job',
      jobId: 'j1',
      inner: { kind: 'image', url: 'http://x/1.png', seed: 0, imageType: '白底' },
      imageType: '白底',
    })
  })

  it('unwraps job_event image_failed', () => {
    const e = parseChatEvent('job_event', '{"job_id":"j1","type":"image_failed","data":{"image_type":"场景","error":"provider 500"}}')
    expect(e).toEqual({
      kind: 'job',
      jobId: 'j1',
      inner: { kind: 'image_failed', imageType: '场景', error: 'provider 500' },
      imageType: undefined,
    })
  })

  it('returns unknown for unrecognized type', () => {
    expect(parseChatEvent('whatever', '{}')).toEqual({ kind: 'unknown' })
  })
})

describe('applyChatEvent reducer', () => {
  const feed = (s: ChatState, evs: Parameters<typeof applyChatEvent>[1][]) => evs.reduce(applyChatEvent, s)

  it('accumulates assistant delta into a fresh assistant bubble after user msg', () => {
    let s = pushUserMessage(initialChatState(), '给我的花生出一套 5 张')
    expect(s.streaming).toBe(true)
    s = feed(s, [
      { kind: 'session', sessionId: 's1' },
      { kind: 'assistant_delta', text: '好的，' },
      { kind: 'assistant_delta', text: '这就出。' },
    ])
    expect(s.sessionId).toBe('s1')
    expect(s.bubbles).toHaveLength(2)
    expect(s.bubbles[0]).toMatchObject({ role: 'user', text: '给我的花生出一套 5 张' })
    expect(s.bubbles[1]).toMatchObject({ role: 'assistant', text: '好的，这就出。' })
  })

  it('cost_confirm sets awaiting + attaches card; assistant_end ends stream', () => {
    let s = pushUserMessage(initialChatState(), 'x')
    s = feed(s, [
      { kind: 'tool_call', tool: 'generate' },
      { kind: 'step', step: { phase: 'planning', detail: '套图 5 张' } },
      {
        kind: 'cost_confirm',
        confirm: { confirmToken: 'ct_1', tool: 'generate', count: 5, unitCost: '0.40', estimateCny: '2.00' },
      },
      { kind: 'assistant_end', status: 'awaiting_confirm' },
    ])
    expect(s.awaiting?.confirmToken).toBe('ct_1')
    expect(s.bubbles[1].cost?.estimateCny).toBe('2.00')
    expect(s.bubbles[1].tools).toEqual(['generate'])
    expect(s.bubbles[1].steps).toHaveLength(1)
    expect(s.bubbles[1].ended).toBe(true)
    expect(s.streaming).toBe(false)
  })

  it('confirm flow: job_started prefills slots, job images fill by image_type', () => {
    let s: ChatState = { ...initialChatState(), sessionId: 's1', awaiting: { confirmToken: 'ct_1', tool: 'generate', count: 3, unitCost: '0.40', estimateCny: '1.20' } }
    s = clearAwaiting(s)
    expect(s.awaiting).toBeNull()
    s = feed(s, [{ kind: 'job_started', jobId: 'j1', tool: 'generate', count: 3 }])
    expect(s.activeJobId).toBe('j1')
    expect(s.slots).toHaveLength(3)
    expect(s.jobTotal).toBe(3)
    // 三张陆续到达
    s = feed(s, [
      { kind: 'job', jobId: 'j1', inner: { kind: 'image', url: 'http://x/a.png', imageType: '白底' }, imageType: '白底' },
      { kind: 'job', jobId: 'j1', inner: { kind: 'image', url: 'http://x/b.png', imageType: '场景' }, imageType: '场景' },
      { kind: 'job', jobId: 'j1', inner: { kind: 'image_failed', imageType: '场景', error: '失败' }, imageType: undefined },
    ])
    expect(s.jobDone).toBe(2)
    expect(s.slots.filter((x) => x.url).length).toBe(2)
    expect(s.slots.some((x) => x.error === '失败')).toBe(true)
  })

  it('error event stops streaming and records code', () => {
    let s = pushUserMessage(initialChatState(), 'x')
    s = applyChatEvent(s, { kind: 'error', code: 'session_job_limit', message: '本次对话出图已达上限' })
    expect(s.streaming).toBe(false)
    expect(s.error).toEqual({ code: 'session_job_limit', message: '本次对话出图已达上限' })
  })
})

describe('sessionMessagesToBubbles（回显：转录→气泡）', () => {
  const preview = (id: string) => `/api/uploads/${id}?access_token=T`

  it('按 seq 排序、过程态为空、assistant job_id 挂上、user attachment 转预览 url', () => {
    const msgs: ChatTranscriptMessage[] = [
      { seq: 2, role: 'assistant', content: '5 张已出好', job_id: 'j1' },
      { seq: 1, role: 'user', content: '出一套', attachment_upload_ids: ['u1', 'u2'] },
    ]
    const bubbles = sessionMessagesToBubbles(msgs, preview)
    expect(bubbles.map((b) => b.role)).toEqual(['user', 'assistant']) // seq 排序
    expect(bubbles[0]).toEqual({
      role: 'user',
      text: '出一套',
      images: ['/api/uploads/u1?access_token=T', '/api/uploads/u2?access_token=T'],
      steps: [],
      tools: [],
      ended: true,
      jobId: undefined,
    })
    expect(bubbles[1]).toMatchObject({ role: 'assistant', text: '5 张已出好', jobId: 'j1', steps: [], tools: [] })
    expect(bubbles[1].images).toBeUndefined()
  })

  it('无 attachment / 无 job_id → images/jobId 皆 undefined（纯澄清轮回显）', () => {
    const bubbles = sessionMessagesToBubbles(
      [{ seq: 1, role: 'assistant', content: '请描述你的产品', job_id: null }],
      preview,
    )
    expect(bubbles[0].images).toBeUndefined()
    expect(bubbles[0].jobId).toBeUndefined()
  })
})
