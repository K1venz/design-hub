import { describe, it, expect } from 'vitest'

import {
  parseChatEvent,
  applyChatEvent,
  pushUserMessage,
  clearAwaiting,
  consumeChatEditSource,
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
  it('shows only for an idle empty session without duplicating a stale capability list', () => {
    const empty = initialChatState()
    expect(shouldShowChatWelcome(empty)).toBe(true)
    expect(CHAT_WELCOME_COPY).toBe(
      '上传图片并告诉我想完成什么即可；你也可以直接问我平台目前支持哪些功能。',
    )

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

  it('captures the selected key for one send and clears the composer selection', () => {
    const selected = {
      url: 'https://img/result.png',
      imageKey: 'result.png',
      imageType: '场景',
    }

    expect(consumeChatEditSource(selected)).toEqual({
      editSourceImageKey: 'result.png',
      nextSelection: null,
    })
    expect(consumeChatEditSource(null)).toEqual({
      editSourceImageKey: undefined,
      nextSelection: null,
    })
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

  it('maps generation_confirm with a stable model snapshot and no price data', () => {
    const e = parseChatEvent(
      'generation_confirm',
      '{"confirm_token":"ct_1","tool":"generate","count":5,"image_model":"wan2.7-image-pro","model_display_name":"Wan 2.7","render_tier":"standard","ratio":"3:4"}',
    )
    expect(e).toEqual({
      kind: 'generation_confirm',
      confirm: {
        confirmToken: 'ct_1',
        tool: 'generate',
        count: 5,
        modelId: 'wan2.7-image-pro',
        modelDisplayName: 'Wan 2.7',
        renderTier: 'standard',
        ratio: '3:4',
      },
    })
    expect(parseChatEvent('cost_confirm', '{}')).toEqual({ kind: 'unknown' })
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

  it('maps a background workbench action card without flattening its prefill', () => {
    expect(
      parseChatEvent(
        'action_card',
        JSON.stringify({
          feature: 'background_replace',
          label: '打开换背景工作台',
          prefill: {
            source_kind: 'upload',
            source_id: 'u/product.png',
            background_kind: 'description',
            background_description: '极简摄影棚',
          },
        }),
      ),
    ).toEqual({
      kind: 'action_card',
      action: {
        feature: 'background_replace',
        label: '打开换背景工作台',
        prefill: {
          source_kind: 'upload',
          source_id: 'u/product.png',
          background_kind: 'description',
          background_description: '极简摄影棚',
        },
      },
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

  it('generation_confirm sets awaiting with its model snapshot', () => {
    let s = pushUserMessage(initialChatState(), 'x')
    s = feed(s, [
      { kind: 'tool_call', tool: 'generate' },
      { kind: 'step', step: { phase: 'planning', detail: '套图 5 张' } },
      {
        kind: 'generation_confirm',
        confirm: {
          confirmToken: 'ct_1',
          tool: 'generate',
          count: 5,
          modelId: 'wan2.7-image-pro',
          modelDisplayName: 'Wan 2.7',
          renderTier: 'standard',
          ratio: '3:4',
        },
      },
      { kind: 'assistant_end', status: 'awaiting_confirm' },
    ])
    expect(s.awaiting?.confirmToken).toBe('ct_1')
    expect(s.bubbles[1].generation?.modelId).toBe('wan2.7-image-pro')
    expect(s.bubbles[1].generation?.modelDisplayName).toBe('Wan 2.7')
    expect(s.bubbles[1].tools).toEqual(['generate'])
    expect(s.bubbles[1].steps).toHaveLength(1)
    expect(s.bubbles[1].ended).toBe(true)
    expect(s.streaming).toBe(false)
  })

  it('confirm flow: job_started anchors the job to its assistant bubble', () => {
    let s = pushUserMessage(initialChatState(), '生成三张图')
    s = applyChatEvent(s, {
      kind: 'generation_confirm',
      confirm: {
        confirmToken: 'ct_1',
        tool: 'generate',
        count: 3,
        modelId: 'gpt-image-2',
        modelDisplayName: 'GPT Image 2',
        renderTier: 'standard',
        ratio: '1:1',
      },
    })
    s = applyChatEvent(s, {
      kind: 'assistant_end',
      status: 'awaiting_confirm',
    })
    s = clearAwaiting(s)
    s = applyChatEvent(s, {
      kind: 'job_started',
      jobId: 'j1',
      tool: 'generate',
      count: 3,
    })
    expect(s.awaiting).toBeNull()
    expect(s.bubbles.at(-1)?.jobId).toBe('j1')

    const afterImageEvent = applyChatEvent(s, {
      kind: 'job',
      jobId: 'j1',
      inner: { kind: 'image', url: 'http://x/a.png', imageType: '白底' },
      imageType: '白底',
    })
    expect(afterImageEvent).toBe(s)
  })

  it('error event stops streaming and records code', () => {
    let s = pushUserMessage(initialChatState(), 'x')
    s = applyChatEvent(s, { kind: 'error', code: 'session_job_limit', message: '本次对话出图已达上限' })
    expect(s.streaming).toBe(false)
    expect(s.error).toEqual({ code: 'session_job_limit', message: '本次对话出图已达上限' })
  })

  it('attaches an action card to the current assistant bubble', () => {
    let state = pushUserMessage(initialChatState(), '打开换背景页面')
    state = applyChatEvent(state, {
      kind: 'action_card',
      action: {
        feature: 'background_replace',
        label: '打开换背景工作台',
        prefill: { source_kind: 'upload', source_id: 'u/product.png' },
      },
    })

    expect(state.bubbles[1].action).toEqual({
      feature: 'background_replace',
      label: '打开换背景工作台',
      prefill: { source_kind: 'upload', source_id: 'u/product.png' },
    })
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
