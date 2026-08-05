import { describe, expect, it } from 'vitest'

import { buildChatMessageBody } from '@/api/chat'

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
