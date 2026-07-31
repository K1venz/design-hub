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
        uploadIds: ['u1'],
      }),
    ).toEqual({
      session_id: 's1',
      message: '做一张主图',
      chat_model: 'deepseek-v4-flash',
      image_model: 'wan2.7-image-pro',
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
        editSourceImageKey: 'result.png',
      }),
    ).toEqual({
      session_id: 's1',
      message: '背景换成海边',
      chat_model: 'doubao-chat',
      image_model: 'gpt-image-2',
      upload_ids: [],
      edit_source_image_key: 'result.png',
    })
  })
})
