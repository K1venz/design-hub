import { afterEach, describe, expect, it, vi } from 'vitest'

import { buildChatMessageBody, confirmChat } from '@/api/chat'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('buildChatMessageBody', () => {
  it('omits edit source for normal chat messages', () => {
    expect(
      buildChatMessageBody({
        sessionId: 's1',
        message: '做一张主图',
        chatModel: 'deepseek-v4-flash',
        imageModel: 'wan2.7-image-pro',
        imageOptions: {
          render_tier: 'standard',
          count: 3,
          ratio: '3:4',
        },
        uploadIds: ['u1'],
      }),
    ).toEqual({
      session_id: 's1',
      message: '做一张主图',
      chat_model: 'deepseek-v4-flash',
      image_model: 'wan2.7-image-pro',
      image_options: {
        render_tier: 'standard',
        count: 3,
        ratio: '3:4',
      },
      upload_ids: ['u1'],
    })
  })

  it('maps a selected generated image to edit_source_image_key', () => {
    expect(
      buildChatMessageBody({
        sessionId: 's1',
        message: '背景换成海边',
        chatModel: 'doubao-chat',
        imageModel: 'gpt-image-2',
        imageOptions: {
          render_tier: '4k',
          count: 1,
          ratio: '16:9',
        },
        editSourceImageKey: 'result.png',
      }),
    ).toEqual({
      session_id: 's1',
      message: '背景换成海边',
      chat_model: 'doubao-chat',
      image_model: 'gpt-image-2',
      image_options: {
        render_tier: '4k',
        count: 1,
        ratio: '16:9',
      },
      upload_ids: [],
      edit_source_image_key: 'result.png',
    })
  })
})

describe('confirmChat streaming', () => {
  it('delivers job_started before surfacing a subsequent reader failure', async () => {
    const encoder = new TextEncoder()
    let pullCount = 0
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (pullCount++ === 0) {
          controller.enqueue(encoder.encode(
            'event: job_started\ndata: {"job_id":"j1","tool":"generate","count":2}\n\n',
          ))
          return
        }
        controller.error(new Error('network interrupted'))
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })))
    const events: unknown[] = []

    await expect(confirmChat({
      sessionId: 's1', confirmToken: 'ct1', action: 'confirm',
    }, (event) => events.push(event))).rejects.toThrow('network interrupted')

    expect(events).toContainEqual({
      kind: 'job_started', jobId: 'j1', tool: 'generate', count: 2,
    })
  })
})
